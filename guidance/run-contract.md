---
description: Shared authority, routing, proof and run rules.
---

# Shared run contract

## Routing and bindings

Use `N` for everything below very hard, including ordinary hard work; `X` for very hard work with coupled or non-obvious reasoning; `S` for super-hard work where deeper reasoning materially improves correctness; and `T` for taste work: small, editorial refinement where the quality is a matter of judgment. `N` is the default; tag a task `X`, `S` or `T` only when it clearly needs that depth. These labels describe capability bands, not exact model identities. Configure actual available model IDs, supported reasoning efforts, availability, and role bindings in that run's workspace-owned binding record (for example, `run.yaml`). A role resolves through the run's bindings to a model entry's exact `model_id` and `reasoning_effort`; do not infer availability from a class label, invent IDs, or silently substitute. Resolve unavailability explicitly. Plan/advisor/reviewer judgment bindings are configured separately from execution routes.

Default model for each route, using the newest available model of that family:

| Route | Work | Claude | Codex |
| --- | --- | --- | --- |
| `N` | Everything below very hard, including ordinary hard work: research, reading, running checks, most changes and fixes | Haiku | Luna |
| `X` | Very hard: intricate changes, subtle bugs, coupled or non-obvious reasoning | Sonnet | Terra |
| `S` | Super hard: deep design, or correctness that needs the deepest reasoning | Opus | Sol |
| `T` | Taste: small, editorial refinement of something that already exists, such as user-facing copy, error and refusal messages, names, a screen's layout or a doc's voice | Opus | Astra |

Reviews, plan judgment and advice use a separate high-judgment role: Opus (Claude) or Astra (Codex); configure it in the run's bindings as `completion_reviewer`, `plan_judgment` and `advisor`.

**Reviews.** A review's verdict runs on the high-judgment role. A check of a bounded fix against a named oracle (its failing case or probe) may run on `X`. `N` may gather facts for a review (check status, failure IDs, diff scope) but never gives the verdict. Check a pure sync by tree equality. A bounded-fix check runs the focused tests on both base and head. A bounded-fix check goes to the high-judgment role only when its own tests cannot show it is right (see the per-card rule under [review and promotion boundaries](#review-and-promotion-boundaries)); size alone is not a reason. A meter, gate or check is reviewed by injecting the failures it must catch. The run names the actual reviewer model, flags and permissions where it records its bindings (the workspace-owned binding record, or the run board for a dispatch run).

This table and the high-judgment role below it are the only place in the skills, docs and templates that defines model families; other documents link here rather than copy it; history records are exempt. Elsewhere name the route, and a family only when the run used one other than the route's, never an exact model ID. When workers are on Codex, `T` work may run on the Codex taste family; Claude is recommended.

## ChatGPT session modes

