# hybrid-agent

A deliberately small engineering agent built on one principle:

> Use the simplest reliable reasoning mechanism for each part of an engineering problem.

The deterministic controller handles the workflow, routing, model choice, calculations and
verification. A trained decision (classification) model is in scope for closed-set decisions
that fixed rules cannot make reliably. An LLM is called only for semantic work: interpreting an ambiguous request,
reading unfamiliar code and proposing hypotheses. Its output is treated as a proposal and checked
before a human sees it. Nothing is executed. The human makes the decisions.

## Architecture

```
Engineer request
  -> deterministic controller (hybrid_agent/controller.py)
       parse_request        deterministic   keyword/allow-list rules
       interpret_request    LLM             only if the rules find the request ambiguous
       gather_evidence      deterministic   pluggable local tools (tools.py)
       compare_windows      computation     percentiles / error rates (compute.py)
       detect_regression    deterministic   explicit threshold rule
       generate_hypotheses  LLM             only if a regression was detected
  -> deterministic verification (verify.py)
  -> report for human review (report.py), status = awaiting_human_review
```

| Module | Responsibility |
| --- | --- |
| `models.py` | Typed `Task`, `Evidence`, `Hypothesis`, `ProposedAction`, `Report`. Observations, derived results, hypotheses, unknowns and actions are separate fields. |
| `tools.py` | `Tool` protocol plus three local tools: deploy log, request metrics, code diff. |
| `compute.py` | Statistics and the regression rules. All numbers are computed here, not by the LLM. |
| `llm.py` | `LLM` protocol, `FakeLLM`, prompts, strict JSON parsing, per-operation model requirements. |
| `verify.py` | Checks hypotheses and report invariants. |
| `controller.py` | Routing table, workflow, model assignment, audit trace. |
| `report.py` | Plain-text rendering of a report for human review. The report text under *Worked example* is its output. |
| `__main__.py` | Command-line entry point: `python -m hybrid_agent "<question>" --evidence DIR`, with `--llm-script` for scripted responses and `--json` for the report as JSON. |

### Choosing a model for each LLM operation

Each LLM operation has its own documented needs (`llm.MODEL_REQUIREMENTS`) and is routed to the
model assigned to it in configuration (`Controller(models={LLMOperation: LLM})`):

| Operation | What it needs |
| --- | --- |
| `interpret_request` | A small, fast, low-cost model. It does a short closed-set mapping, and the result is validated against allow-lists. |
| `generate_hypotheses` | The strongest available reasoning/code model, with enough context for the diffs. |

The choice is explicit and made by people, not by an LLM. If no model is assigned to an
operation, the agent records an unknown. It does not quietly fall back to a different model. The
trace records which model handled each call.

### Decision (classification) models

A trained classifier sits between fixed rules and an LLM: it is the mechanism for a decision with a
closed set of answers that rules cannot make reliably but that does not need language
understanding. Likely first uses are routing a request to a known service and metric, and judging
whether a before/after change is a regression where a fixed threshold proves too blunt. None is
built yet; the first one comes when a concrete case shows the rules failing. The same discipline
applies as to the LLM:

- Its label set is closed and validated against the same allow-lists as the rules. A label outside
  the set is an unknown, never a guess.
- It reports a confidence, and the controller applies an explicit threshold in code. Below it, the
  decision is recorded as an unknown or passed on to the next mechanism, never silently accepted.
- The model, its version and its training data are chosen and recorded by people, like the LLM
  assignments, and the trace names which model made each decision.
- It is evaluated on held-out examples before it is used, and the evaluation is kept with it. A
  classifier's output is a derived result, not an observation.
- Rules still come first. A classifier is used only where a rule has been tried and shown to be
  insufficient, and an LLM only where a classifier would not do.

### What verification checks

These checks are deterministic. Passing them means a hypothesis is *consistent with the evidence*.
It does not mean the hypothesis is true.

- Every cited evidence ID exists, and each hypothesis cites at least one.
- Every figure with a unit (`ms`, `s`, `%`, `pp`) matches a computed result, allowing for rounding.
  A figure with a sign must also match in sign.
- Every file the hypothesis names is in the deployed change.
- Derived results point to observations that exist.
- No action has been executed or bypasses human approval. These fields are set by code; the LLM
  cannot set them.

