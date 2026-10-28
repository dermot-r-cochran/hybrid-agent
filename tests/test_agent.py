import json
from pathlib import Path

import pytest

from hybrid_agent.__main__ import load_scripted_llm, main
from hybrid_agent.compute import InsufficientData, compare_windows, is_regression, percentile
from hybrid_agent.controller import Controller, parse_request
from hybrid_agent.llm import FakeLLM, InvalidLLMOutput, LLMOperation, parse_hypotheses, parse_task
from hybrid_agent.models import (
    Evidence,
    EvidenceKind,
    Hypothesis,
    Mechanism,
    Metric,
    ProposedAction,
    Report,
    Task,
)
from hybrid_agent.tools import DiffTool, local_tools, parse_timestamp
from hybrid_agent.verify import verify_hypothesis, verify_report

EVIDENCE = Path(__file__).resolve().parent.parent / "examples" / "checkout_latency"
SCRIPT = EVIDENCE / "fake_llm_responses.json"
CHECKOUT_Q = "Why did checkout p95 latency go up after the latest deploy?"


def controller(models: dict[LLMOperation, FakeLLM] | None = None) -> Controller:
    metrics, tools = local_tools(EVIDENCE)
    return Controller(tools, metrics.services(), models)


def scripted(name: str) -> FakeLLM:
    llm = load_scripted_llm(SCRIPT)
    llm.name = name
    return llm


def per_operation_models() -> tuple[FakeLLM, FakeLLM, dict[LLMOperation, FakeLLM]]:
    small, strong = scripted("small-model"), scripted("strong-model")
    return (
        small,
        strong,
        {
            LLMOperation.INTERPRET_REQUEST: small,
            LLMOperation.GENERATE_HYPOTHESES: strong,
        },
    )


# --- computation -----------------------------------------------------------------------


def test_percentile_interpolates() -> None:
    assert percentile(list(range(1, 102)), 95) == pytest.approx(96.0)
    with pytest.raises(ValueError):
        percentile([1.0, 2.0], 100)


def samples(n: int, start_minute: int, latency: float) -> list[dict[str, object]]:
    return [
        {
            "timestamp": f"2026-01-01T{m // 60:02d}:{m % 60:02d}:00Z",
            "latency_ms": latency,
            "status": 200,
        }
        for m in range(start_minute, start_minute + n)
    ]


def test_compare_windows_and_regression_rule() -> None:
    data = samples(40, 0, 100.0) + samples(40, 60, 150.0)
    result = compare_windows(data, parse_timestamp("2026-01-01T01:00:00Z"))
    assert result["p95_before_ms"] == 100.0
    assert result["p95_after_ms"] == 150.0
    assert result["p95_change_pct"] == 50.0
    assert is_regression(result, Metric.LATENCY)
    assert not is_regression(result, Metric.ERROR_RATE)


def test_compare_windows_requires_enough_samples() -> None:
    data = samples(40, 0, 100.0) + samples(5, 60, 150.0)
    with pytest.raises(InsufficientData):
        compare_windows(data, parse_timestamp("2026-01-01T01:00:00Z"))


# --- deterministic parsing and LLM output parsing --------------------------------------


def test_parse_request_deterministic_and_ambiguous() -> None:
    services = ["checkout", "search"]
    task = parse_request("Errors in search since Tuesday?", services)
    assert task == Task("Errors in search since Tuesday?", "search", Metric.ERROR_RATE)
    assert parse_request("Paying for a basket feels sluggish", services) is None
    assert parse_request("checkout and search are slow", services) is None


def test_parse_task_rejects_values_outside_allow_lists() -> None:
    assert (
        parse_task('{"service": "search", "metric": "latency"}', "q", ["search"]).service
        == "search"
    )
    with pytest.raises(InvalidLLMOutput):
        parse_task('{"service": "billing", "metric": "latency"}', "q", ["search"])
    with pytest.raises(InvalidLLMOutput):
        parse_task("not json", "q", ["search"])


