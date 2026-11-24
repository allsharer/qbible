package org.qbible.app

import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.qbible.core.QBibleException
import org.qbible.core.Search
import org.qbible.core.SearchQueryException

/**
 * The shared vectors again, but on the device's own SQLite (FTS4) through
 * AndroidDb, the code path the app really uses.
 */
@RunWith(AndroidJUnit4::class)
class DeviceCoreTest {
    private val ctx = InstrumentationRegistry.getInstrumentation().targetContext
    private val testCtx = InstrumentationRegistry.getInstrumentation().context
    private val data = (ctx.applicationContext as QBibleApplication).data

    private fun spec(name: String) = JSONObject(testCtx.assets.open("spec/$name").use { it.readBytes().toString(Charsets.UTF_8) })
    private fun JSONArray.objects() = (0 until length()).map { getJSONObject(it) }
    private fun JSONArray.strings() = (0 until length()).map { getString(it) }
    private fun JSONObject.str(k: String): String? = if (!has(k) || isNull(k)) null else getString(k)

    @Test
    fun sqliteFacts() {
        val db = android.database.sqlite.SQLiteDatabase.create(null)
        val v = db.rawQuery("SELECT sqlite_version()", null).use { it.moveToFirst(); it.getString(0) }
        val fts5 = runCatching { db.execSQL("CREATE VIRTUAL TABLE t USING fts5(x)"); true }.getOrDefault(false)
        Log.i("qbible-test", "device SQLite $v, FTS5 available: $fts5, API ${android.os.Build.VERSION.SDK_INT}")
        db.close()
        assertEquals("kjv", data.bible.id)
    }

    @Test
    fun referenceVectors() {
        val cases = spec("reference-cases.json")
        val bible = data.bible
        for (c in cases.getJSONArray("valid").objects()) {
            val p = bible.resolve(bible.parse(c.getString("input")))
            assertEquals(c.getString("input"), c.getString("display"), p.display())
            assertEquals(c.getString("input"), c.getString("key"), p.key())
        }
        for (c in cases.getJSONArray("invalid").objects()) {
            val code = try { bible.resolve(bible.parse(c.getString("input"))); "none" } catch (e: QBibleException) { e.code }
            assertEquals(c.getString("input"), c.getString("code"), code)
        }
    }

    @Test
    fun searchVectors() {
        val cases = spec("search-cases.json").getJSONArray("search").objects()
        val bible = data.bible
        val failures = ArrayList<String>()
        for (c in cases) {
            val label = "<${c.getString("query")}> ${c.getString("mode")} ${c.getString("sort")} offset=${c.getInt("offset")}"
            try {
                val r = bible.search(
                    c.getString("query"), mode = c.getString("mode"), limit = c.getInt("limit"), offset = c.getInt("offset"),
                    sort = c.getString("sort"), book = c.str("book")?.let { data.catalogue.get(it) },
                    testament = c.str("testament"), context = c.getInt("context"),
                )
                if (c.has("error")) { failures.add("$label: expected error"); continue }
                if (r.total != c.getInt("total")) failures.add("$label: total ${r.total} want ${c.getInt("total")}")
                val want = c.getJSONArray("results").objects()
                if (r.hits.map { it.key } != want.map { it.getString("key") }) failures.add("$label: keys ${r.hits.map { it.key }}")
                for ((h, w) in r.hits.zip(want)) {
                    val ws = w.getJSONArray("segments").objects().map { Search.Segment(it.getString("text"), it.getBoolean("supplied"), it.getBoolean("match")) }
                    if (ws != h.segments) failures.add("$label ${h.key}: segments")
                }
            } catch (e: SearchQueryException) {
                if (c.optString("error") != e.code) failures.add("$label: ${e.message}")
            }
        }
        assertEquals(failures.joinToString("\n"), 0, failures.size)
        Log.i("qbible-test", "search-cases.json: ${cases.size} cases passed on the device's SQLite")
    }

    @Test
    fun userStoreOnDevice() {
        val ref = data.bible.parse("Psalm 23")
        val (b, _) = data.user.addBookmark("kjv", data.bible.resolve(ref).reference, "device test")
        assertEquals("PSA.23", b.key)
        data.user.removeBookmark(b.id)
        val keys = data.user.exportJson()
        assertEquals(true, keys.contains("qbible-user-data"))
    }

    @Test
    fun searchSpeedOnDevice() {
        val t = System.nanoTime()
        for (q in listOf("the", "lord", "\"and it came to pass\"", "love -fear", "belie*")) data.bible.search(q, limit = 50)
        val canonical = (System.nanoTime() - t) / 1_000_000
        val t2 = System.nanoTime()
        data.bible.search("the", sort = "relevance", limit = 25)
        val relevance = (System.nanoTime() - t2) / 1_000_000
        Log.i("qbible-test", "5 searches in $canonical ms; 'the' (24,123 verses) by relevance in $relevance ms")
    }
}
