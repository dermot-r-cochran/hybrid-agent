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
   the LLM cannot set those fields. *Narrowed on 11 November 2026 for one
   case, a confirmed, read-only evidence call to a configured local partner
   (A local partner, recipes and workflows, below).*

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
    *Multi-agent orchestration was narrowed on 11 November 2026 to allow one
    hand-over to a configured local partner and nothing more (A local
    partner, recipes and workflows, below).*

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

## Direction rulings, 3 November 2026

- **This repository is the public face of the idea.** A deterministic
  controller, an LLM only for semantic steps, an unknown where no model is
  assigned: the author keeps a private engineering agent built on the same
  principle, and this is the one that is published.
- **It may learn from the private agent, one way, in design only** (the
  author, the same day: hybrid-agent may learn from it in terms of design
  and use a streamlined public-facing version of its capabilities). This
  narrows the "nothing crosses" ruling above for that one sibling and in
  that one direction:
  - **What may cross:** design ideas and capabilities, rewritten here in
    this repository's own terms, streamlined for a public reader, and each
    under the rulings above (ruling 11's deferred list and ruling 12's "not
    for show" still decide whether a capability earns its place).
  - **What never crosses:** code copied wholesale, its record of rulings,
    and anything that came from the private agent's working environment
    (names, figures, logs, examples).
  - **How it is named:** the private sibling is described, never named, and
    nothing flows back the other way through this repository.
- **More languages and deployment environments are in scope in principle.**
  The controller, the evidence kinds and the verification are not
  Python-specific, so support for further coding languages and deployment
  environments is a direction, not a ruling to build. Each one arrives when
  a concrete need shows it, through ruling 12's clean boundaries rather than
  a speculative abstraction layer (ruling 11).
- **It will eventually be published as an SDK package** on a public Python
  feed (PyPI or similar). Not yet: there is no package name, no version
  policy and no release process, and each of those is a decision for this
  file when the time comes. Ruling 11 still governs the package: no runtime
  dependencies.
- **The package imposes cost limits by default.** Out of the box it makes no
  model calls: every limit defaults to 0, so a step that would call a model
  records an unknown, the same unknown the controller already records when
  no model is assigned to an operation (the README's *Choosing a model for
  each LLM operation*). A user who assigns a model also sets limits, which are counted in
  input-equivalent tokens (each token kind weighted by its price relative to
  base input, with weights per model and ratios only, never prices), as an
  allowance that accrues daily. Unspent allowance rolls over up to a burst
  cap, under a rolling 30-day cap that holds whatever the bucket holds (the
  same day, the author: unused daily quota may roll over, subject to a
  30-day rolling limit). A request that fits neither the bucket nor the
  rolling cap is refused before it is sent, and the refusal is an unknown
  with the reason in the trace. *The daily accrual, the burst cap and the
  30-day cap were replaced by one weekly cap on 11 November 2026 (below);
  the defaults of 0, the input-equivalent count and the refusal as an
  unknown stand.*
  Limits are the user's own numbers. No price, currency or real figure ships
  in the package, its tests or its docs.
- **A management approver is a code owner or an organisation admin** (the
  author, the same day, answering the first open question on issue #11). A
  change that raises a cost ceiling counts as approved when a code owner of
  the policy repository, or an admin of the GitHub organisation that holds
  it, has approved it. The package keeps no list of approvers of its own:
  who holds either role is the hosting platform's record, so the approval
  and the approver stay in the repository's own history. The rest of #11
  (how the policy file is trusted, per-person views, baseline collection)
  stays open.
- **The policy lives with the work; the keys stay local** (the author, the
  same day, answering the second open question on issue #11). The cost
  policy file lives in the target repository or in a repository of its
  organisation, so it is trusted the way that repository's other reviewed
  files are: changed only through a change its approvers (above) accepted.
  Model keys and credentials never go in the policy or in any repository.
  They stay in a local file on the user's machine, unless the policy names a
  key management service, in which case the keys come from that service
  instead. The policy may name the service; it never holds a key. Which
  services are supported is decided when one is first needed, under ruling
  11 (no runtime dependencies). Per-person views and baseline collection on
  #11 stay open.
- **Usage and savings are reported per squad or per team, never per
  person** (the author, the same day, answering the third open question on
  issue #11: per-squad or per-team usage would be useful). A report may
  break usage, limits and savings down by squad or by team, and an
  organisation ceiling may be set at either level. The grouping comes from
  the organisation's own record (its GitHub teams, for example), not a list
  the package keeps. The minimum group size still holds: a squad smaller
  than it is reported inside its parent team, never alone, so no breakdown
  can single out one person. Baseline collection on #11 stays open.
- **A weekly quota sits between the daily accrual and the 30-day cap** (the
  author, the same day: weekly quotas might also be helpful). It is a
  rolling 7-day cap, counted in the same input-equivalent tokens and derived
  from the same usage record as the 30-day cap. Like every limit it defaults
  to 0, so a user who assigns a model sets it too. A request is sent only if
  it fits the bucket and every rolling cap; otherwise it is refused before it
  is sent, and the refusal names which limit it hit. An organisation policy
  (issue #11) may set weekly ceilings per user, per squad or per team, and
  the lower of the organisation's and the user's number wins, as for the
  other limits. *Since 11 November 2026 this weekly cap is the only limit
  (below).*
- **Quotas may be enforced per GitHub user; reports still never name one**
  (the author, the same day: quotas can be enforced per individual GitHub
  user even if not mentioned in the reports). Enforcement and reporting are
  separate:
  - **Enforcement:** an organisation policy may set the limit (the weekly
    cap since 11 November 2026; daily, burst and 30-day before) for an
    individual GitHub user, as well as for a
    squad or a team. The lowest number that applies to that user wins.
  - **Where it is counted:** on the user's own machine, from their own
    usage record, as the user's own limits already are. A refusal is shown
    to that user and recorded in their own trace; it is not sent anywhere.
  - **Reporting:** unchanged. Reports go no finer than a squad or team, the
    minimum group size holds, and no report shows which user hit a limit.
- **Keys come through a small key-source contract, and the organisation
  policy may name the command** (the author, the same day, on issue #11:
  the key management service depends on the local architecture; asked
  whether the organisation policy or only the user's local config may name
  the command that fetches a key, *"Org policy too"*).
  - **The contract is the package's side, not the service's.** The package
    never speaks a vendor's key-service API, which would mean a runtime
    dependency or a client per vendor (ruling 11). A `KeySource` takes a key
    name and returns the secret or fails; a failure is an unknown with the
    reason in the trace, never a fallback to another source.
  - **Two sources ship:** a local file (the default), and a command source,
    a local command that prints the secret on stdout (an organisation's own
    vault CLI, for example).
  - **Either the user's local config or the organisation policy may name
    the command.** A command named in the policy is approved the way the
    policy is, by the policy repository's code owners or organisation admins
    (above).
  - **What never changes:** the policy holds no secret and no URL for the
    package to call; secrets are never logged, traced or reported, and are
    fetched fresh each run, never cached to disk.
  - **A narrow exception to "nothing is executed".** That founding rule is
    about proposed actions, and it stands: the controller still executes
    none. Running the named key command is the one command the package
    runs, only to fetch a key, never to act on the investigation.
- **Each local instance tracks its own user; metrics are reported per team
  and squad** (the author, the same day, answering the last open question
  on issue #11, how baselines are collected).
  - **Tracked locally:** each user's instance keeps that user's own usage
    record and the timings behind the person-hours baseline, on that user's
    machine, as it already keeps their limits. The user can read their own
    record; no one else's instance can.
  - **Reported in aggregate:** what leaves an instance is an allowlisted
    contribution (counts, totals, task kinds, coarse dates; no free text and
    no money) that is only ever shown summed at squad or team level, under
    the minimum group size.
  - **Still to design when #11 is built:** how a contribution reaches the
    squad or team total without the route itself naming its sender (a pull
    request, for example, is attributed to whoever opens it).
- **Contributions are summed by additive masking, with safeguards for
  changes of membership** (the author, the same day, on issue #11). The
  problem is the one secret ballots solve: the total is public and
  checkable, each contribution is private, and the route must not name its
  sender. Of the three known approaches (a trusted tallier, additive
  masking, homomorphic tallying), additive masking is chosen: an exact total
  with no one trusted, and only arithmetic and a shared secret per pair of
  members, so no runtime dependency (ruling 11).
  - **How it works:** for each round, every pair of members in a squad or
    team derives a fresh random mask from a secret they share; one adds it
    to their contribution and the other subtracts it. Each masked
    contribution on its own reads as noise; summed, the masks cancel and the
    total is exact. Masks are never reused between rounds.
  - **Safeguard 1, a frozen roster.** A round's members are fixed when the
    round opens, from the organisation's own record (above). Someone who
    joins mid-round waits for the next one; someone who leaves mid-round
    voids it.
  - **Safeguard 2, all or nothing.** A round publishes only if every member
    of its roster contributed. A missing contribution would leave masks
    uncancelled, and a partial reveal is never offered, so the round is
    void and rerun with the roster as it then stands.
  - **Safeguard 3, no differencing.** Two totals whose rosters differ by
    one or two people would reveal those people's figures by subtraction.
    A total is therefore withheld when its roster differs from the last
    published one by fewer than the minimum group size, and that period is
    folded into the next publishable one or into the parent team. (Widened
    to every published roster on 5 November 2026, below.)
  - **The minimum group size holds for every round,** as for every report.
  - **Left to the build:** how each pair agrees its shared secret within
    the standard library, and how a void round is told apart from a quiet
    one without naming who did not contribute.
- **The bar is relative privacy, not absolute secrecy** (the author, the
  same day, on issue #11). The aim is that, in ordinary use, no colleague or
  manager can read one person's figures from what is published. It is not a
  guarantee against a determined insider, collusion between members, the
  hosting platform, or someone with access to a member's own machine.
  What this changes:
  - **Additive masking and its safeguards stand,** because they are cheap
    and they make the ordinary case private by construction. They are not
    required to resist collusion: if members pool their masks they can
    recover a colleague's figures, and that is accepted.
  - **The build takes the simplest option that meets the bar** at each point
    left open above. A pairwise secret may come from a simple exchange
    rather than a hardened protocol, and a void round may say plainly that
    it is void, as long as it does not name who was missing.
  - **The minimum group size and the no-differencing rule stay,** since
    they are what stop the ordinary reader, not only the determined one.
- **A trusted collector is rejected; do not re-propose it** (the author, the
  same day: a collector would be a single point of failure). Relative
  privacy (above) would have allowed one, but a single component holding
  every member's figures is one place to fail, to leak and to be pressed
  for an individual's numbers. Additive masking keeps no such place: no
  component, and no person, ever holds one member's unmasked figures.

## Design challenge rulings, 5 November 2026

The design challenges (`tests/test_design_challenges.py`) found three promises
the rulings above did not keep. These closures are recommendations that follow
from those rulings. The author took them up the same day (*"The three gaps"*,
*"The group size"*) and accepted the direction (*"Sounds good"*). The wording is
the recommendation, not the author's, and it stands until the author changes it. What was checked is the samples in
`examples/cost_control`, not a built feature.

- **A limit is checked against the worst case.** The cap is promised to hold,
  and a response's size is not known before it is sent, so a request reserves
  its prompt plus the largest response allowed, is refused if that does not fit,
  and has the unused part refunded afterwards. A request that would have fitted
  can therefore be refused near a limit; that is the price of the cap holding. A
  failed call keeps its reservation, because what it cost is not known. Building
  this needs the `LLM` protocol to carry the maximum and report the counts, and
  it relies on the provider keeping to the maximum.
- **No-differencing compares with every published roster,** not only the last.
  Otherwise a round in between lets two nearly equal rosters both publish. It
  does not expire: a withheld total folds into a later period or the parent team
  (above), so this never leaves a figure with nowhere to go.
- **What remains after subtraction counts as a group.** A squad folded into its
  team is still alone if the team total minus the published squads leaves only
  that squad. So the people a team total leaves unaccounted for must number none,
  or at least the minimum group size, and the smallest published squad is held
  back until they do. This applies wherever a total sits above smaller totals.
- **The minimum group size is at least three.** In a group of two, either member
  reads the other's figure by subtracting their own, which fails the relative
  privacy bar. Three is the package's default and its floor; an organisation
  policy may raise it, and may not lower it.
- **One person can use it alone, with no team, no metrics and no organisation
  policy** (the author's question and *"Yes, record both"*, the same day; this
  states what the rulings above already imply). They set their own limits, or
  no model is called. Their usage stays on their own machine, where they read
  it directly. No round is opened and nothing leaves the machine.
- **There are no virtual members.** A roster comes only from the organisation's
  own record, and the package offers no way to add to one. Alone, an invented
  member gains nothing, since the total would still be one person's figure. In a
  real team of two, one invented member would reach the minimum group size and
  let either real member read the other's figure.

## Team metrics deferred, 5 November 2026

**Team metrics and additive masking are deferred until a concrete need shows
up; do not build them or re-propose them without one** (the author, the same
day: *"Metrics are a secondary requirement if there is another way to show
business value for concerned managers"*, then *"Yes, defer them"*, on being
shown other ways). This defers the 3 November direction on reporting; it does
not reverse it. The rulings stay on record, ready if the need comes.

- **Deferred:** per-squad and per-team usage and savings reports, contributions
  and additive masking with its safeguards, the person-hours baseline, and the
  question of where masked contributions go (issue #11).
- **Stays:** cost limits, organisation ceilings at every level, per-user
  enforcement, approval as a reviewed change, and the key-source contract. Each
  user's own usage record stays, because the limits are counted from it.
- **Still ruled out:** a trusted collector, and any report that names a person.
- **How value is shown instead,** none of which collects figures from anyone:
  the ceilings and the provider's own bill for cost; a repeatable before-and-after
  on a fixed set of example investigations; the trace, which already shows which
  steps took no model; and written cases from people who choose to share them.
- **The limit of this:** a benchmark shows what the agent can do, not how much a
  team uses it, and a bill shows spend, not time saved. A manager who needs
  measured team savings is the concrete need that would reopen this.

## One weekly cap, 11 November 2026

**The allowance is one rolling weekly cap; this supersedes the daily
accrual, the burst cap and the 30-day cap of 3 November** (the author, the
same day: *"Yes update the cost ruling"*, accepting a recommendation to carry
over a lesson from use). The author's private engineering agent, described
here and never named, was built with the same daily, rollover and 30-day
limits and was cut down to one weekly figure after use showed the extra
limits added settings without adding protection. The reasoning is restated
here in this repository's terms.

- **The week is the rollover.** A quiet day leaves its share inside the
  7-day window for a busy one, which is what the daily figure and the burst
  cap together were built to allow.
- **The week bounds the month.** Any 30 days fall within five 7-day windows,
  so they spend at most five times the weekly figure. A user or an
  organisation that thinks in monthly money sets the weekly cap at a fifth
  of it, and the 30-day bound holds without a 30-day cap.
- **What is given up.** One day may spend the whole week's figure. Stopping
  a runaway investigation is the job of the per-call maximum the reservation
  already uses, not of a daily figure.
- **What stands:** every limit defaults to 0, so out of the box no model is
  called; usage is counted in input-equivalent tokens from the user's own
  record; a request is reserved at its worst case and refused before it is
  sent, with the refusal an unknown that names the cap and what is left;
  organisation ceilings at every level and per-user enforcement apply to the
  weekly cap, and the lowest number wins.
- **Proof.** The sample in `examples/cost_control/quota.py` now holds one
  weekly cap, and `tests/test_design_challenges.py` checks that a quiet day
  leaves room for a busy one, that any 30 days spend at most five weeks'
  worth, and that the cap holds over a year of random requests.

## A local partner, recipes and workflows, 11 November 2026

**The agent may work with a local partner: a separate agent customised for
the user's own machine and stack, which the user may or may not have**
(the author, the same day: *"Hybrid Agent is technology stack agnostic
whereas my [own agent] is customized for my own local Work PC and cloud
stack"*, then *"Hybrid Agent may assume a customized local agent which may or
may not already exist"*). The author's own partner is the private
engineering agent of the 3 November direction, described and never named;
here it is a role that any user may fill. This is a direction: nothing is
built in the package until the issue that tracks it is taken up.

- **The stack stays out of the package.** Commands, cloud tools, credentials
  and models trained on a user's data belong to the partner or to the user's
  own files. The package ships formats, validation and synthetic samples,
  never a recipe or a trained model for a real stack.
- **Three terms, kept apart:**
  - A **recipe** is a fixed, linear list of concrete steps on one stack that
    stops at its first failure. It lives in the partner.
  - A **meta-recipe** is a fixed, linear list of stack-agnostic evidence
    steps, for example a service's deploy record and its metrics for an hour
    either side. It lives here, as data, and has no branches.
  - A **workflow** is this agent's own route from a question to a verified
    report, with branches and state. It stays in code, one per investigation
    type, each arriving with its own end-to-end scenario (ruling 13). Every
    branch is decided by code, or by a decision model above its threshold
    in code (ruling 5); never by the LLM (ruling 2). A meta-recipe is one
    step inside a workflow. Workflows written as user files would need a
    branching language, which ruling 11 defers.
- **The partner is described in a local configuration file** in the user's
  home folder, read with the standard library (`tomllib`), never committed;
  the repository ships a sample with an invented stack (the author: *"on my
  work PC can add a config for my Hybrid Agent to know about my [own
  agent]"*). It names the folder the partner writes evidence to, binds each
  meta-recipe step to one of the partner's recipes by name, marks which of
  those recipes are read-only, and describes each decision model the
  partner runs: its labels, its threshold and where its output lands.
- **Two ways to hand work over, both allowed** (the author: *"the Hybrid
  agent could drop files for the local agent or call it directly from the
  command line, or both"*, then *"Both, narrowed"*):
  - **Files.** The agent writes a request file naming the meta-recipe and
    its bound recipes, and the partner or the user picks it up.
  - **A direct call, narrowed.** The agent may start the configured partner
    from the command line, only to run a recipe the configuration marks as
    read-only, only for evidence, and only after the user confirms that call
    at the prompt. The partner's own approval steps still apply. Fixes,
    merges, deployments and every other consequential action are proposed,
    never run.
- **Both are command-line tools running locally** (the author: *"Command
  Line Interface, running locally for both, even if they are cloud-aware"*).
  The partner is reached only as a process on the same machine, or through
  a folder on it; never as a network service, a hosted agent or a remote
  endpoint. Either may talk to cloud services on its own account, as the
  partner's recipes may, but the hand-over between them never leaves the
  machine, and this agent opens no listener of its own.
- **Without a partner, nothing breaks.** The meta-recipe is printed as a
  checklist for a person to gather the evidence by hand, which is how the
  agent works today. Having no partner is the default, like having no model.
- **A partner's decision model is the partner's.** Its output reaches this
  agent as a derived result that records which model gave it, the label and
  the threshold, under the decision-model discipline of 30 October; never as
  an observation.
- **This narrows two founding rulings, for this one role:**
  - **Ruling 9** stands for every consequential action. Starting the
    configured partner for a confirmed, read-only evidence recipe is the one
    thing this agent may start.
  - **Ruling 11's deferral of multi-agent orchestration** is narrowed to
    allow this hand-over and nothing more: one configured partner, one
    confirmed call at a time, no channel kept open between the two, no
    shared memory, and no agent started by the partner. Anything beyond that
    is still deferred.
