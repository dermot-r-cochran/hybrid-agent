"""Design challenges: the rulings of 3 November 2026, attacked before they are built.

Each test holds a ruling in docs/decisions.md to what it promises, through the
sketches in examples/cost_control. A plain test is a promise that held. A test
marked `gap` states a promise the design as ruled does not keep: it is expected
to fail, and strictly, so whoever closes the gap in the sample gets a red run
until the mark comes off. An error other than the failed assertion is never
expected, so a broken challenge cannot pass as a gap.
"""

import random
from contextlib import suppress
from itertools import combinations
from pathlib import Path

import pytest

from examples.cost_control.masking import (
    MIN_GROUP_SIZE,
    Ledger,
    Round,
    Secrets,
    masked,
    reported_groups,
)
from examples.cost_control.quota import (
    Allowance,
    Ceilings,
    Limits,
    MeteredLLM,
    Refused,
    effective,
    input_equivalent,
)
from hybrid_agent.__main__ import load_scripted_llm
from hybrid_agent.controller import Controller
from hybrid_agent.llm import LLM, FakeLLM, LLMOperation
from hybrid_agent.models import AWAITING_HUMAN_REVIEW
from hybrid_agent.tools import local_tools

EVIDENCE = Path(__file__).resolve().parent.parent / "examples" / "checkout_latency"
SCRIPT = EVIDENCE / "fake_llm_responses.json"
CHECKOUT_Q = "Why did checkout p95 latency go up after the latest deploy?"


def gap(reason: str) -> pytest.MarkDecorator:
    return pytest.mark.xfail(strict=True, raises=AssertionError, reason=reason)


# --- cost limits -----------------------------------------------------------------------


def metered_controller(allowance: Allowance) -> tuple[Controller, FakeLLM]:
    metrics, tools = local_tools(EVIDENCE)
    inner = load_scripted_llm(SCRIPT)
    models: dict[LLMOperation, LLM] = {
        LLMOperation.GENERATE_HYPOTHESES: MeteredLLM(inner, allowance, lambda: 0, max_response=1000)
    }
    return Controller(tools, metrics.services(), models), inner


def test_default_limits_refuse_before_sending() -> None:
    controller, inner = metered_controller(Allowance(Limits()))
    report = controller.investigate(CHECKOUT_Q)
    assert inner.calls == []
    assert report.hypotheses == []
    assert any("refused by the bucket" in unknown for unknown in report.unknowns)
    assert any("refused by the bucket" in step.detail for step in report.trace)
    assert report.status == AWAITING_HUMAN_REVIEW


def test_assigned_limits_let_the_workflow_run_unchanged() -> None:
    allowance = Allowance(Limits(1_000_000, 1_000_000, 1_000_000, 1_000_000))
    controller, inner = metered_controller(allowance)
    report = controller.investigate(CHECKOUT_Q)
    assert len(inner.calls) == 1
    assert len(report.hypotheses) == 2
    assert allowance.used(0, 30) > 0


def test_unspent_allowance_rolls_over_only_to_the_burst_cap() -> None:
    allowance = Allowance(Limits(daily=10, burst=30, weekly=1000, monthly=1000))
    assert allowance.refusal(100, 31) is not None
    assert allowance.refusal(100, 30) is None


@pytest.mark.parametrize(
    ("limit", "limits", "tokens"),
    [
        ("bucket", Limits(50, 50, 1000, 1000), 51),
        ("weekly", Limits(50, 50, 60, 1000), 20),
        ("30-day", Limits(50, 50, 1000, 60), 20),
    ],
)
def test_a_refusal_names_the_limit_it_hit(limit: str, limits: Limits, tokens: int) -> None:
    allowance = Allowance(limits)
    allowance.charge(0, 50)
    assert limit in (allowance.refusal(1, tokens) or "")


def test_rolling_caps_hold_for_a_year_when_estimates_are_exact() -> None:
    limits = Limits(daily=100, burst=400, weekly=500, monthly=1500)
    allowance, rng = Allowance(limits), random.Random(0)
    sent = refused = 0
    for day in range(365):
        for _ in range(rng.randrange(4)):
            tokens = rng.randrange(1, 300)
            if allowance.refusal(day, tokens) is None:
                allowance.charge(day, tokens)
                sent += 1
            else:
                refused += 1
        assert allowance.bucket <= limits.burst
        assert allowance.used(day, 7) <= limits.weekly
        assert allowance.used(day, 30) <= limits.monthly
    assert sent and refused


def test_the_lowest_limit_wins_and_an_unset_ceiling_leaves_the_users_number() -> None:
    own = Limits(daily=100, burst=200, weekly=300, monthly=400)
    team, personal = Ceilings(daily=500, weekly=250), Ceilings(weekly=150)
    assert effective(own, team, personal) == Limits(100, 200, 150, 400)


def test_an_unweighted_token_kind_is_refused_not_free() -> None:
    weights = {"input": 1.0, "output": 3.0}
    assert input_equivalent({"input": 3, "output": 2}, weights) == 9
    with pytest.raises(KeyError):
        input_equivalent({"thinking": 1}, weights)


class Verbose:
    """A response far larger than the prompt, within the maximum it was given."""

    name = "verbose"

    def complete(self, prompt: str) -> str:
        return "x" * 40


def test_a_rolling_cap_holds_when_the_response_is_larger_than_estimated() -> None:
    allowance = Allowance(Limits(100, 100, 100, 100))
    metered = MeteredLLM(Verbose(), allowance, lambda: 0, max_response=50, count=len)
    for _ in range(5):
        with suppress(Refused):
            metered.complete("prompt")
    assert allowance.used(0, 30) <= allowance.limits.monthly