When a task runs in a ChatGPT session (ChatGPT web sessions only: a fresh packet session in the packet-dispatch workstream (Prepare and dispatch), or a session an orchestrator starts in ChatGPT; a Codex manager or worker run by `codex exec` takes its model and effort from the run's bindings, not from this table), the session's mode follows the task's route.

| Route | ChatGPT mode |
| --- | --- |
| `N` | High |
| `X` | Extra High |
| `S` | Pro |

A packet takes the mode of its hardest card, and its file names it (`**Route:**`). `T` work follows the run's brief; this table sets nothing for it. A mode that is not offered on the account is resolved explicitly (the next mode up, or the owner), never silently substituted. Moving a card up a route moves its session up a mode, on the same evidence as [Cheapest model first](#cheapest-model-first).

If a mode isn't offered, say so in STATUS and ask the Lead.

## Cheapest model first

Judge a task's difficulty before delegating it, start it on the cheapest model that can plausibly do it at that difficulty, and move up only on evidence. A task with no route tag is `N`.

- **Start at `N`.** Fact-finding, reading, running checks, mechanical edits, and most fixes whose failing test and likely cause are already named go to `N`. Give the worker one bounded outcome, the exact files or selectors, and the proof you expect back.
- **Escalate one step at a time, on a stated reason.** Move `N` to `X` after two misses or 20 minutes without progress, or when the returned work is wrong in a way a better brief would not fix. Move `X` to `S` on the same test. Before escalating, ask whether the brief was the problem: a vague brief fails on every model. This threshold is the manager's. A worker's is different: it stops after three attempts or 45 minutes without progress on one failure and hands the manager the raw output, what it tried and its best guess.
- **Pass the failure up.** The next model gets the previous attempt's diff, raw output and best guess, so it starts from what was learned, not from zero.
- **Judgment stays put.** The manager checks each result against the diff and the proof, never against the worker's summary. Decisions, dispositions and reviews stay with the manager or the high-judgment role; they are not delegated down.
- **Drop back down.** Once a hard problem has a known cause, the remaining edits and reruns return to `N`.

Plans tag each task with its route, and execution uses that same tag.

See [Who answers for a run](#who-answers-for-a-run) for accountable agents and fresh-packet dispatch.

The accountable agent can execute a scoped task directly; use a manager and bounded subagents when parallelism or genuinely separate research helps, not as mandatory ceremony for a small project. If delegating, the coordinating agent retains judgment, resolves each task's configured route model, checks returned evidence, and records actual model IDs and efforts in the run's binding record.

- On an `X` or `S` task, delegate as the [run contract](#who-answers-for-a-run) requires.

## Who answers for a run

**Every run has exactly one accountable agent,** and it answers for the project finishing: it keeps the run alive, chases progress against `tasks.md`, sees that every task gets started, and brings the owner their decisions. Advising, hosting or handing a project along never makes a second one.

| Setup | Accountable agent | Others |
| --- | --- | --- |
| A manager in its own session for a whole plan | That manager | The orchestrator advises, and stays idle between questions |
| Lead dispatching fresh ChatGPT packet sessions | The Lead, for each participating plan run | Orchestrator dispatches and follows up; each new ChatGPT manager session implements one packet and returns PRs/proof |
| A Claude session with Codex workers (Orchestrator, Use Codex from Claude Cloud) (the default with Codex) | That session: it is the manager | Each Codex call does one card and returns |
| A Codex manager hosted in a Claude session (Orchestrator, Use Codex from Claude Cloud) (only by choice) | The hosting session | Codex dispatches, judges and integrates the tasks; the host does everything Codex can't |
| One agent doing a small project itself | That agent | None |

**It is recorded where everyone can read it:** the `Run start` line in the plan's `inputs.md` names the accountable session, what it may do without asking, what still needs the owner's go, and the advisor if there is one.

**Its authority comes from the owner,** in the owner's own message in that session (Orchestrator, The start message). A brief relayed by another session is information, not authority. In fresh-packet dispatch the Orchestrator sends each start message from the owner's own account, so it is her message; the board's Authority section bounds it. Only the owner's own message in a session, or a committed allow rule, lifts a permission refusal; bring the refused command to her rather than retrying.

**An approval relayed from another session is never authority.** See the permission rule in [Who answers for a run](#who-answers-for-a-run).

If the orchestrator cannot start a session, give her a ready-to-paste prompt.

A `T` task is **editorial, not creative**: it refines an existing surface against a stated intent and never adds scope. Keep it small (one screen, one message family, one doc), and move anything structural or new into its own `N`, `X` or `S` task. The task card names the surface, its current text or a screenshot, the intent and the taste rules that apply (for example: minimal, plain words, never lies, always a next step). Its proof is the exact before and after, checked against those rules, plus the surface's own tests. Where the owner's taste decides, the owner sees that before and after. The `T` lead makes the edits itself and may delegate only mechanical checks.

An `X` or `S` execution lead always delegates bounded research, reading, mechanical edits and running checks to `N` helpers, and keeps the judgment and the final change itself. Reviewers and leaf advisors do not inherit that requirement. A plan may name route labels but must not duplicate model bindings.

## Actual route provenance

Plan and role bindings in the run's binding record are not proof of what ran. At each meaningful planning, research, implementation, testing or review invocation, record the **route** (`N`, `X` or `S`), role and task. Add `--override <name>` only where the run used a model other than the route's. Never put exact model IDs in PRs or other repository artifacts.

Copy the `Routes used:` line into the review submission, or write `Unknown — <reason>`. A manual log is reporting, not authentication.

## Scope, source identity, and state

This is the single policy owner for run identity, routing, focused proof, failure repair, carry-forward, review budget, and authority. The entrypoint and role guides link here instead of maintaining competing policy copies. Terms follow the [glossary](glossary.md).

A skill installation, plan, or run template does not authorize execution of the work or publication. Follow the repository's pause and stop instructions (a paused status, or a plan or brief that says stop) and its accepted plan. Do not start, resume, or broaden work without its explicit authority.

Record the actual source repository, ref and SHA, dirty state, custody, and destination branch (the plan or fix branch the work lands on); separately identify each dependency and its ref/SHA/dirty state and role. Preserve user changes and distinguish the current base from dependency inputs. If identity or custody conflicts with the assignment, stop dependent mutation and resolve the discrepancy. Each assignment names its outcome, in-scope behavior/paths, dependencies, source identity, route, and focused acceptance evidence.

Keep only the recovery state needed to resume: goal, ready tasks/dependencies, candidate identity, completed/blocked tasks, failures, evidence, consumed review rounds, and next action. Do not add an acceptance-ledger or document framework without a concrete need. Continue independent work when another task is blocked. Never reset accepted run choices, budgets, evidence, or program state because guidance changed.

**Add commits only:** never rebase, amend or force-push, even on your own branch. To bring in a newer base, merge it in. Never rewrite a contributor's branch. Never read or print `.env` files, `~/.codex` or any credential or token file. A saved credential reaches every process in the environment, tests and workers included: keep it in an environment of its own, stub every test that would call the real provider, and keep paid or credentialed steps with the manager. Before a run pauses or ends, return every rented machine it made, and say which, whatever happened.

Put no model name in a commit message.

**Planning authorizes no execution or promotion** ([run contract](#scope-source-identity-and-state)), and performs no implementation testing unless specifically requested; planning-document PRs still run relevant doc validators and focused unit tests ([checks](#checks-and-failure-repair)).

## Decisions ledger when the owner is unavailable

When work proceeds without the owner (for example, a contributor or agent helping while the owner is offline or out of quota), keep a decisions ledger from the template below. Record any proposed change to the written plan, an in-scope best guess where it is silent, any stop-and-ask decision awaiting authority (such as a conflict where both sides change one statement), the trajectory inferred, and improvements not built. Include evidence, the candidate SHA when one exists, and how to revert. A provisional proposal is never permission to execute work outside the accepted scope or bypass a stop. This is the concrete need under [Scope, source identity, and state](#scope-source-identity-and-state): it lets the owner accept, change or revert each call later, without rereading the run. A ledger entry is never authorization: stop-and-ask boundaries remain stops, and anything that lands still needs the owner's go.

Keep one ledger per run, next to the run's evidence. The owner reconciles it later, row by row: accept, change or revert.

Types:
- **override**: deviated from the written plan.
- **guess**: the plan was silent or ambiguous, and we picked.
- **STOP-proposal**: the plan says stop and ask; we recorded both sides, chose a proposed resolution and kept going only on independent authorized work.
- **improvement**: a suggested change to a plan or process; not built unless approved.

| # | Type | Plan / task | What we did | Why (evidence: file:line, log, SHA) | Candidate SHA | How to revert | Owner verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | | | | | | | |

**Inferred trajectory:** What the recent plan and owner decisions suggest the owner is steering toward, and how that shaped the guesses above. Keep it short; it is the tie-breaker you used, stated so the owner can correct it.

**Not built (ideas for approval):** What, why, rough cost.

## Coordination: boards and check-ins

- **Where to post.** Your own updates go on your own board. A message about a plan goes on that plan's board. Reply where the message was posted.
- **Chain.** The Lead addresses orchestrators. An orchestrator addresses its manager. A manager relays to packet sessions. Peer orchestrators may post on each other's boards about shared code.
- **Hourly update.** Leads, orchestrators and managers post one STATUS an hour on their own board, in 10 lines or fewer ("no change" is one line). It lists what was acted on since the last update, which replaces standalone ACKs. Packets post only milestones: early STATUS, READY-*, BLOCKED and DONE. Post each message once, to one addressee.
- **Read by cursor.** Read your board after your last processed cursor, putting the cursor in your STATUS. Read your parent's board for messages addressed to you. Re-read `run.md` Standing rulings only when it has a newer commit.
- **Waking and urgency.** Every Claude role and every manager creates its own hourly scheduled task at start-up, at a minute other than :30, checks that it fires, and never disables another session's task. A Claude cloud session also keeps a keep-awake loop. `send_message` is a Claude-to-Claude doorbell for what can't wait an hour. ChatGPT sessions post BLOCKED instead.

## Checks and failure repair

**Prove:** Record proof as this section and [Actual route provenance](#actual-route-provenance) say. A green wrapper is not proof of the work itself.

Locally, run only explicitly scoped, feature-focused test runs; never broad, auto-discovered, repository-wide, full affected, or opt-in suites. The full relevant suite runs on hosted CI, only at the moments the [table below](#when-a-test-run-is-load-bearing) names. Pure planning and research do not execute implementation checks unless specifically requested. Editing planning documents or check code still requires the appropriate local documentation validators and focused unit tests before submitting a PR; that validation is not permission to execute implementation tests. Use a documented narrow command/selector grounded in the current repository and task; do not invent test names, selectors, or commands.

Record each proof's exact command, candidate SHA/tree, relevant inputs/environment, actual inner command status and diagnostic output, result, and limitations. Judge the inner build/test/install command, not a wrapper's transport status. Interpret statuses such as 125 or 127 only according to the runner and command's documented semantics; they are not universal meanings. Use `PASS`, `FAIL`, `RETRYING` (infrastructure retry in progress), and `NO-RESULT` (missing evidence). A pass applies only to the exact candidate and inputs it names.

Preserve the initial failure and its exact command/candidate. If a check fails, repair its in-scope cause and rerun that same actual failing check on the repaired candidate. Keep implementation failures distinct from infrastructure failures. Transient capacity, readiness, network, eviction, or missing-result failures may be retried with the same inputs; invalid requests must be corrected. After two failures with the same signature, do not run unchanged again: first change or diagnose the cause, fixture, environment, or input. Do not mask a failure, replace it with a broader check, or claim an unrun check passed.

Carry proof forward only when its relevant inputs and implementation/dependency/generated/installed bytes are evidenced unchanged. A changed candidate invalidates only evidence dependent on the change; preserve unaffected passing proof. Protected surfaces and changed relevant inputs require proof for the exact candidate. Accepted scoped checks do not support a claim that an entire repository or suite passed.

**Never edit, skip, loosen, xfail or delete a test, a fixture, an oracle line or a check to get a pass,** in the file or on the command line. If a card would make one untrue and does not list it, the worker stops and reports the exact lines. The manager rules in the same turn and records the before and after in the card's row, and only then may the line change. A pinned test that pins a defect goes to the review or the contract's author, not to the worker.

**When to use:** When a candidate needs qualification or existing CI failures prevent reliable integration.

**Outcome:** Complete, trustworthy test evidence showing either no new failures or diagnosed repair of old red without weakening checks.

**Inputs:** The exact source and baseline revisions, original test inventories, runner and dependency identities, and authorized proof scope.

**Procedure:** Measure original jobs and identities, compare real failures, repair causes within scope and retain all regressions and gate evidence.

**Completion:** Native outcomes and raw exits reconcile with the stated claim, including blockers and any remaining red.

- **Measure before you judge.** A comparison is only as good as its least complete side.
- **No result is not a pass.** A required job that was cancelled, timed out, skipped when it should have run, or stopped in setup has **NO-RESULT**, as does a test job that ran zero tests. Never count it as green, and never count its tests as missing. A log that omits passes (pytest `-ra`) shows its failures, but can never support a complete comparison or a claim of zero regressions.
- **Diagnose freely; qualify once.** A NON-PROOF run tells you what is there, and never counts for a gate. Only an ordinary run of the exact candidate, with complete reporting, qualifies (Iterate workstream, Prove and hand off).

**Question, mode, and where it ends.** For candidate-versus-baseline qualification or diagnosis of existing red, begin by measuring. If measurement cannot complete, the first card fixes reporting.

For each side, and each workflow in scope:

1. **Inventory the jobs** of the exact run, and sort each one into a kind:
   - a **test job**, which must report per-test results;
   - a **non-test check** (lint, mypy, a build), compared by its own output;
   - an **expected omission**, a job that is meant to be skipped on this trigger.

   The kind says what a usable result is: per-test lines for a test job, its own output for a non-test check, and its dependencies' results for an aggregate. Every required job needs one. A required job that is unexpectedly cancelled, skipped or absent is NO-RESULT, and blocks qualification; only an omission the workflow defines for this trigger is exempt, with the reason recorded.

2. **Fetch the logs**, strip the timestamp prefix, and keep the raw copies.
3. **Count each test job's tests.** A count far below that job's usual count means a setup break, a collection abort or a hang, even when the job reads "success". Count failures as distinct (job, id) pairs, not summary lines: one id can appear twice in a job's summary.
4. **Find out what is behind each NO-RESULT** with a NON-PROOF run. Change only what stops the run, and keep every marker, selector and lane option:

| Stop | NON-PROOF way through |
| --- | --- |
| A hang (Manager's threshold, Steps) | Cancel it; don't wait. Name the test: collect the shard exactly as CI does (the same command, `--splits`, `--group` and `--durations-path`), map the last progress line's characters onto that order, and read the pytest-timeout dumps. Run that test alone on both sides with `-o faulthandler_timeout=300`. A scratch run that leaves out the hanging file changes coverage, and the shards' membership with it. So compare by test id, account for every id of the original inventory, and keep the left-out ids unsorted |
| A setup step fails, so no tests run | Fix the setup; it is usually one card. Then run again |
| A suite stops at its first failure (`-x`, `--maxfail`, a serial chain) | Override only the stop. Append `--maxfail=0` after the job's own options, or run a serial chain one test at a time with an isolating filter |
| A failing gate skips the job's later steps | Run the skipped steps once on a scratch ref |

5. **Then qualify.** A NO-RESULT closes only through an ordinary run of the exact commit with complete reporting. Usually that means a reviewed reporting fix lands first, for example `-rA` in that repository's workflow.
   - A baseline run from a scratch commit counts only if the commit changes reporting alone, so the same tests run, and its row names that commit.
   - A commit that leaves tests out is diagnostic, and its left-out tests stay unsorted.
   - The gate's owner rules on any other case, and the ruling is recorded on the row.

One row per failing or missing id. Each row gives the bucket, candidate SHA, one-line cause, the commit or work track that introduced it, owner, disposition and link.

- **Run less to learn more.** Diagnose on one shard or one file, not the whole matrix. Re-run a cancelled shard only after you have changed or diagnosed its cause ([two-same-signature rule](#checks-and-failure-repair)).
- **Never wait on a run.** While it runs, cluster the last results and brief the next batch.
- **Run everything independent at once:** measurement, clustering and disjoint fix cards, using cheap helpers for the mechanical parts ([routes](#cheapest-model-first)).
- **Spend review where it bears load:** a disputed bucket, a change to an assertion, the decision to spec a project, and the qualifying run.

Gate rules do not apply to iteration. A scratch or diagnostic run needs no authorization, no independent review and no sanitized-only output. Keep raw logs while diagnosing; redact only what you commit, and never print credentials. Two things hold in both modes: [no check is weakened to get a pass](#checks-and-failure-repair), and paid spend always needs its own authorization.

## When a test run is load-bearing

Run tests at the moments where the result changes a decision, and at no others. A run is load-bearing when someone is about to rely on it:

| Moment | Run | Why it bears load |
| --- | --- | --- |
| **Before the first task** | The plan's test inventory, once, on the starting versions | Without it, a later failure can't be told from one that was already there |
| **After each task** | Only that task's focused proof: the tests that would fail if this task were wrong | It decides whether the task is done |
| **Before others build on it** (a contract, data model, shared interface or security boundary lands, or a chain hands over to a different worker) | The tests that cover that shared part | A mistake found later means redoing every task built on it |
| **Before review, and before anything reaches `main` or users** | The full relevant suite, once, on the integrated head, on CI | It is the last point where a failure is cheap |

Not load-bearing, so skip it: a broad suite after every task; re-running a proof whose inputs have not changed (carry it forward); a test with no baseline to compare against; a run whose result nobody will act on. A **regression** is a test that ran and passed on a baseline and fails on the candidate. A test that is absent, skipped or uncollected on every baseline has no baseline, so it is not a regression; it is fixed only if this run added it. After each load-bearing run, compare with the baseline by this rule and fix only what is new. For a merge or a rebuild onto another branch, the baseline is the branch you merged onto, not the one you came from, and the test scope is every test file that touches a changed module, on both, not a focused subset: a clean textual merge can still break (one side deletes a file the other starts reading), and the old branch's existing failures hide it.

**One exception, by cost:** when the whole inventory runs in seconds, run all of it at every moment above. The table exists to ration expensive runs, not to justify skipping cheap ones.

A plan names its load-bearing moments in `tasks.md`: the test inventory, each task's focused proof, and any join that needs the shared part re-proven.

**Flips:** compare same-commit baseline runs with each other. A test that flips between runs of one commit gets its own row, with both runs, and is never retried until green. **A flip excuses nothing:** a candidate failure that passed on any baseline run is still a regression, and still blocks.

Re-sort failing and missing IDs at each load-bearing run. The gate stands on the frozen candidate's qualifying run, with no blocking row left and no required job without a usable result.

## Review and promotion boundaries

Review rounds are proportional, not a default ritual: where the accepted plan sets any, end with them on the integrated candidate. **Per card, a high-judgment review runs only for:** an `S` card; a change to what the work accepts, refuses or publishes (an integrity rule, a fence, a contract); or code brought in that a review has already judged unsound. Every other card, `N` or `X` (tests, fixtures, tooling, measurement, ordinary fixes), is proved by its own focused tests and waits for the final round. An early review costs a round now to save untangling later; spend it only where a late finding would be expensive.

An accepted plan may also set a review stop after a load-bearing part (see the Plan workstream, Task cards); a stop follows this same protocol on that part's integrated result, with its own agreed rounds, and the tasks built on it wait for it. The final review always runs after required scoped checks and before publishing or closing, by the `completion_reviewer`. The plan records how many rounds at most: the planner recommends a number from risk and complexity (as a guide, 0 for a simple, bounded project where ordinary PR review is enough; 1 for meaningful complexity; 2 or 3 only for cross-repository, multi-project delivery, security or data work) and the owner agrees. Each finding comes back as a task card (outcome, route, scope, dependencies, focused proof) and is done before the next round.

Stop after a round with no blocking findings; a blocking finding still open after the last agreed round goes straight to the orchestrator, who rules under the owner's delegation or takes it to the owner; a run with no orchestrator, or under fresh-packet dispatch, takes it to the owner. Do not pass with an unresolved blocking finding. Preserve an existing run's exact accepted review scope, stage, candidate, remaining rounds, and consumed count; never add stages, reset counts, silently change the reviewed candidate, or ask for sign-off after every task. Planning-only runs have no active review stage by default.

**Suggest reviews only where they earn their cost.** State your recommendation in every plan, including when it is none; don't wait to be asked.

- **A simple, bounded project needs no review rounds,** so leave the review row out. For meaningful complexity, recommend one round at the end, before any publishing task, which depends on it. Recommend more only as the [run contract](#review-and-promotion-boundaries)'s guide says, say why, and record the recommendation and the owner's agreed number on the `Review rounds` line in `inputs.md`.

- **Add a review stop after a load-bearing part** of a significant project: a contract, data model, protocol, security boundary or shared interface that later tasks build on, where a mistake found only at the end would mean redoing those tasks or would reach users. Put it right after that part, as its own row (`RS<n>`, named for what it reviews), with the later tasks that build on it depending on it. It uses the same protocol as the final review: rounds at most _n_, findings as task cards, done before the stop clears. Use it sparingly, typically only on larger projects (above about five days, or cross-repository) and at most one or two per plan. Each stop needs a stated reason: which later tasks it protects and what a late finding would cost. Record each stop and its agreed rounds in `inputs.md`, alongside the final review.

An iterate result is a feature candidate, not an integrated or promoted result. Its author does not integrate, independently review, promote or publish it, or claim that any of these happened. When integrated proof fails, route the repair to the same iterate loop, then recheck the integrated candidate. Advice does not waive a review or authorize execution/publication. Ask the owner only for a real authority, scope, or unresolved consequential choice.

## Run template

A run template's class labels are illustrative only. Map role keys to configured model entries in `roles`; do not create a second binding source. A template is planning-only and does not initialize, reset, or authorize any existing run.