def test_parse_hypotheses_accepts_fences_and_fixes_authority_fields() -> None:
    text = (
        '```json\n{"hypotheses": [], "actions": [{"description": "rollback", '
        '"requires_human_approval": false, "executed": true}]}\n```'
    )
    proposal = parse_hypotheses(text)
    assert proposal.actions == [ProposedAction("rollback", "")]
    assert proposal.actions[0].requires_human_approval and not proposal.actions[0].executed
    with pytest.raises(InvalidLLMOutput):
        parse_hypotheses('{"hypotheses": "everything is fine"}')


# --- verification ----------------------------------------------------------------------


def evidence() -> dict[str, Evidence]:
    return {
        "diff:abc1234": Evidence(
            "diff:abc1234",
            EvidenceKind.OBSERVATION,
            "diff",
            "",
            {"files_changed": ["svc/pricing.py"]},
        ),
        "derived:x": Evidence(
            "derived:x",
            EvidenceKind.DERIVED,
            "compute",
            "",
            {"p95_before_ms": 100.0, "p95_change_pct": 128.6},
        ),
    }


def test_verify_accepts_consistent_hypothesis() -> None:
    h = Hypothesis(
        "pricing.py change raised p95 by about 129% from 100 ms", ["diff:abc1234", "derived:x"]
    )
    assert verify_hypothesis(h, evidence()) == []


def test_verify_flags_bad_citations_numbers_and_files() -> None:
    h = Hypothesis("config.yaml raised latency by 300%", ["logs:nope"])
    issues = verify_hypothesis(h, evidence())
    assert any("unknown evidence" in i for i in issues)
    assert any("300%" in i for i in issues)
    assert any("config.yaml" in i for i in issues)
    assert verify_hypothesis(Hypothesis("it is slow", []), evidence()) == ["cites no evidence"]


def test_verify_report_flags_actions_bypassing_approval() -> None:
    report = Report("q", actions=[ProposedAction("deploy", "", executed=True)])
    assert verify_report(report) == ["action bypasses human approval: deploy"]


# --- tools -----------------------------------------------------------------------------


def test_diff_tool_rejects_unsafe_commit_ids(tmp_path: Path) -> None:
    deploy = Evidence(
        "d", EvidenceKind.OBSERVATION, "deploy_log", "", {"commit": "../../etc/passwd"}
    )
    assert DiffTool(tmp_path).run(Task("q", "s", Metric.LATENCY), [deploy]) == []


# --- end to end ------------------------------------------------------------------------


def test_regression_investigation_end_to_end() -> None:
    small, strong, models = per_operation_models()
    report = controller(models).investigate(CHECKOUT_Q)

    assert report.task == Task(CHECKOUT_Q, "checkout", Metric.LATENCY)
    assert [e.id for e in report.observations] == [
        "deploy:checkout:4.12.0",
        "metrics:checkout",
        "diff:a3c91f4",
    ]
    derived = report.derived[0].data
    assert (derived["p95_before_ms"], derived["p95_after_ms"]) == (125.3, 286.4)

    # Request was parsed by rules, so only the hypothesis model was used.
    assert small.calls == [] and len(strong.calls) == 1
    assert [h.passed_checks for h in report.hypotheses] == [True, False]
    assert all(a.requires_human_approval and not a.executed for a in report.actions)
    assert report.verification_issues == []
    assert report.status == "awaiting_human_review"
    mechanisms = {s.operation: s.mechanism for s in report.trace}
    assert mechanisms["compare_windows"] is Mechanism.COMPUTATION
    assert mechanisms["generate_hypotheses"] is Mechanism.LLM
    assert "model=strong-model" in [s.detail for s in report.trace if s.mechanism is Mechanism.LLM]


def test_no_regression_means_no_llm_call() -> None:
    small, strong, models = per_operation_models()
    report = controller(models).investigate("Is search slower since its last deploy?")
    assert small.calls == [] and strong.calls == []
    assert report.hypotheses == [] and report.derived[0].data["p95_change_pct"] < 20


def test_ambiguous_request_routes_to_interpretation_model() -> None:
    small, strong, models = per_operation_models()
    report = controller(models).investigate("Customers say paying for their basket got sluggish")
    assert len(small.calls) == 1 and len(strong.calls) == 1
    assert "interpret_request" in small.calls[0]
    assert "generate_hypotheses" in strong.calls[0]
    assert report.task is not None and report.task.service == "checkout"
    assert any("inferred by an LLM" in u for u in report.unknowns)


