"""OT-7 identity policies, stable identities and reverse source lookup."""
import unittest

from otto.ids import (IdPolicy, IdResolver, LocatedError, RecordRef, SourceLocation,
                      identity_from_path, validate_identity)


class IdentityTests(unittest.TestCase):
    def test_standard_presets_round_trip(self):
        cases = (
            ("project", IdPolicy("NN-slug", "parent"), "items/01-first/plan.md", "01"),
            ("project", IdPolicy("NN-slug", "parent"), "items/100-later/plan.md", "100"),
            ("gap", IdPolicy("XX-NNN", "stem"), "gaps/AA-001-title.md", "AA-001"),
            ("gap", IdPolicy("XX-NNN", "stem"), "gaps/B-042.md", "B-042"),
            ("idea", IdPolicy("slug", "stem"), "ideas/short-example.md", "short-example"),
            ("project", IdPolicy("slug", "parent"), "items/launch-note/plan.md", "launch-note"),
            ("release", IdPolicy("regex", "stem", r"\d+"), "releases/007.md", "007"),
        )
        entries = []
        for kind, policy, path, expected in cases:
            with self.subTest(path=path):
                value = identity_from_path(kind, policy, path, line=3)
                self.assertEqual(value, expected)
                source = SourceLocation(path, 3)
                self.assertEqual(validate_identity(kind, policy, value, source), expected)
                entries.append((RecordRef(kind, value), source))
        resolver = IdResolver(entries)
        for ref, source in entries:
            with self.subTest(ref=ref):
                self.assertEqual(resolver.source_for(ref), source)
                self.assertEqual(resolver.refs_at(source.path), (ref,))

    def test_rename_preserves_numeric_identity_and_leading_zeroes(self):
        policy = IdPolicy("NN-slug", "parent")
        old = "items/01-old-title/plan.md"
        new = "items/01-new-title/plan.md"
        ref = RecordRef("project", identity_from_path("project", policy, old))
        self.assertEqual(ref.id, identity_from_path("project", policy, new))
        self.assertNotEqual(ref, RecordRef("project", "1"))
        resolver = IdResolver(((ref, SourceLocation(new, 1)),))
        self.assertEqual(resolver.source_for(ref).path, new)
        self.assertEqual(resolver.refs_at(old), ())

    def test_adapter_preset_identity_is_not_locator_component(self):
        source = SourceLocation("items/example.md", 2)
        cases = (
            ("project", IdPolicy("NN-slug", "adapter"), "01", "01-example"),
            ("gap", IdPolicy("XX-NNN", "adapter"), "A-001", "A-001-example"),
            ("idea", IdPolicy("slug", "adapter"), "short-example", "Bad Slug"),
            ("goal", IdPolicy("regex", "adapter", r"(?:pillar|principle):[a-z0-9-]+/[a-z0-9-]+"),
             "pillar:theme/aim", "theme/aim"),
        )
        for kind, policy, good, bad in cases:
            with self.subTest(kind=kind):
                self.assertEqual(validate_identity(kind, policy, good, source), good)
                with self.assertRaises(LocatedError) as raised:
                    validate_identity(kind, policy, bad, source)
                self.assertEqual(str(raised.exception),
                                 f"items/example.md:2: invalid {kind} identity: {bad!r}")
                ref = RecordRef(kind, good)
                resolver = IdResolver(((ref, source),))
                self.assertEqual(resolver.source_for(ref), source)
                self.assertEqual(resolver.refs_at(source.path), (ref,))

    def test_qualified_identity_and_shared_canonical_path(self):
        policy = IdPolicy("regex", "adapter", r"(?:pillar|principle):[a-z0-9-]+/[a-z0-9-]+")
        path = "strategy.md"
        first = SourceLocation(path, 2, "first-aim")
        second = SourceLocation(path, 7, "second-aim")
        a = RecordRef.parse("goal:pillar:theme/first-aim")
        b = RecordRef.parse("goal:principle:theme/second-aim")
        self.assertEqual(a.id, "pillar:theme/first-aim")
        self.assertEqual(str(a), "goal:pillar:theme/first-aim")
        self.assertEqual(validate_identity(a.kind, policy, a.id, first), a.id)
        self.assertEqual(validate_identity(b.kind, policy, b.id, second), b.id)
        resolver = IdResolver(((b, second), (a, first)))
        self.assertEqual(resolver.refs_at(path), (a, b))
        self.assertEqual(resolver.refs_at(path, line=7), (b,))
        self.assertEqual(resolver.refs_at(path, anchor="first-aim"), (a,))
        self.assertEqual(resolver.refs_at(path, anchor="first-aim", line=7), ())
        self.assertEqual(resolver.refs_at(path, anchor="absent"), ())

    def test_duplicate_record_ref_fails_at_second_source(self):
        ref = RecordRef("idea", "same")
        with self.assertRaises(LocatedError) as raised:
            IdResolver(((ref, SourceLocation("ideas/one.md", 1)),
                        (ref, SourceLocation("ideas/two.md", 4))))
        self.assertEqual(str(raised.exception), "ideas/two.md:4: duplicate record identity")
        # Identical bare IDs in different kinds are still distinct.
        other = RecordRef("goal", "same")
        resolver = IdResolver(((ref, SourceLocation("ideas/one.md", 1)),
                               (other, SourceLocation("strategy.md", 5))))
        self.assertEqual(resolver.source_for(other).path, "strategy.md")

    def test_invalid_component_and_generic_lexical_identity(self):
        for kind, policy, path, component in (
            ("project", IdPolicy("NN-slug", "parent"), "items/1-first/plan.md", "1-first"),
            ("gap", IdPolicy("XX-NNN", "stem"), "gaps/aa-001.md", "aa-001"),
            ("idea", IdPolicy("slug", "stem"), "ideas/Bad Slug.md", "Bad Slug"),
            ("release", IdPolicy("regex", "stem", r"\d+"), "releases/not-number.md", "not-number"),
        ):
            with self.subTest(path=path):
                with self.assertRaises(LocatedError) as raised:
                    identity_from_path(kind, policy, path, line=4)
                self.assertEqual(str(raised.exception),
                                 f"{path}:4: invalid {kind} identity component {component!r} for policy {policy.policy}")
        for identity in ("", " untrimmed", "trailing ", "bad space", "bad\tspace", "bad\x00control", "bad\x7fcontrol"):
            with self.subTest(identity=identity):
                with self.assertRaises(ValueError) as raised:
                    RecordRef("idea", identity)
                self.assertEqual(str(raised.exception), f"invalid idea identity: {identity!r}")
                with self.assertRaises(LocatedError) as raised:
                    validate_identity("idea", IdPolicy("regex", "adapter", r".*"), identity,
                                      SourceLocation("idea.md", 2))
                self.assertEqual(str(raised.exception), f"idea.md:2: invalid idea identity: {identity!r}")


if __name__ == "__main__":
    unittest.main()
