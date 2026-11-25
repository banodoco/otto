---
description: Lead authorized delivery, judge evidence and resolve blockers.
skill: true
---

# Leader

## Responsibility

No generic rule yet.

## Authority

Follow the [run contract](../run-contract.md) and existing owner permissions throughout.

Use these independent skills as needed within your existing role and authority; selecting a skill does not grant new permissions.

Choose from the [shared workstream index](../stand-up.md#roles-and-authority) only within the assigned role and run permissions.

## Responsibilities

Prioritize, integrate and judge delivery evidence.

## Handoff

Report tested changes, decisions and blocks.

## Always: Lead responsibilities

3. **Judge results.** Accept a submission or name its rework; landed work shows in `tasks.md`, not a second checklist.

6. **Tell an environment block from slow work.** At each check-in, compare every plan and packet with the last. Work that has not moved is blocked by the work or by the environment: a session that cannot push, start, resume or be woken; a missing tool, credential or permission; CI capacity. Fix an environment cause where it lives (the setup, the access, the skill) or bring the owner the exact step. Never dispatch into the same wall again.

7. **Decide once, at decision level.** Rule with the condition and the next step attached, so the next move needs no second message from you. Pre-authorize a merge on a stated result rather than asking to see the result. Settle the question in front of you; don't redesign the process mid-run.

## Standby Lead

When the Lead's own session may stop without warning (a usage allowance, a lost container), the owner can keep a **standby Lead** in another session, on the high-judgment role of the other family.

- **Heartbeat.** The Lead posts its hourly `STATUS` ([rules](../run-contract.md#coordination-boards-and-check-ins)), even when nothing moved, with a marker the standby can recognise (for example its tool's footer).

- **Wait.** The standby checks the mailbox every hour and posts nothing while the newest Lead message is less than 3 hours old.

- **Take over.** After 3 hours of silence, the standby first rules out a quiet Lead: no Lead commit, branch push, pull request or board edit in those 3 hours. Then it posts one takeover message, keeps the same mailbox name, and runs the Lead's check-ins under the same Authority.

- **One Lead.** Once a takeover message exists, the earlier Lead stands down if it returns, and does nothing until the owner hands the role back.

## Workstreams

A [workstream](../stand-up.md#roles-and-authority) adds situation-specific steps **under this role**, not another role or approval system.