def test_the_unused_part_of_a_reservation_is_refunded() -> None:
    allowance = Allowance(Limits(100, 100, 100, 100))
    MeteredLLM(Verbose(), allowance, lambda: 0, max_response=50, count=len).complete("prompt")
    assert allowance.used(0, 30) == len("prompt") + 40
    assert allowance.bucket == 100 - (len("prompt") + 40)


def test_a_failed_call_keeps_its_reservation() -> None:
    class Failing:
        name = "failing"

        def complete(self, prompt: str) -> str:
            raise TimeoutError("no response")

    allowance = Allowance(Limits(100, 100, 100, 100))
    metered = MeteredLLM(Failing(), allowance, lambda: 0, max_response=50, count=len)
    with pytest.raises(TimeoutError):
        metered.complete("prompt")
    assert allowance.used(0, 30) == len("prompt") + 50


# --- additive masking ------------------------------------------------------------------

FIGURES = {name: 11 * (i + 1) for i, name in enumerate("abcdefghi")}
ABCDEF = frozenset("abcdef")
SECRETS: Secrets = {
    frozenset(pair): random.Random("".join(pair)).randbytes(32)
    for pair in combinations(sorted(FIGURES), 2)
}


def contributions(current: Round, figures: dict[str, int] = FIGURES) -> dict[str, int]:
    return {m: masked(m, figures[m], current, SECRETS) for m in current.roster}


def publish(ledger: Ledger, round_id: str, roster: frozenset[str]) -> int | None:
    current = ledger.open(round_id, roster)
    return ledger.close(current, contributions(current), roster).total


def test_masks_cancel_to_the_exact_total() -> None:
    assert publish(Ledger(), "r1", ABCDEF) == sum(FIGURES[m] for m in ABCDEF)


def test_a_masked_contribution_shows_nothing_of_its_figure_or_of_other_rounds() -> None:
    first, second = Round("r1", ABCDEF), Round("r2", ABCDEF)
    assert masked("a", FIGURES["a"], first, SECRETS) != FIGURES["a"]
    assert masked("a", FIGURES["a"], first, SECRETS) != masked("a", FIGURES["a"], second, SECRETS)


def test_a_round_id_is_never_reused_even_after_a_void_round() -> None:
    ledger = Ledger()
    current = ledger.open("r1", ABCDEF)
    assert ledger.close(current, {}, ABCDEF).total is None
    with pytest.raises(ValueError):
        ledger.open("r1", ABCDEF)


def test_a_missing_contribution_voids_the_round_and_names_no_one() -> None:
    ledger, current = Ledger(), Round("r1", ABCDEF)
    partial = contributions(current)
    del partial["c"]
    outcome = ledger.close(current, partial, ABCDEF)
    assert outcome.total is None
    assert outcome.reason.startswith("void")
    assert not set(outcome.reason.split()) & ABCDEF
    assert ledger.published == []


def test_a_leaver_voids_the_round_and_a_joiner_waits_for_the_next() -> None:
    current = Round("r1", ABCDEF)
    outcome = Ledger().close(current, contributions(current), ABCDEF - {"f"})
    assert outcome.total is None
    joined = Ledger().close(current, contributions(current), ABCDEF | {"g"})
    assert joined.total == sum(FIGURES[m] for m in ABCDEF)


def test_a_group_below_the_minimum_size_is_withheld() -> None:
    current = Round("r1", frozenset("ab"))
    assert Ledger().close(current, contributions(current), current.roster).total is None


def test_a_group_of_three_publishes_and_no_member_can_read_a_colleague() -> None:
    assert MIN_GROUP_SIZE == 3
    roster = frozenset("abc")
    total = publish(Ledger(), "r1", roster)
    assert total is not None
    for member in roster:
        remainder = total - FIGURES[member]
        assert remainder not in {FIGURES[m] for m in roster - {member}}


def test_a_total_too_close_to_a_published_roster_is_withheld() -> None:
    ledger = Ledger()
    publish(ledger, "r1", ABCDEF)
    assert publish(ledger, "r2", ABCDEF - {"a"}) is None


def test_no_differencing_holds_across_an_intervening_round() -> None:
    ledger = Ledger()
    before = publish(ledger, "r1", ABCDEF)
    publish(ledger, "r2", frozenset("defghi"))
    after = publish(ledger, "r3", ABCDEF - {"a"})
    assert before is None or after is None or before - after != FIGURES["a"]


def test_a_folded_squad_cannot_be_recovered_from_the_totals_around_it() -> None:
    squads = {
        "alpha": frozenset("abc"),
        "beta": frozenset("def"),
        "gamma": frozenset("g"),
    }
    assert len(squads["gamma"]) < MIN_GROUP_SIZE
    team = frozenset("abcdefg")
    ledger = Ledger()
    groups = reported_groups(team, squads)
    totals = {name: publish(ledger, f"r-{name}", roster) for name, roster in groups.items()}
    whole = totals.pop("team")
    assert whole is not None
    assert whole - sum(t for t in totals.values() if t is not None) != FIGURES["g"]


def test_squads_that_cover_their_team_are_all_published() -> None:
    squads = {"alpha": frozenset("abc"), "beta": frozenset("def")}
    assert set(reported_groups(ABCDEF, squads)) == {"alpha", "beta", "team"}
