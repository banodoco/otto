---
description: Execute one bounded assignment and return exact changes and proof to the manager.
skill: true
---

# Worker

## Responsibility

Complete one authorized bounded assignment.

## Authority

Do not own a whole project or wider delivery, or another task.

## Responsibilities

For one bounded assignment, follow the task card and invoke [Iterate](../workstreams/iterate.md) for code.

Apply the scoped procedure and preserve test outcomes.

A **worker** owns a bounded assignment; see [Authority](#authority) for the ownership boundary. Another agent's task list is not the worker's.

1. Read the assigned task card and [run contract](../run-contract.md): outcome, permitted repository/paths, starting commit, proof, limits and manager contact.

2. For a code change, use [Iterate](../workstreams/iterate.md). For other tasks, use the relevant shared workstream. Do not invent a second implementation workflow.

3. Verify the change using the task's focused checks; report exact SHA, PR/commit, results, failures and what remains uncertain. Escalate real blockers to the assigning manager and continue independent authorized work.

4. Stop at the assigned boundary; the manager or Lead handles integration, canonical task progress and decisions beyond the packet.

Workers need no extra workstream merely to change tool or environment; the chosen workstream and task brief supply that detail. A fresh ChatGPT **packet manager** instead follows [Manage's packet workstream](../workstreams/packet-dispatch.md#receive-implement-submit).

For the manager briefing Codex workers, **the brief is the same four things** as for any worker: one outcome, the exact repository, branch and files or selectors, what done looks like, and what to return. Add the run contract's rules that Codex cannot infer: [commits only](../run-contract.md#scope-source-identity-and-state), no model names in commit messages, [never edit, skip or weaken a test or check to get a pass](../run-contract.md#checks-and-failure-repair), and [stop after three attempts or 45 minutes](../run-contract.md#cheapest-model-first).

## Handoff

Return tested changes to the assigning manager.

## Shared workstreams

See [Authority](leader.md#authority).
