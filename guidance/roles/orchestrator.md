---
description: Deploy and supervise authorized manager sessions, advise on hard questions and keep handoffs moving.
skill: true
---

# Orchestrator

## Responsibility

Keep authorized manager sessions progressing.

## Authority

Coordinate but do not assume a manager's execution or owner powers.

## Responsibilities

When supervising managers or dispatching work sessions, keep manager runs and handoffs moving, advise and check in.

Dispatch, advise and unblock according to the run.

**Your job:** get authorized work into manager sessions and keep it moving. The default is a continuing project manager; the [fresh-packet workstream](../workstreams/packet-dispatch.md#prepare-and-dispatch) uses a **new ChatGPT manager session for each packet**, with the Lead owning plan-level integration.

1. **Deploy:** brief managers from accepted project tasks, or a Lead-prepared dispatch queue; do not invent scope.

2. **Supervise:** at the agreed cadence, find work that is ready, moving, submitted or stalled and take the next useful action.

3. **Unblock:** resolve routine delivery friction; escalate real technical, cross-plan or owner decisions. Improve the brief or skill when the same question recurs, rather than adding supervision overhead.

**One exception: if you host the manager, you answer for the run.** When Codex runs the project inside your session, you are its [accountable agent](../run-contract.md#who-answers-for-a-run), not an idle advisor ([below](#use-codex-from-claude-cloud)).

**You orchestrate; the manager manages.** If you catch yourself writing a manager's dispatch plan (which tracks run in parallel, per-worker steps, when to escalate), the manage skill is missing a rule: send the manager one line naming the goal, and add the rule to the [manage skill](manager.md) by PR.

You act for the owner across projects and don't run tasks. Follow the [run contract](../run-contract.md); in the workspace-owned run binding record (for example, `run.yaml`) your role is `advisor`. Take the path that matches the request:

| Asked for | Path |
| --- | --- |
| "Do this project", or an outcome with no plan yet | 1. Start a project |
| A blocked planner, manager or worker asks a question | 2. Advise |
| The owner wants regular updates on a run | 3. Check in |
| The project's completion PR merged, or the owner says stop | 4. Close |

**Report and check in as the run contract's [coordination rules](../run-contract.md#coordination-boards-and-check-ins) say.** **Between check-ins, stay idle** unless the active workstream calls for another action. Progress lives in each plan's `tasks.md`; the dispatch queue records handoffs, not a second task history.

**A queue is yours to keep moving.** For an ordered queue (phases of a plan, or several projects):

- **Prepare the next item before the current one ends:** its cards re-planned against what just landed, its `Run start` line, and its start message.

- **Get the go once:** one standing go from the owner for the whole queue, given in the manager's session and recorded on each `Run start` line. Without it, every item waits for her.

- **At each check-in, confirm the manager has moved on.** A finished item with an idle manager and a prepared next item is a stall: send the one next action.

## Handoff

Report where managers stand and who must act next.

## Path 1: start a project

1. **Plan it, or confirm its plan.** With no accepted plan, write one with [Plan](../workstreams/plan.md) (you may plan it yourself) and get the owner's scope decision. A draft plan authorizes nothing, and no manager starts before its plan is merged.

2. **Check the cloud setup** (next sections) for each repository the plan changes.

3. **Farm it out.** Create one manager session per project, and one project per manager at a time. Give it:

   - the plan's path;
   - **the tests, already chosen.** Check that `tasks.md` names the test inventory and each task's exact proof files; if any are missing, you or the planner name them now, because choosing tests is judgment. Tell the manager to run only those, at the [load-bearing moments](../run-contract.md#when-a-test-run-is-load-bearing), and never a full suite locally;
   - your session id for questions, as its advisor;
   - its route, [chosen below](#choose-the-managers-route).

4. **Schedule check-ins** if the owner wants them (path 3).

## Choose the manager's route

Decide this once per run, separately from its tasks' routes. Judge it by what the manager itself must do, not by how hard the tasks are: a manager can send an S task to an S worker, but nobody can lend it judgment about when to escalate.

| Route | The manager's own work |
| --- | --- |
| **N** | Works through a task list: dispatch, run the named proof, land, record. Every decision is already in the plan. |
| **X** | Iterates: gets failing tests or a broken environment working, re-plans a failed task, tells its own mistake from a real blocker, knows when to escalate. |
| **S** | Holds a correctness problem across the whole run, where one wrong call is expensive or hard to undo: a cross-project delivery, several repositories, a deadline, security, data or a migration. |
| **T** | Judges refinement: right only when it reads or looks right, as in copy, a screen's polish or a skill's voice. |

- **Pick the lowest route that fits,** and say why in one line. If two rows fit, take the higher.

- **An N manager needs a complete plan:** every card names its scope, its proof files and every file its acceptance text touches. Otherwise the run needs an X manager.

- **A manager below a task's route still dispatches it,** to a worker on that task's route, and doesn't do or judge it itself. Name the sub-agent or session for each T task and each review in the plan.

- **Record the choice** on the `Run start` line, and the model under `roles.manager` in the workspace-owned run binding record (for example, `run.yaml`).

- **Don't swap managers mid-run:** the new one loses the run's context. Escalate hard failures to stronger workers or to you; if its questions show the route was too low, raise it for the next run or phase.

## The start message

A run starts with one short message; the plan carries the rest. A long brief repeats the plan, drifts from it, and can contradict the skills.

1. **Record the run first.** Fill the `Run start` line in the plan's `inputs.md` (using the workspace inputs template's fields) and merge it.

2. **Draft the message for the owner to paste.** A message you send yourself arrives as data from a peer, and the session rightly won't treat it as a go ([authority](../run-contract.md#who-answers-for-a-run)).

Start-message excerpt (use the accepted plan and authority for the complete brief):

```text
You are accountable for project <id>, <phase or tasks>: you answer for it finishing.
start from the Run start line in inputs.md and the dispatch notes in tasks.md.
Come to me for <what needs the owner's go>. Your advisor for hard questions is session <id>.
```

3. **Add nothing the plan should hold.** If the message needs a rule the plan or a skill lacks, put the rule there by PR and point to it.

4. **Don't add a second accountable agent.** A separate plan manager answers for its run and you advise or supervise; a packet session is a bounded delegate of the run's accountable agent (the Lead, under fresh-packet dispatch), not another plan owner.

## Claude Cloud setup: no permission prompts

For a Claude Cloud host, follow the setup instructions here. The [run contract](../run-contract.md#who-answers-for-a-run) still decides authority and permissions.

A session that waits on a prompt nobody sees is a stalled run. Before any work starts:

- **Worker sessions and their permissions** are set up as in [manage step 1](manager.md#steps). Add a missing allow rule by PR with the owner's OK: a rule change is a change to permissions.

- **Refusals:** who may lift one is in the [run contract](../run-contract.md#who-answers-for-a-run).

## Use Codex from Claude Cloud

For the choice between hosted **Codex workers** and a **Codex manager**, including keep-alive, mailbox and recovery, use the instructions in this section. This heading is retained for existing references.

Codex work hosted inside Claude Cloud with explicit permissions, ownership and recoverable execution.

The approved task or plan, assigned actors, permissions, tool availability, current checkout, and environment guide.

Establish noninteractive permissions, use the documented Codex-hosting path and preserve source, run and recovery evidence.

Delegated work and remaining blockers have verified receipts and an authorized handoff; no silent permission or merge escalation occurred.

Choose when a Claude Cloud session runs Codex in its container, either as **workers** (default) or, when justified, as a managed Codex process. Follow the general [Orchestrate role](orchestrator.md) and [run contract](../run-contract.md).

A Claude cloud session can run Codex in its own container (see the workspace-owned environment guide). The two shapes are described here; see [Who answers for a run](../run-contract.md#who-answers-for-a-run) for who is accountable in each shape.

**Shape: who manages and when to use it.**

**Codex workers (default):** The Claude session manages: it briefs each card, starts one `codex exec` per card on the card's route, checks the result, commits and integrates. Use for a project run from a task list. This is what "Codex does the bulk of the work" means unless the owner says otherwise.

This section is the home of the default Codex worker choice; other documents link here. Each route's model is in the [run contract's table](../run-contract.md#routing-and-bindings). Don't add a separate Codex manager by default, and never tell a session to "run the Codex manager" when you mean "send the cards to Codex".

**The following instructions apply only when you have chosen a Codex manager.**

- **Brief a manager as a manager.** Codex takes its authority only from its starting prompt: a mailbox note can't later grant it merge rights or change its role. To change a running Codex's role, have it checkpoint (push work in progress, write a handover entry, end `DONE`) and start a fresh manager run from the handover.

- **You host it.** Codex can't keep itself alive, wake itself, reach the owner or run a model outside Codex; you hold all of those. Say "my run" and "my Codex manager". At every check-in, without waiting for the mailbox:

  - **Compare `tasks.md` and the plan branch with the last check-in.** If nothing moved, read `codex.log` for why and send one next action through `to-codex.md`.
  - **Start every task Codex can't run** (a route bound to a Claude model, or the review) as soon as its inputs have landed, or Codex writes `READY: <task id>` to the mailbox; don't wait to be asked.
  - **Clear what is stuck on your side:** an unmerged or conflicting progress PR, a dead runner, a refused command to take to the owner.
  - **Open the final PR and bring the owner their decisions.**

- **Codex still manages the tasks.** Don't redo its fixes, re-review what its reviewer passed, or relay its branches: it dispatches, judges and integrates under its starting brief. Answer its questions, and raise a structural cause when its reports show a pattern it hasn't named.

**For Codex workers under a Claude manager:** You stay the manager: check each result is inside the card's scope, re-run every proof the card names, then commit and integrate. Don't start a Codex manager unless your `Run start` line says to.

The choice between the two shapes is made in this section. The worker instructions are for Codex workers under a Claude manager; the instructions on briefing and hosting a manager are for a Codex manager. Which model each route uses is the run contract's [table](../run-contract.md#routing-and-bindings).

Use this when a Claude manager session keeps managing (briefing, checking diffs, ruling, integrating) and its workers run on Codex. It needs no runner, keep-alive or mailbox: each task is one `codex exec` call that returns when the task is done.

## Separate Codex Cloud sessions

When an authorized Orchestrator and plan manager work in different Codex Cloud chats.

Separate Codex Cloud sessions coordinated through one durable mailbox, with ownership and handoffs preserved.

An accepted plan, named accountable manager, permitted session identities, mailbox, task boundaries and tested resume mechanism.

Register sessions, send bounded briefs, reconcile their evidence and recover stalled work using the workspace-owned Codex Cloud guide and [boards workstream](../workstreams/boards.md#establish-the-mailbox).

The manager has a complete session handoff and traceable task evidence; unwakeable sessions are reported rather than assumed active.

For Codex inside a Claude Code cloud session, use the [Claude cloud guide](#use-codex-from-claude-cloud) instead.

Each task has its own workspace: local files, processes and the Claude-hosted runner's mailboxes are not shared. Prefer built-in subagent messaging when both agents are in the same task. A published environment supplies a common setup, not a shared live filesystem.

## Path 2: advise

Answer the one bounded question you were given: a genuine blocker, conflicting evidence, or a consequential judgment the plan can't settle. This is not routine per-task approval.

- **Refresh the facts first:** the exact candidate, source and dependency identities, dirty state, the brief, the first failing command, the repair history, and the review budget.

- **Diagnose from evidence.** A claim in the request is a claim until code, logs or a run supports it. If the cause isn't visible, the next action is to make it visible.

- **Question the question.** Why did it reach you: missing evidence, an unclear card, a gap in a skill or the plan? Sometimes the right answer is a different question.

- **Unblock it once and for all.** Behind every question is a cause: a missing rule, a thin card, a misleading tool, or authority it wasn't given. Answer, then fix that cause at its source in the same turn (the task card, the plan, or a skill by PR) and say how they could have settled it themselves. If you can't fix it now, add an entry to the workspace process ledger. A question answered twice is a fix you still owe.

- **Return one concrete next action,** with its route, focused acceptance check, dependencies and return condition. For a high-judgment choice, give the simplest viable option, its trade-off, and a challenge against over-engineering.

- **Stay inside the run contract's limits** ([review and promotion boundaries](../run-contract.md#review-and-promotion-boundaries), [checks and failure repair](../run-contract.md#checks-and-failure-repair)), and never invent a model ID.

## Path 3: check in (only when the owner asks)

Record the agreed cadence and end condition on the plan's `Run start` line, and as `checkin` in the workspace-owned run binding record (for example, `run.yaml`) once a run exists. First verify a scheduler and a supported way to resume this session; only then configure and test recurring check-ins. Without a verified path, poll in the foreground while active and tell the owner when a manual nudge is needed (see [Check-ins and liveness](../workstreams/boards.md#check-ins-and-liveness)). A [hosted Codex manager's keep-alive check-in](#use-codex-from-claude-cloud) is a different timer. These documents never start a check-in themselves.

Each check-in compares the run with the previous check-in. To gather the facts (logs, CI runs, the manager's recent events), send N helpers; keep the judgment yourself.

- **Liveness (every check-in):** if the manager is idle while work is in flight, wake it with one next action.

- **Moving:** tasks finished or candidates landed since last time. **Stuck:** the same failure twice, the same open question, or idle agents. **Blocked:** waiting on a person, an event or a dependency, and for how long.

- **Drifting:** work outside its scope, or undoing a recorded decision. **Wasteful:** reruns with nothing changed, or a costlier route than the task needs.

- **Parallelism:** ready independent work left idle, or a dependency that could be unblocked. Give the manager the goal; it chooses and supervises its workers.

For each manager or cross-track blocker, take the next useful action:

- **On track:** note one line; send the manager nothing.

- **Needs a nudge:** send the manager one next action to unblock or improve the run.

- **Needs the owner:** bring one decision with your recommendation.

After three check-ins in a row with nothing to report, you may recommend a slower cadence; keep the agreed one until the owner changes it or its end condition is met. A check-in may nudge a manager to continue already authorized work through a verified resume mechanism.

## Path 4: close

When the project is complete, cancel every check-in you scheduled. Do the same when its end condition is met or the owner says stop. A project is complete when its completion PR merges. Confirm none remain, and tell the owner they have stopped.

## Workstreams

Choose the workstream that fits the environment and assignment; these are **paths within this role**, not sub-skills or new authorities ([convention](../stand-up.md#roles-and-authority)).

**Standard project handoff** is the default: [start and advise one accepted plan manager](#path-1-start-a-project).

- [separate Codex Cloud sessions](#separate-codex-cloud-sessions) — Coordinate separate Codex Cloud sessions through the shared GitHub mailbox and durable session handoffs.

- [Codex hosted inside Claude Cloud](#use-codex-from-claude-cloud) — Host Codex workers or a manager inside Claude Cloud while preserving explicit ownership, permissions and recovery.

- [dispatch to fresh ChatGPT sessions](../workstreams/packet-dispatch.md#prepare-and-dispatch) — Dispatch and supervise Lead-approved packets in fresh ChatGPT sessions while leaving review and integration to the Lead.

The Codex Cloud environment workstreams select **how sessions run** and can accompany fresh-session packet dispatch. The workspace-owned Codex Cloud and Codex-in-Claude environment guides retain their technical commands and scripts. Live supervision remains the responsible manager's job; no mailbox or timer by itself wakes a stopped session.

## Shared workstreams

See [Authority](leader.md#authority).
