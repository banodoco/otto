"""OT-7 configuration contract and authored-location refusal fixtures."""
from pathlib import Path
import os
import re
import shutil
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from otto.config import load_workspace, read_declaration
from otto.ids import LocatedError


MINIMAL = '''version = 1

[workspace]
name = "sample"
skill_namespace = "sample-"
'''
RECORDS = '''
[paths]
items = "items"

[ids.project]
policy = "slug"
source = "parent"

[[record_kinds]]
name = "project"
root = "items"
files = ["*/plan.md"]
reader = "headers"
pack = true
'''
RELATIONS = '''
[[relation_kinds]]
name = "serves"
sources = ["project"]
targets = ["project"]
roles = ["primary"]

[relation_kinds.by_role.primary]
per_source = "any"
'''
ADAPTER = '''
[adapters]
module = "reader.py"
records = "records"

[checks]
register = "checks"

[views]
register = "views"
marker_prefix = "<!-- Example: "
hint = "refresh"
'''


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "items").mkdir()
        self.config = self.root / "otto.toml"

    def load(self, text):
        self.config.write_text(text, encoding="utf-8")
        return load_workspace(self.root)

    def refuse(self, text, line, message):
        with self.assertRaises(LocatedError) as raised:
            self.load(text)
        self.assertEqual(str(raised.exception), f"otto.toml:{line}: {message}")

    def at(self, text, needle, *, occurrence=1):
        lines = [n for n, line in enumerate(text.splitlines(), 1) if needle in line]
        return lines[occurrence - 1]

    def changed(self, text, old, new, needle, message):
        text = text.replace(old, new, 1)
        self.refuse(text, self.at(text, needle), message)

    def adapter(self, text="def records(workspace): return None\n"
                           "def checks(workspace): return ()\n"
                           "def views(workspace): return ((), [])\n"):
        (self.root / "reader.py").write_text(text, encoding="utf-8")

    def test_config_root_missing_and_config_file_missing(self):
        absent = self.root / "absent"
        with self.assertRaises(ValueError) as raised:
            load_workspace(absent)
        self.assertEqual(str(raised.exception),
                         f"workspace root is not an existing directory: {absent}")
        with self.assertRaises(ValueError) as raised:
            load_workspace(self.root)
        self.assertEqual(str(raised.exception), f"no otto.toml found in {self.root}")
        self.config.write_text(MINIMAL)
        with self.assertRaises(ValueError) as raised:
            load_workspace(self.root / "items")
        self.assertEqual(str(raised.exception), f"no otto.toml found in {self.root / 'items'}")

    def test_toml_syntax_uses_parser_line_and_reason(self):
        text = MINIMAL + 'bad = "unclosed\n'
        with self.assertRaises(tomllib.TOMLDecodeError) as parsed:
            tomllib.loads(text)
        self.refuse(text, 6, f"invalid TOML: {parsed.exception}")
        text = MINIMAL + "bad = [1,"
        with self.assertRaises(tomllib.TOMLDecodeError) as parsed:
            tomllib.loads(text)
        self.refuse(text, 6, f"invalid TOML: {parsed.exception}")

    def test_version_name_namespace(self):
        cases = [
            ("version = 1", "version = 2", "version =", "unsupported declaration version 2; expected 1"),
            ("version = 1", "version = true", "version =", "version must be an integer"),
            ('name = "sample"', 'name = "Bad Name"', "name =", "invalid workspace name 'Bad Name'; expected lowercase kebab-case"),
            ('name = "sample"', 'name = ""', "name =", "invalid workspace name ''; expected lowercase kebab-case"),
            ('skill_namespace = "sample-"', 'skill_namespace = "sample"', "skill_namespace =", "skill namespace must be lowercase kebab-case with a trailing hyphen"),
        ]
        for old, new, needle, message in cases:
            with self.subTest(message=message):
                self.changed(MINIMAL, old, new, needle, message)

    def test_blank_and_immutable_config_defaults(self):
        workspace = self.load(MINIMAL)
        self.assertEqual(workspace.root, self.root)
        self.assertEqual(workspace.name, "sample")
        self.assertEqual(workspace.skill_namespace, "sample-")
        self.assertEqual(workspace.record_kinds, ())
        self.assertEqual(workspace.relation_kinds, ())
        self.assertEqual(dict(workspace.sources), {})
        self.assertEqual(workspace.paths["agent"], self.root / "agent")
        self.assertEqual(workspace.paths["skills_output"], self.root / ".generated/skills")
        self.assertNotIn("pack_templates", workspace.paths)
        self.assertFalse((self.root / "agent").exists())
        self.assertFalse((self.root / ".generated").exists())
        with self.assertRaises(TypeError):
            workspace.paths["agent"] = self.root

    def test_pin_diagnostics(self):
        prefix = MINIMAL + "\n[otto]\n"
        bad = prefix + 'commit = "NotHex"\n'
        self.refuse(bad, self.at(bad, "commit ="), "otto.commit must be 40 lowercase hex characters")
        bad = prefix + 'tag = "v0"\n'
        self.refuse(bad, self.at(bad, "tag ="), "otto.tag requires otto.commit")
        bad = prefix + f'commit = "{"a"*40}"\ntag = ""\n'
        self.refuse(bad, self.at(bad, "tag ="), "otto.tag must be nonempty")
        good = prefix + f'commit = "{"a"*40}"\ntag = "v0"\n'
        self.assertEqual(self.load(good).config.otto.tag, "v0")

    def test_closed_tables_unknown_key(self):
        self.adapter()
        text = MINIMAL + RECORDS + RELATIONS + ADAPTER
        # Each insertion is in the named real table (not the first textual
        # occurrence of the key or value).
        cases = [
            ("version = 1", "otto.toml"),
            ("[workspace]", "workspace"),
            ("[ids.project]", "ids.project"),
            ("[[record_kinds]]", "record_kinds"),
            ("[[relation_kinds]]", "relation_kinds"),
            ("[relation_kinds.by_role.primary]", "relation_kinds.by_role.primary"),
            ("[adapters]", "adapters"),
            ("[checks]", "checks"),
            ("[views]", "views"),
        ]
        for header, scope in cases:
            with self.subTest(scope=scope):
                bad = text.replace(header, header + '\nnam = "unused"', 1)
                self.refuse(bad, self.at(bad, 'nam = "unused"'), f"unknown key 'nam' in {scope}")
        bad = MINIMAL + '\n[otto]\ncommit = "' + "a"*40 + '"\nnam = 0\n'
        self.refuse(bad, self.at(bad, "nam ="), "unknown key 'nam' in otto")

    def test_missing_required_keys_at_table_headers(self):
        self.adapter()
        text = MINIMAL + RECORDS + RELATIONS + ADAPTER
        cases = [
            ('name = "sample"\n', "[workspace]", "workspace", "name"),
            ('skill_namespace = "sample-"\n', "[workspace]", "workspace", "skill_namespace"),
            ('policy = "slug"\n', "[ids.project]", "ids.project", "policy"),
            ('source = "parent"\n', "[ids.project]", "ids.project", "source"),
            ('name = "project"\n', "[[record_kinds]]", "record_kinds", "name"),
            ('root = "items"\n', "[[record_kinds]]", "record_kinds", "root"),
            ('files = ["*/plan.md"]\n', "[[record_kinds]]", "record_kinds", "files"),
            ('reader = "headers"\n', "[[record_kinds]]", "record_kinds", "reader"),
            ('name = "serves"\n', "[[relation_kinds]]", "relation_kinds", "name"),
            ('sources = ["project"]\n', "[[relation_kinds]]", "relation_kinds", "sources"),
            ('targets = ["project"]\n', "[[relation_kinds]]", "relation_kinds", "targets"),
            ('roles = ["primary"]\n', "[[relation_kinds]]", "relation_kinds", "roles"),
            ('register = "checks"\n', "[checks]", "checks", "register"),
            ('register = "views"\n', "[views]", "views", "register"),
        ]
        for old, header, scope, field in cases:
            with self.subTest(field=field, scope=scope):
                bad = text.replace(old, "", 1)
                self.refuse(bad, self.at(bad, header), f"missing required key {field!r} in {scope}")
        self.refuse(MINIMAL.replace("version = 1\n", ""), 1,
                    "missing required key 'version' in otto.toml")
        bad = MINIMAL + "\n[otto]\n"
        self.refuse(bad, self.at(bad, "[otto]"), "missing required key 'commit' in otto")
        bad = (MINIMAL + RECORDS).replace('policy = "slug"', 'policy = "regex"')
        self.refuse(bad, self.at(bad, "[ids.project]"), "missing required key 'pattern' in ids.project")

    def test_types_parameterized(self):
        self.adapter()
        text = MINIMAL + RECORDS + RELATIONS + ADAPTER
        cases = [
            ('name = "sample"', 'name = false', "workspace.name must be a string"),
            ('skill_namespace = "sample-"', 'skill_namespace = 2', "workspace.skill_namespace must be a string"),
            ('items = "items"', 'items = 2', "paths.items must be a string"),
            ('policy = "slug"', 'policy = 2', "ids.project.policy must be a string"),
            ('source = "parent"', 'source = []', "ids.project.source must be a string"),
            ('name = "project"', 'name = 4', "record_kinds.name must be a string"),
            ('root = "items"', 'root = false', "record_kinds.root must be a string"),
            ('files = ["*/plan.md"]', 'files = 4', "record_kinds.files must be an array of strings"),
            ('files = ["*/plan.md"]', 'files = [4]', "record_kinds.files must be an array of strings"),
            ('reader = "headers"', 'reader = 3', "record_kinds.reader must be a string"),
            ('pack = true', 'pack = 1', "record_kinds.pack must be a boolean"),
            ('name = "serves"', 'name = []', "relation_kinds.name must be a string"),
            ('sources = ["project"]', 'sources = "project"', "relation_kinds.sources must be an array of strings"),
            ('targets = ["project"]', 'targets = false', "relation_kinds.targets must be an array of strings"),
            ('roles = ["primary"]', 'roles = [false]', "relation_kinds.roles must be an array of strings"),
            ('per_source = "any"', 'per_source = 1', "relation_kinds.by_role.primary.per_source must be a string"),
            ('module = "reader.py"', 'module = false', "adapters.module must be a string"),
            ('records = "records"', 'records = false', "adapters.records must be a string"),
            ('register = "checks"', 'register = 1', "checks.register must be a string"),
            ('register = "views"', 'register = 1', "views.register must be a string"),
            ('marker_prefix = "<!-- Example: "', 'marker_prefix = true', "views.marker_prefix must be a string"),
            ('hint = "refresh"', 'hint = []', "views.hint must be a string"),
        ]
        for old, new, message in cases:
            with self.subTest(message=message):
                # In the two register cases the replacement may duplicate
                # the text, but the source line is taken from the changed text.
                self.changed(text, old, new, new, message)
        for field in ("otto", "workspace", "paths", "ids", "adapters", "checks", "views"):
            with self.subTest(table=field):
                if field == "workspace":
                    bad = 'version = 1\nworkspace = false\n'
                else:
                    bad = f'version = 1\n{field} = false\n' + MINIMAL.split("\n", 1)[1]
                self.refuse(bad, 2, f"{field} must be a table")
        for field in ("record_kinds", "relation_kinds"):
            for value in ('"wrong"', '[1]'):
                with self.subTest(field=field, value=value):
                    bad = f"version = 1\n{field} = {value}\n" + MINIMAL.split("\n", 1)[1]
                    self.refuse(bad, 2, f"{field} must be an array of tables")

    def test_source_map_repeated_array_tables_and_multiline_escaped_values(self):
        text = '''version = 1
[workspace]
name = "sample"
skill_namespace = "sample-"
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
[[record_kinds]]
name = "idea"
root = "items"
files = [
    "*.md", # this is not another table
]
reader = "frontmatter"
"n\\u0061m" = """
fake = "[[record_kinds]]"
[workspace]
"""
'''
        self.refuse(text, self.at(text, '"n\\u0061m"'), "unknown key 'nam' in record_kinds")
        self.config.write_text(text, encoding="utf-8")
        data, source = read_declaration(self.config)
        self.assertEqual(data["record_kinds"][1]["nam"], 'fake = "[[record_kinds]]"\n[workspace]\n')
        self.assertEqual(source.line(("record_kinds", 0, "name")), 14)
        self.assertEqual(source.line(("record_kinds", 1, "name")), 19)
        self.assertEqual(source.line(("record_kinds", 1, "files", 0)), 22)
        self.assertEqual(source.line(("record_kinds", 1, "missing")), 18)
        self.assertEqual(source.line(("record_kinds", 1, "nam")), 25)

    def test_source_map_dotted_inline_and_nested_role_occurrences(self):
        text = '''version = 1
workspace.name = "sample"
workspace.skill_namespace = "sample-"
record_kinds = [
    {name = "project", root = "items", files = ["*.md"], reader = "headers"},
    {name = "idea", root = "items", files = ["*.md"], reader = "frontmatter", typo = true},
]
[paths]
items = "items"
[ids.project]
policy = "slug"
source = "stem"
[ids.idea]
policy = "slug"
source = "stem"
'''
        self.refuse(text, 6, "unknown key 'typo' in record_kinds")
        nested = MINIMAL + RECORDS + RELATIONS + RELATIONS.replace('name = "serves"', 'name = "routes"').replace('per_source = "any"', 'per_source = "any"\nwrong = "any"')
        self.refuse(nested, self.at(nested, "wrong ="), "unknown key 'wrong' in relation_kinds.by_role.primary")
        good = MINIMAL + RECORDS + RELATIONS
        source = self.load(good).source_map
        self.assertEqual(source.line(("relation_kinds", 0, "by_role", "primary", "per_source")),
                         self.at(good, "per_source ="))

    def test_duplicate_kind_at_second_entry(self):
        text = MINIMAL + RECORDS + RECORDS[RECORDS.index("[[record_kinds]]"):]
        self.refuse(text, self.at(text, 'name = "project"', occurrence=2), "duplicate record kind 'project'")

    def test_kind_reader_files_and_empty_name(self):
        base = MINIMAL + RECORDS
        cases = [
            ('name = "project"', 'name = "Project Items"', "invalid record kind name 'Project Items'; expected lowercase kebab-case"),
            ('name = "project"', 'name = ""', "record_kinds.name must be a nonempty string"),
            ('reader = "headers"', 'reader = "unknown"', "unknown reader 'unknown'; expected headers, frontmatter or adapter"),
            ('files = ["*/plan.md"]', 'files = []', "record kind project requires at least one source pattern"),
            ('files = ["*/plan.md"]', 'files = [""]', "invalid source pattern '': empty path"),
            ('files = ["*/plan.md"]', 'files = ["../outside"]', "invalid source pattern '../outside': parent components are not allowed"),
            ('files = ["*/plan.md"]', 'files = ["x**.md"]', "invalid source pattern 'x**.md': '**' must be a complete path component"),
        ]
        for old, new, message in cases:
            with self.subTest(message=message):
                self.changed(base, old, new, new, message)
        good = base.replace('files = ["*/plan.md"]', 'files = ["*/plan.md", "*/plan.md"]')
        self.assertEqual(self.load(good).record_kinds[0].files, ("*/plan.md",))

    def test_id_declarations(self):
        text = MINIMAL + RECORDS
        cases = [
            ('policy = "slug"', 'policy = "other"', "unknown ID policy 'other'"),
            ('source = "parent"', 'source = "unknown"', "unknown ID source 'unknown'; expected parent, stem, adapter"),
            ('source = "parent"', 'source = "adapter"', "ID source 'adapter' is incompatible with reader 'headers'"),
            ('policy = "slug"', 'policy = "slug"\npattern = "x"', "pattern is only valid for regex ID policy"),
        ]
        for old, new, message in cases:
            with self.subTest(message=message):
                self.changed(text, old, new, new.splitlines()[-1], message)
        bad = text.replace('policy = "slug"', 'policy = "regex"\npattern = "["')
        try:
            re.compile("[")
        except re.error as exc:
            expected = f"invalid ID regex for project: {exc}"
        self.refuse(bad, self.at(bad, "pattern ="), expected)
        bad = text.replace("[ids.project]", "[ids.unknown]")
        self.refuse(bad, self.at(bad, "[ids.unknown]"), "ID policy names unknown kind 'unknown'")
        bad = text.replace('[ids.project]\npolicy = "slug"\nsource = "parent"\n', "")
        self.refuse(bad, self.at(bad, 'name = "project"'), "missing ID policy for kind project")
        self.changed(text, 'reader = "headers"', 'reader = "adapter"', 'source = "parent"',
                     "ID source 'parent' is incompatible with reader 'adapter'")

    def test_paths_escape_type_unknown_unused_and_overlap(self):
        text = MINIMAL + RECORDS
        for path in ('../outside', '/absolute', 'C:/outside', 'C:outside', r'x\\y'):
            with self.subTest(path=path):
                # Literal TOML string preserves the backslashes exactly.
                bad = text.replace('items = "items"', f"items = '{path}'")
                self.refuse(bad, self.at(bad, "items ="), "paths.items must resolve inside the workspace root")
        (self.root / "file").write_text("not a directory")
        self.changed(text, 'items = "items"', 'items = "file"', "items =", "paths.items must name a directory")
        self.changed(text, 'items = "items"', 'items = "missing"', "items =", "paths.items must name a directory")
        bad = text.replace('[paths]', '[paths]\nprojetcs = "items"')
        self.refuse(bad, self.at(bad, "projetcs ="), "unused record root 'projetcs'")
        self.changed(text, 'root = "items"', 'root = "missing"', "root =", "record kind project names unknown root 'missing'")
        bad = text.replace('[paths]', '[paths]\nagent = "guide"\nskills_output = "guide/generated"')
        self.refuse(bad, self.at(bad, "skills_output ="), "skill source and output roots must not overlap")
        # §13.1: a record root (including .) may contain generated output.
        valid = text.replace('items = "items"', 'items = "."')
        self.assertEqual(self.load(valid).paths["items"], self.root)
        bad = text.replace('[paths]', '[paths]\npack_templates = "missing"')
        self.refuse(bad, self.at(bad, "pack_templates ="), "paths.pack_templates must name a directory")

    def symlink(self, path, target, *, directory=False):
        try:
            path.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable on this host")

    def test_contained_source_alias_and_escaped_or_dangling_paths(self):
        text = MINIMAL + RECORDS
        project = self.root / "items/alpha"
        project.mkdir()
        (project / "plan.md").write_text("# Alpha\n")
        self.symlink(self.root / "alias", self.root / "items", directory=True)
        valid = text.replace('items = "items"', 'items = "alias"')
        self.assertEqual(self.load(valid).sources["project"], ("alias/alpha/plan.md",))
        with tempfile.TemporaryDirectory() as outside:
            self.symlink(self.root / "escape", Path(outside), directory=True)
            bad = text.replace('items = "items"', 'items = "escape"')
            self.refuse(bad, self.at(bad, "items ="), "paths.items must resolve inside the workspace root")
            self.symlink(project / "other.md", Path(outside) / "lost")
            # Existing literal root alias escape is diagnosed at the pattern.
            bad = text.replace('files = ["*/plan.md"]', 'files = ["*/*.md"]').replace("pack = true", "pack = false")
            self.refuse(bad, self.at(bad, "files ="), "paths.items must resolve inside the workspace root")
        self.symlink(self.root / "dangling", self.root / "gone", directory=True)
        bad = text.replace('items = "items"', 'items = "dangling"')
        self.refuse(bad, self.at(bad, "items ="), f"cannot read dangling: {os.strerror(2)}")
        bad = text.replace('[paths]', '[paths]\nskills_output = "alias/out"')
        self.refuse(bad, self.at(bad, "skills_output ="), "paths.skills_output must not be or pass through a symlink")

    def test_discovery_sorted_deduplicated_and_pack_source(self):
        for name in ("zeta", "alpha"):
            path = self.root / "items" / name
            path.mkdir()
            (path / "plan.md").write_text("# Example\n")
        text = MINIMAL + RECORDS
        duplicate = text.replace('files = ["*/plan.md"]', 'files = ["*/plan.md", "**/plan.md"]')
        self.assertEqual(self.load(duplicate).sources["project"],
                         ("items/alpha/plan.md", "items/zeta/plan.md"))
        (self.root / "items/alpha/not-plan.md").write_text("# Example")
        bad = text.replace('files = ["*/plan.md"]', 'files = ["*/*.md"]')
        self.refuse(bad, self.at(bad, "files ="),
                    "record kind project sets pack = true but its pattern matched 'items/alpha/not-plan.md', which is not named plan.md")

    def test_adapter_module_and_export_declarations(self):
        base = (MINIMAL + RECORDS).replace('source = "parent"', 'source = "adapter"').replace('reader = "headers"', 'reader = "adapter"')
        self.refuse(base, 1, "adapter record kinds require adapters.module and adapters.records")
        text = base + ADAPTER
        self.refuse(text, self.at(text, 'module ='), "adapter module does not exist: reader.py")
        self.adapter()
        self.changed(text, 'module = "reader.py"', 'module = "reader.txt"', "module =",
                     "adapters.module must name a .py file inside the workspace")
        self.changed(text, 'records = "records"', 'records = "obj.method"', "records =",
                     "adapter export name 'obj.method' must be a bare identifier")
        for old, new, message in [
            ('records = "records"', 'records = "missing"', "adapter export 'missing' is missing or not callable"),
            ('register = "checks"', 'register = "missing"', "adapter export 'missing' is missing or not callable"),
            ('register = "views"', 'register = "missing"', "adapter export 'missing' is missing or not callable"),
        ]:
            # use exact changed position, not first occurrence of 'missing'
            with self.subTest(old=old):
                self.changed(text, old, new, new, message)
        bad = MINIMAL + '\n[checks]\nregister = "checks"\n'
        self.refuse(bad, self.at(bad, "register ="), "registrations require adapters.module")
        self.adapter("raise RuntimeError('example failure')\n")
        self.refuse(text, self.at(text, "module ="), "cannot load adapter reader.py: example failure")

    def test_registration_exports_can_be_validated_later(self):
        text = MINIMAL + ADAPTER
        self.config.write_text(text, encoding="utf-8")
        for name, other in (("checks", "views"), ("views", "checks")):
            for bad in ("", f"{name} = None\n"):
                with self.subTest(name=name, bad=bad):
                    self.adapter("def records(workspace): return None\n"
                                 f"def {other}(workspace): return ()\n" + bad)
                    line = self.at(text, f'register = "{name}"')
                    expected = (f"otto.toml:{line}: "
                                f"adapter export '{name}' is missing or not callable")
                    with self.assertRaises(LocatedError) as eager:
                        load_workspace(self.root)
                    self.assertEqual(str(eager.exception), expected)
                    workspace = load_workspace(self.root, validate_registrations=False)
                    self.assertTrue(callable(workspace.export(other, declaration=(other, "register"))))
                    with self.assertRaises(LocatedError) as deferred:
                        workspace.export(name, declaration=(name, "register"))
                    self.assertEqual(str(deferred.exception), expected)

    def test_deferred_registration_validation_keeps_records_export_eager(self):
        text = MINIMAL + ADAPTER
        self.config.write_text(text, encoding="utf-8")
        self.adapter("records = None\nchecks = None\nviews = None\n")
        with self.assertRaises(LocatedError) as raised:
            load_workspace(self.root, validate_registrations=False)
        self.assertEqual(str(raised.exception),
                         f"otto.toml:{self.at(text, 'records =')}: adapter export 'records' is missing or not callable")

    def test_unreadable_config_and_inventory(self):
        self.config.write_text(MINIMAL, encoding="utf-8")
        with patch.object(Path, "read_text", side_effect=PermissionError(13, os.strerror(13))):
            with self.assertRaises(LocatedError) as raised:
                load_workspace(self.root)
        self.assertEqual(str(raised.exception), f"otto.toml:1: cannot read otto.toml: {os.strerror(13)}")
        text = MINIMAL + RECORDS
        self.config.write_text(text, encoding="utf-8")
        real_scandir = os.scandir
        def deny_items(path):
            if Path(path) == self.root / "items":
                raise PermissionError(13, os.strerror(13))
            return real_scandir(path)
        with patch("otto.config.os.scandir", side_effect=deny_items):
            with self.assertRaises(LocatedError) as raised:
                load_workspace(self.root)
        self.assertEqual(str(raised.exception), f"otto.toml:{self.at(text, 'items =')}: cannot read items: {os.strerror(13)}")

    def test_relation_shape_is_closed_but_semantics_are_deferred(self):
        text = MINIMAL + RECORDS + RELATIONS
        bad = text.replace('roles = ["primary"]', 'roles = [""]')
        self.refuse(bad, self.at(bad, "roles ="), "relation_kinds.roles must be a nonempty string")
        # OT-8, not OT-7, validates endpoints, role duplicates and cardinality.
        deferred = text.replace('sources = ["project"]', 'sources = ["unknown"]').replace('roles = ["primary"]', 'roles = ["primary", "primary"]').replace('per_source = "any"', 'per_source = "not-a-cardinality"')
        result = self.load(deferred)
        self.assertEqual(result.relation_kinds[0]["sources"], ("unknown",))
        self.assertEqual(result.relation_kinds[0]["roles"], ("primary", "primary"))
        with self.assertRaises(TypeError):
            result.relation_kinds[0]["by_role"]["primary"]["per_source"] = "any"

    def test_unchanged_specimens_load_only_with_materialized_inputs(self):
        fixtures = Path(__file__).parent / "fixtures"
        for name in ("dev", "marketing"):
            with self.subTest(specimen=name), tempfile.TemporaryDirectory() as folder:
                original = fixtures / name / "otto.toml"
                raw = original.read_bytes()
                data = tomllib.loads(raw.decode())
                root = Path(folder).resolve()
                shutil.copyfile(original, root / "otto.toml")
                # Bare specimens lack real source roots and modules.
                with self.assertRaises(LocatedError) as raised:
                    load_workspace(root)
                projects_line = self.at(raw.decode(), 'projects =')
                self.assertEqual(str(raised.exception),
                                 f"otto.toml:{projects_line}: paths.projects must name a directory")
                paths = data["paths"]
                for kind in data["record_kinds"]:
                    (root / paths[kind["root"]]).mkdir(parents=True, exist_ok=True)
                if "pack_templates" in paths:
                    (root / paths["pack_templates"]).mkdir(parents=True, exist_ok=True)
                adapter = root / data["adapters"]["module"]
                adapter.parent.mkdir(parents=True, exist_ok=True)
                # No specimen data, only the exact registered export names.
                adapter.write_text(
                    "from otto.records import RecordBatch\n"
                    + f"def {data['adapters']['records']}(workspace): return RecordBatch()\n"
                    + f"def {data['checks']['register']}(workspace): return ()\n"
                    + f"def {data['views']['register']}(workspace): return ((), [])\n",
                    encoding="utf-8",
                )
                workspace = load_workspace(root)
                self.assertEqual(workspace.name, data["workspace"]["name"])
                self.assertEqual(len(workspace.record_kinds), len(data["record_kinds"]))
                self.assertEqual(dict(workspace.sources), {kind["name"]: () for kind in data["record_kinds"]})
                self.assertEqual((root / "otto.toml").read_bytes(), raw)
                self.assertEqual(original.read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
