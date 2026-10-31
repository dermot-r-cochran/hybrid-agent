# Decisions

The design record for hybrid-agent: why the agent is shaped the way it is, what
it deliberately does not do, and each ruling in "do not re-propose" form. The
README says what the agent does; this file says why. Read it before proposing
a new mechanism, dependency, tool or investigation type.

The founding rulings are quoted from the prompt that created the repository
(pull request #1, 28 October 2026, written by the author and carried out by a
coding agent). The prompt is the brief; everything since is held against it.

## Founding rulings, 28 October 2026

1. **One principle governs the design.** *"Use the simplest reliable reasoning
   mechanism for each part of an engineering problem."* A proposal that adds a
   mechanism is judged by whether a simpler one would have done.

2. **Deterministic shell, probabilistic core, human authority.** *"Deterministic
   shell, probabilistic reasoning core, human authority."* Workflow state,
   permissions, routing, validation, calculations and verification stay outside
   the LLM *"wherever practical"*. The status of every report is
   `awaiting_human_review`; the code sets it, not the model.

3. **Ordinary software first.** *"Prefer ordinary software over AI when the
   required behaviour can be implemented reliably and simply in code."* The
   request parser, the evidence tools and the regression rule are code, and
   stay code until a concrete case shows the rules failing.

4. **Numbers are computed, never asked for.** *"Use mathematical or statistical
   computation rather than asking an LLM to perform calculations that can be
   computed directly."* Percentiles, error rates and changes come from
   `compute.py`; a figure in an LLM proposal is checked against them.

5. **Trained models are optional and earn their place.** *"Traditional ML is
   optional and should only be introduced for a concrete problem where
   classification, ranking, anomaly detection, prediction, or similar
   statistical inference is justified."* A decision (classification) model is
   in scope for closed-set decisions the rules cannot make reliably (README,
   30 October 2026, pull request #3); none is built until such a case exists.

6. **The LLM does semantic work.** *"Use the LLM primarily for: interpreting
   natural-language engineering requests; understanding unfamiliar code and
   evidence; synthesising information; generating and comparing hypotheses;
   proposing possible changes; explaining results."* Two operations exist so
   far, `interpret_request` and `generate_hypotheses`, each with its own model
   assignment and documented needs.

7. **LLM output is a proposal.** *"Treat LLM output as a proposal, not as
   evidence, truth, or authority."* Hypotheses are labelled as proposals in the
   report, verified before a human sees them, and never promoted to evidence.
   Malformed output and provider errors become unknowns.

8. **Evidence is kept in five separate kinds.** *"Preserve the evidence
   supporting important conclusions and distinguish: observations; derived
   results; hypotheses; unknowns; proposed actions."* They are separate fields
   of `Report`, and a reader can tell which is which.

9. **Human review for consequential decisions.** *"Require human review for
   consequential decisions or actions."* Nothing is executed. An action with
   `executed` set, or `requires_human_approval` cleared, fails verification;
   the LLM cannot set those fields.

10. **No formal methods without a concrete requirement.** *"Do not use
    traditional formal methods unless a concrete requirement justifies their
    complexity. Prefer familiar engineering mechanisms such as types, schemas,
    assertions, invariants, tests, static analysis, numerical computation, and
    explicit business rules."* Strict typing, a strict linter and tests are
    the verification here.

11. **Small and dependency-light.** *"Keep the repository deliberately small
    and dependency-light."* There are no runtime dependencies. Deferred until a
    concrete need shows up, in the prompt's words: *"multi-agent orchestration;
    knowledge graphs; dedicated symbolic reasoning engines; theorem provers or
    heavyweight formal methods; vector databases; custom ML models without a
    demonstrated use case; autonomous merging or deployment; speculative
    abstraction layers; complex frameworks where straightforward code is
    sufficient."* Do not re-propose any of these without the need.

12. **Extensible, but not for show.** Boundaries are kept clean so that real
    LLM providers, classical ML models, more tools, retrieval and lightweight
    rules can be added later. *"Do not build these capabilities merely to
    demonstrate extensibility."*

13. **One scenario proves the architecture.** *"Identify the single end-to-end
    scenario that will prove the architecture."* It is the checkout latency
    regression in `examples/checkout_latency`, with one sound and one
    deliberately flawed hypothesis. A second investigation type needs its own
    scenario first.

14. **Limitations are not defects.** *"Separate known limitations from
    defects."* The README keeps a *Known limitations (not defects)* section;
    a limitation listed there is a choice, and changing it is a decision, not
    a fix.

15. **The objective, in the prompt's words:** *"The objective is not to build a
    general-purpose AI platform. The objective is to demonstrate that an
    engineering agent can achieve useful behaviour by composing conventional
    software, computation, and LLM reasoning while keeping control,
    verification, and authority outside the model."*

## Intake rulings, 29 to 31 October 2026

- **A personal-capacity disclaimer closes the README** (pull request #2,
  29 October 2026). It is the author's statement and is not reworded here.
- **Decision (classification) models are in scope** for closed-set decisions
  that rules cannot make reliably, under the same discipline as the LLM:
  closed label set, confidence with an explicit threshold in code, model and
  data chosen and recorded by people, evaluated before use, a derived result
  and never an observation (pull request #3, 30 October 2026).
- **Nothing crosses between this repository and the author's others.** How
  they relate is kept in one map, linked from the README's *Related* section
  (pull request #4, 30 October 2026).
- **Every capability claim in the README names its proof** (the README-proof
  convention of the author's other repositories, 10 October 2026): the test
  as `tests/test_agent.py::test_name`, or the words *no test yet*. A `docs`
  job in CI (`.github/scripts/check_docs.py`) fails on a cited test that does
  not exist, a broken relative link or a stray front-matter block. A claim
  without a test is written down as such, not quietly dropped (31 October
  2026).
- **The development tools are pinned to exact versions** in `pyproject.toml`
  (`pytest==9.2.0`, `ruff==0.17.3`, `mypy==2.4.1`, the versions the green run
  of 30 October 2026 installed), so a CI failure means the code changed, not
  the linter. Raising a pin is its own small change, made on purpose
  (31 October 2026).
- **This file is the design record.** Rulings land here, dated, in a form
  that says what not to re-propose. The README is the manual and does not
  carry them (31 October 2026).
- **No GitHub Pages site.** This is a code repository with a README and one
  decisions file, not a documentation set; the README is read on GitHub
  (31 October 2026).
- **No behaviour changes come from review alone.** A review finding with a
  done state becomes an issue; the code changes when the issue is taken up,
  not as a side effect of documenting it (31 October 2026).
