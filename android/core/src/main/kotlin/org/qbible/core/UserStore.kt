package org.qbible.core

import org.json.JSONArray
import org.json.JSONObject
import java.time.OffsetDateTime
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit

/**
 * Bookmarks and reading history (port of `qbible/userdata.py`).
 *
 * Same tables, migrations, stable reference keys (`JHN.3.16-JHN.3.21`) and
 * timestamp format as the desktop `user.sqlite`, so the two can be exchanged
 * or synced later. Only keys are stored, never copies of scripture.
 */
class UserStore(private val db: SqlDb, private val books: BookCatalogue) {

    data class Bookmark(
        val id: Long,
        val translation: String,
        val reference: Reference,
        val label: String,
        val createdAt: String,
        val updatedAt: String,
    ) {
        val key: String get() = reference.key()
    }

    data class HistoryEntry(val id: Long, val translation: String, val reference: Reference, val openedAt: String) {
        val key: String get() = reference.key()
    }

    init {
        migrate()
    }

    fun schemaVersion(): Int {
        val has = db.query("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'")
        if (has.isEmpty()) return 0
        return db.query("SELECT coalesce(max(version), 0) FROM schema_migrations")[0].int(0)
    }

    /** Apply pending migrations; a database from a newer qbible is refused, not modified. */
    fun migrate(): List<Int> {
        val current = schemaVersion()
        if (current > LATEST_VERSION) {
            throw UserDataException(
                "The user database was created by a newer qbible (schema $current); " +
                    "this version understands up to $LATEST_VERSION. Upgrade qbible."
            )
        }
        db.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (" +
                "version INTEGER PRIMARY KEY, description TEXT NOT NULL, applied_at TEXT NOT NULL)"
        )
        val applied = ArrayList<Int>()
        for ((version, description, sql) in MIGRATIONS) {
            if (version <= current) continue
            try {
                db.transaction {
                    if (schemaVersion() < version) {
                        sql.split(";").filter { it.isNotBlank() }.forEach { db.execute(it) }
                        db.execute(
                            "INSERT INTO schema_migrations (version, description, applied_at) VALUES (?, ?, ?)",
                            listOf(version.toLong(), description, now()),
                        )
                        applied.add(version)
                    }
                }
            } catch (e: QBibleException) {
                throw e
            } catch (e: Exception) {
                throw UserDataException("Migration $version failed: ${e.message}")
            }
        }
        return applied
    }

    // -- bookmarks ---------------------------------------------------------------------

    private fun checkLabel(label: String?): String {
        val l = (label ?: "").trim()
        if (l.codePointCount(0, l.length) > MAX_LABEL) throw UserDataException("Bookmark labels are limited to $MAX_LABEL characters.")
        return l
    }

    /** Add a bookmark; an existing one for the same passage is returned (label updated if given). */
    fun addBookmark(translation: String, ref: Reference, label: String = ""): Pair<Bookmark, Boolean> {
        val l = checkLabel(label)
        val key = ref.key()
        return db.transaction {
            val now = now()
            val row = db.query("SELECT id FROM bookmarks WHERE translation = ? AND ref_key = ?", listOf(translation, key))
            if (row.isNotEmpty()) {
                val id = row[0].long(0)
                if (l.isNotEmpty()) db.execute("UPDATE bookmarks SET label = ?, updated_at = ? WHERE id = ?", listOf(l, now, id))
                getBookmark(id) to false
            } else {
                val id = db.insert(
                    "INSERT INTO bookmarks (translation, ref_key, label, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    listOf(translation, key, l, now, now),
                )
                getBookmark(id) to true
            }
        }
    }

    fun getBookmark(id: Long): Bookmark {
        val r = db.query(
            "SELECT id, translation, ref_key, label, created_at, updated_at FROM bookmarks WHERE id = ?", listOf(id)
        ).firstOrNull() ?: throw NotFoundException("No bookmark with id $id.")
        return Bookmark(r.long(0), r.str(1), parseKey(r.str(2), books), r.str(3), r.str(4), r.str(5))
    }

