"""Design challenges: the rulings of 3 to 11 November 2026, attacked before they are built.

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
    assert any("refused by the weekly cap" in unknown for unknown in report.unknowns)
    assert any("refused by the weekly cap" in step.detail for step in report.trace)
    assert report.status == AWAITING_HUMAN_REVIEW


def test_assigned_limits_let_the_workflow_run_unchanged() -> None:
    allowance = Allowance(Limits(weekly=1_000_000))
    controller, inner = metered_controller(allowance)
    report = controller.investigate(CHECKOUT_Q)
    assert len(inner.calls) == 1
    assert len(report.hypotheses) == 2
    assert allowance.used(0, 30) > 0


def test_a_quiet_day_leaves_its_share_for_a_busy_one() -> None:
    allowance = Allowance(Limits(weekly=70))
    allowance.charge(0, 10)
    assert allowance.refusal(6, 60) is None
    assert allowance.refusal(6, 61) is not None
    assert allowance.refusal(7, 70) is None


def test_a_refusal_names_the_cap_and_what_is_left() -> None:
    allowance = Allowance(Limits(weekly=60))
    allowance.charge(0, 50)
    assert allowance.refusal(1, 20) == "refused by the weekly cap of 60: 20 requested, 10 left"


def test_any_30_days_spend_at_most_five_weeks_worth() -> None:
    allowance = Allowance(Limits(weekly=100))
    for day in range(120):
        if allowance.refusal(day, 100) is None:
            allowance.charge(day, 100)
        assert allowance.used(day, 30) <= 5 * allowance.limits.weekly


def test_the_weekly_cap_holds_for_a_year_when_estimates_are_exact() -> None:
    limits = Limits(weekly=500)
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
        assert allowance.used(day, 7) <= limits.weekly
        assert allowance.used(day, 30) <= 5 * limits.weekly
    assert sent and refused


def test_the_lowest_limit_wins_and_an_unset_ceiling_leaves_the_users_number() -> None:
    own = Limits(weekly=300)
    assert effective(own, Ceilings(weekly=250), Ceilings(weekly=150)) == Limits(weekly=150)
    assert effective(own, Ceilings(weekly=500)) == Limits(weekly=300)
    assert effective(own, Ceilings()) == own


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


def test_the_weekly_cap_holds_when_the_response_is_larger_than_estimated() -> None:
    allowance = Allowance(Limits(weekly=100))
    metered = MeteredLLM(Verbose(), allowance, lambda: 0, max_response=50, count=len)
    for _ in range(5):
        with suppress(Refused):
            metered.complete("prompt")
    assert allowance.used(0, 7) <= allowance.limits.weekly


def test_the_unused_part_of_a_reservation_is_refunded() -> None:
    allowance = Allowance(Limits(weekly=100))
    MeteredLLM(Verbose(), allowance, lambda: 0, max_response=50, count=len).complete("prompt")
    assert allowance.used(0, 7) == len("prompt") + 40


def test_a_failed_call_keeps_its_reservation() -> None:
    class Failing:
        name = "failing"

        def complete(self, prompt: str) -> str:
            raise TimeoutError("no response")

    allowance = Allowance(Limits(weekly=100))
    metered = MeteredLLM(Failing(), allowance, lambda: 0, max_response=50, count=len)
    with pytest.raises(TimeoutError):
        metered.complete("prompt")
    assert allowance.used(0, 7) == len("prompt") + 50


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
