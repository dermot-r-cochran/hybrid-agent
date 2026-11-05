"""Sample of the cost limits ruled on 3 November 2026 (docs/decisions.md).

A sketch to challenge the design with, not the package's code: it is not
installed, and nothing in hybrid_agent imports it. Days are plain integers so
the challenges can walk a year without a clock.

`MeteredLLM` wraps any `LLM` and raises `Refused` before sending. The
controller already turns a raised exception into an unknown with its reason in
the trace, so limits need no change to the workflow.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, fields

from hybrid_agent.llm import LLM


class Refused(RuntimeError):
    pass


@dataclass(frozen=True)
class Limits:
    """A user's own numbers, in input-equivalent tokens. Every one defaults to 0."""

    daily: int = 0
    burst: int = 0
    weekly: int = 0
    monthly: int = 0


@dataclass(frozen=True)
class Ceilings:
    """An organisation's numbers. Unset means no ceiling, not a ceiling of 0."""

    daily: int | None = None
    burst: int | None = None
    weekly: int | None = None
    monthly: int | None = None


def effective(own: Limits, *ceilings: Ceilings) -> Limits:
    """The lowest number that applies wins, so a user can lower a limit but not raise it."""

    def lowest(name: str) -> int:
        values: list[int | None] = [getattr(own, name), *(getattr(c, name) for c in ceilings)]
        return min(v for v in values if v is not None)

    return Limits(**{f.name: lowest(f.name) for f in fields(Limits)})


def input_equivalent(counts: Mapping[str, int], weights: Mapping[str, float]) -> int:
    """Weight each token kind relative to base input; an unweighted kind is an error, not free."""
    return math.ceil(sum(n * weights[kind] for kind, n in counts.items()))


@dataclass
class Allowance:
    limits: Limits
    day: int = 0
    usage: list[tuple[int, int]] = field(default_factory=list)
    bucket: int = field(init=False)

    def __post_init__(self) -> None:
        self.bucket = min(self.limits.daily, self.limits.burst)

    def _accrue(self, day: int) -> None:
        earned = (day - self.day) * self.limits.daily
        self.bucket = min(self.bucket + earned, self.limits.burst)
        self.day = day

    def used(self, day: int, window: int) -> int:
        return sum(tokens for d, tokens in self.usage if day - window < d <= day)

    def refusal(self, day: int, tokens: int) -> str | None:
        """The limit this request would break, or None if it fits them all."""
        self._accrue(day)
        if tokens > self.bucket:
            return f"refused by the bucket: {tokens} requested, {self.bucket} held"
        if self.used(day, 7) + tokens > self.limits.weekly:
            return f"refused by the weekly cap of {self.limits.weekly}"
        if self.used(day, 30) + tokens > self.limits.monthly:
            return f"refused by the 30-day cap of {self.limits.monthly}"
        return None

    def charge(self, day: int, tokens: int) -> None:
        self.bucket -= tokens
        self.usage.append((day, tokens))


def rough_count(text: str) -> int:
    return max(1, len(text) // 4)


@dataclass
class MeteredLLM:
    """Reserves the prompt plus the largest response allowed, then refunds what went unused.

    A response's size is not known before it is sent, so the worst case is what
    has to fit. A failed call keeps its reservation, since what it cost is not
    known. `LLM.complete` takes no maximum and returns text only, so the real
    thing would need the protocol to carry the one and report the counts; the
    sample trusts `inner` to keep to `max_response`, and `count` stands in.
    """

    inner: LLM
    allowance: Allowance
    today: Callable[[], int]
    max_response: int
    count: Callable[[str], int] = rough_count
    name: str = field(init=False)

    def __post_init__(self) -> None:
        self.name = self.inner.name

    def complete(self, prompt: str) -> str:
        day, sent = self.today(), self.count(prompt)
        reserved = sent + self.max_response
        reason = self.allowance.refusal(day, reserved)
        if reason is not None:
            raise Refused(reason)
        self.allowance.charge(day, reserved)
        response = self.inner.complete(prompt)
        self.allowance.charge(day, sent + self.count(response) - reserved)
        return response