    fun bookmarks(): List<Bookmark> =
        db.query(
            "SELECT id, translation, ref_key, label, created_at, updated_at FROM bookmarks ORDER BY created_at DESC, id DESC"
        ).mapNotNull { r ->
            try {
                Bookmark(r.long(0), r.str(1), parseKey(r.str(2), books), r.str(3), r.str(4), r.str(5))
            } catch (e: Exception) {
                null // skip a corrupt row rather than failing the whole list
            }
        }

    fun findBookmark(translation: String, ref: Reference): Bookmark? {
        val row = db.query("SELECT id FROM bookmarks WHERE translation = ? AND ref_key = ?", listOf(translation, ref.key()))
        return row.firstOrNull()?.let { getBookmark(it.long(0)) }
    }

    fun updateBookmarkLabel(id: Long, label: String): Bookmark {
        val l = checkLabel(label)
        val n = db.execute("UPDATE bookmarks SET label = ?, updated_at = ? WHERE id = ?", listOf(l, now(), id))
        if (n == 0) throw NotFoundException("No bookmark with id $id.")
        return getBookmark(id)
    }

    fun removeBookmark(id: Long) {
        val n = db.execute("DELETE FROM bookmarks WHERE id = ?", listOf(id))
        if (n == 0) throw NotFoundException("No bookmark with id $id.")
    }

    // -- history -----------------------------------------------------------------------

    /** Record that a passage was opened (moves an existing entry to the top). */
    fun record(translation: String, ref: Reference) {
        val key = ref.key()
        db.transaction {
            db.execute("DELETE FROM history WHERE translation = ? AND ref_key = ?", listOf(translation, key))
            db.execute("INSERT INTO history (translation, ref_key, opened_at) VALUES (?, ?, ?)", listOf(translation, key, now()))
            db.execute(
                "DELETE FROM history WHERE id NOT IN (SELECT id FROM history ORDER BY id DESC LIMIT ?)",
                listOf(MAX_HISTORY.toLong()),
            )
        }
    }

    fun history(limit: Int = 20): List<HistoryEntry> =
        db.query(
            "SELECT id, translation, ref_key, opened_at FROM history ORDER BY id DESC LIMIT ?",
            listOf(limit.coerceIn(1, MAX_HISTORY).toLong()),
        ).mapNotNull { r ->
            try {
                HistoryEntry(r.long(0), r.str(1), parseKey(r.str(2), books), r.str(3))
            } catch (e: Exception) {
                null
            }
        }

    fun lastPosition(): HistoryEntry? = history(1).firstOrNull()

    fun clearHistory(): Int = db.execute("DELETE FROM history")

    // -- export and import ----------------------------------------------------------------

    /** All bookmarks and history as JSON (format `qbible-user-data`, version 1). */
    fun exportJson(): String {
        val o = JSONObject()
        o.put("format", EXPORT_FORMAT)
        o.put("version", 1)
        o.put("exported_at", now())
        val bm = JSONArray()
        for (b in bookmarks().reversed()) {
            bm.put(JSONObject().put("translation", b.translation).put("key", b.key).put("reference", b.reference.display())
                .put("label", b.label).put("created_at", b.createdAt).put("updated_at", b.updatedAt))
        }
        o.put("bookmarks", bm)
        val h = JSONArray()
        for (e in history(MAX_HISTORY).reversed()) {
            h.put(JSONObject().put("translation", e.translation).put("key", e.key).put("reference", e.reference.display())
                .put("opened_at", e.openedAt))
        }
        o.put("history", h)
        return o.toString(1)
    }

    data class ImportReport(val bookmarksAdded: Int, val bookmarksUpdated: Int, val historyAdded: Int, val skipped: Int)

