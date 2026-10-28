"""Deterministic controller: owns workflow state, routing and model choice.

Which mechanism handles each operation is decided here, in code. The LLM is
called only for semantic work, and only when earlier deterministic steps show
it is needed. Each LLM operation is sent to the model assigned to it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence

from .compute import (
    ERROR_RATE_REGRESSION_PP,
    LATENCY_REGRESSION_PCT,
    InsufficientData,
    compare_windows,
    is_regression,
)
from .llm import (
    LLM,
    InvalidLLMOutput,
    LLMOperation,
    hypotheses_prompt,
    interpret_request_prompt,
    parse_hypotheses,
    parse_task,
)
from .models import Evidence, EvidenceKind, Mechanism, Metric, Report, Step, Task
from .tools import Tool, find_deploy, parse_timestamp
from .verify import verify_report

ROUTES: dict[str, Mechanism] = {
    "parse_request": Mechanism.DETERMINISTIC,
    LLMOperation.INTERPRET_REQUEST.value: Mechanism.LLM,
    "gather_evidence": Mechanism.DETERMINISTIC,
    "compare_windows": Mechanism.COMPUTATION,
    "detect_regression": Mechanism.DETERMINISTIC,
    LLMOperation.GENERATE_HYPOTHESES.value: Mechanism.LLM,
    "verify": Mechanism.DETERMINISTIC,
}

METRIC_KEYWORDS: dict[Metric, tuple[str, ...]] = {
    Metric.LATENCY: ("latency", "slow", "p95", "p99", "response time"),
    Metric.ERROR_RATE: ("error", "5xx", "failure", "failing"),
}


def _mentions(text: str, words: Iterable[str]) -> bool:
    return any(re.search(r"\b" + re.escape(w), text) for w in words)


def parse_request(request: str, services: Iterable[str]) -> Task | None:
    """Rule-based parse; returns None when the request is ambiguous."""
    text = request.lower()
    found_services = [s for s in services if re.search(rf"\b{re.escape(s)}\b", text)]
    found_metrics = [m for m, words in METRIC_KEYWORDS.items() if _mentions(text, words)]
    if len(found_services) == 1 and len(found_metrics) == 1:
        return Task(request=request, service=found_services[0], metric=found_metrics[0])
    return None


class Controller:
    def __init__(
        self,
        tools: Sequence[Tool],
        services: Iterable[str],
        models: Mapping[LLMOperation, LLM] | None = None,
    ) -> None:
        self.tools = list(tools)
        self.services = sorted(services)
        self.models = dict(models or {})

    def investigate(self, request: str) -> Report:
        report = Report(request=request)
        task = self._task(request, report)
        if task is not None:
            report.task = task
            self._gather(task, report)
            comparison = self._compute(task, report)
            if comparison is not None and self._detect(task, comparison, report):
                self._hypothesise(task, report)
        report.verification_issues = verify_report(report)
        failed = sum(1 for h in report.hypotheses if not h.passed_checks)
        self._step(
            report,
            "verify",
            f"{len(report.hypotheses)} hypotheses checked, {failed} failed; "
            f"{len(report.verification_issues)} report-level issues",
        )
        return report

    # --- steps ---------------------------------------------------------------

    def _step(self, report: Report, operation: str, detail: str) -> None:
        report.trace.append(Step(operation, ROUTES[operation], detail))

    def _call_llm(self, report: Report, operation: LLMOperation, prompt: str) -> str | None:
        model = self.models.get(operation)
        if model is None:
            self._step(report, operation.value, "skipped: no model assigned")
            report.unknowns.append(f"{operation.value} needed an LLM but none is assigned")
            return None
        try:
            text = model.complete(prompt)
        except Exception as exc:  # provider failures must not crash the workflow
            self._step(report, operation.value, f"model={model.name} failed: {exc}")
            report.unknowns.append(f"{operation.value} failed: {exc}")
            return None
        self._step(report, operation.value, f"model={model.name}")
        return text

    def _task(self, request: str, report: Report) -> Task | None:
        task = parse_request(request, self.services)
        if task is not None:
            self._step(
                report, "parse_request", f"service={task.service}, metric={task.metric.value}"
            )
            return task
        self._step(report, "parse_request", "ambiguous; semantic interpretation needed")
        op = LLMOperation.INTERPRET_REQUEST
        text = self._call_llm(report, op, interpret_request_prompt(request, self.services))
        if text is None:
            return None
        try:
            task = parse_task(text, request, self.services)
        except InvalidLLMOutput as exc:
            report.unknowns.append(f"could not interpret the request: {exc}")
            return None
        report.unknowns.append(
            f"service={task.service} and metric={task.metric.value} were inferred by "
            "an LLM; confirm this matches the request"
        )
        return task

    def _gather(self, task: Task, report: Report) -> None:
        for tool in self.tools:
            try:
                found = tool.run(task, report.observations)
            except (OSError, ValueError, KeyError) as exc:
                self._step(report, "gather_evidence", f"{tool.name}: failed: {exc!r}")
                report.unknowns.append(f"{tool.name} evidence could not be read: {exc!r}")
                continue
            report.observations.extend(found)
            self._step(report, "gather_evidence", f"{tool.name}: {len(found)} item(s)")
            if not found:
                report.unknowns.append(f"no {tool.name} evidence for {task.service}")

    def _compute(self, task: Task, report: Report) -> dict[str, float] | None:
        deploy = find_deploy(report.observations)
        metrics = next((e for e in report.observations if e.source == "metrics"), None)
        if deploy is None or metrics is None:
            self._step(report, "compare_windows", "skipped: needs a deploy and metrics")
            return None
        try:
            comparison = compare_windows(
                metrics.data["samples"], parse_timestamp(deploy.data["timestamp"])
            )
        except (InsufficientData, ValueError, KeyError) as exc:
            self._step(report, "compare_windows", f"skipped: {exc}")
            report.unknowns.append(f"cannot compare before/after deploy: {exc}")
            return None
        report.derived.append(
            Evidence(
                id=f"derived:{task.service}:before_after_deploy",
                kind=EvidenceKind.DERIVED,
                source="compute.compare_windows",
                summary=(
                    f"p95 {comparison['p95_before_ms']} ms -> {comparison['p95_after_ms']} ms "
                    f"({comparison['p95_change_pct']:+}%); error rate "
                    f"{comparison['error_rate_before_pct']}% -> "
                    f"{comparison['error_rate_after_pct']}%"
                ),
                data={**comparison, "inputs": [metrics.id, deploy.id]},
            )
        )
        self._step(report, "compare_windows", report.derived[-1].summary)
        return comparison

    def _detect(self, task: Task, comparison: dict[str, float], report: Report) -> bool:
        regression = is_regression(comparison, task.metric)
        if task.metric is Metric.LATENCY:
            rule = (
                f"p95 change {comparison['p95_change_pct']:+}% "
                f"vs threshold +{LATENCY_REGRESSION_PCT}%"
            )
        else:
            rule = (
                f"error rate change {comparison['error_rate_change_pp']:+} pp "
                f"vs threshold +{ERROR_RATE_REGRESSION_PP} pp"
            )
        verdict = "regression" if regression else "no regression; no hypotheses needed"
        self._step(report, "detect_regression", f"{rule} -> {verdict}")
        return regression

    def _hypothesise(self, task: Task, report: Report) -> None:
        evidence = [*report.observations, *report.derived]
        op = LLMOperation.GENERATE_HYPOTHESES
        text = self._call_llm(report, op, hypotheses_prompt(task, evidence))
        if text is None:
            return
        try:
            proposal = parse_hypotheses(text)
        except InvalidLLMOutput as exc:
            report.unknowns.append(f"LLM proposal rejected as malformed: {exc}")
            return
        report.hypotheses.extend(proposal.hypotheses)
        report.unknowns.extend(proposal.unknowns)
        report.actions.extend(proposal.actions)
