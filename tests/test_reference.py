import json
import unittest

from qbible.books import BookCatalogue, catalogue
from qbible.errors import (
    InvalidChapterError,
    InvalidVerseError,
    ReferenceSyntaxError,
    UnknownBookError,
)
from qbible.reference import find_references, format_reference, parse, parse_key, resolve
from qbible.books import reference_versification

from .helpers import SPEC

KJV = reference_versification("kjv")


def resolve_text(text):
    return resolve(parse(text), KJV)


class SharedVectorTests(unittest.TestCase):
    """spec/reference-cases.json — shared with future clients."""

    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads((SPEC / "reference-cases.json").read_text(encoding="utf-8"))

    def test_valid_cases(self):
        for case in self.cases["valid"]:
            with self.subTest(input=case["input"]):
                p = resolve_text(case["input"])
                self.assertEqual(p.display(), case["display"])
                self.assertEqual(p.key(), case["key"])

    def test_invalid_cases(self):
        for case in self.cases["invalid"]:
            with self.subTest(input=case["input"]):
                with self.assertRaises(Exception) as cm:
                    resolve_text(case["input"])
                self.assertEqual(getattr(cm.exception, "code", None), case["code"], str(cm.exception))


class BookTests(unittest.TestCase):
    def test_66_books_in_order(self):
        books = list(catalogue())
        self.assertEqual(len(books), 66)
        self.assertEqual(books[0].name, "Genesis")
        self.assertEqual(books[-1].name, "Revelation")
        self.assertEqual([b.order for b in books], list(range(1, 67)))
        self.assertEqual(sum(1 for b in books if b.testament == "OT"), 39)
        self.assertEqual(sum(1 for b in books if b.testament == "NT"), 27)

    def test_every_full_name_and_slug_resolves(self):
        cat = catalogue()
        for b in cat:
            self.assertIs(cat.resolve(b.name), b)
            self.assertIs(cat.resolve(b.slug), b)
            self.assertIs(cat.resolve(b.id), b)
            for a in b.aliases:
                self.assertIs(cat.resolve(a), b, a)

    def test_ambiguous_prefix_lists_candidates(self):
        with self.assertRaises(UnknownBookError) as cm:
            catalogue().resolve("Jo")
        names = {b.name for b in cm.exception.candidates}
        self.assertTrue({"John", "Job", "Joel", "Jonah", "Joshua"} <= names)

    def test_alias_collision_is_rejected(self):
        cat = catalogue()
        a, b = cat.get("GEN"), cat.get("EXO")
        from dataclasses import replace
        with self.assertRaises(ValueError):
            BookCatalogue([a, replace(b, aliases=("gen",))])


class ParserTests(unittest.TestCase):
    def test_kinds(self):
        r = parse("John")
        self.assertTrue(r.is_whole_book)
        r = parse("John 3")
        self.assertEqual((r.start_chapter, r.start_verse), (3, None))
        r = parse("John 3:16-18")
        self.assertEqual((r.start_chapter, r.start_verse, r.end_chapter, r.end_verse), (3, 16, 3, 18))

    def test_whole_chapter_resolution_uses_verse_counts(self):
        p = resolve_text("Psalm 119")
        self.assertEqual((p.start, p.end), ((119, 1), (119, 176)))
        p = resolve_text("Genesis 1-2")
        self.assertEqual((p.start, p.end), ((1, 1), (2, 25)))
        p = resolve_text("Obadiah")
        self.assertEqual((p.start, p.end), ((1, 1), (1, 21)))

    def test_error_messages_are_specific(self):
        with self.assertRaisesRegex(InvalidChapterError, "John has 21 chapters; there is no chapter 22"):
            resolve_text("John 22:1")
        with self.assertRaisesRegex(InvalidVerseError, "John 3 has 36 verses; there is no verse 37"):
            resolve_text("John 3:37")
        with self.assertRaisesRegex(InvalidVerseError, "Psalm 23 has 6 verses"):
            resolve_text("Ps 23:7")
        with self.assertRaisesRegex(ReferenceSyntaxError, "ends before it begins"):
            resolve_text("Gen 2:3-1:1")

    def test_no_clamping_of_out_of_range_end(self):
        with self.assertRaises(InvalidVerseError):
            resolve_text("John 3:30-99")

    def test_key_round_trip(self):
        for text in ["John", "John 3", "John 3:16", "John 3:16-21", "Gen 1:1-2:3", "Gen 1-3", "Jude 3"]:
            r = parse(text)
            self.assertEqual(parse_key(r.key()), r, text)

    def test_parse_key_rejects_garbage(self):
        for bad in ["", "john", "JHN.x", "JHN.3.16-GEN.1.1", "../etc"]:
            with self.assertRaises(Exception):
                parse_key(bad)

    def test_long_input_rejected(self):
        with self.assertRaises(ReferenceSyntaxError):
            parse("John " + "1" * 500)

    def test_format(self):
        self.assertEqual(format_reference(parse("Ps 23:1-3")), "Psalm 23:1-3")
        self.assertEqual(format_reference(parse("Psalms 22-23")), "Psalms 22-23")


class FindReferencesTests(unittest.TestCase):
    def valid(self, ref):
        try:
            resolve(ref, KJV)
            return True
        except Exception:
            return False

    def found(self, text):
        return [f.reference.display() for f in find_references(text, self.valid)]

    def test_finds_common_forms(self):
        self.assertEqual(
            self.found("Read Romans 8:28, then 1 Cor 13:4-7 and Psalm 23; also Jn 3:16."),
            ["Romans 8:28", "1 Corinthians 13:4-7", "Psalm 23", "John 3:16"],
        )

    def test_false_positives(self):
        self.assertEqual(self.found("I am 3 years old; chapter 5 of 12; at 3:16 pm; John 99:1."), [])
        self.assertEqual(self.found("Ps 23 is lovely"), [])  # abbreviation without a verse: not linked
        self.assertEqual(self.found("Jude 3"), [])  # single-chapter book without colon: ambiguous

    def test_positions(self):
        text = "see Rom 8:28!"
        f = find_references(text, self.valid)[0]
        self.assertEqual(text[f.start:f.end], "Rom 8:28")


if __name__ == "__main__":
    unittest.main()
