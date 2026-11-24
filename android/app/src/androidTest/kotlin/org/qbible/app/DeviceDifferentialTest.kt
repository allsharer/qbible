package org.qbible.app

import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.qbible.core.QBibleException
import org.qbible.core.Search
import org.qbible.core.SearchQueryException
import org.qbible.core.findReferences
import org.qbible.core.parseKey
import org.qbible.core.parseReference
import org.qbible.core.resolveReference

/**
 * The generated differential vectors (desktop Python engine output) on the
 * device: Android's ICU regex engine and SQLite differ from the JVM's, so
 * every rule is checked again here.
 */
@RunWith(AndroidJUnit4::class)
class DeviceDifferentialTest {
    private val ctx = InstrumentationRegistry.getInstrumentation().targetContext
    private val testCtx = InstrumentationRegistry.getInstrumentation().context
    private val data = (ctx.applicationContext as QBibleApplication).data
    private val vectors = JSONObject(testCtx.assets.open("differential.json").use { it.readBytes().toString(Charsets.UTF_8) })
    private fun arr(name: String) = vectors.getJSONArray(name).let { a -> (0 until a.length()).map { a.getJSONObject(it) } }

    @Test
    fun references() {
        val failures = ArrayList<String>()
        val cases = arr("references")
        for (c in cases) {
            val input = c.getString("input")
            val got = try {
                val p = resolveReference(parseReference(input, data.catalogue), data.bible.verseCounts)
                "${p.key()}|${p.display()}"
            } catch (e: QBibleException) { e.code }
            val want = if (c.has("code")) c.getString("code") else "${c.getString("key")}|${c.getString("display")}"
            if (got != want) failures.add("<$input> got $got want $want")
        }
        assertEquals(failures.take(30).joinToString("\n"), 0, failures.size)
        Log.i("qbible-test", "differential: ${cases.size} reference inputs agree on the device")
    }

    @Test
    fun keysAndDetection() {
        for (c in arr("keys")) {
            val got = try { parseKey(c.getString("input"), data.catalogue).key() } catch (e: QBibleException) { e.code }
            assertEquals(c.getString("input"), if (c.has("code")) c.getString("code") else c.getString("key"), got)
        }
        for (c in arr("find")) {
            val text = c.getString("text")
            val got = findReferences(text, data.catalogue, data.bible::isValid).map { "${it.start}-${it.end}:${it.reference.key()}" }
            val f = c.getJSONArray("found")
            val want = (0 until f.length()).map { f.getJSONObject(it) }.map { "${it.getInt("start")}-${it.getInt("end")}:${it.getString("key")}" }
            assertEquals(text, want, got)
        }
    }

    @Test
    fun searches() {
        val failures = ArrayList<String>()
        val cases = arr("search")
        for (c in cases) {
            val q = c.getString("query")
            try {
                val r = data.bible.search(q, mode = c.getString("mode"), sort = c.getString("sort"),
                    testament = if (c.isNull("testament")) null else c.getString("testament"), limit = c.getInt("limit"))
                if (c.has("code")) { failures.add("<$q>: want error"); continue }
                val keys = r.hits.map { "${it.verse.bookId}.${it.verse.chapter}.${it.verse.verse}" }
                val wk = c.getJSONArray("keys").let { a -> (0 until a.length()).map { a.getString(it) } }
                if (r.total != c.getInt("total") || keys != wk) failures.add("<$q> ${c.getString("mode")} ${c.getString("sort")}: total ${r.total}")
                val segs = c.getJSONArray("segments")
                for ((i, h) in r.hits.withIndex()) {
                    val w = segs.getJSONArray(i).let { a -> (0 until a.length()).map { a.getJSONObject(it) } }
                        .map { Search.Segment(it.getString("text"), it.getBoolean("supplied"), it.getBoolean("match")) }
                    if (w != h.segments) failures.add("<$q> ${h.key}: segments")
                }
            } catch (e: SearchQueryException) {
                if (c.optString("code") != e.code) failures.add("<$q>: ${e.message}")
            }
        }
        assertEquals(failures.take(30).joinToString("\n"), 0, failures.size)
        Log.i("qbible-test", "differential: ${cases.size} random searches agree on the device")
    }
}
