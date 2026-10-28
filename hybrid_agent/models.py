"""Typed task, evidence and report models.

The report keeps observations, derived results, hypotheses, unknowns and
proposed actions in separate fields so they can never be confused.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Mechanism(StrEnum):
    """How an operation is carried out."""

    DETERMINISTIC = "deterministic"
    COMPUTATION = "computation"
    LLM = "llm"


class Metric(StrEnum):
    LATENCY = "latency"
    ERROR_RATE = "error_rate"


@dataclass(frozen=True)
class Task:
    """A natural-language request reduced to a typed investigation."""

    request: str
    service: str
    metric: Metric


class EvidenceKind(StrEnum):
    OBSERVATION = "observation"  # read directly from a tool
    DERIVED = "derived"  # computed from observations


@dataclass(frozen=True)
class Evidence:
    id: str
    kind: EvidenceKind
    source: str
    summary: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class Hypothesis:
    """An LLM proposal. Never treated as evidence."""

    statement: str
    evidence_ids: list[str]
    verification_issues: list[str] = field(default_factory=list)

    @property
    def passed_checks(self) -> bool:
        return not self.verification_issues


@dataclass(frozen=True)
class ProposedAction:
    description: str
    rationale: str
    requires_human_approval: bool = True
    executed: bool = False


@dataclass(frozen=True)
class Step:
    """One entry in the audit trail: what ran, and by which mechanism."""

    operation: str
    mechanism: Mechanism
    detail: str


AWAITING_HUMAN_REVIEW = "awaiting_human_review"


@dataclass
class Report:
    request: str
    task: Task | None = None
    observations: list[Evidence] = field(default_factory=list)
    derived: list[Evidence] = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    actions: list[ProposedAction] = field(default_factory=list)
    trace: list[Step] = field(default_factory=list)
    verification_issues: list[str] = field(default_factory=list)
    status: str = AWAITING_HUMAN_REVIEW

    def evidence_by_id(self) -> dict[str, Evidence]:
        return {e.id: e for e in [*self.observations, *self.derived]}

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for h, raw in zip(self.hypotheses, result["hypotheses"], strict=True):
            raw["passed_checks"] = h.passed_checks
        return result
