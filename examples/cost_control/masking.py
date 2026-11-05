"""Sample of the additive masking ruled on 3 November 2026 (docs/decisions.md).

A sketch to challenge the design with, not the package's code: it is not
installed, and nothing in hybrid_agent imports it. One figure per member stands
for a whole contribution, and how a pair agrees its secret is left to the
build, so the secrets are handed in.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping
from dataclasses import dataclass, field

MODULUS = 2**64
# The rulings name no number. Three is the floor: in a group of two, either
# member reads the other's figure from the total by subtracting their own.
MIN_GROUP_SIZE = 3

Secrets = Mapping[frozenset[str], bytes]


@dataclass(frozen=True)
class Round:
    id: str
    roster: frozenset[str]


@dataclass(frozen=True)
class Outcome:
    total: int | None
    reason: str


def _mask(secret: bytes, round_id: str) -> int:
    digest = hmac.new(secret, round_id.encode(), hashlib.sha256).digest()
    return int.from_bytes(digest[:8], "big")


def masked(member: str, figure: int, current: Round, secrets: Secrets) -> int:
    """A figure with one mask per colleague: one of each pair adds it, the other subtracts it."""
    value = figure
    for other in current.roster - {member}:
        mask = _mask(secrets[frozenset({member, other})], current.id)
        value += mask if member < other else -mask
    return value % MODULUS


def reported_groups(
    team: frozenset[str], squads: Mapping[str, frozenset[str]]
) -> dict[str, frozenset[str]]:
    """The team, and each squad big enough to stand alone; a smaller one sits inside the team."""
    large = {name: roster for name, roster in squads.items() if len(roster) >= MIN_GROUP_SIZE}
    return {**large, "team": team}


@dataclass
class Ledger:
    """Opens rounds and decides what each one may publish."""

    opened: set[str] = field(default_factory=set)
    published: list[frozenset[str]] = field(default_factory=list)

    def open(self, round_id: str, roster: frozenset[str]) -> Round:
        """Freeze a round's roster. A rerun takes a new id, so its masks are fresh."""
        if round_id in self.opened:
            raise ValueError(f"round {round_id} was already opened; masks are never reused")
        self.opened.add(round_id)
        return Round(round_id, roster)

    def close(
        self, current: Round, contributions: Mapping[str, int], roster_now: frozenset[str]
    ) -> Outcome:
        roster = current.roster
        if len(roster) < MIN_GROUP_SIZE:
            return Outcome(None, "withheld: below the minimum group size")
        if roster - roster_now or roster - contributions.keys():
            return Outcome(None, "void: the frozen roster did not all contribute")
        if self.published and 0 < len(roster ^ self.published[-1]) < MIN_GROUP_SIZE:
            return Outcome(None, "withheld: too close to the last published roster")
        self.published.append(roster)
        return Outcome(sum(contributions[m] for m in roster) % MODULUS, "published")
