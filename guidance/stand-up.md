---
description: Set up a workspace, a folder of documents and settings, using Otto's reviewed contract and guidance.
skill: true
---

# Stand up a workspace

- [ ] [Read Otto's reviewed contract, `docs/contract.md`, section 13.](../docs/contract.md#13-amendments-from-the-rs1-review-25-november-2026)

  Otto cannot check that you understood it; the next step puts its rules into your workspace.

Next: [Config](#config).

## Config

- [ ] [Write the workspace settings](../docs/contract.md#3-the-ottotoml-schema) in `otto.toml`.

  The workspace folder now contains `otto.toml` with the required fields shown in the linked format.

Next: [Strategy](#strategy).

## Strategy

- [ ] [Write the strategy in one source document.](../docs/contract.md#1-scope-and-source-of-truth)

  The strategy file exists at its chosen path; no Otto command can judge whether the strategy is sound.

Next: [Record kinds](#record-kinds).

## Record kinds

- [ ] [Declare record kinds](../docs/contract.md#record-kind-declarations-and-readers), the types of items Otto reads, in `otto.toml`.

  Their entries and identifier rules are in `otto.toml`; each declared source folder must exist.

Next: [Pipelines](#pipelines).

## Pipelines

- [ ] [Declare pipelines](../docs/contract.md#5-pipeline-declarations), the ordered links between types of records.

  The declarations are files in the configured pipeline folder; `otto pipeline list` prints their identifiers, or nothing when none are declared.

Next: [Project templates](#project-templates).

## Project templates

- [ ] Choose the [templates](../docs/contract.md#7-project-template-manifests), or document formats, your workspace will use for [projects](glossary.md#records-and-relationships).

  Each choice has a `template.toml` file, supplied by Otto or your workspace, naming its work procedure and any extra documents.

Next: [Roles and authority](#roles-and-authority).

## Roles and authority

- [ ] [Review who is responsible for the work and what they may do.](../docs/contract.md#1-scope-and-source-of-truth)

  The role documents record responsibilities and authority; no Otto command can confirm permission.

- [ ] [Review the skill documents offered as instructions to agents.](../docs/contract.md#skill-documents-build-and-installation)

  The reviewed source files are Markdown, plain text with headings and links; reading them does not install anything.

[This guide](#stand-up-a-workspace) directs requests to existing contributions, procedures, or the [accountable role](glossary.md#roles).

A role defines an ongoing identity and its authority: who acts, what they may do, and who answers for the work.
Each role has one file: [Leader](roles/leader.md#leader), [Orchestrator](roles/orchestrator.md#orchestrator), [Manager](roles/manager.md#manager), or [Worker](roles/worker.md#worker).

A role's own [workstreams](glossary.md#records-and-relationships) are procedures adapted for that role.
Keep them in a folder beside the role file.
They inherit the role's authority and are usually read through its document.

Shared workstreams are procedures that permitted roles can call directly under the active assignment.

The [shared run policy](run-contract.md#shared-run-contract), [glossary](glossary.md#glossary), and workspace's domain map describe rules, terms, and subject areas.
They are reference documents, not another role.
Keep environment guides and executable helpers, the workspace's setup instructions and supporting programs, as separate resources.

The [shared run rules](run-contract.md#shared-run-contract) govern every invocation, each use of a role or procedure during a [run](glossary.md#runs-and-evidence).

**Authority:** Follow the [shared run contract](run-contract.md#shared-run-contract), the workspace's contribution principles, and the instructions in the active repository, a versioned collection of files.
This guide directs work; it grants no permission to do it, combine changes, or move results into their next approved destination.
Never install skills or change a contributor's machine merely to explain the workspace.

Next: [Boards](#boards).

## Boards

- [ ] [Review the boundary for boards](../docs/contract.md#1-scope-and-source-of-truth), where sessions exchange messages.

  The reviewed boundary is in `docs/contract.md`; Otto does not create boards or resume waiting sessions.

Next: [First project](#first-project).

## First project

- [ ] [Choose the template for your first project.](../docs/contract.md#7-project-template-manifests)

  The selected `template.toml` names the work procedure and any documents added to `plan.md`, `inputs.md`, and `tasks.md`.

You need not understand every repository first.
Identify the person's goal, then find the existing issue (a work or problem report), project, and code.

**Work and its procedure.**

- **Investigate:** Trace actual behaviour and earlier work before changing it.
  Search issues and projects.
  Confirm the exact source version, what it depends on, and the evidence for its behaviour.

- **Decide:** Agree the smallest complete result and test of success.
  Reuse the accepted scope, the agreed limits of the work.
  Question important design choices without requiring a second planning process.

- **Build:** Work on the authorised source using [Iterate](workstreams/iterate.md#implement).
  Protect existing work and respect the active run's limits.

Start at the first stage not already supported by evidence.
An investigation can finish without building anything.
A known small fix need not revisit the overall design.

Use the workspace's contributor guide to claim work, propose work, request a start decision, ask questions, submit multiple implementation pull requests (proposed changes), or finish a project.
Claiming work gives ownership, not permission to execute it.

No separate place for project conversations is required.
The completion pull request is a short index of real evidence, not another database.

Next: [Author guidance](#author-guidance).

## Author guidance

- [ ] [Review the required format for role and workstream documents.](../docs/contract.md#skill-documents-build-and-installation)

  The requirements are listed below; the review changes no files, and Otto checks their structure rather than their instructions.

Choose a procedure only for a task already authorised.
Choosing a workstream grants no new role, approval, or permission.
The procedure index, a list of procedures, does not select files for packaging into skill folders.
Only `skill: true` in a document's opening settings block does that.

Write one Markdown file with a useful top heading.
Its frontmatter, the settings block at the top, must contain one plain-text description.
Use a nonempty line of at most 240 characters, ending in punctuation.
Add the optional `skill: true` line when finding this document as a skill on its own is useful.

~~~yaml
---
description: Describe what this does and when to use it.
skill: true
---
~~~

A document's folder determines who owns it, not its generated skill name.
Duplicate skill stems, filenames without `.md`, are an error.
Omit `skill: true` for shared reference guides and workstreams that only make sense within their parent role.

A role contains sections for Responsibility, Authority, Responsibilities, and Handoff.
A workstream contains sections for When to use, Outcome, Inputs, Procedure, and Completion.
Keep the actual steps in Procedure; do not repeat a separate contract with those five fields.
Permission comes from the [owner](glossary.md#roles) and the active run, never from choosing a skill.

Each workstream must define an outcome that can be checked independently.
Keep its full instructions and discovery metadata, the information used to find it, in that workstream's document.
A role's navigation summary is not a second source for those instructions or metadata.

Never replace actual steps or evidence with placeholder summaries.
Give shared run policy and shared workstreams one authoritative source each; do not duplicate their instructions.
Keep a role's responsibilities, defaults, selection rules, and guidance for combining roles and procedures in its role document.
Do not create folders for workstreams that need no variant, or adapted procedure.

Otto checks document structure.
It does not judge whether instructions are correct, evidence is sufficient, or the person acting has authority.

Next: [Build and install skills](#build-and-install-skills).

## Build and install skills

- [ ] [Review how skill packages are built and installed.](../docs/contract.md#skill-documents-build-and-installation)

  The reference is the skill contract in `docs/contract.md`; reading it does not create packages or install links.

- [ ] [Read the reviewed layout for guidance files.](../docs/contract.md#13-amendments-from-the-rs1-review-25-november-2026)

  Section 13 describes how Otto recognises role and workstream documents under `guidance`; reading it changes no files.

Each generated `SKILL.md` links to reference files in the checkout, the local copy of the repository.
Install its package through a symlink, a filesystem link to that package, while the checkout remains available.
Check command and symlink support in each environment where you will use the skill.

The installer never replaces foreign entries, the files or links it does not own.
Packaging a skill grants no extra permission to do work, install anything, spend money, publish, or merge changes.

If a session's list of available skills omits a readable skill on disk, read that skill's `SKILL.md` directly.
Do not remove existing skills or change credentials, such as passwords or access tokens.
Verify each new task independently; a link on another machine does not establish installation here.

Next: [pick the next project and choose its template after finishing the first](#first-project).
