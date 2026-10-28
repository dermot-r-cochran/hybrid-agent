"""Deterministic verification of LLM proposals and report invariants.

Passing these checks means a hypothesis is *consistent with* the gathered
evidence; it does not make it true. That judgement stays with the human.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from .models import Evidence, EvidenceKind, Hypothesis, Report

# Signed numbers (optionally with thousands separators) followed by a unit.
_NUMERIC_CLAIM = re.compile(
    r"(?<![\w.,])([+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[+-]?\d+(?:\.\d+)?)\s*"
    r"(ms|milliseconds?|s|secs?|seconds?|%|percent|pp|percentage points?)(?!\w)",
    re.IGNORECASE,
)
# Canonical unit and scale factor for each spelling.
_UNITS = {
    "ms": ("ms", 1.0),
    "millisecond": ("ms", 1.0),
    "milliseconds": ("ms", 1.0),
    "s": ("ms", 1000.0),
    "sec": ("ms", 1000.0),
    "secs": ("ms", 1000.0),
    "second": ("ms", 1000.0),
    "seconds": ("ms", 1000.0),
    "%": ("%", 1.0),
    "percent": ("%", 1.0),
    "pp": ("pp", 1.0),
    "percentage point": ("pp", 1.0),
    "percentage points": ("pp", 1.0),
}
_FILE_REF = re.compile(r"[\w./-]+\.(?:py|html|js|ts|go|java|sql|ya?ml|json|toml|cfg)\b")
_UNIT_SUFFIX = {"_ms": "ms", "_pct": "%", "_pp": "pp"}


def _computed_values(evidence: Iterable[Evidence]) -> dict[str, list[float]]:
    values: dict[str, list[float]] = {"ms": [], "%": [], "pp": []}
    for e in evidence:
        if e.kind is not EvidenceKind.DERIVED:
            continue
        for key, value in e.data.items():
            for suffix, unit in _UNIT_SUFFIX.items():
                if key.endswith(suffix) and isinstance(value, int | float):
                    values[unit].append(float(value))
    return values


def _matches(claim: str, value: float, candidates: list[float]) -> bool:
    """Signed claims must match in sign; unsigned ones ("fell by 3%") by magnitude."""
    signed = claim.startswith(("+", "-"))

    def close(c: float) -> bool:
        # Allow for the rounding people (and models) naturally apply when quoting.
        return abs(value - (c if signed else abs(c))) <= max(1.0, 0.02 * abs(c))

    return any(close(c) for c in candidates)


def _changed_files(evidence: Iterable[Evidence]) -> set[str]:
    files: set[str] = set()
    for e in evidence:
        files.update(e.data.get("files_changed", []))
    return files


def verify_hypothesis(hypothesis: Hypothesis, evidence: dict[str, Evidence]) -> list[str]:
    issues = []
    if not hypothesis.evidence_ids:
        issues.append("cites no evidence")
    unknown = [i for i in hypothesis.evidence_ids if i not in evidence]
    if unknown:
        issues.append(f"cites unknown evidence: {', '.join(unknown)}")

    computed = _computed_values(evidence.values())
    for number, unit in _NUMERIC_CLAIM.findall(hypothesis.statement):
        canonical, scale = _UNITS[unit.lower()]
        value = float(number.replace(",", "")) * scale
        if not _matches(number, value, computed[canonical]):
            claim = f"{number}{unit}" if unit == "%" else f"{number} {unit}"
            issues.append(f"numeric claim {claim} does not match any computed result")

    changed = _changed_files(evidence.values())
    for ref in _FILE_REF.findall(hypothesis.statement):
        if not any(f == ref or f.endswith("/" + ref) for f in changed):
            issues.append(f"refers to {ref}, which is not in the deployed change")
    return issues


def verify_report(report: Report) -> list[str]:
    """Check each hypothesis and the report-wide invariants; return report-level issues."""
    evidence = report.evidence_by_id()
    for h in report.hypotheses:
        h.verification_issues = verify_hypothesis(h, evidence)

    issues = []
    for d in report.derived:
        missing = [i for i in d.data.get("inputs", []) if i not in evidence]
        if missing:
            issues.append(f"{d.id} derived from missing evidence: {', '.join(missing)}")
    for a in report.actions:
        if a.executed or not a.requires_human_approval:
            issues.append(f"action bypasses human approval: {a.description}")
    return issues