Malformed LLM output, and provider errors, are turned into unknowns. They are never trusted.

## What the tests prove

Every capability row in this table names the test that proves it (file and test name), or
says it has no test yet (the README-proof convention, 10 October 2026). A claim without a test
is written down as such rather than dropped. `.github/scripts/check_docs.py`, run in CI, fails if
a cited test does not exist, a relative link resolves to nothing, or a Markdown file carries a
second front-matter block. The tests in this table are in `tests/test_agent.py`.

| Claim | Proved by |
| --- | --- |
| Rules parse a request that names a known service and metric; one they cannot place, or that names two services, is left for the LLM | `tests/test_agent.py::test_parse_request_deterministic_and_ambiguous` |
| Percentiles are interpolated, and an out-of-range percentile is refused | `::test_percentile_interpolates` |
| Before and after windows are compared and the +20% p95 rule fires on latency, not on error rate | `::test_compare_windows_and_regression_rule` |
| Too few samples stop the comparison instead of producing a number | `::test_compare_windows_requires_enough_samples` |
| An LLM-inferred service or metric outside the allow-lists is rejected, as is non-JSON | `::test_parse_task_rejects_values_outside_allow_lists`, `::test_non_string_llm_fields_are_rejected_not_crashing` |
| The LLM cannot mark an action executed or clear its need for approval; code sets those fields | `::test_parse_hypotheses_accepts_fences_and_fixes_authority_fields`, `::test_verify_report_flags_actions_bypassing_approval` |
| A hypothesis consistent with the evidence passes verification | `::test_verify_accepts_consistent_hypothesis` |
| Unknown citations, unmatched figures, files not in the change and an empty citation list are flagged | `::test_verify_flags_bad_citations_numbers_and_files` |
| Sign, thousands separators, seconds and percentage points are all checked against computed values | `::test_numeric_claims_cannot_slip_past_verification`, `::test_equivalent_numeric_claims_pass` |
| Derived results point to observations that exist | `::test_verify_report_flags_a_derived_result_whose_inputs_are_missing` |
| The worked example end to end: three observations, one derived result, H1 passes and H2 fails, nothing executed, status `awaiting_human_review`, and the trace names the model that handled each LLM call | `::test_regression_investigation_end_to_end` |
| The report says how many steps took no model; a skipped step counts among them and a failed call does not. This counts steps, and says nothing of what each cost or was worth | `::test_report_counts_the_steps_that_took_no_model` |
| No regression means no LLM call | `::test_no_regression_means_no_llm_call` |
| An ambiguous request goes to the model assigned to `interpret_request`, and the inferred task is listed as an unknown to confirm | `::test_ambiguous_request_routes_to_interpretation_model` |
| A missing model is reported as an unknown, never replaced by another model | `::test_missing_model_is_reported_not_substituted` |
| Malformed LLM output and provider errors become unknowns, with no hypotheses and no actions | `::test_malformed_or_failing_llm_output_is_not_trusted` |
| An unreadable evidence file becomes an unknown and the run still ends in human review | `::test_unreadable_evidence_becomes_an_unknown` |
| The diff tool refuses unsafe commit ids and lists deleted files among the changed ones | `::test_diff_tool_rejects_unsafe_commit_ids`, `::test_diff_tool_includes_deleted_files` |
| Timestamps without a zone are read as UTC | `::test_naive_timestamps_are_treated_as_utc` |
| `--json` prints the report with the same verdicts as the text run | `::test_cli_json_output` |
| The text report shown under *Worked example* is what the command prints, line for line, so a change to the output must change the README in the same commit | `::test_worked_example_transcript_matches_readme` |
| Decision (classification) models | no test yet (none is built; see the section above) |

## Design challenges

The cost limits and additive masking in [`docs/decisions.md`](docs/decisions.md) are rulings, not
code: the package has neither. `examples/cost_control` holds a small sample of each, which is not
installed and which nothing in the package imports, so that the rulings can be attacked before they
are built. `tests/test_design_challenges.py` does the attacking. A passing test is a promise that
held. A test marked `gap` states a promise the design as ruled does not keep: it is expected to
fail, strictly, so closing the gap in the sample turns the run red until the mark comes off. None
is open: the first three were closed by rulings of 5 November 2026 in `docs/decisions.md`. Team
metrics and masking were then deferred the same day, so the masking sample and its challenges are
kept as the record of that design, not as a plan to build it.

