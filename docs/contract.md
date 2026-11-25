# Otto v0 workspace contract

**Task:** Plan 95 / OT-4 (packet P95-04).
**State:** Design candidate for RS1. This document specifies OT-7 through OT-14 and the Dev migration; it does not claim those implementations or their proof exist.

## 1. Scope and source of truth

Otto reads a workspace's Markdown, constructs an immutable in-memory record and relationship snapshot, checks declared constraints, and renders read-only pipeline queries. Markdown remains authoritative. A pipeline never owns a project's status, owner, tasks, or evidence.

The contract has two consumers: Dev's existing delivery and frozen-issue compositions, and the entirely synthetic Marketing example beside this document. Every option below serves one of those consumers or a named acceptance fixture. No private Marketing data, contacts, analytics, credentials, or run logs belong in these examples.

Source baseline: [astrid-dev at a9da325e274a70a249239d1f95913495797780ee](https://github.com/banodoco/astrid-dev/tree/a9da325e274a70a249239d1f95913495797780ee). Read in full: the eleven Python modules in section 10, `agent/README.md`, `docs/extending.md`, Plan 95's plan/inputs/tasks, and [Plan 96's public plan](https://github.com/banodoco/astrid-dev/blob/a9da325e274a70a249239d1f95913495797780ee/plans/96-astrid-marketing-organisation/plan.md). Supporting source reads: `project_contract.py` and `pack_shape.py`. The [OT-1 receipt](https://github.com/banodoco/astrid-dev/blob/37e9fd2dafc05a8ca05dd57a9a63abf301511040/plans/95-composable-agentic-workspaces/evidence/baseline/summary.md) is the parity oracle, including its stated limits. The initial Otto parent is `ef946b9d291bceb9eab1271a44e15c3d54918234`.

The packet calls Marketing's second pipeline `issue`; Plan 95's plan/tasks and Plan 96 call it `intake`. The [Lead's Step 1 decision](https://github.com/banodoco/astrid-dev/issues/1886#issuecomment-7174437754) confirms `intake` and identifies the packet wording as a slip. It also accepts preserving Dev cardinality without new global obligations, leaving `.otto/runs` with Dev, and separating stable IDs from locator extraction. Dev's separate `issue` pipeline keeps its name. There is no alias or third Marketing pipeline.

**Non-goals:** a scheduler, execution, transitions, a state machine, approval or publication authority, a graph database, a visual builder, a general expression/query language, template inheritance, remote adapter loading, or an extension sandbox. Otto owns this small declarative layer; Plan 72's earlier exclusion of a generic pipeline language is not reopened. Workspace Python is as trusted as its repository. Reading declarations does not install packages, fetch live issues, call a provider, or modify records.

## 2. Files, roots and schema conventions

The root is the directory containing the selected `otto.toml`. CLI commands use the current directory, with an explicit `--root DIRECTORY` override; no upward search or fallback to an unrelated checkout. A root must be an existing directory. `otto list` alone retains OT-3's no-config behavior: empty stdout, `no otto.toml found` on stderr, exit 0. Other workspace commands require the file.

Declarations use UTF-8 TOML and schema `version = 1`. Unknown keys, wrong types, missing required keys, duplicate named entries, and unsupported versions are errors. Tables are closed except the explicitly keyed `paths`, `ids` and `by_role` maps. Array order is meaningful only where this document says it is. Identifiers for kinds, relations, pipeline/stage IDs and template names are lowercase kebab-case; record IDs have their own policy.

All source paths are slash-separated and relative to their declared root. Reject absolute paths (including drive/UNC forms), backslashes, control characters, `..` components, and resolved escapes. `"."` is permitted only as an input root, for Marketing's `strategy.md`. Input aliases wholly inside the root may retain Dev's existing behavior; dangling or escaped symlinks fail. Generated output and view targets retain the stricter no-symlink-component rule of their existing engines. No environment-variable, shell, or home-directory expansion occurs.

Discovery is shallow for declarations: `<pipelines>/*.toml` and `<templates>/*/template.toml`. A nonexistent optional declaration directory means an empty inventory; a configured existing non-directory, dangling symlink, escape, or unreadable inventory is an error. Template discovery also detects and rejects a `template.toml` below the allowed one-level layout, instead of silently ignoring it. Declared record roots must exist as directories; empty directories are valid. Source patterns are relative glob patterns, not commands. Zero matching records is allowed; malformed matching sources are not silently dropped by generic readers. A workspace with no record kinds, relations, pipelines, views or opted-in skills is valid.

The examples under `tests/fixtures/dev/` and `tests/fixtures/marketing/` are **TOML design specimens**, not complete runnable workspaces in OT-4. OT-14 and OT-19/20 provide their referenced Markdown, adapters, template documents and generated outputs. The `examples/` files are specimens of package manifests, outside workspace template discovery. All supplied TOML must parse; parsing is not a claim that a workspace passes `otto check`.

## 3. The otto.toml schema

### Top-level keys

| Key | Type and requirement | Meaning and consumer |
| --- | --- | --- |
| `version` | Required integer, exactly `1`; a boolean is not an integer here | Declaration schema, distinct from the package version |
| `otto` | Optional table with `commit` and optional `tag` | Consumer pin metadata; Dev and Marketing pin a real tag and its commit at OT-23 |
| `workspace` | Required table with `name` and `skill_namespace` | Human workspace name and generated skill identity |
| `paths` | Optional string map | Reserved paths below, plus roots named by a record kind |
| `ids` | Required once any kind is declared; one table per kind | Stable identity validation and path-component extraction |
| `record_kinds` | Array of tables, default `[]` | Known kinds and their authored sources |
| `relation_kinds` | Array of tables, default `[]` | Directed endpoint, role and degree rules |
| `adapters` | Optional table | One trusted local module and optional record-loader export |
| `checks` | Optional table with `register` | Export returning additional check registrations |
| `views` | Optional table with `register`, `marker_prefix`, `hint` | Export returning views/preflight errors; presentation parameters |

`otto.commit` is exactly 40 lowercase hex characters. `tag`, if present, is a nonempty tag string and requires `commit`. Pin metadata records identity; it does not fetch, install, or prove the tag's referent. The orchestrator verifies tag-to-commit equality against the requirement pin at OT-23. The example commit is the real starting skeleton, not a claim that it implements this contract. No invented release tag is supplied.

`workspace.name` is a nonempty single-line string. `skill_namespace` matches `[a-z0-9]+(?:-[a-z0-9]+)*-` and includes the trailing hyphen. Complete generated package names retain the 64-character limit. Dev uses `astrid-dev-`; the synthetic consumer uses `demo-marketing-`. Namespace and source root map to OT-6's `SkillConfig`. Marker, lock and staging names are derived from that configuration, not individually configurable TOML features.

Reserved `paths` keys are:

| Key | Default if omitted | Purpose |
| --- | --- | --- |
| `agent` | `agent` | Markdown skill source root |
| `skills_output` | `.generated/skills` | Generated package root, passed to `SkillConfig.output` |
| `pipelines` | `pipelines` | Pipeline declarations |
| `templates` | `templates` | Workspace additions to package template names |
| `pack_templates` | Otto's package `templates/project/` resources | Common `plan.md`, `inputs.md`, `tasks.md` shapes |

Every other path key must be referenced by at least one `record_kinds.root`; this permits `projects`, `vision`, `gaps`, `releases`, `strategy`, `campaigns`, `issues` and `ideas` without accepting arbitrary unused misspellings. A record root key must be explicitly present. Empty roots are valid. Explicit `pack_templates` must exist and supply all three common files when a pack is checked; a typo does not fall back to package defaults. Source and generated-output roots must not overlap. Defaults create no directories on read.

### Identity policies and bidirectional resolution

Each `[ids.<kind>]` contains `policy` and `source`; `pattern` is required only for `policy = "regex"`. `source` is `parent`, `stem` or `adapter`. For generic readers, parent is the immediate parent directory name, and stem is the filename without its final suffix. An adapter supplies the ID directly and is validated against the policy's **identity** pattern, not a synthesized path.

| Policy | Component-to-ID rule | ID validation and consumer |
| --- | --- | --- |
| `NN-slug` | Full match `\d{2,}-[a-z0-9-]+`; keep the text before the first hyphen | `\d{2,}`, as a string; Dev projects |
| `XX-NNN` | Full match `([A-Z]{1,3}-\d{3})(?:-[a-z0-9-]+)?`; keep capture 1 | `[A-Z]{1,3}-\d{3}`; Dev gaps |
| `slug` | Component is already the ID | `[a-z0-9]+(?:-[a-z0-9]+)*`; all synthetic Marketing kinds |
| `regex` | Component is already the ID; `pattern` is a full-match validator | Dev's qualified goals and decimal release/issue IDs |

The Dev presets intentionally retain the existing Python regular-expression semantics. Do not cast numeric IDs to integers: `"01"` and `"1"` differ, and project `"100"` is valid. `NN-slug` describes a locator component, not a project identity that changes with its title.

The resolver indexes the discovered `(kind, id)` to its canonical `SourceLocation`, and paths/anchors back to the identities declared there. It does not invent a filename from an ID or rename a folder. An ID resolves to exactly one canonical source; two files claiming the same identity fail. A source can hold several records (goals in one strategy page, frozen issues in one release). Reverse resolution then needs the anchor/record location, or returns the ordered identities at the path; it must not arbitrarily pick one. Renaming a project folder without changing its numeric prefix keeps its identity. An adapter consolidates repeated occurrences of one frozen issue before emitting its one record; each relationship retains the actual row that declared it.

Every identity is also nonempty, trimmed, without whitespace or control characters. Colon and slash remain legal when the declared policy permits them; qualified Dev goal IDs require both. The printable reference is `kind:id`, splitting on its first colon only.

### Record-kind declarations and readers

Each `[[record_kinds]]` has:

| Key | Value |
| --- | --- |
| `name` | Unique kind ID |
| `root` | A key in `paths` |
| `files` | Nonempty array of relative glob strings, deduplicated before reading |
| `reader` | `headers`, `frontmatter`, or `adapter` |
| `pack` | Optional boolean, default false; true gives the record a common project pack at its source file's parent |

Every kind has exactly one ID policy, and every ID policy has a kind. Generic readers use `parent` or `stem` identity sources; adapter readers use `adapter`. A `pack` record's source is `plan.md` and its parent is its pack root. Both consumers have one pack kind, `project`; record kinds need not all be packs.

`headers` requires the first nonblank live line to be a nonempty H1 title, and reads optional single-line `**Status:**` metadata before the first real H2. `frontmatter` uses the existing narrow one-line frontmatter reader and an optional `status` string; the body starts with a title. Write `status: queued`, not YAML collections or quoted values requiring a full YAML decoder. Both expose ordinary fields to local checks, preserve source offsets, and reject duplicate machine-readable status fields. Neither assumes that all records have a status. `**Template:**` selection uses the separate rules in section 7 for either reader.

Generic authored relations have one optional real H2 `Relationships` section, containing only the simple table below (zero rows is allowed). Ignore fenced/body examples when finding the section. A second live section, wrong/duplicate header, wrong cell count, blank cell, or non-table prose in it is an error. Table cells do not support embedded pipes. This is the single generic relationship authoring form; Dev keeps its existing forms through its adapter.

```markdown
## Relationships

| Relation | Target | Role |
| --- | --- | --- |
| serves | goal:clear-example | primary |
```

The source is the enclosing record; the target must be a typed reference to an existing record. Relations declared in an adapter may be authored in another record's file: frozen issue membership is the concrete example. Generic Markdown/frontmatter/heading/table helpers remain separately importable for bespoke readers; no parser expressions are added to TOML.

### Relation-kind declarations

Each `[[relation_kinds]]` contains `name`, nonempty arrays `sources` and `targets` of declared kind IDs, nonempty `roles`, and optional `per_source`, `per_target` and `by_role`. Lists contain unique values. The allowed pairs are the Cartesian product of sources and targets; a workspace needing a different pair set declares another relation kind.

All cardinalities use exactly four strings:

| Value | Minimum | Maximum |
| --- | ---: | ---: |
| `exactly-one` | 1 | 1 |
| `at-most-one` | 0 | 1 |
| `one-or-more` | 1 | unbounded |
| `any` | 0 | unbounded |

Omitted degree rules mean `any`. `by_role.<role>` has optional `per_source` and `per_target` with the same vocabulary and must name an allowed role. Unlisted allowed roles have degree `any`. Global rules count distinct edges over **all** records of each endpoint kind, including zero-degree records. Per-source counts outgoing targets; per-target counts incoming sources. Role-specific rules count only that role; total and role-specific bounds both apply. Reject a declaration whose total and role-specific ranges have no possible common count.

Record identity is `(kind, id)`. Edge identity is `(source, relation, target)`, deliberately excluding role: two rows differing only by primary/supporting are contradictory, not two valid edges. Duplicate records, duplicate edges, unknown endpoints, wrong endpoint kinds, invalid roles, and invalid provenance fail before conformance. The index remains immutable and sorts edges by `source.kind, source.id, relation, target.kind, target.id, role, source_path`, with source line as the final tie-breaker. IDs sort as text, preserving Plan 72 order.

The vocabulary has no special universal meaning for `primary` or `supporting`. Their meaning is the declared role plus its bounds. Dev's `included` and `frozen` roles remain valid, separate roles.

## 4. Trusted adapter and registration boundary

`[adapters]` has required `module` (one root-relative `.py` file) and optional `records` (an export name). The module is loaded once from that exact contained path. No package search, remote import target, expression, callable argument string or entry-point discovery is encoded in TOML. The module and its imports execute as trusted workspace code; containment is a source-identity rule, not a sandbox.

The records export is required if any kind has `reader = "adapter"`. It is called once with the loaded workspace context and returns an in-memory `RecordBatch(records, relationships)` covering those kinds. It may call existing workspace readers. Generic readers contribute their own batches, and Otto combines all batches before checking endpoint existence. Adapter code must not return records assigned to a generic reader, introduce undeclared kinds, silently suppress invalid authored records, or add implicit edges. Reading remains read-only by contract; this is not enforced isolation of arbitrary Python.

The public data boundary is:

| Value | Required information |
| --- | --- |
| Workspace context | Resolved root; validated immutable configuration; declaration source map; sorted source paths per kind |
| `Record` | `ref: RecordRef`, canonical `source: SourceLocation`, optional `title` and `status`, ordinary field values and their source locations |
| `SourceLocation` | Root-relative `path` and positive 1-based `line`; optional anchor for embedded records |
| `RecordBatch` | Ordered records and relationships; no persistent registry |
| `Relationship` | Existing `source, kind, target, role, source_path` plus positive `source_line` for authored edges |

Generic readers always supply a title; an adapter may omit a title absent from the canonical source, as with Dev's frozen issue rows. Record locations must belong to the kind's discovered source files, and relation provenance to a discovered source file of some kind. Lines must be within that file's actual line range.

Low-level compatibility constructors used by Plan 72's in-memory unit fixtures may leave line metadata absent. A loaded workspace may not: missing/invalid adapter locations produce a registration error at the `adapters.records` declaration, never fabricated `:1` evidence. A missing-edge diagnostic uses the source/target record's declaration line because no edge line exists.

`checks.register` and `views.register` are bare export names in this same module. A missing module/export, non-callable export, exception during loading, or wrong return shape fails closed at its declaration. Factories receive the workspace context:

- The check factory returns an ordered tuple of the existing `Check(id, trigger, description, run)` values. `run(Context) -> list[str]` keeps its current API, including `root, base, event, body_file`. Closures can retain the validated workspace snapshot.
- The view factory returns `(tuple[View, ...], list[str])`, matching Dev's existing composition/preflight shape. All preflight errors must be reported before any output write.

Otto's fixed generic check order is `markdown-links`, `link-anchors`, `pack-shape`, `relationship-validity`, `pipeline-conformance`, `skill-packages-current`, `generated-views`, followed by local registrations in their declared factory order. Each check runs only with its necessary context; `pack-shape` always validates explicit template opt-ins, and uses `base` to identify new common packs/downgrades. Empty inventories pass. No registration can replace or disable a generic check. Duplicate IDs, including collisions with generic IDs, fail; Dev's additional checks therefore have `dev-` IDs.

`otto list` reports the assembled IDs, triggers and descriptions. `otto check` keeps the injectable runner's `always`/`pr` semantics and `ERROR <check-id>: <message>` rendering. A PR-context check needs `--base` and exactly one of `--event` or `--body-file` together. Core conformance is `always`. A missing registration never means an empty successful check.

Dev's existing `astrid_dev.py` wrapper retains its own exact 23-entry registry and legacy dispatch/output. Its domain checks call Otto's mechanisms as needed; the new Otto CLI need not masquerade as that wrapper. The adapter's `dev-record-contracts` check invokes the retained Dev domain rules, and `dev-project-addresses` owns the enabler/ordinary-project exception described in section 8. Registration data does not move those policies into Otto.

The `View` contract retains name, source patterns, target, render callable and optional string region. A region is a string or absent, never boolean `true`. `views.marker_prefix` is optional; absent passes `None` for the plain generated marker. Dev passes its exact existing prefix. `views.hint` is optional, default `"regenerate the view"`. Dev keeps its own legacy diagnostic presentation where byte parity requires it. Adapter-local index preflight, shared-block discovery and root allow/deny rules stay Python, not new TOML features.

## 5. Pipeline declarations

One `<paths.pipelines>/<id>.toml` contains `version`, `id`, `stages` and `links`. The declared ID must match the filename stem and be unique in the workspace. A chain has at least two stages and exactly one link connecting each adjacent pair. Stage IDs are unique; a kind may occur at more than one stage. This is an ordered chain, not a branching program. Multiple pipelines can refer to the same records and edges.

### Stage and link fields

Each `[[stages]]` has `id`, a nonempty unique `kinds` array, optional `optional` (false by default), and optional nonempty unique `statuses` array. Kinds must be declared. Statuses are exact strings, not a lifecycle or transition table. An omitted status list imposes no status constraint.

Each `[[links]]` has `relation`, `from` and `to` naming adjacent stage IDs, optional `per_source`/`per_target`, and optional `by_role` with the same structure as relation-kind rules. `from` is the **authored relation source**, even when the display chain goes in the opposite direction. For Dev the display order is goal, gap, project, release, while the arrows are gap -> goal, project -> gap and release -> project.

The stage kind sets must be subsets of the relation's respective allowed endpoints. A link's role keys must be allowed by its relation. Repeated links for the same adjacent pair, missing pairs, nonadjacent links, unknown stages/relations, and an empty chain fail. Pipeline constraints add to global relation constraints; they never override or relax global rules. Reject an impossible intersection of bounds.

### Membership, degree and optional stages

The population of a stage is every loaded record of its allowed kinds. There is no membership flag, query expression, status-based exclusion, copied owner, or second task list. Thus a Marketing project with no `serves` edge still belongs to the project stage and can fail the required goal rule. Status restrictions are validations, not filters that make bad records disappear.

Each link examines every edge of its named relation. An edge that does not match the declared source/target stage kinds is a pipeline endpoint violation, even if the more general relation declaration permits it. Each endpoint's degree is counted over its stage population, including records with zero links. A different semantic use needs a different relation kind; v0 has no subgraph selector. A campaign may later track issues with another declared relation, without changing Otto.

The five constraints have these precise meanings:

1. **Cardinality at both ends.** Per-source and per-target bounds, for totals and declared roles, apply independently to the distinct edge set.
2. **Required and optional stages.** A required stage keeps the configured lower bounds on links that count its records. An optional stage lowers those **pipeline** lower bounds to zero. It changes neither upper bounds nor global relation rules. This is a structural absence rule, not permission to omit a declaration or to ignore malformed records.
3. **Primary/supporting roles.** Allowed roles come from the relation, and `by_role` constrains their counts at either end. A second primary can fail even when the total number of links is allowed.
4. **Allowed kinds.** Relation endpoints and stage-kind subsets are both checked; no silent dropping or coercion of wrong-kind edges.
5. **Allowed statuses.** Every stage record must have one of the listed statuses when a list is present. Missing status fails at the record declaration; a wrong value fails at its authored status field. No list means no new restriction, as needed for Dev.

For a link from A to B, making **B** optional relaxes `per_source` and its per-source role lower bounds (A counts B neighbors). Making **A** optional relaxes `per_target` and its per-target role lower bounds (B counts A neighbors). A present optional campaign can still be required to name a project; an ordinary project need not have a campaign.

An optional stage is incompatible with a facing `exactly-one` bound: reject the declaration instead of silently changing it to `at-most-one`. This applies to the corresponding total and role bounds. A global positive lower bound facing an optional stage is also a contradiction because a pipeline cannot relax the global rule. A facing pipeline `one-or-more` becomes zero-or-more when optional and keeps its lower bound when required.

**There is no hidden lower bound.** `optional = false` plus `any` does not make every project belong to a release or require every goal to have a gap. Required stages must be present in a complete traversal result; graph validity still uses the explicitly declared degree bounds. When a missing neighbor violates a positive lower bound, report the required-stage absence; when an upper bound is exceeded, report cardinality. Both are the same counted data, not two inconsistent validators.

The Dev adapter validates all non-enabler primary-address rules separately. Its delivery pipeline leaves `addresses` degree unrestricted so it does not invent a predicate language or reject valid enablers. A delivery path still needs actual goal/gap/project/release edges before the compatibility wrapper prints it.

### Deterministic read-only queries

`otto pipeline list` prints one pipeline ID per line, sorted lexicographically. An empty inventory prints nothing and exits 0.

`otto pipeline show <pipeline-id> <record-id>` accepts a typed `kind:id`, or an unqualified ID only when unique across the pipeline's kinds. Unknown pipeline is a declaration/usage error, exit 1. Unknown record prints `Unknown record <record-id>` and exits 0; an ambiguous unqualified ID names the candidates and exits 1. Dev's wrapper continues to print nothing and exit 0 for an unknown goal or issue.

Traversal follows declared stage order in either direction from the queried record, respecting each authored relation direction. It emits each distinct complete path containing that record once, ordered lexicographically by its stage-slot references and edge role/kind tuples. A missing optional end stage is rendered `<stage-id>=-`. Missing required slots produce no complete row. Optional interior stages do not invent bypass edges: a path cannot jump a missing middle record. Partial adjacency can still be inspected by the index's incoming/outgoing API.

The generic row format is `<stage-id>=<kind:id> -> <stage-id>=<kind:id>`, one slot per stage; noninitial present slots append `(<relation>, <role>)` for their joining edge, regardless of authored direction. Optional empty slots append no edge text. Example: `goal=goal:clear-example -> project=project:launch-note (serves, primary) -> campaign=-`. Records or edges reached through more than one path are not duplicated in storage.

The traversal tracks `(stage position, RecordRef)` on the current path and never recurses into an already visited state; it deduplicates final paths, not globally visited records. This preserves converging paths and terminates even when record kinds repeat and authored relationships form a cycle. Finite stage count also bounds depth. It never modifies graph, files or status. Removing a pipeline deletes only that declaration's conformance/traversal, not records, edges, other pipelines, or global relation checks.

## 6. Source locations and diagnostic ownership

TOML syntax/values are parsed by `tomllib`. The loader must retain a source map keyed by full table/key path **and array-table occurrence**, so repeated `[[links]]` do not all point at the first link. Semantic errors name the offending key line; a missing key names its containing table's header line. Syntax errors use the parser's actual line. Do not search for a value's first text occurrence or attach line 1 to every error.

Generic record readers retain the first H1/identity location, status/template field locations, and exact relationship table row lines. Dev adapters obtain offsets from their canonical source: embedded goal heading, gap metadata line, project header link, release membership bullet, frozen issue row. Missing required edges point to their record declaration; excess edges point to the first excess edge in authored source order and include the relevant reference/count in the message.

New checker diagnostics have `<relative-path>:<line>: <message>`, within the existing runner's check prefix. Sort diagnostics by path, line, then message within each check; check order remains registration order. Invalid configuration stops dependent loaders; invalid graph stops pipeline traversal. Independent domain checks may still report their own errors. Missing-edge diagnostics must not be emitted from a partially loaded graph. When zero total neighbors violates a required-stage minimum, emit that absence once rather than cascading missing-role errors for the same endpoint/link. A missing root-level TOML key may correctly point to the document's first line; this is a scope location, not an invented record location.

Plan 72's structural message text remains unchanged, with location added separately for the Otto CLI. In particular:

| Condition | Preserved message body |
| --- | --- |
| Duplicate record | `duplicate record identity` |
| Unknown record kind | `unknown record kind: '<kind>'` |
| Unknown edge endpoint | `<path>: <relation> names unknown <kind:id>` |
| Wrong endpoint pair | `<relation> requires <source-kind> -> <target-kind>, got <actual-source> -> <actual-target>` |
| Invalid role | `<relation>: invalid role '<role>'` |
| Duplicate/conflicting edge | `<path>: duplicate or contradictory <relation> <source> -> <target>` |
| Primary count | `<ref>: expected one primary <relation> relationship, found <n>` |
| Enabler with addresses | `<path>: enabler <project-ref> cannot declare addresses` |

A legacy body that already contains a path keeps that body; the location wrapper does not rewrite its wording. Dev's legacy CLI retains its old formatting and byte output. New location-aware diagnostics are an Otto entry-point feature, not permission to alter the Dev golden fixture.

## 7. Project template manifests

`**Template:** <name>` is one optional, unquoted single-line field in the project document's live header, before its first real H2. Absent means `standard`. A duplicate, empty, body-only, unknown, or fence-only header selector fails. A selector inside a fenced header example is not a live opt-in and must be reported rather than silently downgrading to standard. Examples in later body sections do not select a template.

Otto ships `templates/standard/template.toml` and `templates/loop/template.toml`. A workspace adds `<paths.templates>/<name>/template.toml`. Name must equal its immediate parent directory; no deeper template nesting, inheritance, includes, variable interpolation, parent templates or override precedence. Duplicate names across package/workspace inventories fail. Existing built-in names are not overridden; the workspace's `pack_templates` customizes the common pack once.

Every manifest contains `version`, `name`, `workstream` and optional `documents` (default `[]`):

| Key | Contract |
| --- | --- |
| `workstream` | Root-relative Markdown path with optional `#anchor`; relative to the package root for a package manifest, workspace root for a workspace manifest |
| `documents` | Array of additive document requirements |
| `documents[].path` | Unique pack-relative file path; cannot collide with `plan.md`, `inputs.md` or `tasks.md` |
| `documents[].source` | File path relative to the manifest directory, used as the new-document example; containment required |
| `documents[].headings` | Nonempty array of unique required H2 headings, in order; extra headings are allowed |
| `documents[].task_reference_field` | Optional bold header field whose value names a real standing task in this pack's `tasks.md` |

The referenced workstream and optional anchor must exist when the manifest is loaded; its selection never authorizes execution. The source document must exist and satisfy its declared heading shape. There is no mandatory content assertion about baseline results: a draft may say its baseline is pending.

Common pack shape comes from `plan.md` and `inputs.md` H2 headings and the first `tasks.md` table header in the configured common templates, as in Plan 48. A manifest is **one additive level** on that common pack. The standard manifest has no additional documents. The loop manifest adds `rounds.md` with `Baseline`, `Method`, `Stop rule`, `Rounds` and `task_reference_field = "Standing task"`. The field is authored in `rounds.md` as, for example, `**Standing task:** LOOP-1`. The value must be an actual unique task ID in this pack, not a generic word like “loop”.

The generic task reference reader takes the first token of the first cell of a live tasks-table data row, allowing an enclosing code or bold span; IDs match `[A-Za-z][A-Za-z0-9]*(?:[.-][A-Za-z0-9]+)*`. It ignores fenced examples and header/separator rows. An adapter can retain a stricter existing task parser, but cannot satisfy a reference with a nonexistent row. The loop reference accommodates Dev's actual `SL-4` (Plan 77) and `ER-L` (Plan 94) without renaming their tasks or putting project-specific IDs in the common manifest.

The `research` example adds `findings.md` and a local research workstream, without a new Otto feature. Its headings serve the third-template acceptance fixture. Template additions do not introduce record kinds or duplicate project status/tasks.

### Existing packs and downgrade detection

For Dev, common-pack shape checks remain on **new packs relative to the supplied Git base**, retaining Plan 48's rename-aware gate. Every explicit `Template` opt-in is checked against the selected manifest regardless of pack age. Existing packs with no selector remain standard and are not retroactively rejected by newly added common headings. A new fixture workspace is checked with a base/new-pack set supplied by its harness; no private persistent adoption ledger is introduced.

With a base supplied, compare the same stable project identity at base and head. Removing an explicit old nonstandard selector reports `explicit Template field removed from <ref>; write **Template:** standard to select standard deliberately`. Renames do not evade this comparison. An explicit change to another known template, including standard, selects and fully validates that template and its common pack; it does not delete former extra documents. There is no migration approval language or hidden adoption ledger in Otto. The ordinary workspace review can assess the explicit authored change.

Without a base, a snapshot cannot prove that a selector was deleted. It validates current explicit selections and reports no historical claim. PR checks must supply the base to prove downgrade detection; unavailable base fails the PR-context check. This is why a hand-edited historical pack is not silently certified as an unchanged standard pack.

OT-20 opts in only the named real loop plans. It may add missing headings/reference fields that link existing evidence; it must not invent rounds, measurements, completed baselines or task IDs. Plan 89 requires its own release Lead's go; Plans 87/88 and all other standard packs do not opt in automatically.

## 8. Exact Dev mapping and parity boundary

The following accounts for every Plan 72 kind/relation literal and domain cardinality rule; none is left implicit.

| Existing literal/rule | Contract home |
| --- | --- |
| `RECORD_KINDS = {goal, gap, project, release, issue}` | Exactly five `record_kinds` entries in the Dev example |
| `measures = (gap, goal, {primary, supporting})` | Dev `relation_kinds.measures` endpoints/roles |
| `addresses = (project, gap, {primary, supporting})` | Dev `relation_kinds.addresses` endpoints/roles |
| `includes = (release, project, {included})` | Dev `relation_kinds.includes` |
| `listed-in = (issue, release, {frozen})` | Dev `relation_kinds.listed-in` |
| Exactly one primary `measures` per gap | `measures.by_role.primary.per_source = "exactly-one"` globally; supporting and incoming degree remain any |
| Exactly one primary `addresses` per non-enabler project | Named adapter check `dev-project-addresses`: ordinary-project primary count, using canonical `plan_gap_links`; the global declaration stays any to permit enablers |
| Enablers declare no `addresses` | The same `dev-project-addresses` rule rejects every addresses edge from an explicitly validated enabler |
| Enabler set contains only existing projects | The same adapter rule, retaining `foundational enabler must be an existing project` |
| Primary/supporting cannot duplicate an edge | Otto's role-independent edge identity |
| No release-membership lower bound in this graph | `includes` and `listed-in` total/role bounds are any; pipeline declarations add no minimum |

`dev-project-addresses` uses the explicit `**Vision role:** Foundational enabler` or `Communication enabler` grammar. Lack of edges is never evidence of an enabler. The canonical parser still requires exactly one Vision gaps/role declaration, a primary first linked gap, no duplicate/contradictory roles, and existing canonical target hrefs. These are not recreated as generic TOML predicates.

| Dev kind | Stable identity and retained adapter |
| --- | --- |
| goal | `pillar:<subject-stem>/<goal-id>` or `principle:<subject-stem>/<goal-id>`; `vision_subject.parse_subject` |
| gap | `XX-NNN` from canonical filename, matching title; `gap_relationships` metadata and primary-goal parser |
| project | Numeric folder prefix verbatim; `project_contract.project_number` and `plan_gap_links` |
| release | Numeric filename stem matching release heading/field; `records.release_brief` |
| issue | Decimal issue number, emitted only from frozen release rows; `records.release_issue_block` |

The Dev adapter retains root/source containment checks; duplicate gap/project source checks; real canonical href matching; release folder/membership validation; and frozen-vs-draft issue semantics. A project marked done never implies release membership or gap closure. No live GitHub result is promoted into an authored relation. Dev stages omit status lists because `load_delivery` currently imposes none.

The two declarations are `delivery` (goal, gap, project, release) and `issue` (issue, release). The old `DeliveryPath` projection and wrappers preserve:

```text
Validated <N> records and <M> typed relationships
goal:<id> -> gap:<id> (<role>) -> project:<id> (<role>) -> release:<id>
issue:<id> -> release:<id>
ERROR project delivery: <message>
```

The complete-path wrapper emits no partial release-less row, even though such records are valid. Generic Otto query text in section 5 is separate. The wrapper must not change lexicographic order, duplicate/converging path behavior, or empty-output semantics.

OT-1 records check counts and a full suite, but explicitly lacks real goal/issue output hashes. Do not invent them. Preserve its existing fixture tests and exact check result as the stated oracle; the orchestrator can add a real source query hash if it establishes one. Public vision JSON and skill-tree hash use the exact OT-1 revision/input controls.

## 9. Synthetic Marketing shape

The example uses only invented entities and the namespace `demo-marketing-`. All five kinds use slug IDs: goal, project, campaign, issue, idea. Goals are embedded in synthetic `strategy.md` and use a local reader; projects/campaigns/issues use bold headers, and ideas demonstrate the existing narrow frontmatter reader. Ordinary knowledge documents are not record kinds.

The synthetic goal reader reads one live `## Goals` table with header `| ID | Goal |`. Each unique slug in ID creates one goal, the Goal cell is its title, and the row supplies its source line; no relations or statuses are inferred. `register_checks` supplies `example-title-length`, an `always` check requiring each project title to be at most 80 characters. `register_views` supplies `project-catalog`, a sorted project-ID/title table at `projects/index.md`. OT-14 also supplies one `skill: true` draft-note workstream under `agent/shared/workstreams/` with the existing required headings. These are local demonstration policies, not Otto defaults.

Relations are:

| Relation | Endpoints | Roles and global degree |
| --- | --- | --- |
| `serves` | project -> goal | primary/supporting; any globally, so the strategy pipeline owns required goal membership |
| `includes` | campaign -> project | included; any globally |
| `routes-to` | issue or idea -> project | primary/supporting; any globally |

`strategy` requires each project to serve one primary goal and permits supporting goals. A campaign, when present, includes one or more projects. Campaign is optional for a project and its facing pipeline lower bound relaxes to zero. `intake` allows an issue or idea to remain unassigned; if assigned, at most one project is primary and any number supporting. Project membership in both pipelines is one record and one task list.

The later positive corpus has `goal:clear-example`, standard `project:launch-note`, loop `project:try-message`, ungrouped `project:standalone-note`, optional `campaign:sample-week`, `issue:clarify-heading` and `idea:short-example`. Each project serves the goal, the campaign includes the first two, the issue routes to launch-note, and the idea may remain unassigned. “Ungrouped” means no campaign, not a missing required goal. All sample project statuses are `queued`; the strategy project stage permits the six existing default lifecycle names. No stage changes them.

This corpus supplies an optional campaign, a zero-degree intake record, a multi-kind stage, an allowed-status rule, roles, both directions of cardinality, two project templates and the research-template extension. No additional facility is justified by a hypothetical third production consumer.

## 10. Module and function map

This map covers every top-level function/class in the eleven required source modules. Methods follow their owning class unless separately named. “Split” means one mechanism in Otto plus the existing domain wrapper/policy in Dev, not two diverging generic copies. No Python is changed by OT-4.

### Markdown, Git and records

| Source | Move to Otto | Stay in Dev / split detail |
| --- | --- | --- |
| `document_structure.py` | Entire module into `otto/markdown.py`: `_heading_spans, headings, markdown_heading_anchors, ordered_heading_error, frontmatter, section, ordered_bold_fields` | Caller-owned required labels/headings remain local data |
| `records.py` generic readers | `read_text, _search, _finditer, heading, heading_present, section_after_match, matching_sections, field_match, named_field_matches, key_value_lines, split_table_row, is_placeholder` -> `otto/markdown.py` | Placeholder token sets remain Dev/test data; no Dev constants in Otto |
| `records.section` | Same body as `otto.markdown.section_by_heading` | Dev aliases it back to `section`; `document_structure.section` keeps Otto's `section` name, per OT-5 decision |
| `records.py` Git helpers | `git_result, git_output, git_show` -> `otto/git.py` | Existing failure/missing-blob behavior retained |
| `records.py` domain readers | None of `project_fields, release_issue_block, release_branch_errors, active_plan_errors, release_fix_issue_errors, release_brief, priority_order, projects` becomes generic policy | All remain Dev, calling Otto readers/resolver. `projects` replaces path discovery/identity literals with configuration while retaining catalog order and output |
| `records.py` constants | Only mechanism regexes used by moved helpers move with them | `PLAN_CELL`, all `PLACEHOLDERS_*`, `PROJECT_FIELDS`, `RELEASE_*`, `ISSUE_*` and `BRANCH_*` stay with their Dev consumers |

### Lifecycle and relationships

| Source | Disposition |
| --- | --- |
| `lifecycle.py` | Entire passive module -> `otto/lifecycle.py` under OT-5: `Status, names, terminal, phrase, route_pattern, requiring, definitions`; `STATUSES, NAMED_OWNER, COMPLETION_ASSESSMENT, NEEDS` are the existing **default** vocabulary. Dev imports it unchanged. Stage lists are explicit constraints; they neither execute these needs nor introduce transition APIs |
| `relationships.RelationshipError` | Otto exception |
| `relationships.RecordRef` (`__post_init__, __str__`) | Otto immutable typed identity; kind membership comes from configuration |
| `relationships.Relationship` (`__post_init__, identity`) | Otto configured endpoint/role/provenance validation, role-independent identity, added authored source line |
| `relationships.RelationshipIndex` (`__init__, outgoing, incoming`) | Split: immutable sorted index, duplicate/existence validation and queries in Otto; configured degree checks generic; enabler-specific policy in Dev |
| `relationships.RECORD_KINDS, RELATION_KINDS` | Deleted as generic literals, represented by Dev declaration data |

### Check registry and command dispatch

| Source symbols | Disposition |
| --- | --- |
| `checks.Context, Check, _body` | Otto contracts/body helper |
| `checks._markdown_links, _link_anchors` | Split: generic link/anchor mechanism in Otto; Dev mandatory source list, catalog gate and anchor target regex in Dev. Otto anchor `target_pattern=None` means all relative Markdown targets |
| `checks._workstream_structure, _generated_views` | Split: call Otto document/view mechanisms; retain Dev index/routing policy, duplicate-diagnostic suppression, trigger and legacy hint wording |
| `checks._pack_shape_impl, _pack_shape` | Split: generic manifest/common-shape mechanism; Dev new-pack gate, planning-label ownership and legacy diagnostics |
| `checks._catalog, _catalog_ready, _unique_project_numbers, _release_documents, _active_plans_in_releases, _strategy_consistency, _catalog_paths, _gap_structure, _plan_files, _subjects, _obsolete_sources, _canonical_principles, _obsolete_templates, _ledger, _public_vision` | Stay Dev |
| `checks._completion_impl, _boundary_impl, _planning_impl, _completion, _boundary, _planning, _project_delivery` | Stay Dev; these are domain/gate wrappers, not Otto defaults |
| `checks.REGISTRY` | Stay Dev, exact order/descriptions/gates; adapter registers additional checks separately |
| `astrid_dev.main` | Split: injectable list/check parser, selection, Context construction and runner -> `otto/checks.py`; Dev keeps release dispatch, legacy `sync`, skill/view dispatch and registry. OT-13 wires Otto CLI to the new config. `ROOT` remains a Dev wrapper default |

The retained registry order is `plan-catalog, unique-project-numbers, release-documents, active-plans-in-releases, strategy-consistency, catalog-paths, gap-structure, plan-files, subjects, obsolete-sources, canonical-principles, obsolete-templates, ledger, markdown-links, link-anchors, public-vision-content, workstream-structure, project-delivery, generated-views, completion-assessment, gap-boundary-assessment, project-planning-evidence, pack-shape`. This list is a parity inventory, not an Otto registration literal.

### Views

| Source symbols | Disposition |
| --- | --- |
| `View, _index_parts, _with_marker, expected, touched, check_view, check, sync` | Otto engine; explicit declarations, marker prefix and hint parameters; string/absent region, no boolean compatibility |
| `rebase_links, _blank_fences, _block_regions, _owner_body, _render_block` | Otto generic marker/link helpers |
| `block_views` | Stay Dev, including tracked-file discovery, allowed copy roots/history exclusions and generated declarations; per OT-5 decision |
| `_checks` | Split: generic rendering can consume a registry; Dev's check-catalog view and wrapper command remain Dev |
| `_agent_index, agent_index_errors, views_for` | Stay Dev composition/preflight, calling generic helpers and injecting the resulting declarations into Otto |
| `_vision, _root_readme, _root_statement, _catalog, _status_definitions, release_membership, _strategy, _agent_routing_errors` | Stay Dev renderers and policy |
| `VIEWS, ROLE_INDEX_TARGETS, BLOCK_COPY_ROOTS, BLOCK_COPY_HISTORY` | Stay Dev. `MARKER_PREFIX` becomes the supplied Dev parameter. Generic marker/fence regexes move with helpers |

The existing `public-vision`, root summaries, catalog, lifecycle, check-catalog, role/shared-workstream indexes and strategy-version regions keep their registrations/renderers. The runtime view engine has no hidden Dev global registry.

### Skill documents, build and installation

| Source symbols | Disposition |
| --- | --- |
| `agent_documents.AgentDocument` (including `skill_name`), `routing_table_headers, _kind, parse_document, discover_documents, validate_documents` | `otto/skills/documents.py`; namespace/source root from `SkillConfig`. Generic role/workstream section conventions and name limits move; Dev document content and route-policy ownership do not |
| `skill_builder._active_lines, _real_anchors, _ref_key, _mask_code_spans, _rewrite_links, render_skill, expected_packages` | `otto/skills/builder.py`; preserve source-link validation and emitted package bytes under Dev settings |
| `skill_builder._output_root, _assert_package_dir, _check_output, check_packages, _build_output, _build_lock, _exchange_paths, _probe_exchange, build_packages, _build_packages, PublicationCommittedError` | Same Otto module; namespace-isolated output/ownership/lock/staging parameters, existing atomic-publication and honest partial-failure behavior |
| `skill_builder` constants | Generic link regexes remain with mechanism; `OUTPUT, MARKER, REPO_LINK, _MARKER_SOURCE, _LOCK_CONTENT` derive from configuration (repository link from output depth) |
| `skill_installer.CommittedRetargetCleanupError, PartialInstallationError, default_destinations, _target_of, _identity, _retarget_owned_link` | `otto/skills/installer.py`, parameterized namespace/staging |
| `skill_installer._owned_link, install_packages` | Split: generic current-namespace, exact owned-generation link handling in Otto; legacy Dev `skills/` links and special `astrid-dev`/`shared` names stay in a named Dev migration helper |

No namespace can retire the other's packages. A matching prefix alone does not prove ownership. No Otto installer special-case names Dev's old packages. Real installation still needs its existing authorization; OT-4 config selects no destinations and runs no installation. Guidance content/role-rule moves are OT-15 through OT-21's map, not implicitly moved by this code map.

### Delivery adapters and supporting modules

| Source | Disposition |
| --- | --- |
| `project_delivery.load_delivery` (including nested `require_authored_source`), `ROOT, GAP_FILE` | Stay Dev as the canonical-source adapter; replace graph mechanics with Otto imports, retain all domain checks |
| `project_delivery.DeliveryPath` | Stay Dev compatibility projection |
| `project_delivery.deliveries_for_goal, frozen_releases_for_issue` | Split: generic traversal/index in Otto, exact Dev projection/roles/frozen semantics/order in wrappers |
| `project_delivery.main` | Stay Dev compatibility CLI and byte formatting |
| `project_contract.project_number, PLAN_FOLDER` | Split: configured ID/path resolver replaces generic extraction/pattern ownership; Dev callable/diagnostics remain compatible |
| `project_contract.plan_gap_links, plan_gap_ids` and gap/enabler regexes | Stay Dev; one canonical source parser |
| `pack_shape._headings, _first_table_header, _ordered_error` | Generic shape helpers use Otto Markdown |
| `pack_shape.template_shape, shape_errors, new_packs` | Split: configurable common/manifest shape and stable-identity new-pack mechanics in Otto; Dev planning-label gates, legacy wording and rename interpretation remain at the adapter boundary |
| `pack_shape._planning_labels` | Stay Dev planning-evidence interpretation |
| `check_docs.local_links` and link/anchor mechanics | Generic portion moves under OT-5; all other Dev catalog/release/gap/public-feed policy stays |
| `vision_subject, gap_relationships, export_public_vision, release_status, check_completion, check_gap_boundaries, check_project_planning` | Remain Dev domain modules; reuse imported mechanisms only |
| `agent/README.md, docs/extending.md` | Dev navigation, commands and domain examples remain Dev; generic authoring mechanisms are documented by Otto. Guidance rule dispositions belong to OT-15's separate map |
| All other astrid-dev modules, workflows and tests not explicitly assigned a generic lift | Remain Dev. No release/GPU/product-repository/claim/publication/issue-fetch/merge automation moves under this contract |

Test assertion/oracle changes are not authorized by this map. OT-5/6 list mechanical import/setup adaptations; OT-8 lists any contract-level message changes; Dev golden assertions remain protected.

### Run-state ownership

**Otto v0 leaves `<project>/.otto/runs/<run-id>/` to Dev.** Its existing ignored run recovery files, `run.yaml` and `model-usage.jsonl` are neither a config input nor a database for Otto. No module here scans, writes, migrates or resets them. Generic guidance may describe a local recovery convention through OT-15's rule map, but the shared spelling grants Otto no run engine or authority. Raw model/provider IDs and private provenance logs stay out of this public repository.

## 11. Planted fixture specifications and expected messages

These are named, reproducible fixture specifications for the later owning cards, **not executed tests or already-created negative workspaces**. Each starts from the positive Dev/Marketing corpus, makes only the stated change, and expects failure with the location in section 6. The fixture identifier is the stable handoff name; OT-7 through OT-14 turn these into executable tests. This keeps OT-4 within its document/TOML-only scope.

Expected messages below are the body after `<file>:<line>:`. `<...>` placeholders bind to the changed fixture's actual ID/count/location. Each executable fixture must assert the exact affected file and authored key/row line, not merely a nonzero exit or message substring.

### Five constraints and their boundaries

| Fixture ID | Single planted change / control | Expected message or result | Owner |
| --- | --- | --- | --- |
| `degree-source-max` | One primary and one supporting route from issue:clarify-heading to different projects, with a test link total `at-most-one` | `pipeline intake: issue:clarify-heading has 2 routes-to targets; expected at-most-one` | OT-10 |
| `degree-target-max` | Two campaigns include launch-note with test link `per_target = "at-most-one"` | `pipeline strategy: project:launch-note has 2 incoming includes sources; expected at-most-one` | OT-10 |
| `required-stage-absent` | Remove launch-note's serves row | `pipeline strategy: project:launch-note has no required goal through serves` | OT-10 |
| `optional-stage-absent` | Remove all sample-week includes edges and the campaign record; keep projects | PASS, no campaign required for projects | OT-10 |
| `optional-stage-present-empty` | Keep campaign sample-week but remove its project edges | `pipeline strategy: campaign:sample-week has no required project through includes` | OT-10 |
| `role-two-primaries` | Two distinct primary serves goals; total degree allows both | `pipeline strategy: project:launch-note has 2 primary serves targets; expected exactly-one` | OT-10 |
| `role-supporting-valid` | One primary plus two distinct supporting goals | PASS | OT-10 |
| `stage-source-kind` | A narrower test intake stage admits only issue; existing idea routes-to remains globally legal | `pipeline intake: routes-to source idea:short-example is not allowed in stage intake` | OT-10 |
| `stage-target-kind` | Campaign includes a goal instead of a project | `includes requires campaign -> project, got campaign -> goal` | OT-8/10 |
| `stage-status` | Change launch-note status to `published` | `pipeline strategy: project:launch-note status 'published' is not allowed in stage project` | OT-10 |
| `stage-status-missing` | Remove its Status field | `pipeline strategy: project:launch-note has no status for stage project` | OT-10 |
| `zero-degree-record-counted` | Add a project without serves, with otherwise valid metadata | Same required-goal diagnostic for that project | OT-10 |
| `no-pipelines` | Remove both pipeline files from a copy, keep records and global rules | PASS; same snapshot identities/bytes | OT-10/14 |
| `delete-one-pipeline` | Remove intake only | No intake verdict; strategy and relation verdicts unchanged; no record deletion | OT-10/14 |
| `shared-project-identity` | Query launch-note through strategy and intake | One RecordRef, one source file and one tasks.md, present in both results | OT-9/14 |
| `cycle-terminates` | A test pipeline repeats the project kind at distinct stages and has a record cycle | Deterministic finite output, no repeated traversal state or source mutation | OT-9 |
| `query-unknown` | Query a nonexistent typed record | `Unknown record project:missing`, exit 0 | OT-9 |
| `query-ambiguous` | Same bare slug in two participating kinds | `ambiguous record id 'shared': goal:shared, project:shared`, exit 1 | OT-9 |

The source/target maximum fixtures and the primary-role fixture separate total degree from role degree. The optional negative distinguishes an absent optional record from a malformed existing campaign. Status absence is not treated as a filter.

### Configuration and adapter declaration failures

| Fixture ID | Planted change | Expected message | Owner |
| --- | --- | --- | --- |
| `config-root-missing` | Select nonexistent root | `workspace root is not an existing directory: <root>` (CLI argument, no invented source file) | OT-7 |
| `config-file-missing` | Existing root without otto.toml, command check | `no otto.toml found in <root>` | OT-7 |
| `toml-syntax` | Supply unclosed string in an ephemeral config | `invalid TOML: <tomllib reason>` at parser line | OT-7 |
| `config-version` | `version = 2` | `unsupported declaration version 2; expected 1` | OT-7 |
| `config-unknown-key` | Add `workspace.nam` | `unknown key 'nam' in workspace` | OT-7 |
| `config-missing-key` | Remove workspace name | `missing required key 'name' in workspace` | OT-7 |
| `config-type` | Set record_kinds to a string | `record_kinds must be an array of tables` | OT-7 |
| `declaration-empty-list` | Empty a required nonempty kind/role/status/heading/source list | The field-specific `<field> must be nonempty` message, parameterized over those declarations | OT-7/8/9/11 |
| `declaration-duplicate-list` | Repeat a value in a unique kind/role/status/heading list | The field-specific `<field> contains duplicate '<value>'` message, parameterized over those declarations | OT-7/8/9/11 |
| `config-duplicate-kind` | Repeat a project entry | `duplicate record kind 'project'` at second entry | OT-7 |
| `config-bad-name` | Kind `Project Items` | `invalid record kind name 'Project Items'; expected lowercase kebab-case` | OT-7 |
| `config-namespace` | Remove the namespace's final hyphen | `skill namespace must be lowercase kebab-case with a trailing hyphen` | OT-7 |
| `config-pin` | Nonhex commit, or tag without commit | `otto.commit must be 40 lowercase hex characters` / `otto.tag requires otto.commit` | OT-7 |
| `config-path-escape` | Root `../outside`, absolute/drive path, or escaped symlink | `<key> must resolve inside the workspace root` | OT-7 |
| `config-path-type` | A directory path names a file | `<key> must name a directory` | OT-7 |
| `config-path-unused` | Unused `paths.projetcs` | `unused record root 'projetcs'` | OT-7 |
| `config-root-key` | Kind references absent path key | `record kind project names unknown root 'missing'` | OT-7 |
| `config-source-output-overlap` | Generated output under agent source | `skill source and output roots must not overlap` | OT-7 |
| `config-id-policy` | Unknown policy or missing per-kind policy | `unknown ID policy '<policy>'` / `missing ID policy for kind project` | OT-7 |
| `config-id-extra` | ID policy for undeclared kind | `ID policy names unknown kind '<kind>'` | OT-7 |
| `config-id-regex` | Invalid regular expression or pattern on a preset | `invalid ID regex for <kind>: <reason>` / `pattern is only valid for regex ID policy` | OT-7 |
| `config-id-reader` | Generic reader with adapter ID source, or converse | `ID source '<source>' is incompatible with reader '<reader>'` | OT-7 |
| `record-id-policy` | Folder `Bad Slug` under slug project source | `invalid project identity component 'Bad Slug' for policy slug` | OT-7 |
| `config-reader` | Unknown reader string | `unknown reader '<reader>'; expected headers, frontmatter or adapter` | OT-7 |
| `config-empty-sources` | Empty files array | `record kind project requires at least one source pattern` | OT-7 |
| `config-adapter-missing` | Adapter kind without records export/module | `adapter record kinds require adapters.module and adapters.records` | OT-7 |
| `adapter-file-missing` | Module file absent | `adapter module does not exist: <path>` | OT-7 |
| `adapter-export-missing` | Named export absent/non-callable | `adapter export '<name>' is missing or not callable` | OT-7/13 |
| `adapter-return-shape` | Loader/factory returns wrong data | `adapter export '<name>' returned an invalid <contract>` | OT-7/13 |
| `adapter-provenance` | Record/edge has missing or out-of-root location | `adapter export '<name>' returned invalid source location for <ref>` | OT-7/8 |
| `registration-duplicate` | Two checks/views share ID, including a core collision | `duplicate check id '<id>'` / `duplicate view name '<name>'` | OT-13 |
| `registration-invalid` | Bad Check trigger, description or callable | Existing `Check` validation message (`check trigger must be always or pr` etc.) | OT-13 |
| `registration-import-error` | Trusted module raises while loading | `cannot load adapter <module>: <exception>` | OT-13 |

Unknown-key, missing-key and wrong-type fixtures are parameterized over **every table/entry defined in sections 3, 5 and 7**, including role maps, not just the illustrative keys above. Empty/duplicate lists and nonpositive source lines get their field-specific message. They cover the closed schema without accepting unlisted syntax.

### Relation and pipeline declaration failures

| Fixture ID | Planted change | Expected message | Owner |
| --- | --- | --- | --- |
| `relation-duplicate-kind` | Duplicate relation name | `duplicate relation kind '<name>'` | OT-8 |
| `relation-unknown-kind` | Undeclared source/target kind | `relation <name> names unknown record kind '<kind>'` | OT-8 |
| `relation-empty-endpoint` | Empty sources, targets or roles | `relation <name> requires nonempty <field>` | OT-8 |
| `relation-duplicate-role` | Repeated role value | `relation <name> repeats role '<role>'` | OT-8 |
| `relation-cardinality-token` | `per_source = "two"` | `unknown cardinality 'two'` | OT-8 |
| `relation-role-bound` | by_role names an unallowed role | `relation <name> has cardinality for unknown role '<role>'` | OT-8 |
| `relation-impossible-bounds` | Total at-most-one with two roles each exactly-one | `inconsistent cardinality bounds for relation <name> at source` | OT-8 |
| `pipeline-id-mismatch` | ID differs from filename stem | `pipeline id '<id>' does not match filename '<stem>'` | OT-9 |
| `pipeline-duplicate-id` | Two loaded declarations with one ID (loader fixture) | `duplicate pipeline id '<id>'` | OT-9 |
| `pipeline-empty-chain` | Empty stages, or one stage | `pipeline <id> requires at least two stages` | OT-9 |
| `pipeline-stage-duplicate` | Repeat stage ID | `pipeline <id> repeats stage '<stage>'` | OT-9 |
| `pipeline-stage-kind` | Stage references unknown kind | `pipeline <id> stage <stage> names unknown kind '<kind>'` | OT-9 |
| `pipeline-link-relation` | Link references unknown relation | `pipeline <id> names unknown relation '<relation>'` | OT-9 |
| `pipeline-link-stage` | from/to references unknown stage | `pipeline <id> link names unknown stage '<stage>'` | OT-9 |
| `pipeline-link-direction` | Swap endpoints against relation kinds | `pipeline <id> link <relation> endpoints do not match stages <from> -> <to>` | OT-9 |
| `pipeline-link-topology` | Missing/repeated/nonadjacent stage pair | `pipeline <id> requires exactly one link between adjacent stages <a> and <b>` | OT-9 |
| `pipeline-optional-one` | Optional campaign with facing per_target exactly-one | `pipeline strategy: optional stage campaign conflicts with exactly-one per_target on includes` | OT-9 |
| `pipeline-optional-role-one` | Same contradiction in facing by_role included | `pipeline strategy: optional stage campaign conflicts with exactly-one per_target for role included on includes` | OT-9 |
| `pipeline-optional-global-min` | Global includes per_target has positive minimum while campaign optional | `pipeline strategy: optional stage campaign conflicts with global minimum on includes` | OT-9 |
| `pipeline-impossible-bounds` | Pipeline lower bound cannot satisfy relation upper bound | `pipeline <id> has incompatible bounds for <relation> at <end>` | OT-9 |
| `pipeline-status-list` | Empty, repeated or non-string status values | `pipeline <id> stage <stage> statuses must be nonempty unique strings` | OT-9 |

### Authored graph and template refusals

| Fixture ID | Planted change | Expected message | Owner |
| --- | --- | --- | --- |
| `graph-duplicate-record` | Second source with same typed identity | `duplicate record identity` | OT-8 |
| `graph-unknown-target` | Valid typed reference to absent target | Preserved `<path>: <relation> names unknown <ref>` | OT-8 |
| `graph-contradictory-role` | Same source/relation/target primary and supporting | Preserved duplicate-or-contradictory message | OT-8 |
| `graph-invalid-role` | `secondary` where only primary/supporting allowed | `<relation>: invalid role 'secondary'` | OT-8 |
| `graph-invalid-identity` | Empty, untrimmed, whitespace/control-containing or policy-breaking adapter ID | Preserved `invalid <kind> identity: '<id>'` or the policy-specific diagnostic | OT-7/8 |
| `dev-gap-two-primaries` | Gap has two primary measures | `gap:<id>: expected one primary measures relationship, found 2` | OT-8/20 |
| `dev-project-missing-primary` | Non-enabler has no primary addresses (adapter/index fixture) | `project:<id>: expected one primary addresses relationship, found 0` | OT-8/20 |
| `dev-enabler-addresses` | Explicit valid enabler also emits an addresses edge | Preserved enabler-cannot-declare-addresses message | OT-8/20 |
| `dev-invalid-enabler` | Arbitrary Vision role or nonproject exemption | Canonical unsupported Vision role / existing-project diagnostic | OT-20 |
| `dev-canonical-href` | Project link carries real gap ID but resolves to another file | Preserved `gap:<id> link '<href>' does not name canonical source <path>` | OT-20 |
| `dev-unfrozen-issue` | Replace frozen stamp with a valid draft stamp | No issue/edge emitted from that draft; no false membership | OT-20 |
| `markdown-relation-shape` | Duplicate section, bad header/row or prose in table | `invalid Relationships table: <specific shape error>` | OT-7/8 |
| `markdown-duplicate-status` | Two live status fields | `duplicate status field` | OT-7 |
| `markdown-title` | No nonempty H1 at the reader's required title position | `record document must start with a nonempty # title` | OT-7 |
| `markdown-frontmatter` | Missing/unclosed block, duplicate key, or multiline/empty value | The existing `frontmatter` reader's exact message, at the offending source line | OT-7 |
| `template-unknown` | `Template: missing` | `unknown project template 'missing'` | OT-11 |
| `template-selector-shape` | Empty/duplicate/body-only/fence-only selector | `empty Template field` / `duplicate Template field` / `Template must be in the project header` / `Template declaration is inside a fenced block` | OT-11 |
| `template-duplicate` | Workspace redeclares built-in loop | `duplicate template name 'loop'` | OT-11 |
| `template-name-location` | Manifest name differs from its folder | `template name '<name>' does not match directory '<directory>'` | OT-11 |
| `template-nested` | Manifest deeper than one named directory | `template manifests must be one level below the template root` | OT-11 |
| `template-inheritance` | Add extends/include key | `unknown key 'extends' in template` (or that actual unknown key) | OT-11 |
| `template-workstream` | Missing target or anchor | `template <name>: workstream target does not exist: <reference>` / `template <name>: workstream anchor does not exist: <reference>` | OT-11 |
| `template-path-escape` | Extra doc/source/workstream escapes owning root | `template <name>: <field> must resolve inside <root>` | OT-11 |
| `template-document-collision` | Duplicate extra path or collision with common pack | `template <name>: duplicate or common document path '<path>'` | OT-11 |
| `template-source-missing` | Extra document source absent | `template <name>: missing document source '<source>'` | OT-11 |
| `template-source-shape` | Source lacks a required heading | `template <name>: document source <source> is missing heading '## <heading>'` | OT-11 |
| `template-heading-list` | Empty/duplicate/non-string headings | `template <name>: headings must be nonempty unique strings` | OT-11 |
| `loop-rounds-missing` | Opted-in loop with no rounds.md | `template loop: missing required document rounds.md` | OT-11/12 |
| `loop-stop-rule-missing` | Remove Stop rule H2 | `template loop: rounds.md is missing heading '## Stop rule'` | OT-11/12 |
| `loop-heading-order` | Put Method before Baseline | `template loop: rounds.md heading '## Method' is out of order` | OT-11/12 |
| `loop-standing-task-missing` | Remove Standing task header or its task row | `template loop: rounds.md needs **Standing task:** naming one existing task` | OT-11/12 |
| `loop-draft-baseline` | Valid headings, real standing row, baseline text Pending | PASS; no fabricated measurement required | OT-12 |
| `template-downgrade` | Delete explicit loop selector against base | `explicit Template field removed from <ref>; write **Template:** standard to select standard deliberately` | OT-11 |
| `template-switch` | Explicit loop -> research or standard against base | Selected template and common pack fully checked; former extra files remain untouched | OT-11 |
| `template-base-missing` | Historical comparison base unavailable | `cannot compare template selection: base revision '<base>' is unavailable` | OT-11 |
| `template-research-addition` | Add supplied research manifest/docs/workstream | PASS without changing Otto code | OT-12/14 |
| `old-standard-pack` | Existing no-selector pack has old common headings | PASS under unchanged new-pack gate | OT-11/20 |
| `local-check-runs` | Give a synthetic project an 81-character title | `project:<id> title exceeds 80 characters` from `example-title-length` | OT-13/14 |
| `generated-view-stale` | Hand-edit registered output | Existing stale-view diagnostic with configured hint/prefix | OT-13 |
| `generated-skill-stale` | Hand-edit one owned SKILL.md | `<package>: generated SKILL.md is stale` | OT-13 |

TOML syntax errors are generated as ephemeral test input by the later harness, not committed as invalid `.toml` examples: OT-4's parse-all proof must remain meaningful. Source-line assertions include escaped/multiline strings and repeated array tables. Filesystem refusal fixtures cover escaped and dangling source roots and output symlink components; no malformed declaration is accepted because it happened to yield zero records.

## 12. Implementation handoff and proof

OT-7 implements config/readers/resolver and source maps; OT-8 global relation checks and preserved graph messages; OT-9 declarations/traversal; OT-10 conformance; OT-11/12 templates; OT-13 registry assembly; OT-14 runnable synthetic/blank fixtures. OT-19/20 preserve Dev's domains and exact compatibility outputs. RS1 reviews this contract before those dependent cards proceed.

The packet's selectors are **none**. On the exact candidate head, the orchestrator runs this standard-library parse command from the Otto root:

```sh
python3 - <<'PY'
from pathlib import Path
import tomllib

paths = sorted(
    path
    for root in (Path("tests/fixtures/dev"), Path("tests/fixtures/marketing"))
    for path in root.rglob("*.toml")
)
if not paths:
    raise SystemExit("No OT-4 TOML examples found")
for path in paths:
    with path.open("rb") as source:
        tomllib.load(source)
    print(path.as_posix())
print(f"Parsed {len(paths)} TOML examples")
PY
```

Expected OT-4 scope: this document and the nine TOML example files described below, with no Python, executable tests, private data or astrid-dev edits. The orchestrator records the actual parse result and commissions the one read-only RS1 round. This packet does not claim schema/conformance execution, unit-suite success, installed behavior, or acceptance.

| Example file | Role |
| --- | --- |
| `tests/fixtures/dev/otto.toml` | Existing five kinds, four relations, numeric/qualified identities, Dev adapter registrations |
| `tests/fixtures/dev/pipelines/delivery.toml` | The read-only goal/gap/project/release chain |
| `tests/fixtures/dev/pipelines/issue.toml` | Frozen issue/release chain |
| `tests/fixtures/dev/examples/standard.template.toml` | Specimen of Otto's standard manifest, outside workspace discovery |
| `tests/fixtures/dev/examples/loop.template.toml` | Specimen of Otto's additive loop manifest |
| `tests/fixtures/marketing/otto.toml` | Synthetic slug workspace and local reader/check/view registration |
| `tests/fixtures/marketing/pipelines/strategy.toml` | Required project goal, optional campaign, status and role examples |
| `tests/fixtures/marketing/pipelines/intake.toml` | Multi-kind issue/idea intake; unassigned records remain valid |
| `tests/fixtures/marketing/templates/research/template.toml` | Third template added without engine changes |

Deliberately omitted: per-workspace parser/query expressions, arbitrary graph selection, status transitions, inheritance/overrides, configurable ownership-marker strings, provider or model bindings, installation destinations, record creation commands and pipeline execution. The two fixtures do not need them. Existing Dev policy remains explicit local code instead of being generalized without a consumer.
