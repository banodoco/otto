"""OT-7 generic Markdown reader and trusted adapter acceptance fixtures."""
from pathlib import Path
import tempfile
import unittest

from otto.config import load_workspace
from otto.ids import LocatedError, RecordRef, SourceLocation
from otto.records import Record, RecordBatch, RelationshipRow, load_records, read_record


BASE = '''version = 1
[workspace]
name = "example"
skill_namespace = "example-"
[paths]
items = "items"
[ids.project]
policy = "slug"
source = "parent"
[ids.idea]
policy = "slug"
source = "stem"
[[record_kinds]]
name = "project"
root = "items"
files = ["*/plan.md"]
reader = "headers"
pack = true
[[record_kinds]]
name = "idea"
root = "items"
files = ["*.md"]
reader = "frontmatter"
'''
ADAPTER = '''
[ids.goal]
policy = "slug"
source = "adapter"
[[record_kinds]]
name = "goal"
root = "items"
files = ["strategy.txt"]
reader = "adapter"
[adapters]
module = "reader.py"
records = "records"
[checks]
register = "checks"
[views]
register = "views"
'''
FENCE = chr(96) * 3
HEADER = "| Relation | Target | Role |"
SEPARATOR = "| --- | --- | --- |"


class RecordsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        (self.root / "items").mkdir()
        self.write("otto.toml", BASE)

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return target

    def load(self):
        return load_records(load_workspace(self.root))

    def refuse(self, path, text, line, message):
        self.write(path, text)
        with self.assertRaises(LocatedError) as raised:
            self.load()
        self.assertEqual(str(raised.exception), f"{path}:{line}: {message}")

    def project(self, text, name="alpha"):
        return self.write(f"items/{name}/plan.md", text)

    def adapter(self, source):
        self.write("otto.toml", BASE + ADAPTER)
        self.write("items/strategy.txt", "First line\nSecond line\nThird line\n")
        self.write("reader.py", (
            "from otto.ids import RecordRef, SourceLocation\n"
            "from otto.records import Record, RecordBatch, RelationshipRow\n"
            "def checks(workspace): raise AssertionError('factory not called by reader')\n"
            "def views(workspace): raise AssertionError('factory not called by reader')\n"
            + source
        ))

    def adapter_refuse(self, source, message):
        self.adapter(source)
        line = (BASE + ADAPTER).splitlines().index('records = "records"') + 1
        with self.assertRaises(LocatedError) as raised:
            self.load()
        self.assertEqual(str(raised.exception), f"otto.toml:{line}: {message}")

    def test_headers_and_relationship_lines_ignore_fenced_and_body_examples(self):
        text = (
            "\n# A title\n"
            "**Status:** queued\n"
            "**Owner:** Example\n"
            "**Template:** loop\n"
            f"{FENCE}markdown\n"
            "**Status:** ignored\n"
            "## Relationships\n"
            "| bad example |\n"
            f"{FENCE}\n"
            "## Details\n"
            "**Status:** not machine metadata\n"
            "\n## Relationships\n\n"
            f"{HEADER}\n{SEPARATOR}\n"
            "| serves | goal:pillar:theme/aim | primary |\n"
            "| other-relation | arbitrary:unknown | unknown-role |\n"
        )
        self.project(text)
        workspace = load_workspace(self.root)
        record_path = "items/alpha/plan.md"
        batch = read_record(workspace, workspace.record_kinds[0], record_path)
        record = batch.records[0]
        self.assertEqual(record.ref, RecordRef("project", "alpha"))
        self.assertEqual(record.source, SourceLocation(record_path, 2))
        self.assertEqual(record.title, "A title")
        self.assertEqual(record.status, "queued")
        self.assertEqual(record.status_location, SourceLocation(record_path, 3))
        self.assertEqual(record.fields["Owner"], "Example")
        self.assertEqual(record.field_locations["Owner"], SourceLocation(record_path, 4))
        self.assertEqual(record.template_location, SourceLocation(record_path, 5))
        self.assertEqual(batch.relationships, (
            RelationshipRow(record.ref, "serves", RecordRef("goal", "pillar:theme/aim"),
                            "primary", record_path, 17),
            RelationshipRow(record.ref, "other-relation", RecordRef("arbitrary", "unknown"),
                            "unknown-role", record_path, 18),
        ))
        # OT-7 reads authored rows even when graph semantics later reject them.
        self.assertEqual(load_records(workspace), batch)
        with self.assertRaises(TypeError):
            record.fields["Owner"] = "Changed"

    def test_frontmatter_status_and_field_locations(self):
        self.write("items/short-example.md", (
            "---\nstatus: queued\nowner: Example\n---\n\n"
            "# Idea title\n**Template:** standard\n"
            "## Details\nText\n## Relationships\n"
            f"{HEADER}\n{SEPARATOR}\n"
            "| routes-to | project:alpha | supporting |\n"
        ))
        batch = self.load()
        record = batch.records[0]
        path = "items/short-example.md"
        self.assertEqual(record.ref, RecordRef("idea", "short-example"))
        self.assertEqual(record.source, SourceLocation(path, 6))
        self.assertEqual(record.status, "queued")
        self.assertEqual(record.status_location, SourceLocation(path, 2))
        self.assertEqual(record.fields["owner"], "Example")
        self.assertEqual(record.field_locations["owner"], SourceLocation(path, 3))
        self.assertEqual(record.template_location, SourceLocation(path, 7))
        self.assertEqual(batch.relationships[0].source_line, 13)

    def test_status_optional_and_empty_relationship_table(self):
        self.project(f"# No status\n## Relationships\n{HEADER}\n{SEPARATOR}\n")
        self.write("items/idea.md", "---\nowner: Example\n---\n# No status\n")
        result = self.load()
        self.assertEqual([r.status for r in result.records], [None, None])
        self.assertEqual(result.relationships, ())

    def test_markdown_title_and_duplicate_status(self):
        path = "items/alpha/plan.md"
        for text, line, message in [
            ("\n## Not a title\n", 2, "record document must start with a nonempty # title"),
            ("#   \n", 1, "record document must start with a nonempty # title"),
            ("# Title\n**Status:** queued\n**Status:** done\n", 3, "duplicate status field"),
        ]:
            with self.subTest(text=text):
                self.refuse(path, text, line, message)

    def test_frontmatter_exact_errors(self):
        path = "items/idea.md"
        cases = [
            ("# Missing frontmatter\n", 1, "missing frontmatter; the first line must be '---'"),
            ("---\nstatus: queued\n# Title\n", 1, "unclosed frontmatter; add a closing '---'"),
            ("---\nstatus: queued\nowner: \n---\n# Title\n", 3,
             "frontmatter fields must be nonempty single-line 'key: value' entries"),
            ("---\nowner: |\n  continuation\n---\n# Title\n", 3,
             "frontmatter fields must be nonempty single-line 'key: value' entries"),
            ("---\nowner: One\nowner: Two\n---\n# Title\n", 3, "duplicate frontmatter field 'owner'"),
            ("---\nstatus: queued\nstatus: done\n---\n# Title\n", 3, "duplicate status field"),
            ("---\nstatus: queued\n---\n# Title\n**Status:** done\n", 5, "duplicate status field"),
            ("---\nowner: Example\n---\n\n## Wrong title\n", 5,
             "record document must start with a nonempty # title"),
        ]
        for text, line, message in cases:
            with self.subTest(text=text):
                self.refuse(path, text, line, message)

    def test_relationship_table_exact_shape_errors(self):
        path = "items/alpha/plan.md"
        start = "# Title\n\n## Relationships\n\n"
        table = start + f"{HEADER}\n{SEPARATOR}\n"
        cases = [
            (start, 3, "expected Relation | Target | Role header"),
            (start + "| Role | Target | Relation |\n" + SEPARATOR + "\n", 5,
             "expected Relation | Target | Role header"),
            (start + HEADER + "\n", 5, "invalid separator row"),
            (start + HEADER + "\n| --- | --- | xx |\n", 6, "invalid separator row"),
            (table + "| serves | goal:aim |\n", 7, "expected exactly three cells"),
            (table + "| serves | goal:aim | primary | extra |\n", 7, "expected exactly three cells"),
            (table + "|| goal:aim | primary |\n", 7, "blank cell"),
            (table + "| serves | | primary |\n", 7, "blank cell"),
            (table + "Prose is not a relationship row.\n", 7, "non-table content"),
            (table + "| serves | untyped | primary |\n", 7, "invalid typed target reference"),
            (table + "| serves | goal:bad identity | primary |\n", 7, "invalid typed target reference"),
            (table + HEADER + "\n", 7, "expected Relation | Target | Role header"),
            (table + SEPARATOR + "\n", 7, "invalid separator row"),
            (table + "## Relationships\n", 7, "duplicate Relationships section"),
        ]
        for text, line, suffix in cases:
            with self.subTest(suffix=suffix, text=text):
                self.refuse(path, text, line, "invalid Relationships table: " + suffix)

    def test_duplicate_identity_and_invalid_component(self):
        self.refuse("items/Bad Slug/plan.md", "\n# Title\n", 2,
                    "invalid project identity component 'Bad Slug' for policy slug")
        (self.root / "items/Bad Slug/plan.md").unlink()
        self.write("otto.toml", BASE.replace('policy = "slug"\nsource = "parent"', 'policy = "NN-slug"\nsource = "parent"'))
        self.project("# First\n", "01-first")
        self.refuse("items/01-second/plan.md", "\n# Second\n", 2, "duplicate record identity")

    def test_adapter_one_call_and_mixed_provenance(self):
        self.project("# Alpha\n")
        self.adapter(
            "calls = 0\n"
            "def records(workspace):\n"
            "    global calls\n"
            "    calls += 1\n"
            "    assert calls == 1\n"
            "    first = RecordRef('goal', 'clear-aim')\n"
            "    second = RecordRef('goal', 'second-aim')\n"
            "    records = (Record(first, SourceLocation('items/strategy.txt', 2, 'first'), 'Clear aim'),\n"
            "               Record(second, SourceLocation('items/strategy.txt', 3, 'second')))\n"
            "    edges = (RelationshipRow(first, 'authored-in', RecordRef('project', 'alpha'), 'example', 'items/alpha/plan.md', 1),)\n"
            "    return RecordBatch(records, edges)\n"
        )
        workspace = load_workspace(self.root)
        first_export = workspace.export("records", declaration=("adapters", "records"))
        self.assertIs(first_export, workspace.export("records", declaration=("adapters", "records")))
        result = load_records(workspace)
        self.assertEqual([str(r.ref) for r in result.records],
                         ["project:alpha", "goal:clear-aim", "goal:second-aim"])
        self.assertEqual(result.relationships[0].source_path, "items/alpha/plan.md")
        index = result.resolver()
        self.assertEqual(index.refs_at("items/strategy.txt"),
                         (RecordRef("goal", "clear-aim"), RecordRef("goal", "second-aim")))
        self.assertEqual(index.refs_at("items/strategy.txt", anchor="second"),
                         (RecordRef("goal", "second-aim"),))

    def test_adapter_invalid_shape_and_undeclared_or_generic_kind(self):
        for expression in (
            "None",
            "RecordBatch([], ())",
            "RecordBatch(('not a record',), ())",
            "RecordBatch((Record(RecordRef('other', 'valid'), SourceLocation('items/strategy.txt', 1)),), ())",
            "RecordBatch((Record(RecordRef('project', 'valid'), SourceLocation('items/strategy.txt', 1)),), ())",
            "RecordBatch((), ('not a row',))",
        ):
            with self.subTest(expression=expression):
                self.adapter_refuse("def records(workspace): return " + expression + "\n",
                                    "adapter export 'records' returned an invalid RecordBatch")

    def test_adapter_provenance_at_registration_not_fabricated_line_one(self):
        for location in (
            "SourceLocation('items/strategy.txt', 0)",
            "SourceLocation('items/strategy.txt', True)",
            "SourceLocation('items/strategy.txt', 4)",
            "SourceLocation('../outside', 1)",
            "SourceLocation('items/missing.txt', 1)",
            "None",
        ):
            with self.subTest(location=location):
                self.adapter_refuse(
                    "def records(workspace):\n"
                    f"    return RecordBatch((Record(RecordRef('goal', 'valid'), {location}),), ())\n",
                    "adapter export 'records' returned invalid source location for goal:valid")
        self.adapter_refuse(
            "def records(workspace):\n"
            "    r = Record(RecordRef('goal', 'valid'), SourceLocation('items/strategy.txt', 1), fields={'owner':'Example'})\n"
            "    return RecordBatch((r,), ())\n",
            "adapter export 'records' returned invalid source location for goal:valid")
        self.adapter_refuse(
            "def records(workspace):\n"
            "    edge = RelationshipRow(RecordRef('goal', 'valid'), 'serves', RecordRef('project', 'unknown'), 'primary', 'items/strategy.txt', 0)\n"
            "    return RecordBatch((), (edge,))\n",
            "adapter export 'records' returned invalid source location for goal:valid")

    def test_adapter_identity_validated_against_policy_not_locator(self):
        self.adapter(
            "def records(workspace):\n"
            "    r = Record(RecordRef('goal', 'Uppercase'), SourceLocation('items/strategy.txt', 2))\n"
            "    return RecordBatch((r,), ())\n"
        )
        with self.assertRaises(LocatedError) as raised:
            self.load()
        self.assertEqual(str(raised.exception), "items/strategy.txt:2: invalid goal identity: 'Uppercase'")
        self.adapter_refuse(
            "def records(workspace): return RecordBatch((Record(RecordRef('goal', 'bad identity'), SourceLocation('items/strategy.txt', 2)),), ())\n",
            "invalid goal identity: 'bad identity'")


if __name__ == "__main__":
    unittest.main()
