---
description: Define the terms used by roles, records, runs and evidence.
---

# Glossary

## Terms

One meaning per word; two meanings, two terms.

**home:** the one place a rule, term or fact is written.

A term belongs in the glossary; use judgment.

## Roles

**owner:** the person whose decisions and own message give authority.

**project owner:** the person or account named once on a plan's `Owner:` line (a GitHub handle, the agent account or a role).

**maintainer:** reviews and merges contributors' pull requests.

**orchestrator:** a standing session dispatching and supervising managers. In fresh-packet dispatch it creates a new ChatGPT manager session per packet, owns liveness and handoffs, and leaves acceptance/integration to the Lead.

**advisor:** the role in the run's binding record answering blocking questions: the orchestrator or else a fresh high-judgment sub-agent.

**manager:** an agent executing an accepted engineering assignment. In the standard whole-project setup it owns a plan run; in the fresh ChatGPT packet workstream it implements **one packet in one session**, submitting PRs/proof without owning the plan.

**Codex manager:** a Codex process managing its own sub-agents, hosted in a Claude session or a Codex Cloud chat; never the default.

**host:** the Claude session running a Codex manager; it answers for the run.

**accountable agent:** the one agent answering for a run finishing.

**worker:** an agent given one task: a sub-agent or Codex call.

**helper:** an `N` worker doing bounded reading, editing or verifying for a lead.

**lead (task lead):** the agent doing an individual task or review itself, delegating helper work; distinct from the overall Lead.

**reviewer:** independent of the author, read-only, on an exact commit range.

## Records and relationships

**project:** work with its own owner, priority and completion proof.

**loop plan:** a plan whose end state is known but whose tasks come from each round's live measurement; its `tasks.md` has a few setup cards and one standing loop card, run by the Iterate workstream (Live loops).

**phase:** a part of a plan that delivers value alone.

**task:** one assignment in `tasks.md`; its **card** holds outcome, route, scope, dependencies and proof.

**workstream:** an outcome-driven procedure with one structural contract. Neither a shared nor a role-specific workstream grants authority beyond the invoking role and run.

**task scope:** what a task may change: paths with their tests, shared surfaces or contracts, or `path:symbol`.

**project scope:** the outcome and work the owner accepted; adding to it needs her decision.

**Owner decisions:** the `inputs.md` section of what the owner must decide.

## Runs and evidence

**task route:** `N`, `X`, `S` or `T` (taste), the capability band a task runs on.

**manager's route:** the band chosen once for the manager.

**run:** one authorized execution of a project, begun on its `Run start` line.

**test run:** one execution of tests.

**candidate:** the exact versions a claim is about.

**round:** one review of the integrated candidate.

**review stop:** a task (`RS<n>`) reviewing a load-bearing part.

**track:** parallel work.

**brief:** what an agent is told at its start.

**observation:** an issue saying what someone saw, in a sentence; not a commitment.

**decision log:** a manager's append-only list of its own rulings.

**decisions ledger:** decisions made while the owner is away, for her to accept or revert.
