package org.qbible.core

import org.junit.Assert.assertEquals
import org.junit.Test

class TokensTest {
    /** Kotlin's fold/tokens reproduce the stored index tokens for every verse of the KJV. */
    @Test
    fun everyVerseTokenisesLikeTheIndex() {
        val db = JdbcDb.open(java.io.File(TestData.dataDir, "kjv-android.sqlite"), readOnly = true)
        val rows = db.query("SELECT v.id, v.text, f.body FROM verses v JOIN verses_fts4 f ON f.docid = v.id ORDER BY v.id")
        assertEquals(31102, rows.size)
        var bad = 0
        for (r in rows) {
            if (TextFmt.tokens(TextFmt.plain(r[1] as String)).joinToString(" ") != r[2]) bad++
        }
        assertEquals(0, bad)
        db.close()
    }

    @Test
    fun textConventions() {
        val raw = "¶ The LORD [is] my shepherd; I shall not want."
        assertEquals(true, TextFmt.startsParagraph(raw))
        assertEquals("The LORD is my shepherd; I shall not want.", TextFmt.plain(raw))
        assertEquals("The LORD [is] my shepherd; I shall not want.", TextFmt.render(raw, TextFmt.Supplied.BRACKETS))
        assertEquals(listOf(TextFmt.Part("The LORD "), TextFmt.Part("is", true), TextFmt.Part(" my shepherd; I shall not want.")), TextFmt.parts(raw))
        assertEquals(listOf("caesar", "s", "cafe"), TextFmt.tokens("Cæsar’s café"))
    }
}
