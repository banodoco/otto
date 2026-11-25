---
description: Review one pull request and merge it, request changes or bring it to the owner.
skill: true
---

# Review and merge a pull request

## When to use

For someone else's pull request, usually an outside contributor's, a lead critic and a few cheap helpers review it, then merge it, send it back or bring it to the owner.

When considering another contributor's pull request rather than implementing a task or integrating an entire delivery.

## Outcome

One external or delegated pull request reviewed and disposed as merged, changes requested or escalated to the owner.

## Inputs

The PR diff, source and destination, original CI receipts, applicable authority and review criteria.

## Procedure

Read the untrusted diff safely, gather independent findings (see [Exact-range review](review.md#exact-range-review)), request bounded repairs or make an authorized merge decision.

## Completion

The PR receives a complete, actionable disposition with source-linked findings and any required owner decision.

## Candidate identity

**Check how it lands.** If the change conflicts with other open work, say which goes first. Ask the contributor, or merge the base in ([commits only](../run-contract.md#scope-source-identity-and-state)).

## Review

No generic rule yet.

## Integrate and report

**Decide.** See [Findings and dispositions](review.md#findings-and-dispositions) for requests for changes.

- **Merge** when nothing blocks, CI covering the change is green on the PR's current head, and the change is not in an owner-escalation category or subject to [request changes](review.md#findings-and-dispositions). Use the repository's normal merge method and credit the contributor.

- **Bring it to the owner,** with your recommendation, when the change touches security, credentials, user data, a migration, cost, deployment or promotion machinery, workflow files, or licensing; when the suspicious-content pass found anything; or when the right answer is "no" to a substantial contribution.

**Record it.** Say on the PR what was checked and what wasn't run.

See [commits only](../run-contract.md#scope-source-identity-and-state) for the canonical prohibition on rewriting a contributor's branch.

- **One branch per PR:** never push to a branch whose PR is already merged. Open a fresh branch for each PR.
