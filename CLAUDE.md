# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A deliberately small engineering agent built on one principle: use the simplest reliable reasoning mechanism for each part of an engineering problem. A deterministic controller owns routing, workflow state, calculations and verification; an LLM is called only for semantic work (interpreting an ambiguous request, proposing hypotheses), and everything it returns is a proposal checked before a human sees it. Nothing is executed. Python 3.11+, no runtime dependencies. One investigation type exists: a metric regression after a deploy, proved end to end by `examples/checkout_latency`.

`docs/decisions.md` is the design record: the founding rulings quoted from the prompt that created the repository (28 October 2026) and every ruling since, in "do not re-propose" form. Read it before proposing a new mechanism, dependency, tool or investigation type. The README is the manual.

## Commands

```bash
pip install -e ".[dev]"                 # package + pytest, ruff, mypy at the exact versions CI uses
ruff check . && ruff format --check .   # lint and formatting (line length 100; rules E F I B UP)
mypy hybrid_agent tests                 # strict mode, on the package and the tests
pytest -q                               # the suite (tests/test_agent.py)
pytest -q -k verify                     # tests by keyword
python .github/scripts/check_docs.py    # the doc check CI runs: README citations, links, front matter
python -m hybrid_agent "Why did checkout p95 latency go up after the latest deploy?" \
    --evidence examples/checkout_latency --llm-script examples/checkout_latency/fake_llm_responses.json
```

CI (`.github/workflows/ci.yml`) runs the four checks and the end-to-end demo on Python 3.11 and 3.12, and a `docs` job runs the stdlib doc check. The development tools are pinned to exact versions in `pyproject.toml` (`pytest==9.2.0`, `ruff==0.17.3`, `mypy==2.4.1`); a red run therefore means the code changed, not the linter, and raising a pin is its own small, deliberate change. Every capability the README claims names the test that proves it (`tests/test_agent.py::test_name`) or says *no test yet* (Dermot, 10 October 2026); keep that true when a test or a capability is renamed, and write a new claim's proof in the same change.

## Architecture

Eight modules under `hybrid_agent/`, read in this order: `models.py` (typed `Task`, `Evidence`, `Hypothesis`, `ProposedAction`, `Report`; observations, derived results, hypotheses, unknowns and actions are separate fields), `tools.py` (the `Tool` protocol and three local tools), `compute.py` (every number; the regression rule), `llm.py` (the `LLM` protocol, `FakeLLM`, strict JSON parsing, per-operation model requirements), `verify.py` (hypothesis and report invariants), `controller.py` (routing table, workflow, model assignment, audit trace), `report.py` and `__main__.py`. The README's architecture diagram and verification list are the authority on what each step does.

Two things are set by code and never by the model: the `executed` and `requires_human_approval` fields on an action, and the report status `awaiting_human_review`. A missing model is an unknown, never a silent fallback. Malformed LLM output, provider errors and unreadable evidence become unknowns.

## Conventions

- A review finding with a done state becomes an issue; code changes when the issue is taken up, not as a side effect of a documentation change.
- The *Known limitations (not defects)* section of the README lists choices. Changing one is a decision for `docs/decisions.md`, not a fix.
- The deferred list in `docs/decisions.md` (ruling 11) is binding until a concrete need is shown.
- Tests live in `tests/test_agent.py`, grouped by section comment; a new capability gets its tests and its README row in the same change.

## Which model does which work

Dermot's direction, 2026-10-11: the account-wide split recorded in `star-rangers`' `CLAUDE.md`, applied here. Opus is the default. Fable is kept for narrative prose and image prompts and has no work in this repository, with one exception: a whole-repo next-improvement read.

- **Fable: whole-repo next-improvement reads.** Fable may read the whole repository and propose its next improvement; that is reading and proposing, and it widens no one's write reservations.
- **Haiku: reading and trivial fixes.** Read-only searches, summarising a failing CI log, `check_docs.py` drift, and simple `ruff` fixes. `ruff`, strict `mypy`, the tests and the doc check catch its mistakes.
- **Sonnet: code and tests.** Logic changes and new tests. A test that merely passes is not necessarily one that checks the right thing, which is why this is not Haiku's.
- **Opus: the protected parts.** `verify.py`, the authority fields in `models.py` and their enforcement in `llm.py` and `controller.py`, and `docs/decisions.md`. No model below Opus edits these, even where a gate would catch the mistake.
- **Opus reviews and approves** a Haiku or Sonnet subagent's diff, and it merges when CI is green. Opus escalates where a change needs a judgement it should not make alone: to Fable where one is available, otherwise to Dermot directly as choices (Dermot, 2026-10-11).

A subagent runs on its parent session's model unless the call names another, so name the model on every delegation.

## Related repositories

The map of Dermot's public repositories and what crosses between them is `RELATED-REPOSITORIES.md` in `dermot-r-cochran/star-rangers`, linked from the README's *Related* section. Nothing crosses between this repository and the others; private repositories are described there, never named.
