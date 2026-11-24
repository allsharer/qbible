package org.qbible.core

import org.junit.Assert.assertEquals
import org.junit.Test
import java.io.File

/**
 * Thousands of generated inputs run through the desktop Python engine at build
 * time (android/tools/differential_vectors.py); the Kotlin port must agree on
 * every one.
 */
class DifferentialTest {
    private val data = TestData.json(File(TestData.testDir, "differential.json"))
    private val bible = TestData.bible
    private val books = TestData.catalogue

    @Test
    fun references() {
        val cases = data.getJSONArray("references").objects()
        val failures = ArrayList<String>()
        for (c in cases) {
            val input = c.getString("input")
            try {
                val ref = parseReference(input, books)
                if (c.has("parsed_key") && ref.key() != c.getString("parsed_key")) failures.add("<$input> parsed ${ref.key()} want ${c.getString("parsed_key")}")
                val p = resolveReference(ref, bible.verseCounts)
                if (c.has("code")) failures.add("<$input> resolved ${p.key()}, want ${c.getString("code")}")
                else if (p.key() != c.getString("key") || p.display() != c.getString("display")) {
                    failures.add("<$input> ${p.key()} ${p.display()} want ${c.getString("key")} ${c.getString("display")}")
                }
            } catch (e: QBibleException) {
                if (e.code != c.optString("code")) failures.add("<$input> error ${e.code} (${e.message}), want ${c.opt("code") ?: c.opt("key")}")
            }
        }
        assertEquals(failures.take(40).joinToString("\n"), 0, failures.size)
        println("differential: ${cases.size} reference inputs agree with the desktop parser")
    }

    @Test
    fun keys() {
        for (c in data.getJSONArray("keys").objects()) {
            val input = c.getString("input")
            try {
                val r = parseKey(input, books)
                assertEquals(input, c.optString("key"), r.key())
                assertEquals(input, c.optString("display"), r.display())
            } catch (e: QBibleException) {
                assertEquals("<$input>: ${e.message}", c.optString("code"), e.code)
            }
        }
    }

    @Test
    fun findReferencesInText() {
        for (c in data.getJSONArray("find").objects()) {
            val text = c.getString("text")
            val got = findReferences(text, books, bible::isValid).map { listOf(it.start, it.end, it.text, it.reference.key()) }
            val want = c.getJSONArray("found").objects().map { listOf(it.getInt("start"), it.getInt("end"), it.getString("text"), it.getString("key")) }
            assertEquals(text, want, got)
        }
    }

    @Test
    fun searches() {
        val cases = data.getJSONArray("search").objects()
        val failures = ArrayList<String>()
        for (c in cases) {
            val q = c.getString("query")
            val label = "<$q> ${c.getString("mode")} ${c.getString("sort")} ${c.optStringOrNull("testament")}"
            try {
                val r = bible.search(q, mode = c.getString("mode"), sort = c.getString("sort"),
                    testament = c.optStringOrNull("testament"), limit = c.getInt("limit"))
                if (c.has("code")) { failures.add("$label: want error"); continue }
                if (r.total != c.getInt("total")) failures.add("$label: total ${r.total} want ${c.getInt("total")}")
                val keys = r.hits.map { "${it.verse.bookId}.${it.verse.chapter}.${it.verse.verse}" }
                val want = c.getJSONArray("keys").strings()
                if (keys != want) failures.add("$label: keys\n got  $keys\n want $want")
                val segs = c.getJSONArray("segments")
                for ((i, h) in r.hits.withIndex()) {
                    if (i >= segs.length()) break
                    val w = segs.getJSONArray(i).objects().map { Search.Segment(it.getString("text"), it.getBoolean("supplied"), it.getBoolean("match")) }
                    if (w != h.segments) failures.add("$label ${h.key}: segments differ")
                }
            } catch (e: SearchQueryException) {
                if (c.optString("code") != e.code) failures.add("$label: ${e.message}")
            }
        }
        assertEquals(failures.take(30).joinToString("\n"), 0, failures.size)
        println("differential: ${cases.size} random searches agree with the desktop FTS5 engine")
    }
}
