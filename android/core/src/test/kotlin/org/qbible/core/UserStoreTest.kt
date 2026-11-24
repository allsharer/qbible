package org.qbible.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.io.File
import java.nio.file.Files

class UserStoreTest {
    private val books = TestData.catalogue
    private fun ref(t: String) = TestData.bible.resolve(parseReference(t, books)).reference

    private fun newStore(): Pair<UserStore, JdbcDb> {
        val f = Files.createTempFile("user", ".sqlite").toFile()
        f.delete()
        f.deleteOnExit()
        val db = JdbcDb.open(f)
        return UserStore(db, books) to db
    }

    @Test
    fun bookmarksLikeDesktop() {
        val (s, db) = newStore()
        assertEquals(1, s.schemaVersion())
        val (b, created) = s.addBookmark("kjv", ref("John 3:16-21"), "  nutshell  ")
        assertTrue(created)
        assertEquals("JHN.3.16-JHN.3.21", b.key)
        assertEquals("nutshell", b.label)
        assertTrue(Regex("\\d{4}-\\d\\d-\\d\\dT\\d\\d:\\d\\d:\\d\\d\\+00:00").matches(b.createdAt))
        val (again, created2) = s.addBookmark("kjv", ref("jn 3:16-21"))
        assertFalse(created2)
        assertEquals(b.id, again.id)
        assertEquals("nutshell", again.label)
        s.updateBookmarkLabel(b.id, "new")
        assertEquals("new", s.findBookmark("kjv", ref("John 3:16-21"))!!.label)
        try { s.addBookmark("kjv", ref("Gen 1"), "x".repeat(201)); fail() } catch (e: UserDataException) { }
        s.removeBookmark(b.id)
        assertTrue(s.bookmarks().isEmpty())
        try { s.removeBookmark(b.id); fail() } catch (e: NotFoundException) { }
        db.close()
    }

    @Test
    fun historyMovesToTopAndIsCapped() {
        val (s, db) = newStore()
        s.record("kjv", ref("Genesis 1"))
        s.record("kjv", ref("Exodus 1"))
        s.record("kjv", ref("Genesis 1"))
        assertEquals(listOf("GEN.1", "EXO.1"), s.history().map { it.key })
        for (c in 1..150) s.record("kjv", ref("Psalm $c"))
        for (c in 1..60) s.record("kjv", ref("Isaiah $c"))
        assertEquals(200, s.history(500).size)
        assertEquals("ISA.60", s.lastPosition()!!.key)
        assertEquals(200, s.clearHistory())
        db.close()
    }

    /** A user.sqlite written by the desktop qbible opens unchanged, with the same keys. */
    @Test
    fun readsDesktopDatabase() {
        val src = File(TestData.dataDir, "desktop-user.sqlite")
        val copy = Files.createTempFile("desktop", ".sqlite").toFile()
        src.copyTo(copy, overwrite = true)
        val db = JdbcDb.open(copy)
        val s = UserStore(db, books)
        assertTrue(s.migrate().isEmpty()) // already at the latest schema
        val want = TestData.json(File(TestData.dataDir, "differential.json")).getJSONObject("user")
        assertEquals(want.getJSONArray("bookmarks").objects().map { listOf(it.getString("key"), it.getString("reference"), it.getString("label"), it.getString("created_at")) },
            s.bookmarks().map { listOf(it.key, it.reference.display(), it.label, it.createdAt) })
        assertEquals(want.getJSONArray("history").objects().map { it.getString("key") to it.getString("opened_at") },
            s.history(50).map { it.key to it.openedAt })
        db.close()
        copy.delete()
    }

    @Test
    fun refusesNewerSchema() {
        val (s, db) = newStore()
        db.execute("INSERT INTO schema_migrations VALUES (99, 'future', 'x')")
        try { UserStore(db, books); fail() } catch (e: UserDataException) { assertTrue(e.message!!.contains("newer")) }
        assertEquals(99, s.schemaVersion())
        db.close()
    }

    @Test
    fun exportAndImport() {
        val (a, dbA) = newStore()
        a.addBookmark("kjv", ref("Psalm 23"), "shepherd")
        a.addBookmark("kjv", ref("Rom 8:28"))
        a.record("kjv", ref("Genesis 1"))
        a.record("kjv", ref("John 1"))
        val json = a.exportJson()

        val (b, dbB) = newStore()
        b.addBookmark("kjv", ref("Rom 8:28"))
        b.record("kjv", ref("Mark 1"))
        val rep = b.importJson(json)
        assertEquals(1, rep.bookmarksAdded)
        assertEquals(2, rep.historyAdded)
        assertEquals(setOf("PSA.23", "ROM.8.28"), b.bookmarks().map { it.key }.toSet())
        assertEquals("shepherd", b.bookmarks().first { it.key == "PSA.23" }.label)
        assertEquals(setOf("GEN.1", "JHN.1", "MRK.1"), b.history().map { it.key }.toSet())
        // Importing twice changes nothing.
        val again = b.importJson(json)
        assertEquals(0, again.bookmarksAdded + again.historyAdded)
        try { b.importJson("{\"format\":\"other\"}"); fail() } catch (e: UserDataException) { }
        try { b.importJson("not json"); fail() } catch (e: UserDataException) { }
        dbA.close(); dbB.close()
    }
}
