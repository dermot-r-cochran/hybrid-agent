"""Declared specialists, shared state and a rule-based arbitrator.

The controller's workflow is a set of specialists, each declaring what it can
do and what it costs, working on one shared ``Board``. A rule in code (the
arbitrator) picks the next specialist; no model takes part in that choice.

A foundation model is one specialist among others. Under the ``rules_first``
policy it is consulted for hypotheses only when the deterministic specialists
have produced none, so a problem the rules can handle completes with no model
call at all.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum

from .models import Mechanism, Report, Task


class Cost(IntEnum):
    """Relative cost class; the arbitrator prefers the cheapest ready specialist."""

    FREE = 0  # local code, no external call
    COMPUTE = 1  # local computation over the evidence
    MODEL = 2  # a foundation-model call


class Policy(StrEnum):
    """How the arbitrator treats the hypothesis specialists."""

    # The founding behaviour: hypotheses come from the LLM; the rule-based
    # hypothesis specialist is not consulted.
    LLM_HYPOTHESES = "llm_hypotheses"
    # Rules first: the rule-based specialist proposes; the LLM is consulted
    # only if it proposed nothing.
    RULES_FIRST = "rules_first"


@dataclass
class Board:
    """Shared state the specialists read and write. The report is its record."""

    report: Report
    task: Task | None = None
    comparison: dict[str, float] | None = None
    regression: bool | None = None
    done: list[str] = field(default_factory=list)  # specialists run, in order

    def ran(self, name: str) -> bool:
        return name in self.done


@dataclass(frozen=True)
class Specialist:
    """A declared capability. ``ready`` reads the board; ``run`` writes to it."""

    name: str  # also the operation name in the audit trace
    capability: str
    mechanism: Mechanism
    cost: Cost
    data_leaves_machine: bool  # True only for a model call to a provider
    ready: Callable[[Board], bool]
    run: Callable[[Board], None]


def choose(board: Board, specialists: Sequence[Specialist]) -> Specialist | None:
    """The arbitrator: the cheapest ready specialist not yet run, by registry order on ties.

    Each specialist runs at most once per investigation, so the loop always ends.
    """
    candidates = [s for s in specialists if not board.ran(s.name) and s.ready(board)]
    if not candidates:
        return None
    return min(candidates, key=lambda s: s.cost)  # min is stable: registry order breaks ties
