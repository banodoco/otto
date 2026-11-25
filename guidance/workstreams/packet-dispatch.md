---
description: Dispatch one bounded packet per fresh session and return exact-head proof handoffs.
---

# Dispatch and execute bounded packets

## When to use

No generic rule yet.

## Outcome

One bounded packet implemented on draft task pull requests, ready for orchestrator proof and Lead review.

## Inputs

The exact packet, assigned task rows, board and current rulings, target repository and base, accepted proof and permissions.

## Procedure

Receive and verify the assignment, implement code and tests directly on the permitted branch, and submit the draft PR and exact-head proof handoff to the orchestrator.

## Completion

Every assigned task has a traceable disposition, exact candidate source and proof selectors, and a Lead-visible handoff without unauthorized merging.

## Prepare and dispatch

**Lead — prepare the queue:** Prepare bounded packets and the coordination boards, run Lead check-ins, review delivered task PRs and integrate only authorized work using the sections below.

The queue and task records reflect every packet, its evidence and disposition, with review/integration decisions owned by the Lead.

Use when the Lead prepares accepted plan work for an Orchestrator to assign to **a fresh ChatGPT manager session per packet**. The [Lead responsibilities](../roles/leader.md) continue to apply.

1. **Prepare packets.** Start from what exists: bring each plan's `tasks.md` up to date, and ask any earlier manager to push its work, write a handover and stop; its open drafts become packet inputs. Use ready task IDs from **one plan**; ~**three human engineering days** is the outer cap for a brief, not permission to bundle cards (the tighter dispatch rule in this section applies). Give each packet the Route of its hardest card, honestly: it sets the session's mode ([ChatGPT session modes](../run-contract.md#chatgpt-session-modes)). Link, never copy, tasks, dependencies and proof; split oversized tasks first. Order the queue by priority; cap Running plus Review at what you can review. A meter, gate or check brief states which realistic ways to get to green it must catch: skips, xfails and deselection through markers, `-k`, `-m`, config or `PYTEST_ADDOPTS`. Fail closed if a registry, baseline or ceiling approves itself or grows, if a PR changes the gate without approval or runs its own gate code, or if results are missing, truncated or show zero tests. Leave crafted bypasses (shadowing the standard library, patching runner internals, packaging or build hooks, deliberately malformed results) and code the candidate runs inside the job to path protection and human review.

- **One contract per packet, aimed at about 3 hours.** Never bundle cards; split a big card at its seams.

- **Rule before dispatch.** Run a local baseline on the plan branch and write into the packet its exact focused selectors, the ids that already fail, the tests that must pass unchanged, and both **May touch** (files and functions) and **Must not touch**; a packet without both is not Ready. See the [packet workstream](#receive-implement-submit).

- **A sweep carries its count:** every site found and every site changed, in the PR before review. Audit it against a count you take yourself.

**Orchestrator — dispatch the queue:** The live run board, accepted packet briefs, task rows, mailbox, session access, capacity and dispatch authority.

Run startup and resume checks, dispatch one packet per session, track check-ins and surface blocked work for Lead decisions.

Every dispatched packet has an identified session, current state and evidence or an explicit blocker; the Lead retains review and integration.

**One packet, one fresh ChatGPT session.** The session writes; **you** run proof and keep sessions moving; **the Lead** reviews and integrates.

1. Read the board, its packets, their `tasks.md` rows and your board. Confirm each packet's dependencies, repository, PR destination, proof and authority.

2. Do the board's startup checks: the mailbox both ways ([protocol](boards.md#establish-the-mailbox)), how sessions start and resume (a comment or session URL cannot wake one), how many ChatGPT sessions this account's subscription can run at once, and that **you** can clone, build the environment and run one focused test on a network-capable machine (packet sessions never do).

4. Dispatch the first packet alone: its early STATUS proves a packet session can push, open a pull request and comment. Each later packet's early STATUS proves its own repository.

5. Give each Ready packet a **new ChatGPT session** in its Route's mode with the [start message](#receive-implement-submit), and name it in your next STATUS; a packet's ID is its file name.

## Receive implement submit

The packet's exact handoff format is given in the start-message excerpt and submit step below. A cache or speed packet emits its counters (hit, miss, recompute); the work track reads them before trusting a timing and measures the numeric gate on the exact head.

Start-message excerpt (use the accepted plan and authority for the complete brief):

```text
Standing rulings: the same file's Standing rulings section; they bind you.
Board: <issue URL>, run <run id>, format in its first post. You are <mailbox name>;
the Orchestrator is <name>; the Lead is <name>.
[Replacing <prior session>: continue from <branch> at <head> and <last STATUS link>;
apply Lead decisions <comment IDs> not yet done.]
Write this packet's code and tests; do not clone, build or run tests. Post STATUS or BLOCKED as comments on the board,
the first as soon as your first branch is pushed and its draft pull request open.
End with READY-PROOF <repo> <PR> <head> <selectors>, then stop.
Do not merge, tick tasks.md or start another packet.
```

Use when a fresh ChatGPT session receives **one** accepted packet from the [Orchestrator](#prepare-and-dispatch). Follow [Manage](../roles/manager.md) for scoped engineering and proof; the review is the Lead's, so commission none. **You do this packet's engineering yourself**; you do not own the plan, and you take no second packet.

0. **Check your mode** against your packet's Route ([ChatGPT session modes](../run-contract.md#chatgpt-session-modes)); if it differs, say so in your first STATUS.

1. **Receive.** Read your board and the Lead board ([rules](../run-contract.md#coordination-boards-and-check-ins)) for messages to you; do so again on every resume and before finishing. Confirm scope, proof, dependencies, working repository, base and **PR target**, limits and authorization. Startup confirms only what the connector does: read files, push a branch, open a draft PR, comment. The start message is the owner's; the board's Authority section bounds it and its Standing rulings bind you ([run contract](../run-contract.md#who-answers-for-a-run)).

2. **Implement.** Work directly, and link the plan/task IDs.

- **Proof.** Write the code and its tests; the orchestrator runs proof as stated in the start-message excerpt. Before `READY-PROOF`, merge the destination's current head into the packet branch ([integration boundaries](../run-contract.md#review-and-promotion-boundaries)) and name it in STATUS.

- **Scope.** The packet's **May touch** is yours. An adjacent edit of about 20 lines or fewer outside it, and not in **Must not touch**, is allowed without asking: list it in the PR body under "adjacent edits". Anything larger, or anything in Must not touch, is one BLOCKED with the exact list.

- **Tests.** Change test setup and assertions only as the [run contract](../run-contract.md#checks-and-failure-repair) allows.

- **Pins.** Put any pin change in its own commit and name it in STATUS; pins are not yours to approve.

- **Pauses.** Before any pause, push work in progress and post STATUS.

3. **Submit and stop.** When code and tests are pushed on the draft PR, post `READY-PROOF <repo> <PR> <head> <selectors>` as a `STATUS` on your board, `to:` the Orchestrator, with the packet ID, task IDs, adjacent edits and remaining limits; then stop. It is not Done. A fix round is a resume with the orchestrator's findings, never a held BLOCKED; the Orchestrator may instead start a **replacement session for the same packet**.

4. **If blocked**, post `BLOCKED` with the failure, what you tried and the action needed; continue independent work.

**Do not merge task PRs, update `tasks.md` or claim the plan is finished:** those are the Lead's. A row the plan lacks goes in STATUS as a proposal.

## Dependencies and shared writers

- Scopes overlap when they change the same function, class or contract, not merely the same file. Never run overlapping tasks at once; start the later from what the earlier landed.

- Run disjoint tasks at once, even in one file, and land them in an agreed order by merging the plan branch in.

## Liveness and replacement

**Lead — keep work moving. Every hop between sessions costs up to an hour.**

- **Rule conditionally.** When a gate needs one more result, rule it with its condition and its next step attached, for example "merge when this run shows no new ids; if one is harm-class, cut a packet". That way nobody comes back to you.

- **Manager cadence.** Managers check every 20 minutes while a packet is Running or in Review, and hourly when idle.

- **Keep managers up.** A ChatGPT manager runs for a window of about two hours, and a board comment can't wake it. Never stand one down while its plan may still need packets. When one goes quiet with work waiting, give the owner the exact text to paste to resume it.

**Orchestrator — check-in pass:** At the [manager cadence](#liveness-and-replacement) a short pass relays submissions, resumes stalled sessions and starts Ready packets. The STATUS stays hourly. If your own run ends, for example at the end of a ChatGPT agent window, say so in your last STATUS, with the text the owner pastes to resume you. Don't stop while your plan may still need packets.

The branch, not the chat, shows health. No commit or STATUS for 3 hours: resume it. A chat that will not load after one reload, is silent 30 minutes after a resume, or is quiet for 6 hours is broken: replace it once its branch has not moved for 30 minutes, naming the head in the replacement's first message. Never two writers on one branch.

**Proof turnaround.** Answer each `READY-PROOF` within 45 minutes, running independent proofs side by side in background subagents, not one box in turn. You run the proof. Findings go back to the packet's session, or to a fresh session at its head; they never become a fix of yours ([fixes are packet work](#receive-implement-submit)). After a ruling, resume it if quiet for 30 minutes.

3. **Relay, then confirm.** A message is delivered when it shows in the chat or the session's next post answers it. Otherwise post it on the board to that session, resume the session, and mark it "unconfirmed" in STATUS.

4. **Act once where needed:** dispatch Ready packets to fresh sessions; nudge/resume stalled sessions; pass submitted PRs and proof to the Lead as Review; relay rework to the same packet, never duplicated; escalate genuine technical/permission/dependency blockers; an environment block (no way to start, resume or push) is one BLOCKED naming the missing capability. Set Done only on the Lead's DONE. A Review unanswered for 4 hours: send the Lead a REQUEST and tell the owner.

If scheduling or resume is unverified, name the manual nudges.