    /**
     * Merge an export into this store. Existing bookmarks are kept; an imported
     * label fills in an empty one. History entries are merged by time (the
     * newest opening of each passage wins) and capped as usual.
     */
    fun importJson(json: String): ImportReport {
        val o = try { JSONObject(json) } catch (e: Exception) { throw UserDataException("That file is not a qbible export.") }
        if (o.optString("format") != EXPORT_FORMAT) throw UserDataException("That file is not a qbible export.")
        if (o.optInt("version", 0) != 1) throw UserDataException("That export was made by a newer qbible.")
        var added = 0
        var updated = 0
        var histAdded = 0
        var skipped = 0
        db.transaction {
            val bm = o.optJSONArray("bookmarks") ?: JSONArray()
            for (i in 0 until bm.length()) {
                val b = bm.optJSONObject(i)
                val tr = b?.optString("translation").orEmpty()
                val ref = try { parseKey(b?.optString("key"), books) } catch (e: Exception) { null }
                if (b == null || ref == null || !TRANSLATION_RE.matches(tr)) { skipped++; continue }
                val label = b.optString("label").trim().take(MAX_LABEL)
                val created = b.optString("created_at").ifBlank { now() }
                val updatedAt = b.optString("updated_at").ifBlank { created }
                val existing = db.query("SELECT id, label FROM bookmarks WHERE translation = ? AND ref_key = ?", listOf(tr, ref.key()))
                if (existing.isEmpty()) {
                    db.insert(
                        "INSERT INTO bookmarks (translation, ref_key, label, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                        listOf(tr, ref.key(), label, created, updatedAt),
                    )
                    added++
                } else if (existing[0].str(1).isEmpty() && label.isNotEmpty()) {
                    db.execute("UPDATE bookmarks SET label = ?, updated_at = ? WHERE id = ?", listOf(label, now(), existing[0].long(0)))
                    updated++
                }
            }
            val hist = o.optJSONArray("history") ?: JSONArray()
            val merged = LinkedHashMap<Pair<String, String>, String>()
            for (r in db.query("SELECT translation, ref_key, opened_at FROM history ORDER BY id")) {
                merged[r.str(0) to r.str(1)] = r.str(2)
            }
            for (i in 0 until hist.length()) {
                val e = hist.optJSONObject(i)
                val tr = e?.optString("translation").orEmpty()
                val ref = try { parseKey(e?.optString("key"), books) } catch (x: Exception) { null }
                val at = e?.optString("opened_at").orEmpty()
                if (e == null || ref == null || at.isBlank() || !TRANSLATION_RE.matches(tr)) { skipped++; continue }
                val k = tr to ref.key()
                val old = merged[k]
                if (old == null) histAdded++
                if (old == null || at > old) merged[k] = at
            }
            val ordered = merged.entries.sortedBy { it.value }.takeLast(MAX_HISTORY)
            db.execute("DELETE FROM history")
            for ((k, at) in ordered) {
                db.execute("INSERT INTO history (translation, ref_key, opened_at) VALUES (?, ?, ?)", listOf(k.first, k.second, at))
            }
        }
        return ImportReport(added, updated, histAdded, skipped)
    }

    companion object {
        const val MAX_HISTORY = 200
        const val MAX_LABEL = 200
        const val EXPORT_FORMAT = "qbible-user-data"
        private val TRANSLATION_RE = Regex("[a-z0-9][a-z0-9-]{0,31}")

        /** Identical to `MIGRATIONS` in `qbible/userdata.py`. */
        val MIGRATIONS: List<Triple<Int, String, String>> = listOf(
            Triple(
                1,
                "bookmarks and reading history",
                """
                CREATE TABLE bookmarks (
                    id          INTEGER PRIMARY KEY,
                    translation TEXT NOT NULL,
                    ref_key     TEXT NOT NULL,
                    label       TEXT NOT NULL DEFAULT '',
                    created_at  TEXT NOT NULL,
                    updated_at  TEXT NOT NULL,
                    UNIQUE (translation, ref_key)
                );
                CREATE TABLE history (
                    id          INTEGER PRIMARY KEY,
                    translation TEXT NOT NULL,
                    ref_key     TEXT NOT NULL,
                    opened_at   TEXT NOT NULL
                );
                CREATE INDEX history_opened ON history (opened_at DESC, id DESC);
                """.trimIndent(),
            ),
        )
        val LATEST_VERSION: Int = MIGRATIONS.last().first

        private val ISO = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ssxxx")

        /** UTC, seconds, `+00:00` offset: the same text as Python's `isoformat(timespec="seconds")`. */
        fun now(): String = OffsetDateTime.now(ZoneOffset.UTC).truncatedTo(ChronoUnit.SECONDS).format(ISO)
    }
}