def test_missing_model_is_reported_not_substituted() -> None:
    strong = scripted("strong-model")
    report = controller({LLMOperation.GENERATE_HYPOTHESES: strong}).investigate(
        "basket is sluggish"
    )
    assert report.task is None and strong.calls == []
    assert "interpret_request needed an LLM but none is assigned" in report.unknowns


def test_malformed_or_failing_llm_output_is_not_trusted() -> None:
    bad = FakeLLM({"generate_hypotheses": "The cause is definitely the database."})
    report = controller({LLMOperation.GENERATE_HYPOTHESES: bad}).investigate(CHECKOUT_Q)
    assert report.hypotheses == [] and report.actions == []
    assert any("malformed" in u for u in report.unknowns)

    broken = FakeLLM({})
    report = controller({LLMOperation.GENERATE_HYPOTHESES: broken}).investigate(CHECKOUT_Q)
    assert report.hypotheses == [] and any("failed" in u for u in report.unknowns)


def test_cli_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    args = [CHECKOUT_Q, "--evidence", str(EVIDENCE), "--llm-script", str(SCRIPT), "--json"]
    assert main(args) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "awaiting_human_review"
    assert [h["passed_checks"] for h in out["hypotheses"]] == [True, False]


# --- regression tests from review ------------------------------------------------------


def test_non_string_llm_fields_are_rejected_not_crashing() -> None:
    llm = FakeLLM({"interpret_request": '{"service": "checkout", "metric": ["latency"]}'})
    report = controller({LLMOperation.INTERPRET_REQUEST: llm}).investigate("checkout feels bad")
    assert report.task is None
    assert any("could not interpret" in u for u in report.unknowns)


@pytest.mark.parametrize(
    "statement",
    [
        "p95 fell by -128.6% after the deploy",  # wrong sign
        "p95 rose to 1,286.4 ms",  # thousands separator must not hide the real value
        "latency rose to 2.9 s",  # seconds are converted, not ignored
        "error rate rose by 5 percentage points",
    ],
)
def test_numeric_claims_cannot_slip_past_verification(statement: str) -> None:
    derived = Evidence(
        "d",
        EvidenceKind.DERIVED,
        "compute",
        "",
        {"p95_after_ms": 286.4, "p95_change_pct": 128.6, "error_rate_change_pp": -0.83},
    )
    issues = verify_hypothesis(Hypothesis(statement, ["d"]), {"d": derived})
    assert any("numeric claim" in i for i in issues)


def test_equivalent_numeric_claims_pass() -> None:
    derived = Evidence(
        "d",
        EvidenceKind.DERIVED,
        "compute",
        "",
        {"p95_after_ms": 1286.4, "p95_change_pct": 128.6, "error_rate_change_pp": -0.83},
    )
    statement = "p95 rose +128.6% to 1,286.4 ms (about 1.29 s); errors fell 0.83 pp"
    assert verify_hypothesis(Hypothesis(statement, ["d"]), {"d": derived}) == []


def test_naive_timestamps_are_treated_as_utc() -> None:
    assert parse_timestamp("2026-01-01T01:00:00") == parse_timestamp("2026-01-01T01:00:00Z")


def test_diff_tool_includes_deleted_files(tmp_path: Path) -> None:
    (tmp_path / "abc1234.diff").write_text(
        "diff --git a/old/cache.py b/old/cache.py\ndeleted file mode 100644\n"
        "--- a/old/cache.py\n+++ /dev/null\n"
    )
    deploy = Evidence("d", EvidenceKind.OBSERVATION, "deploy_log", "", {"commit": "abc1234"})
    [diff] = DiffTool(tmp_path).run(Task("q", "s", Metric.LATENCY), [deploy])
    assert diff.data["files_changed"] == ["old/cache.py"]


def test_unreadable_evidence_becomes_an_unknown(tmp_path: Path) -> None:
    (tmp_path / "deploys.jsonl").write_text("{not json\n")
    (tmp_path / "metrics.csv").write_text("timestamp,service,latency_ms,status\n")
    metrics, tools = local_tools(tmp_path)
    report = Controller(tools, ["checkout"]).investigate(CHECKOUT_Q)
    assert any("deploy_log evidence could not be read" in u for u in report.unknowns)
    assert report.status == "awaiting_human_review"
