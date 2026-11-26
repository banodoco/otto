"""Read-only conformance of a validated workspace graph to its pipelines."""
from __future__ import annotations

from collections import defaultdict

from .checks import Check, Context
from .config import Workspace, load_workspace
from .ids import LocatedError, RecordRef, SourceLocation
from .pipelines import Pipeline, PipelineLink, Stage, effective_bounds, load_pipelines
from .records import Record, RecordBatch, load_records
from .relationships import Relationship, RelationshipIndex, RelationshipSchema


Diagnostic = tuple[SourceLocation, str]


def _render(diagnostics: list[Diagnostic]) -> list[str]:
    return [
        f"{source.path}:{source.line}: {message}"
        for source, message in sorted(
            diagnostics, key=lambda item: (item[0].path, item[0].line, item[1])
        )
    ]


def _edge_location(edge: Relationship) -> SourceLocation:
    # Loaded rows always carry validated provenance. The low-level graph's
    # compatibility constructors may omit lines, but those are not a loaded
    # workspace snapshot and must not generate fabricated evidence.
    source = edge.source_location
    assert source is not None, "pipeline conformance requires authored edge locations"
    return source


def _authored_order(edge: Relationship):
    source = _edge_location(edge)
    return source.path, source.line, edge.source, edge.target, edge.role


def _degrees(
    pipeline: Pipeline, link: PipelineLink, record: Record, opposite: Stage,
    edges: list[Relationship], *, end: str,
) -> list[Diagnostic]:
    """Evaluate one endpoint, counting only edges admitted by both stages."""
    bounds = [(None, getattr(link, end))]
    bounds.extend((role, rule[end]) for role, rule in sorted(link.by_role.items())
                  if end in rule)
    rules = [
        (role, token, *effective_bounds(token, optional=opposite.optional))
        for role, token in bounds
    ]
    prefix = f"pipeline {pipeline.id}: {record.ref}"
    if not edges and any(low > 0 for _, _, low, _ in rules):
        # Absence is a single diagnosis even when several role minima fail.
        return [(record.source, f"{prefix} has no required {opposite.id} through {link.relation}")]

    diagnostics = []
    authored = sorted(edges, key=_authored_order)
    for role, token, low, high in rules:
        matching = authored if role is None else [edge for edge in authored if edge.role == role]
        count = len(matching)
        if low <= count and (high is None or count <= high):
            continue
        source = (_edge_location(matching[high])
                  if high is not None and count > high else record.source)
        label = "" if role is None else f"{role} "
        neighbors = (f"{label}{link.relation} targets" if end == "per_source"
                     else f"{label}incoming {link.relation} sources")
        diagnostics.append((source, f"{prefix} has {count} {neighbors}; expected {token}"))
    return diagnostics


def _evaluate(
    pipeline: Pipeline, batch: RecordBatch, index: RelationshipIndex,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    stages = {stage.id: stage for stage in pipeline.stages}
    populations = {
        stage.id: tuple(record for record in batch.records if record.ref.kind in stage.kinds)
        for stage in pipeline.stages
    }

    for stage in pipeline.stages:
        if stage.statuses is None:
            continue
        for record in populations[stage.id]:
            prefix = f"pipeline {pipeline.id}: {record.ref}"
            if record.status is None:
                diagnostics.append((record.source, f"{prefix} has no status for stage {stage.id}"))
            elif record.status not in stage.statuses:
                source = record.status_location
                assert source is not None
                diagnostics.append((
                    source, f"{prefix} status {record.status!r} is not allowed in stage {stage.id}"
                ))

    by_relation: dict[str, list[Relationship]] = defaultdict(list)
    for edge in index.relationships:
        by_relation[edge.kind].append(edge)

    for link in pipeline.links:
        source_stage, target_stage = stages[link.from_stage], stages[link.to_stage]
        outgoing: dict[RecordRef, list[Relationship]] = defaultdict(list)
        incoming: dict[RecordRef, list[Relationship]] = defaultdict(list)
        for edge in by_relation[link.relation]:
            valid_source = edge.source.kind in source_stage.kinds
            valid_target = edge.target.kind in target_stage.kinds
            if not valid_source:
                diagnostics.append((
                    _edge_location(edge),
                    f"pipeline {pipeline.id}: {link.relation} source {edge.source}"
                    f" is not allowed in stage {source_stage.id}",
                ))
            if not valid_target:
                diagnostics.append((
                    _edge_location(edge),
                    f"pipeline {pipeline.id}: {link.relation} target {edge.target}"
                    f" is not allowed in stage {target_stage.id}",
                ))
            if valid_source and valid_target:
                outgoing[edge.source].append(edge)
                incoming[edge.target].append(edge)

        # Count in authored direction, not display order. Stage populations
        # are independent of edges and statuses, including zero-degree records.
        for record in populations[source_stage.id]:
            diagnostics.extend(_degrees(
                pipeline, link, record, target_stage, outgoing[record.ref], end="per_source"
            ))
        for record in populations[target_stage.id]:
            diagnostics.extend(_degrees(
                pipeline, link, record, source_stage, incoming[record.ref], end="per_target"
            ))
    return diagnostics


def evaluate_pipeline(
    pipeline: Pipeline, batch: RecordBatch, index: RelationshipIndex,
) -> list[str]:
    """Check one declaration against a matching, validated authored snapshot."""
    return _render(_evaluate(pipeline, batch, index))


def check_pipeline_conformance(
    workspace: Workspace, *, schema: RelationshipSchema | None = None,
    batch: RecordBatch | None = None, index: RelationshipIndex | None = None,
) -> list[str]:
    """Check all declarations without mutation or running a traversal.

    Optional prebuilt inputs must belong to the same workspace snapshot; an
    injected index must already have passed global graph validation. A caller
    orchestrating other checks can share that snapshot. An empty inventory
    imposes no pipeline constraints and need not load any records.
    """
    try:
        if schema is None:
            schema = RelationshipSchema.from_workspace(workspace)
        pipelines = load_pipelines(workspace, schema=schema)
        if not pipelines:
            return []
        if batch is None:
            batch = load_records(workspace)
        if index is None:
            index = RelationshipIndex.from_batch(batch, schema=schema)
        diagnostics = []
        for pipeline in pipelines.values():
            diagnostics.extend(_evaluate(pipeline, batch, index))
        return _render(diagnostics)
    except LocatedError as exc:
        # Do not diagnose degrees on a partially loaded or invalid graph.
        return [str(exc)]


def pipeline_conformance(context: Context) -> list[str]:
    """Registry entry point; command assembly is owned by the caller."""
    try:
        workspace = load_workspace(context.root)
    except LocatedError as exc:
        return [str(exc)]
    return check_pipeline_conformance(workspace)


PIPELINE_CONFORMANCE = Check(
    "pipeline-conformance", "always", "Check declared pipeline constraints", pipeline_conformance
)
