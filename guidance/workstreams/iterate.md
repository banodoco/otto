---
description: Implement or repair one scoped change and return an exact candidate with focused proof.
skill: true
---

# Iterate on one scoped change

## When to use

When executing an assigned code or focused document change under an accepted task or issue.

Read the [shared run contract](../run-contract.md), the assigned brief (an issue, bug report or existing project task), and the working repository's instructions. **An issue or small fix needs no new project pack.** This is the single implementation/debug/focused-test repair loop. Work only within the accepted outcome, paths, dependencies, frozen source identity, route, and authority. Do not create another worker workflow. In a [loop plan](#live-loops) each round's fix is an ordinary run of this loop, with the live scenario that failed as its red test.

## Outcome

A scoped implementation candidate with focused acceptance proof, reproducible source identity and clearly stated residual failures.

## Inputs

The authorized brief, repository and exact base, relevant existing behavior, focused proof and permitted dependencies.

## Procedure

Trace the behavior, make the smallest complete repair, qualify original tests and return source and evidence to the manager.

## Completion

The candidate is linked to exact revisions and focused results, with all remaining uncertainty or downstream failures visible.

## Diagnose

- Confirm the actual repository, ref/SHA, dirty state, current base, dependency identities, and custody before mutation. Preserve user changes; report mismatched or missing source identity to the manager.

- Trace the assigned behavior from setup and inputs through the existing action/state path to its observable result and focused acceptance check. Reuse current code and fix demonstrated causes at their source. Make the smallest complete in-scope change.

## Implement

Each single fix is one [Iterate](iterate.md) card.

- Use the cheapest venue that can prove the stated claim. A higher venue alone does not make proof stronger.

Two different activities share the word "test". Keep them apart.

- **Iterating** is getting one red test to green. It is cheap and disposable. Reproduce the failing test with its exact command, keep the full raw output in your workdir, read the first error before forming a hypothesis, fix the cause, and rerun that test as often as you need. Reruns on a new commit need no permission, no review and no committed record. Stop at the worker threshold in the [run contract](../run-contract.md#cheapest-model-first) and hand the manager the raw output, what you tried and your best guess.

## Prove and hand off

Record each check's proof, repair its failures and carry proof forward exactly as the [run contract](../run-contract.md#checks-and-failure-repair) says.

Return the exact candidate SHA/tree and source identity, changed paths, mapped behavior, focused commands and inner exits, proof carried forward with its unchanged-input basis, first failures and reruns, remaining claims/gaps, and any dependency or scope issue. A candidate is a [feature handoff only](../run-contract.md#review-and-promotion-boundaries).

## Live loops

When an accepted plan's end state is clear but its tasks can only be found by measuring the live implementation round by round.

A plan whose end state holds on two consecutive live rounds, with every round, fix and plan delta recorded.

Run the scenarios live, record the round, ask the strategist, pick the smallest fixes, land each as an Iterate PR into the plan branch, rebuild and rerun.

The plan's end state holds on two consecutive rounds, or the loop stops at a recorded reason and the owner has the open question.

Use when the plan is a [loop plan](../glossary.md): its end state is known, its tasks can't be written up front, and its `tasks.md` ends in one standing loop card. Everything in [whole project](../roles/manager.md#steps) still applies (progress, decisions, dispatch); this adds the round. The [run contract](../run-contract.md) governs routes, proof and review; it is not restated here.

- **Coordinator** (the manager session): keeps the judgment. Reads every round row and picks the fixes. Treats what Codex and the strategist return as evidence to check.

- **Strategist:** the run's high-judgment advisor binding, read-only (`-s read-only`), consulted on strategy each round. Its advice is evidence, not a verdict; it tends to over-engineer, so ask it what to remove first.

3. **Ask the strategist:** give it the row and the previous rows, not your conclusion.

4. **Pick the fixes.** Each is one failing scenario, a cause, and the smallest change at its source.

5. **Fix** each as an ordinary [Iterate](iterate.md) run, a PR into the plan branch, with the failing live scenario as its red test.

Append each round's rows, picks and PRs under the loop card in `tasks.md`; progress PRs follow [whole project](../roles/manager.md#progress-is-always-current).

Stop when the plan's end state holds on two consecutive rounds, or when a round finds nothing new and the remaining refusals are real clashes. Stop and ask the owner when three rounds in a row fix nothing, the disk floor the plan names is reached, or the end state needs a design change bigger than a card.

Each round also writes **plan deltas**: what the live evidence changes in the follow-up plans (a task to drop, add, re-estimate or renumber). They go in `rounds.md`, one list per round, and the manager carries them into those plans' PRs at the end.

- Check free disk before each round and stop below the floor the plan names.
