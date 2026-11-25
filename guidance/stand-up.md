---
description: Stand up a Markdown-first workspace using the reviewed contract and its guidance.
skill: true
---

# Stand up a workspace

No generic rule yet.

- [ ] [Read the reviewed contract (section 13)](../docs/contract.md#13-amendments-from-the-rs1-review-25-november-2026)

## Config

No generic rule yet.

- [ ] [Configure the workspace](../docs/contract.md#3-the-ottotoml-schema)

## Strategy

No generic rule yet.

- [ ] [Set out the strategy document and source of truth](../docs/contract.md#1-scope-and-source-of-truth)

## Record kinds

No generic rule yet.

- [ ] [Declare the record kinds](../docs/contract.md#record-kind-declarations-and-readers)

## Pipelines

No generic rule yet.

- [ ] [Declare the pipelines](../docs/contract.md#5-pipeline-declarations)

## Project templates

No generic rule yet.

- [ ] [Choose the project templates](../docs/contract.md#7-project-template-manifests)

## Roles and authority

- [ ] [Review roles and authority in the workspace contract](../docs/contract.md#1-scope-and-source-of-truth)

- [ ] [Review skill documents](../docs/contract.md#skill-documents-build-and-installation)

- [Stand up a workspace](#stand-up-a-workspace) routes requests to an existing contribution, procedure, or accountable role.

- Roles define a continuing identity and its authority, including who is accountable. Each role is a single file: Leader, Orchestrator, Manager, Worker.

- Role-specific workstreams live in the sibling folder of their role file. They inherit that role's authority and are usually loaded through it.

- Shared workstreams are independently callable procedures available to roles permitted by the active assignment.
- [Shared run policy](run-contract.md), [glossary](glossary.md) and a workspace-owned domain map are referenced sources, not another role.
- Workspace-owned environment guides and executable helpers remain separate supporting resources.

[Shared run rules](run-contract.md) govern every invocation.

**Authority:** Follow the [shared run contract](run-contract.md), the workspace's contribution principles, and the active repository's instructions. This skill routes the work; it does not grant execution, integration or promotion permission. Never install skills or change a contributor's machine merely to orient them.

## Boards

No generic rule yet.

- [ ] [Review the boundary between the workspace and external coordination](../docs/contract.md#1-scope-and-source-of-truth)

## First project

- [ ] [Choose the first project template](../docs/contract.md#7-project-template-manifests)

You need not understand every repository first: identify the person's goal, then find the existing issue, project and code.

**Work: where it goes.**

- **Investigate:** Trace actual behavior and prior work before changing it. Search issues and projects; confirm source revision, dependencies and relevant proof.
- **Decide:** Agree the smallest complete result and test of success. Reuse accepted scope; challenge consequential designs without creating a mandatory second planning ritual.
- **Build:** Work on the authorized source using the Iterate workstream (Implement); protect existing work and respect the current run's constraints.

Start at the first stage **not already established by evidence**; a fact-finding task can end after investigation, and a known small fix needn't revisit architectural planning.

Use the workspace's contributor guide to **claim, propose, request a start decision, ask a question, submit multiple implementation PRs or finish a project**. Claiming is ownership, not authorization. No mandatory project conversation hub is created. The concise completion PR is an index of real evidence, not another database.

## Author guidance

- [ ] [Review the authoring and document contract](../docs/contract.md#skill-documents-build-and-installation)

Choose a procedure for an already-authorized task; selecting a workstream never grants a new role, approval, or permission. The procedure index is not a package allowlist: packaging is decided only by `skill: true` in a document's frontmatter.

Write one Markdown file with a useful first-level heading and one plain-text description in frontmatter: a nonempty single line of at most 240 characters, ending in punctuation. Add the optional line shown below if independently discovering the document as a skill is useful.

~~~yaml
---
description: Describe what this does and when to use it.
skill: true
---
~~~

Directory placement determines ownership, **not** the generated identity. Duplicate skill stems are an error. Omit skill: true for shared reference guides or workstreams that are only meaningful within their parent role.

A role contains sections for Responsibility, Authority, Responsibilities, and Handoff. A workstream contains sections for When to use, Outcome, Inputs, Procedure, and Completion. Keep actual steps in the procedure rather than repeating a separate five-field contract. Authorization comes from the owner and active run, never from choosing a skill.

Each workstream has a defined, independently verifiable outcome. Keep its full execution instructions and authoritative discovery metadata in its own document; a role's navigation summary is not a second source. Never replace actual steps or proof with placeholder summaries. Shared run policy and shared workstreams have one authoritative home; do not duplicate their instructions. Keep role responsibilities, defaults, selection rules and composability guidance in the role document. Do not add folders for workstreams that need no variant. The source checks validate structure, not the correctness of instructions, sufficiency of evidence or authority of the actor.

## Build and install skills

- [ ] [Review the skill build and installation contract](../docs/contract.md#skill-documents-build-and-installation)

- [ ] [Read the reviewed guidance layout](../docs/contract.md#13-amendments-from-the-rs1-review-25-november-2026)

Each generated `SKILL.md` links to its references in this checkout, so the skill directory must be installed **as a symlink** to that package while the checkout remains available. Check command and symlink support in each environment. The installer never replaces foreign entries. Skill packaging does not grant additional execution, installation, spend, publication or merge rights.

If a session's skill catalog does not list a readable filesystem skill, read its `SKILL.md` directly. Do not remove existing skills or change credentials. Verify each new task independently: a link on another machine does not establish installation here.

**Next step:** [First project](#first-project).
