"""Local demonstration reader, check and view for the synthetic workspace."""
import re

from otto.checks import Check
from otto.ids import LocatedError, RecordRef, SourceLocation, validate_identity
from otto.markdown import _heading_spans, split_table_row
from otto.records import Record, RecordBatch, read_record
from otto.views import View


def load_strategy_goals(workspace):
    """Read the one live Goals table, retaining actual authored row locations."""
    records = []
    seen = set()
    for path in workspace.sources["goal"]:
        text = (workspace.root / path).read_text(encoding="utf-8")
        headings = _heading_spans(text, 2)
        positions = [i for i, (title, _, _) in enumerate(headings) if title == "Goals"]
        if len(positions) != 1:
            raise LocatedError(SourceLocation(path, 1), "expected exactly one '## Goals' section")
        i = positions[0]
        start = headings[i][2]
        end = headings[i + 1][1] if i + 1 < len(headings) else len(text)
        first = text.count("\n", 0, start) + 1
        rows = [(n, line.strip()) for n, line in enumerate(text[start:end].splitlines(), first)
                if line.strip()]

        def cells(number, row):
            if not (row.startswith("|") and row.endswith("|")):
                raise LocatedError(SourceLocation(path, number), "invalid Goals table row")
            values = split_table_row(row)
            if len(values) != 2 or not all(values):
                raise LocatedError(SourceLocation(path, number), "invalid Goals table row")
            return values

        if not rows or cells(*rows[0]) != ["ID", "Goal"]:
            raise LocatedError(SourceLocation(path, first), "expected ID | Goal header")
        if len(rows) < 2 or not all(re.fullmatch(r":?-+:?", value) for value in cells(*rows[1])):
            raise LocatedError(SourceLocation(path, rows[0][0]), "invalid Goals table separator")
        for number, row in rows[2:]:
            identity, title = cells(number, row)
            source = SourceLocation(path, number)
            validate_identity("goal", workspace.ids["goal"], identity, source)
            if identity in seen:
                raise LocatedError(source, f"duplicate goal identity: {identity!r}")
            seen.add(identity)
            records.append(Record(RecordRef("goal", identity), source, title))
    return RecordBatch(tuple(records))


def _projects(workspace):
    kind = next(kind for kind in workspace.record_kinds if kind.name == "project")
    records = [record for path in workspace.sources["project"]
               for record in read_record(workspace, kind, path).records]
    return sorted(records, key=lambda record: record.ref.id)


def register_checks(workspace):
    def title_length(context):
        return [f"{record.source.path}:{record.source.line}: {record.ref} title exceeds 80 characters"
                for record in _projects(workspace) if len(record.title) > 80]

    return (Check("example-title-length", "always", "Check project titles are at most 80 characters",
                  title_length),)


def register_views(workspace):
    def catalog(root):
        rows = ["# Project catalog", "", "| ID | Title |", "| --- | --- |"]
        for record in _projects(workspace):
            title = record.title.replace("|", "&#124;")
            rows.append(f"| {record.ref.id} | {title} |")
        return "\n".join(rows) + "\n"

    return ((View("project-catalog", ("projects/*/plan.md",), "projects/index.md", catalog),), [])
