"""Explicit fragment targets: only the Lead-approved empty anchor subset."""
import tempfile
import unittest
from pathlib import Path

from otto import checks
from otto.markdown import markdown_fragment_targets, markdown_heading_anchors


GHOST = '<a id="ghost"></a>'
BEFORE = '<a id="before"></a>'
AFTER = '<a id="after"></a>'
# The nine literal token shapes from the motivating table, in a neutral
# synthetic document. The Lead additionally checks the original repository.
ROW_IDS = ("at1-9", "at1-54", "at1-10", "at9", "rt1", "rt2", "pt2", "k2", "k3")
DECOYS = {
    "backtick fence": "\x60\x60\x60html\n" + GHOST + "\n\x60\x60\x60",
    "long fence": "\x60\x60\x60\x60html\n\x60\x60\x60\n" + GHOST + "\n\x60\x60\x60\x60",
    "tilde fence": "~~~html\n" + GHOST + "\n~~~",
    "indented code": "    " + GHOST,
    "tab-indented code": "\t" + GHOST,
    "quote fence": "> \x60\x60\x60html\n> " + GHOST + "\n> \x60\x60\x60",
    "list fence": "- \x60\x60\x60html\n  " + GHOST + "\n  \x60\x60\x60",
    "list continuation": "- An example\n  " + GHOST,
    "lazy quote continuation": "> An example\n" + GHOST,
    "list with blank": "- An example\n\n  " + GHOST,
    "inline code": "Example \x60" + GHOST + "\x60.",
    "long inline code": "Example \x60\x60 \x60 " + GHOST + " \x60 \x60\x60.",
    "multiline inline code": "Example \x60\x60 begins\n" + GHOST + "\nends \x60\x60.",
    "inline comment": "Example <!-- " + GHOST + " -->.",
    "multiline comment": "<!--\n\n\x60\x60\x60\n" + GHOST + "\n\x60\x60\x60\n-->",
    "escaped tag": "\\" + GHOST,
    "entity-escaped tag": '&lt;a id="ghost"&gt;&lt;/a&gt;',
    "raw html block": "<div>\n" + GHOST + "\n</div>",
    "inline raw html": "Example <code>" + GHOST + "</code>.",
    "nested raw html": "<div><div></div>" + GHOST + "</div>",
    "pre comment": "<pre><!-- </pre> -->" + GHOST + "</pre>",
    "script": "<script>\n" + GHOST + "\n</script>",
    "style": "<style>\n" + GHOST + "\n</style>",
    "textarea": "<textarea>" + GHOST + "</textarea>",
    "raw attribute": "Example <span title='" + GHOST + "'>text</span>.",
    "inline link title": "[label](elsewhere 'title ) " + GHOST + " end')",
    "multiline link title": "[label](elsewhere 'title\n" + GHOST + "\nend')",
    "link destination": "[label](<" + GHOST + ">)",
    "link label": "[" + GHOST + "](elsewhere)",
    "reference title": "[ref]: elsewhere '" + GHOST + "'",
    "reference continuation": "[ref]: elsewhere\n  '" + GHOST + "'",
    "reference multiline title": "[ref]: elsewhere 'title\n" + GHOST + "\nend'",
    "reference destination": "[ref]:\n  <" + GHOST + ">",
    "unquoted": "<a id=ghost></a>",
    "extra attribute": '<a id="ghost" title="x"></a>',
    "duplicate attribute": '<a id="ghost" id="other"></a>',
    "nonempty body": '<a id="ghost">text</a>',
    "whitespace body": '<a id="ghost"> </a>',
    "non-anchor element": '<span id="ghost"></span>',
    "self closing": '<a id="ghost"/>',
    "name only": '<a name="ghost"></a>',
}


def anchor(token):
    return f'<a id="{token}"></a>'


def table(ids=ROW_IDS):
    return ("# Archive\n\n| Row | State |\n| --- | --- |\n"
            + "".join(f"| Example {anchor(token)} text | ready |\n" for token in ids))


def findings(files, *, excluded=None, **kwargs):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory).resolve()
        for name, body in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        return checks._link_anchors(
            checks.Context(root), excluded=root / excluded if excluded is not None else None,
            **kwargs)


def missing(source, target, token, line=None):
    location = source if line is None else f"{source}:{line}"
    return (f"{location}: link to {target}#{token} matches no heading in that file; "
            "point the link at a heading that exists")


