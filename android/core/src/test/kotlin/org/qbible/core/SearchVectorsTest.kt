package org.qbible.core

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * spec/search-cases.json, exported from the desktop FTS5 engine: the Kotlin
 * FTS4 search must give the same terms, errors, totals, result order
 * (canonical and BM25 relevance) and highlight segments.
 */
class SearchVectorsTest {
    private val cases = TestData.json(File(TestData.spec, "search-cases.json"))
    private val bible = TestData.bible

    @Test
    fun vectorsMatchThisTranslation() {
        assertEquals(cases.getString("translation_text_sha256"), bible.meta["text_sha256"])
    }

    @Test
    fun parseCases() {
        val list = cases.getJSONArray("parse").objects()
        for (c in list) {
            val q = c.getString("query")
            val mode = c.getString("mode")
            try {
                val terms = Search.parseQuery(q, mode).map { it.describe() }
                assertEquals("terms for <$q> ($mode)", c.getJSONArray("terms").strings(), terms)
                assertTrue("<$q> should fail", !c.has("error"))
            } catch (e: SearchQueryException) {
                assertEquals("error for <$q> ($mode): ${e.message}", c.optString("error"), e.code)
            }
        }
        println("search-cases.json: ${list.size} parse cases passed")
    }

    @Test
    fun searchCases() {
        val list = cases.getJSONArray("search").objects()
        val failures = ArrayList<String>()
        for (c in list) {
            val label = "<${c.getString("query")}> ${c.getString("mode")} ${c.getString("sort")} " +
                "book=${c.optStringOrNull("book")} t=${c.optStringOrNull("testament")} limit=${c.getInt("limit")} offset=${c.getInt("offset")}"
            try {
                val r = bible.search(
                    c.getString("query"), mode = c.getString("mode"), limit = c.getInt("limit"), offset = c.getInt("offset"),
                    sort = c.getString("sort"), book = c.optStringOrNull("book")?.let { TestData.catalogue.get(it) },
                    testament = c.optStringOrNull("testament"), context = c.getInt("context"),
                )
                if (c.has("error")) { failures.add("$label: expected ${c.getString("error")}, got ${r.total} results"); continue }
                compare(label, c, r, failures)
            } catch (e: SearchQueryException) {
                if (c.optString("error") != e.code) failures.add("$label: unexpected ${e.code}: ${e.message}")
            }
        }
        assertEquals(failures.joinToString("\n"), 0, failures.size)
        println("search-cases.json: ${list.size} search cases passed")
    }

    private fun compare(label: String, c: JSONObject, r: SearchResult, failures: MutableList<String>) {
        if (c.getJSONArray("terms").strings() != r.terms.map { it.describe() }) failures.add("$label: terms ${r.terms.map { it.describe() }}")
        if (c.getInt("total") != r.total) failures.add("$label: total ${r.total}, want ${c.getInt("total")}")
        if (c.getBoolean("has_more") != r.hasMore) failures.add("$label: has_more ${r.hasMore}")
        val want = c.getJSONArray("results").objects()
        val gotKeys = r.hits.map { it.key }
        val wantKeys = want.map { it.getString("key") }
        if (gotKeys != wantKeys) { failures.add("$label: keys\n  got  $gotKeys\n  want $wantKeys"); return }
        for ((h, w) in r.hits.zip(want)) {
            val ws = w.getJSONArray("segments").objects().map { Search.Segment(it.getString("text"), it.getBoolean("supplied"), it.getBoolean("match")) }
            if (ws != h.segments) failures.add("$label ${h.key}: segments\n  got  ${h.segments}\n  want $ws")
            if (w.has("context_before")) {
                val key = { v: Verse -> "${v.bookId}.${v.chapter}.${v.verse}" }
                if (w.getJSONArray("context_before").strings() != h.contextBefore.map(key) ||
                    w.getJSONArray("context_after").strings() != h.contextAfter.map(key)
                ) failures.add("$label: context")
            }
        }
    }
}
