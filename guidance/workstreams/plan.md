---
description: Define independently useful project scope and a verifiable end state with executable tasks.
skill: true
---

# Plan a new project

## When to use

Planning a new project: [Planner](plan.md): define the accepted scope and tasks

When defining a new project outcome that cannot reasonably be handled as an existing issue or task.

## Outcome

An agreed, independently useful project scope with a verifiable end state and executable tasks.

## Inputs

The proposed outcome, prior art, current strategy and gaps, design constraints, reviewer input and owner authority.

## Procedure

Investigate existing work, challenge consequential choices, define acceptance evidence and write the project plan and task records.

## Completion

The agreed plan is testable and sufficiently decomposed for another agent to run without reopening accepted decisions.

- A draft can mark what is **Pending**, with the next action.

- A defined project needs real prior-art findings, an explained reuse decision, a traceable owner choice and meaningful completion evidence; a consequential design also needs critique or an explicit unresolved blocker.

- Don't make the agent fabricate evidence, or add heavy ritual to a simple decision.

## Define the project

Terms follow the [glossary](../glossary.md).

You, the **planner** (an administrator: gather evidence, write the task cards, and send consequential judgment to the advisor), produce an agreed, testable end state and tasks another agent can run. An orchestrator may also plan a project itself before farming it out.

1. **Projects are for new, separately useful outcomes** with their own priority, owner and completion proof. Bugs, small fixes and maintenance normally go in issues; existing project tasks use their accepted plan. Write a [loop plan](../glossary.md) only when the end state is clear but the tasks can't be known until a live round measures them; [how it runs](iterate.md#live-loops).

3. **Agree the outcome once.** Record the owner's actual choice with a traceable source; a draft project or PR, or no objection, is not approval. Keep earlier accepted scope; avoid repeated sign-offs.

Trace input → actual implementation → user-visible result, noting useful source revisions, reuse, negative findings and uncertainties. Delegate bounded research when helpful, but no broad audit without a decision it could change.

2. **Pick the smallest complete result.** Justify placement and tradeoffs from evidence, not architectural preference.

3. **Challenge in proportion to consequence.** See the [run contract](../run-contract.md#review-and-promotion-boundaries). Where an independent critique is required and there is no standing advisor, use a fresh high-judgment subagent with no stake in your draft. Record its findings and what you accepted, rejected or left to the owner. A simple bounded project needs only a concise alternatives review and a reason to skip the critique.

4. **Agree the outcome.** Present the real options (as many as the owner needs; ten is a useful technique, not a quota), their user-facing tradeoffs and a testable end state. When the change is complex, or the owner has to picture it to decide, [offer ten vivid statements](#define-the-project).

A long plan hides its biggest decisions. When the work is meaningfully complex (a hard fix, a change to how people work, several decisions the owner must make), ask the owner whether they want about ten statements before they read the plan, and write them if they do. Skip the offer for a simple, bounded project.

- **What they are for:** the owner scans them in a minute, sees the anchor decisions and the edges of the change, and can say "no, not that" before any task is written.

- **Each statement is one sentence about what changes,** phrased boldly enough to disagree with. Contrast works well: "Now, the list defines the plans. After, the plans define the list."

- **Cover the edges, not only the benefits:** what stops being possible, who has to change a habit, what is deliberately left out, and the choice most likely to be controversial.

- **Every statement must be true of the plan as written.** If one overstates it, change the statement or change the plan. Do not write a slogan the tasks don't deliver.

- **Record the owner's reaction** to each contested statement as a decision in `inputs.md`, and revise the plan before seeking greenlight.

Ten is a guide: use fewer when there are fewer real anchors.

Each step below earns its cost only under its condition; skip it otherwise. Each produces a file the next step reads.

| Step | Do it when |
| --- | --- |
| Map current behaviour with parallel N helpers, one read-only area each | the behaviour spans several repositories or areas, or no one planning knows it |
| List each problem with its root cause and where it is fixed | the request starts from symptoms (bugs, confusing UI) rather than a new capability |
| Phase it: a first phase with most of the value, later phases committed, estimates per phase | the estimate exceeds about ten days or value is uneven across tasks |
| Ambiguity pass by N helpers per task group, resolving from code and listing only real owner decisions | other agents will execute the tasks, or any task is X, S or T |
| Record owner decisions in `inputs.md` and enforce them with a test | a later merge could silently undo the decision |

## Task cards

In the workspace tasks template, every task has a **scope** (the paths, and any shared surface or contract, it may change; a path includes its own tests, wherever they live) and:

- **Scope detail:** name the functions or classes too (`path:symbol`) when the task changes only part of a file.

- **A route:** `N`, `X`, `S` or `T`, as the [run contract](../run-contract.md#routing-and-bindings) defines them. Use `S` where correctness needs the deepest reasoning (a protocol never run end to end, security, data safety, migration). Split taste out of larger tasks, so the functional change is `N`, `X` or `S` and the wording or polish is its own small `T` task.

## Dependencies and proof

- **Dependencies,** only where one task needs another's result, or both change the same function, class or contract. Sharing a file is not a dependency: tasks that change different functions in one file run in parallel, with a merge order. The same applies across other active projects. If a shared surface needs one model first, consult the advisor.

- **The critical path:** state it in `tasks.md`, and keep it as short as the work allows. Chain tasks only where the rule above requires it.

- **Before implementation:** its actual base and dependency revisions, exact focused checks and authority.

- **Tests only at load-bearing moments,** per the [run contract's table](../run-contract.md#when-a-test-run-is-load-bearing).

- **A test inventory and focused proofs.** `tasks.md` names the existing tests the plan affects (its test inventory) and, for each task, the exact test files that prove it. The manager's local baseline runs only these.

- **Proofs run on inputs any session can rebuild.** A card's proof uses a generated fixture or a structure-only export (no media), never the owner's own project or media. When a real project surfaces a bug, record its shape: add a minimal reproduction to the fixture builder and file an issue, so the fix is proved and guarded on the fixture; a workaround made in the real project is the owner's to undo, not a card.

- **A card's proof is evidence, not a review.** Tests, a measurement, a render or a read-back; never "an independent review". Reviews live only in the `R` row and any agreed `RS` stop, and a per-card high-judgment review follows the [run contract's per-card rule](../run-contract.md#review-and-promotion-boundaries).

- **A contract card lists what it makes untrue.** A card that changes a contract, a check's trigger or a message names every existing pinned test, fixture and oracle line the change invalidates, and says how each may change. A card whose proof is a `grep` or a list of pinned tests says "re-check against the code at dispatch", because an earlier card may have moved what it names.