| Promise | Result | Challenge |
| --- | --- | --- |
| With no limits set, a call is refused before it is sent, and the refusal is an unknown in the report, through the existing controller and no change to it | held | `tests/test_design_challenges.py::test_default_limits_refuse_before_sending` |
| The weekly cap holds over a year of random requests, and a quiet day leaves its share for a busy one | held | `::test_the_weekly_cap_holds_for_a_year_when_estimates_are_exact`, `::test_a_quiet_day_leaves_its_share_for_a_busy_one` |
| Any 30 days spend at most five weeks' worth, so no 30-day cap is needed (one weekly cap since 11 November) | held | `::test_any_30_days_spend_at_most_five_weeks_worth` |
| The weekly cap holds whatever a response within its maximum turns out to cost, and the unused reservation comes back | held since 5 November | `::test_the_weekly_cap_holds_when_the_response_is_larger_than_estimated`, `::test_the_unused_part_of_a_reservation_is_refunded` |
| A failed call keeps its reservation | held | `::test_a_failed_call_keeps_its_reservation` |
| The lowest limit wins, and a user cannot raise one | held | `::test_the_lowest_limit_wins_and_an_unset_ceiling_leaves_the_users_number` |
| Masks cancel to the exact total | held | `::test_masks_cancel_to_the_exact_total` |
| At the minimum group size of three, a total is published and no member can read a colleague's figure from it | held since 5 November | `::test_a_group_of_three_publishes_and_no_member_can_read_a_colleague` |
| A missing contribution voids the round and names no one | held | `::test_a_missing_contribution_voids_the_round_and_names_no_one` |
| Two totals whose rosters differ by one cannot both be published | held | `::test_a_total_too_close_to_a_published_roster_is_withheld` |
| The same, with another round published in between | held since 5 November | `::test_no_differencing_holds_across_an_intervening_round` |
| A squad below the minimum group size cannot be read from the totals around it, and squads that cover their team all still publish | held since 5 November | `::test_a_folded_squad_cannot_be_recovered_from_the_totals_around_it`, `::test_squads_that_cover_their_team_are_all_published` |

## Usage

Requires Python 3.11+. No runtime dependencies.

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check . && mypy hybrid_agent tests && pytest -q
python -m hybrid_agent "<question>" --evidence examples/checkout_latency \
    [--llm-script examples/checkout_latency/fake_llm_responses.json] [--json]
```

No real LLM provider is bundled. `--llm-script` loads scripted responses into a `FakeLLM`. Without
it, the agent still runs every deterministic and computational step and reports that the LLM step
was skipped.

The development tools are pinned to exact versions in `pyproject.toml` (`pytest==9.2.0`,
`ruff==0.17.3`, `mypy==2.4.1`), so a failing check means the code changed, not the tool. The
reasons behind the design, and what is deliberately not built, are in
[`docs/decisions.md`](docs/decisions.md).

## Worked example

`examples/checkout_latency` contains static, mock evidence:

- per-request metrics for `checkout` and `search`;
- a deploy log;
- the diffs for each deployed commit.

Checkout 4.12.0 (commit `a3c91f4`) replaced a bulk inventory lookup with one lookup per cart item.

The scripted LLM response contains one sound hypothesis and one **deliberately flawed** one. The
flawed one cites evidence that does not exist, quotes an invented number and names a file that
was not changed. This shows the verifier catching it.

```
$ python -m hybrid_agent "Why did checkout p95 latency go up after the latest deploy?" \
    --evidence examples/checkout_latency --llm-script examples/checkout_latency/fake_llm_responses.json
REQUEST: Why did checkout p95 latency go up after the latest deploy?
TASK: service=checkout metric=latency

OBSERVATIONS (read by tools)
  [deploy:checkout:4.12.0] checkout 4.12.0 (commit a3c91f4) deployed at 2026-10-27T12:00:00Z
  [metrics:checkout] 240 request samples for checkout from 2026-10-27T10:00:00Z to 2026-10-27T13:59:00Z
  [diff:a3c91f4] commit a3c91f4 changed 2 file(s): checkout/pricing.py, checkout/templates/order_summary.html

