# hybrid-agent

A deliberately small engineering agent built on one principle:

> Use the simplest reliable reasoning mechanism for each part of an engineering problem.

The deterministic controller handles the workflow, routing, model choice, calculations and
verification. An LLM is called only for semantic work: interpreting an ambiguous request,
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
- classical ML (fixed thresholds have been enough so far);
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
