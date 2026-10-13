import unittest

from qbible.books import catalogue
from qbible.errors import SearchQueryError
from qbible.repository import TranslationPack
from qbible.search import fts_expression, parse_query, search

from .helpers import KJV_PACK, require_kjv


def refs(result):
    return [(h.verse.book_id, h.verse.chapter, h.verse.verse) for h in result.hits]


class QueryParsingTests(unittest.TestCase):
    def test_words_phrases_negation_prefix(self):
        terms = parse_query('faith "without works" -dead belie*')
        self.assertEqual([t.describe() for t in terms], ["faith", '"without works"', "-dead", "belie*"])

    def test_fts_expression_only_contains_quoted_tokens(self):
        expr = fts_expression(parse_query('x") OR NEAR(a b) ; DROP TABLE verses; --'))
        # Every token is a quoted alphanumeric string joined by AND.
        for part in expr.split(" AND "):
            self.assertRegex(part.strip("()"), r'^("[a-z0-9]+"( \+ )?)+$')

    def test_empty_queries_rejected(self):
        for q in ["", "   ", "!!!", '""', "-love"]:
            with self.subTest(q=q), self.assertRaises(SearchQueryError):
                parse_query(q)

    def test_bad_mode(self):
        with self.assertRaises(SearchQueryError):
            parse_query("love", "regex")


class SearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require_kjv()
        cls.pack = TranslationPack(KJV_PACK)

    def s(self, q, **kw):
        return search(self.pack, q, **kw)

    def test_single_word(self):
        r = self.s("faith", limit=500)
        self.assertGreater(r.total, 200)
        self.assertEqual(r.total, len(r.hits) if r.total <= 500 else 500)
        for h in r.hits:
            self.assertRegex(h.verse.text.lower(), r"\bfaith\b")

    def test_phrase_is_not_split_into_words(self):
        phrase = self.s('"faith without works"')
        self.assertEqual(refs(phrase), [("JAS", 2, 20), ("JAS", 2, 26)])
        words = self.s("faith without works")
        self.assertGreaterEqual(words.total, phrase.total)
        self.assertEqual(self.s("works without faith", mode="phrase").total, 0)

    def test_jesus_wept(self):
        r = self.s("Jesus wept", mode="phrase")
        self.assertEqual(refs(r), [("JHN", 11, 35)])
        self.assertEqual(r.hits[0].segments[0], {"text": "Jesus wept", "supplied": False, "match": True})

    def test_case_insensitive(self):
        self.assertEqual(self.s("LORD").total, self.s("lord").total)
        self.assertEqual(self.s('"Fear Not"').total, self.s('"fear not"').total)

    def test_apostrophes_and_punctuation(self):
        for q in ["brother's keeper", "brother’s keeper", '"brother\'s keeper"']:
            with self.subTest(q=q):
                self.assertEqual(refs(self.s(q)), [("GEN", 4, 9)])
        # punctuation in the text does not block phrase matches ("Fear not, Abram")
        self.assertIn(("GEN", 15, 1), refs(self.s('"fear not abram"')))
        # ligature folding: caesar finds Cæsar
        r = self.s("caesar's", limit=50)
        self.assertIn(("MAT", 22, 21), refs(r))
        hit = next(h for h in r.hits if h.verse.chapter == 22 and h.verse.verse == 21)
        self.assertIn({"text": "Cæsar’s", "supplied": False, "match": True}, hit.segments)

    def test_supplied_words_searchable_and_marked(self):
        r = self.s('"the LORD is my shepherd"')
        self.assertEqual(refs(r), [("PSA", 23, 1)])
        segs = r.hits[0].segments
        self.assertTrue(any(s["supplied"] and s["text"] == "is" for s in segs))

    def test_no_matches(self):
        r = self.s("xylophone")
        self.assertEqual((r.total, r.hits), (0, []))

    def test_limits_and_pagination(self):
        r1 = self.s("love", limit=10)
        r2 = self.s("love", limit=10, offset=10)
        all20 = self.s("love", limit=20)
        self.assertEqual(len(r1.hits), 10)
        self.assertEqual(refs(r1) + refs(r2), refs(all20))
        self.assertEqual(r1.total, r2.total)
        self.assertTrue(r1.has_more)
        last = self.s("love", limit=10, offset=r1.total - 3)
        self.assertEqual(len(last.hits), 3)
        self.assertFalse(last.has_more)
        for bad in [dict(limit=0), dict(limit=501), dict(offset=-1)]:
            with self.assertRaises(SearchQueryError):
                self.s("love", **bad)

    def test_canonical_and_relevance_order(self):
        r = self.s("love", limit=50)
        ids = [h.verse for h in r.hits]
        order = {b.id: b.order for b in catalogue()}
        keys = [(order[v.book_id], v.chapter, v.verse) for v in ids]
        self.assertEqual(keys, sorted(keys))
        rel = self.s("love", limit=50, sort="relevance")
        self.assertEqual(rel.total, r.total)

    def test_scope_filters(self):
        nt = self.s("faith", testament="NT")
        ot = self.s("faith", testament="OT")
        self.assertEqual(nt.total + ot.total, self.s("faith").total)
        rom = self.s("faith", book=catalogue().get("ROM"), limit=100)
        self.assertTrue(all(h.verse.book_id == "ROM" for h in rom.hits))

    def test_any_mode_and_negation(self):
        any_ = self.s("xylophone wept", mode="any").total
        self.assertEqual(any_, self.s("wept").total)
        neg = self.s("love -fear")
        self.assertEqual(neg.total, self.s("love").total - self.s("love fear").total)

    def test_prefix(self):
        r = self.s("believ*", limit=500)
        self.assertGreater(r.total, self.s("believe").total)

    def test_sql_injection_attempts_are_harmless(self):
        for q in ["'; DROP TABLE verses; --", "love\" OR 1=1 --", "NEAR(love faith)", "* OR *",
                  "verses_fts MATCH 'x'", "\x00", "%_%"]:
            with self.subTest(q=q):
                try:
                    self.s(q)
                except SearchQueryError:
                    pass
        (n,) = self.pack.conn.execute("SELECT count(*) FROM verses").fetchone()
        self.assertEqual(n, 31102)

    def test_context(self):
        r = self.s("Jesus wept", mode="phrase", context=1)
        h = r.hits[0]
        self.assertEqual([v.verse for v in h.context_before], [34])
        self.assertEqual([v.verse for v in h.context_after], [36])

    def test_performance(self):
        import time
        t = time.perf_counter()
        for q in ["the", "lord", '"and it came to pass"', "love -fear", "belie*"]:
            self.s(q, limit=50)
        self.assertLess(time.perf_counter() - t, 2.0)


if __name__ == "__main__":
    unittest.main()
