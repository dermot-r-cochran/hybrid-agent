"""LLM interface, prompts, and strict parsing of LLM output.

The LLM is only asked for semantic work. Its output is parsed and validated
deterministically; anything malformed is discarded rather than trusted.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from .models import Evidence, EvidenceKind, Hypothesis, Metric, ProposedAction, Task


class LLM(Protocol):
    name: str

    def complete(self, prompt: str) -> str: ...


class LLMOperation(StrEnum):
    INTERPRET_REQUEST = "interpret_request"
    GENERATE_HYPOTHESES = "generate_hypotheses"


# What each operation needs from a model. Model choice is explicit
# configuration (operation -> model), made by people, not by an LLM.
MODEL_REQUIREMENTS: dict[LLMOperation, str] = {
    LLMOperation.INTERPRET_REQUEST: (
        "small, fast, low-cost model: short closed-set mapping of a request to "
        "an allowed service and metric; output is validated against allow-lists"
    ),
    LLMOperation.GENERATE_HYPOTHESES: (
        "strongest available reasoning/code model with enough context for the "
        "diffs: reads unfamiliar code, links it to evidence, proposes causes"
    ),
}

ModelAssignment = Mapping[LLMOperation, LLM]


_OPERATION = re.compile(r"^OPERATION: (\w+)$", re.MULTILINE)


@dataclass
class FakeLLM:
    """Deterministic stand-in for a real model, keyed by prompt operation.

    Records every prompt so tests can assert when the LLM was (not) used.
    """

    responses: Mapping[str, str]
    name: str = "fake"
    calls: list[str] = field(default_factory=list)

    def complete(self, prompt: str) -> str:
        self.calls.append(prompt)
        match = _OPERATION.search(prompt)
        if match is None or match.group(1) not in self.responses:
            raise KeyError("FakeLLM has no scripted response for this prompt")
        return self.responses[match.group(1)]


class InvalidLLMOutput(ValueError):
    pass


def _json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidLLMOutput(f"not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise InvalidLLMOutput("expected a JSON object")
    return value


def _list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise InvalidLLMOutput(f"'{name}' must be a list")
    return value


def _str_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise InvalidLLMOutput(f"'{name}' must be a list of strings")
    return value


# --- interpret_request -------------------------------------------------------


def interpret_request_prompt(request: str, services: Sequence[str]) -> str:
    return "\n".join(
        [
            f"OPERATION: {LLMOperation.INTERPRET_REQUEST.value}",
            "Map the engineering request to a service and metric.",
            f"Allowed services: {', '.join(sorted(services))}",
            f"Allowed metrics: {', '.join(m.value for m in Metric)}",
            'Reply with JSON only: {"service": "...", "metric": "..."}',
            "Use null for anything the request does not determine.",
            f"Request: {request}",
        ]
    )


def parse_task(text: str, request: str, services: Sequence[str]) -> Task:
    data = _json_object(text)
    service, metric = data.get("service"), data.get("metric")
    if not isinstance(service, str) or service not in services:
        raise InvalidLLMOutput(f"unknown service {service!r}")
    if metric not in {m.value for m in Metric}:
        raise InvalidLLMOutput(f"unknown metric {metric!r}")
    return Task(request=request, service=service, metric=Metric(metric))


# --- generate_hypotheses -----------------------------------------------------


def hypotheses_prompt(task: Task, evidence: Sequence[Evidence]) -> str:
    lines = [
        f"OPERATION: {LLMOperation.GENERATE_HYPOTHESES.value}",
        f"Engineering question: {task.request}",
        f"Service: {task.service}; metric: {task.metric.value}",
        "Evidence (cite by id; do not invent ids):",
    ]
    for e in evidence:
        lines.append(f"[{e.id}] ({e.kind.value}) {e.summary}")
        if "diff" in e.data:
            lines.append(str(e.data["diff"]))
        elif e.kind is EvidenceKind.DERIVED:
            lines.append(json.dumps(e.data, sort_keys=True))
    lines += [
        "Propose plausible causes. Do not calculate new numbers; only quote "
        "numbers that appear in the evidence.",
        "Reply with JSON only:",
        '{"hypotheses": [{"statement": "...", "evidence_ids": ["..."]}],',
        ' "unknowns": ["..."],',
        ' "actions": [{"description": "...", "rationale": "..."}]}',
    ]
    return "\n".join(lines)


@dataclass(frozen=True)
class HypothesesProposal:
    hypotheses: list[Hypothesis]
    unknowns: list[str]
    actions: list[ProposedAction]


def parse_hypotheses(text: str) -> HypothesesProposal:
    data = _json_object(text)
    hypotheses, actions = [], []
    for raw in _list(data.get("hypotheses", []), "hypotheses"):
        if not isinstance(raw, dict) or not isinstance(raw.get("statement"), str):
            raise InvalidLLMOutput("each hypothesis needs a 'statement' string")
        hypotheses.append(
            Hypothesis(
                statement=raw["statement"],
                evidence_ids=_str_list(raw.get("evidence_ids", []), "evidence_ids"),
            )
        )
    for raw in _list(data.get("actions", []), "actions"):
        if not isinstance(raw, dict) or not isinstance(raw.get("description"), str):
            raise InvalidLLMOutput("each action needs a 'description' string")
        # Authority fields are fixed here; the LLM cannot set them.
        actions.append(
            ProposedAction(
                description=raw["description"],
                rationale=str(raw.get("rationale", "")),
            )
        )
    unknowns = _str_list(data.get("unknowns", []), "unknowns")
    return HypothesesProposal(hypotheses, unknowns, actions)