DERIVED RESULTS (computed)
  [derived:checkout:before_after_deploy] p95 125.3 ms -> 286.4 ms (+128.6%); error rate 2.5% -> 1.67%

HYPOTHESES (LLM proposals, not evidence)
  H1 [passed checks] Commit a3c91f4 replaced the single get_stock_bulk call in checkout/pricing.py with a get_stock call per cart item (an N+1 pattern), so request time now grows with cart size; this fits p95 rising from 125.3 ms to 286.4 ms after the deploy.
      cites: diff:a3c91f4, derived:checkout:before_after_deploy
  H2 [FAILED checks] A new retry policy in checkout/db.yaml is exhausting the connection pool, increasing latency by 300%.
      cites: derived:checkout:before_after_deploy, logs:checkout:db
      ! cites unknown evidence: logs:checkout:db
      ! numeric claim 300% does not match any computed result
      ! refers to checkout/db.yaml, which is not in the deployed change

UNKNOWNS
  - Cart-size distribution before and after the deploy (no cart-size data was available)
  - Latency of individual inventory get_stock calls

PROPOSED ACTIONS (not executed; require human approval)
  A1 Restore a single get_stock_bulk call in price_cart and keep the per-line stock display
      why: Removes the per-item round trips introduced in a3c91f4
  A2 Before changing code, confirm by plotting checkout latency against cart size for requests after 12:00
      why: An N+1 cause predicts latency that scales with item count

TRACE (operation -> mechanism)
  parse_request        deterministic service=checkout, metric=latency
  gather_evidence      deterministic deploy_log: 1 item(s)
  gather_evidence      deterministic metrics: 1 item(s)
  gather_evidence      deterministic diff: 1 item(s)
  compare_windows      computation   p95 125.3 ms -> 286.4 ms (+128.6%); error rate 2.5% -> 1.67%
  detect_regression    deterministic p95 change +128.6% vs threshold +20.0% -> regression
  generate_hypotheses  llm           model=scripted:fake_llm_responses.json
  verify               deterministic 2 hypotheses checked, 1 failed; 0 report-level issues
  7 of 8 steps took no model

STATUS: awaiting_human_review
```

Two contrasting runs (both covered by tests):

- **`"Is search slower since its last deploy?"`**: p95 changed by +2.3%, below the +20% threshold.
  The rule reports no regression, so **no LLM is called**.
- **`"Customers say paying for their basket got sluggish"`**: the rules cannot find a service or
  metric, so `interpret_request` goes to its assigned model. The model returns
  `checkout`/`latency`, which is validated against the allow-lists. The report then lists, as an
  unknown, that the task was inferred by an LLM and should be confirmed.

## Deliberately deferred

The following are not included. Each should be added only when a concrete need shows up:

- real LLM providers;
- retrieval;
- multi-agent orchestration;
- knowledge graphs or formal methods;
- executing actions;
- investigation types other than a metric regression after a deploy.

## Known limitations (not defects)

- Only one investigation type. The request parser recognises only the services in the metrics file
  and a fixed set of metric keywords.
- Regression detection compares fixed windows before and after the latest deploy against a fixed
  threshold. It does not test statistical significance or control for traffic mix.
- Numeric verification only checks figures that have a unit. A number without a sign is compared
  by magnitude only, so a claim like "fell by 128%" is not caught when the value actually rose.
  File checks only recognise common source-file extensions. None of these checks can confirm
  that a causal claim is correct.
- The evidence and LLM responses are mocks, so they show how the system behaves, not how well a
  real model performs.

## Related

- Nothing crosses between this repository and the author's other public repositories; how they relate is kept in one map: [RELATED-REPOSITORIES.md](https://github.com/dermot-r-cochran/star-rangers/blob/main/RELATED-REPOSITORIES.md).

## Disclaimer

This project and the ideas in it are my own, published in a personal capacity. Any intellectual
property rights that may arise from my employment are retained by **UL Solutions**, as applicable.
No endorsement, sponsorship, or approval by UL Solutions is implied, and nothing here grants rights
to any intellectual property owned by UL Solutions beyond what is permitted by law.
