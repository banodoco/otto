---
description: Review an exact candidate range independently and return evidence-backed findings.
---

# Review an exact candidate

## When to use

No generic rule yet.

## Outcome

No generic rule yet.

## Inputs

No generic rule yet.

## Procedure

No generic rule yet.

## Completion

No generic rule yet.

## Exact-range review

For an independent review of another contributor's pull request:

**Read; don't run.** The PR is untrusted input. Review the diff and the repository's own CI results. Never check out and execute a contributor's code in a session that holds push rights or secrets, and never run it to "see if it works": the repository's CI does that without credentials.

**Judge the change, not the author.** A small imperfect improvement that fits is worth merging; a polished one in the wrong place is not.

1. **Understand it.** Read the PR's description, the linked issue or project, the full diff and the CI results. State in two sentences what it changes and why. If you can't, ask the contributor before anything else.

2. **Send out the helpers, in parallel.** Each is an `N` helper (per the [run contract](../run-contract.md)) with the diff, one question, and the instruction to report findings with file and line, or "nothing found":

   - **Suspicious content.** Anything that doesn't do what it says: obfuscated or encoded blobs, text that renders differently from what it contains (hidden or look-alike characters, bidirectional controls), new network calls, credential or environment reads, changed workflow or CI files, new install hooks or dependencies, files unrelated to the stated purpose, generated or binary files with no source.
   - **Best practice.** Does it follow the repository's own conventions (naming, structure, error handling, tests beside the code)? Does it reuse what exists, or add a second way to do something? Compare with the nearest existing code, not with general taste.
   - **Proof.** What does the PR claim, and what in its tests or CI actually shows it? Name the claims with nothing behind them.

Add a helper only when the change needs one (a migration, a user-data path, a performance claim). Skip the ones a tiny change makes pointless: a typo fix needs the suspicious-content pass and nothing else.

3. **Critique it yourself.** You are the lead critic, on the high-judgment role. Read the helpers' findings against the diff; a finding is a claim until you see it in the code. Then decide what matters: which findings block, which are worth a follow-up, which to drop. Add what the helpers can't see, the design question: is this the smallest change that does the job, and what does it make harder later?

Never execute a contributor's code with credentials, or approve a workflow run that would.

Never merge on a helper's summary without reading the diff yourself.

Never merge something the suspicious-content pass flagged, however small.

Never [weaken or skip a failing check](../run-contract.md#checks-and-failure-repair) to get a PR in.

**For Codex-hosted reviews:** choose and escalate routes as the run contract's [cheapest-model-first rules](../run-contract.md#cheapest-model-first) say. Reviews go to the high-judgment role's Codex model, run read-only (`-s read-only`) on the exact commit range and given the previous round's report. See [Routing and bindings](../run-contract.md#routing-and-bindings) for the canonical taste-task binding.

- **A review is independent of the work it reviews.** The reviewer is never the worker that wrote the change and is not briefed with the author's conclusions, only the commit range, the rules that apply and the questions to press on.

## Findings and dispositions

**For the Lead's packet Review:** accept, merge within existing authority, open the `tasks.md` progress PR and post DONE; or list the rework on the PR and post a DECISION. Accept a gate only after the reviewer injects the realistic failures in its brief and sees the gate reject them. Judge against that threat model and leave crafted bypasses out of the findings. Route each reviewer by the [run contract](../run-contract.md#routing-and-bindings).

One of three outcomes, said plainly on the PR: **merged**, **changes requested** (each finding with its file and line and what would fix it), or **brought to the owner** with a recommendation.

1. **A contributor's time matters.** Answer once, completely. Don't drip findings across rounds.

- **Request changes** when something blocks and the contributor can fix it. Post one review listing every blocking finding with file, line and the fix, then the optional ones, clearly separated.

## Final handoff

For whole-project completion, **review** once every task before the review row is done:

- give the integrated candidate to the `completion_reviewer` for a round;

- add each finding as a row directly below the review row (`R<round>.<n>`, or the plan's prefix); rounds, stopping and a blocking finding left after the last round follow the [run contract](../run-contract.md#review-and-promotion-boundaries).