class FragmentTargetTests(unittest.TestCase):
    def test_heading_parser_is_unchanged_and_ids_are_a_separate_namespace(self):
        text = ("# Example\n\n## Same heading\n\n## Same heading\n\n"
                "## Use \x60check\x60 and [sync](sync.md)\n\n"
                + anchor("same-heading") + " " + anchor("Same-heading") + " "
                + anchor("same-heading") + "\n")
        expected = [(1, "Example", "example"),
                    (2, "Same heading", "same-heading"),
                    (2, "Same heading", "same-heading-1"),
                    (2, "Use \x60check\x60 and [sync](sync.md)", "use-check-and-sync")]
        self.assertEqual(markdown_heading_anchors(text), expected)
        self.assertEqual(markdown_fragment_targets(text),
                         {item[2] for item in expected} | {"Same-heading"})
        duplicate = anchor("Repeat") + " " + anchor("Repeat")
        self.assertEqual(markdown_fragment_targets(duplicate), {"Repeat"})

    def test_approved_quoted_grammar_in_prose_and_cells(self):
        text = ("Before <A ID \t= 'Row_1:part.2' \t></a > after. "
                '<a id="row_1:part.2"></a>\n\n'
                "| First | Middle | Last |\n| --- | --- | --- |\n"
                f"| {anchor('first')} | {anchor('middle')} {anchor('another')} | {anchor('last')} |\n"
                "Unmatched \x60 prose " + anchor("literal-tick") + "\n\n"
                "Unmatched [ prose " + anchor("literal-bracket") + "\n\n"
                "\\\\" + anchor("even-escape") + "\n")
        self.assertEqual(markdown_fragment_targets(text),
                         {"Row_1:part.2", "row_1:part.2", "first", "middle",
                          "another", "last", "literal-tick", "literal-bracket", "even-escape"})
        invalid = ('<a id=""></a> <a id="white space"></a> <a id="café"></a> '
                   '<a id="x&amp;y"></a> <a id="a\\b"></a>')
        self.assertEqual(markdown_fragment_targets(invalid + " " + anchor("valid")), {"valid"})

    def test_decoys_never_grant_targets_or_hide_following_ordinary_prose(self):
        for name, decoy in DECOYS.items():
            with self.subTest(name=name):
                target = BEFORE + "\n\n" + decoy + "\n\n" + AFTER + "\n"
                self.assertEqual(markdown_fragment_targets(target), {"before", "after"})
                self.assertEqual(findings({
                    "reference.md": "[before](target.md#before)\n[ghost](target.md#ghost)\n[after](target.md#after)\n",
                    "target.md": target,
                }, located=True), [missing("reference.md", "target.md", "ghost", 2)])

    def test_unclosed_code_comments_and_raw_contexts_do_not_grant_at_eof(self):
        for prefix in ("\x60\x60\x60html\n", "~~~~\n", "<!--\n", "<pre>\n", "<a id='other'>\n"):
            with self.subTest(prefix=prefix):
                target = BEFORE + "\n\n" + prefix + GHOST + "\n"
                self.assertEqual(markdown_fragment_targets(target), {"before"})
                self.assertEqual(findings({"reference.md": "[ghost](target.md#ghost)\n",
                                           "target.md": target}),
                                 [missing("reference.md", "target.md", "ghost")])

    def test_inline_context_boundaries_and_adjacent_live_targets(self):
        text = ("Example \x60<!-- " + GHOST + " -->\x60 " + BEFORE + "\n\n"
                "<!-- \x60 " + GHOST + " \x60 --> " + AFTER + "\n\n"
                "> \x60\x60\x60\n> " + GHOST + "\n> \x60\x60\x60\n" + anchor("after-quote") + "\n\n"
                "- \x60\x60\x60\n  " + GHOST + "\n  \x60\x60\x60\n" + anchor("after-list") + "\n\n"
                "Example \x60unmatched\n<div>\n\x60 " + GHOST + "\n</div>\n\n"
                + anchor("after-block") + "\n\n"
                "| Code | Target |\n| --- | --- |\n"
                "| \x60" + GHOST + "\x60 | " + anchor("after-cell") + " |\n"
                "| \x60unmatched | " + anchor("separate-cell") + " |\n\n"
                "[ref]: elsewhere\n" + anchor("after-reference") + "\n")
        self.assertEqual(markdown_fragment_targets(text),
                         {"before", "after", "after-quote", "after-list",
                          "after-block", "after-cell", "separate-cell", "after-reference"})

    def test_metadata_is_not_a_rendered_target(self):
        self.assertEqual(markdown_fragment_targets(
            "---\nname: " + GHOST + "\n---\n\n" + BEFORE + "\n"), {"before"})

    def test_all_nine_table_tokens_resolve_and_each_removed_or_decoy_fails(self):
        source = "".join(f"[row](../archive/table.md#{token})\n" for token in ROW_IDS)
        files = {"packets/reference.md": source, "archive/table.md": table()}
        self.assertEqual(findings(files, located=True), [])
        for line, token in enumerate(ROW_IDS, 1):
            row = anchor(token)
            expected = [missing("packets/reference.md", "archive/table.md", token, line)]
            for variant in ("", "\x60" + row + "\x60", "<!-- " + row + " -->"):
                with self.subTest(token=token, replacement=variant):
                    candidate = dict(files, **{"archive/table.md": table().replace(row, variant)})
                    self.assertEqual(findings(candidate, located=True), expected)
            with self.subTest(token=token, replacement="fence"):
                candidate = dict(files, **{"archive/table.md":
                    table().replace(row, "") + "\n\x60\x60\x60html\n" + row + "\n\x60\x60\x60\n"})
                self.assertEqual(findings(candidate, located=True), expected)

    def test_surplus_table_cells_never_supply_targets(self):
        cases = {
            "one column": (
                "| Header |\n| --- |\n"
                "| rendered | " + GHOST + " |\n"
                "| " + BEFORE + " |\n| " + AFTER + " |\n"),
            "two columns without outer pipes": (
                "Header | Second\n--- | ---\n"
                + BEFORE + " | rendered | " + GHOST + "\n"
                + "short row\n"
                + "rendered | " + AFTER + " | " + GHOST + "\n"),
            "escaped pipe is not a column": (
                "| Header | Second |\n| --- | --- |\n"
                "| escaped \\| pipe " + BEFORE + " | " + AFTER
                + " | " + GHOST + " |\n"),
            "discarded comment cannot hide next rendered row": (
                "| Header |\n| --- |\n"
                "| " + BEFORE + " | <!-- " + GHOST + " |\n"
                "| " + AFTER + " |\n"),
        }
        for name, target in cases.items():
            with self.subTest(name=name):
                # Ordinary prose after the table is not subject to its width.
                target += "\nordinary | " + anchor("prose") + "\n"
                self.assertEqual(markdown_fragment_targets(target),
                                 {"before", "after", "prose"})
                self.assertEqual(findings({
                    "reference.md": ("[before](target.md#before)\n"
                                     "[ghost](target.md#ghost)\n"
                                     "[after](target.md#after)\n"
                                     "[prose](target.md#prose)\n"),
                    "target.md": target,
                }, located=True), [missing("reference.md", "target.md", "ghost", 2)])

    def test_multiline_reference_definitions_never_supply_targets(self):
        cases = {
            "reported multiline label": (
                "[multiple\nlines]: /real\n  \"title <a id='ghost'></a>\""),
            "escaped bracket and same-line title": (
                "[multiple \\]\nlines]: /real '" + GHOST + "'"),
            "multiline destination and title": (
                "[multiple\nlines]:\n  /real\n  'title begins\n  "
                + GHOST + "\n  title ends'"),
            "parenthesized title": (
                "[multiple\nlines]: /real\n  (title " + GHOST + ")"),
        }
        for name, definition in cases.items():
            with self.subTest(name=name):
                # The next plain line is not part of the definition; it and
                # the preceding ordinary paragraph must remain valid targets.
                target = BEFORE + "\n\n" + definition + "\n" + AFTER + "\n"
                self.assertEqual(markdown_fragment_targets(target), {"before", "after"})
                self.assertEqual(findings({
                    "reference.md": ("[before](target.md#before)\n"
                                     "[ghost](target.md#ghost)\n"
                                     "[after](target.md#after)\n"),
                    "target.md": target,
                }, located=True), [missing("reference.md", "target.md", "ghost", 2)])

    def test_default_scan_and_legacy_filter_diagnostics_are_preserved(self):
        files = {
            "archive/table.md": "# Heading\n\n" + anchor("Exact") + " " + anchor("Exact") + "\n",
            "docs/guide.md": ("[heading](../archive/table.md#heading)\n"
                              "[explicit](../archive/table.md#Exact)\n"
                              "[case](../archive/table.md#exact)\n"
                              "[suffix](../archive/table.md#Exact-1)\n"
                              "[missing](../archive/table.md#missing)\n"
                              "[same](#local)\n\n" + anchor("local") + "\n"),
            ".generated/skills/example/SKILL.md": "[excluded](../../../archive/table.md#bad)\n",
            "ignored/source.md": "[excluded](../archive/table.md#bad)\n",
        }
        expected = [missing("docs/guide.md", "archive/table.md", token, line)
                    for line, token in ((3, "exact"), (4, "Exact-1"), (5, "missing"))]
        self.assertEqual(findings(files, located=True, excluded=Path("ignored")), expected)
        self.assertEqual(findings(files, excluded=Path("ignored")), [
            missing("docs/guide.md", "archive/table.md", token)
            for token in ("exact", "Exact-1", "missing")])
        self.assertEqual(findings(files, target_pattern=r"(?:agent|templates)/.+\.md|docs/[^/]+\.md"), [])


if __name__ == "__main__":
    unittest.main()
