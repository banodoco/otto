"""Contract for the lifecycle declaration and its consumers."""
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from otto import lifecycle

NAMES = ("queued", "active", "blocked", "paused", "done", "cancelled")
PHRASE = "queued, active, blocked, paused, done or cancelled"
SENTENCE = ("`queued` = planned, not started; `active` = explicitly started; "
            "`blocked` = known impediment; `paused` = deliberately stopped; "
            "`done` = accepted completion evidence; `cancelled` = intentionally abandoned, "
            "with reason in the plan.")
EXTRA = lifecycle.Status("reviewing", True, "under review", ("named-owner", "completion-assessment"))


class DeclarationTests(unittest.TestCase):
    def test_declaration_records(self):
        self.assertEqual([(s.name, s.terminal, s.meaning, s.needs) for s in lifecycle.STATUSES], [
            ("queued", False, "planned, not started", ()),
            ("active", False, "explicitly started", ("named-owner",)),
            ("blocked", False, "known impediment", ()),
            ("paused", False, "deliberately stopped", ()),
            ("done", True, "accepted completion evidence", ("completion-assessment",)),
            ("cancelled", True, "intentionally abandoned, with reason in the plan", ()),
        ])

    def test_names(self):
        self.assertEqual(list(lifecycle.names()), list(NAMES))

    def test_terminal(self):
        self.assertEqual(set(lifecycle.terminal()), {"done", "cancelled"})

    def test_phrase(self):
        self.assertEqual(lifecycle.phrase(), PHRASE)

    def test_route_pattern(self):
        pattern = lifecycle.route_pattern()
        for name in NAMES:
            with self.subTest(name=name):
                match = re.search(pattern, name.upper())
                self.assertIsNotNone(match)
                self.assertEqual(match.group(1), name.upper())
                self.assertIsNone(re.search(pattern, "x" + name + "x"))

    def test_requiring(self):
        self.assertEqual(set(lifecycle.requiring("named-owner")), {"active"})
        self.assertEqual(set(lifecycle.requiring("completion-assessment")), {"done"})
        with self.assertRaises(ValueError):
            lifecycle.requiring("unknown")

    def test_requiring_rejects_unknown_needs(self):
        for need in ("named-owner", "completion-assessment"):
            with self.subTest(need=need):
                self.assertIsInstance(lifecycle.requiring(need), tuple)
        with self.assertRaisesRegex(ValueError, r"known needs: named-owner, completion-assessment"):
            lifecycle.requiring("completion-assesment")

    def test_definitions(self):
        self.assertEqual(lifecycle.definitions(), SENTENCE)


class PatchedDeclarationTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(lifecycle, "STATUSES", lifecycle.STATUSES + (EXTRA,))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_accessors_follow_new_record(self):
        cases = (
            ("names", lambda: list(lifecycle.names()), list(NAMES) + ["reviewing"]),
            ("terminal", lambda: set(lifecycle.terminal()), {"done", "cancelled", "reviewing"}),
            ("phrase", lifecycle.phrase, "queued, active, blocked, paused, done, cancelled or reviewing"),
            ("named-owner", lambda: set(lifecycle.requiring("named-owner")), {"active", "reviewing"}),
            ("completion-assessment", lambda: set(lifecycle.requiring("completion-assessment")), {"done", "reviewing"}),
            ("route", lambda: bool(re.search(lifecycle.route_pattern(), "REVIEWING")), True),
            ("definitions", lifecycle.definitions, SENTENCE[:-1] + "; `reviewing` = under review."),
        )
        for label, read, expected in cases:
            with self.subTest(accessor=label):
                self.assertEqual(read(), expected)
