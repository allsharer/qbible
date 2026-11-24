package org.qbible.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class BibleTest {
    private val bible = TestData.bible

    @Test
    fun packFacts() {
        assertEquals("kjv", bible.id)
        assertEquals("KJV", bible.abbreviation)
        assertEquals(66, bible.books.size)
        assertEquals(1189, bible.verseCounts.values.sumOf { it.size })
        assertEquals(31102, bible.verseCounts.values.sumOf { it.sum() })
    }

    @Test
    fun chapterNavigationCrossesBooks() {
        val v = bible.passage("Malachi 4")
        assertEquals("Malachi 3", v.previous!!.display())
        assertEquals("Matthew 1", v.next!!.display())
        assertNull(bible.passage("Genesis 1").previous)
        assertNull(bible.passage("Revelation 22").next)
        val whole = bible.passage("Jude")
        assertEquals(25, whole.verses.size)
        assertEquals("3 John 1", whole.previous!!.display())
        assertEquals("Revelation 1", whole.next!!.display())
        val range = bible.passage("Gen 1:1-2:3")
        assertEquals(34, range.verses.size)
        assertEquals("Genesis 3", range.next!!.display())
    }

    @Test
    fun wholeBookAndKeys() {
        assertEquals(150, bible.passage("Psalms").passage.end.first)
        assertEquals("JHN.3.16", bible.passage("JHN.3.16").reference.key())
        assertEquals("Mark 4:1-41", bible.passage("mar 4:1-").reference.display())
        assertEquals("MRK.4.1-MRK.4.41", bible.passage("mar 4:1-").reference.key())
        assertEquals("Genesis 1", bible.passage(parseReference("gen", bible.catalogue), wholeBookAsFirstChapter = true).reference.display())
    }

    @Test
    fun copyText() {
        val one = bible.passage("John 11:35")
        assertEquals("Jesus wept.\n— John 11:35 (KJV)", Copying.text(one.verses, one.reference.display(), "KJV"))
        val ps = bible.passage("Ps 23:1-2")
        assertEquals(
            "Psalm 23:1-2 (KJV)\n1 A Psalm of David. The LORD [is] my shepherd; I shall not want.\n2 He maketh me to lie down in green pastures: he leadeth me beside the still waters.",
            Copying.text(ps.verses, ps.reference.display(), "KJV", TextFmt.Supplied.BRACKETS),
        )
        val two = bible.passage("Gen 1:31-2:1")
        assertTrue(Copying.text(two.verses, two.reference.display(), "KJV").contains("\n[1]\n31 ") )
        assertEquals("Genesis 1:31-2:1", Copying.rangeReference(bible.catalogue.get("GEN"), two.verses.first(), two.verses.last()).display())
    }

    @Test
    fun searchSpeed() {
        val t = System.nanoTime()
        for (q in listOf("the", "lord", "\"and it came to pass\"", "love -fear", "belie*")) bible.search(q, limit = 50)
        bible.search("the", sort = "relevance", limit = 20)
        val ms = (System.nanoTime() - t) / 1_000_000
        println("search speed: 5 canonical + 'the' by relevance in $ms ms (JVM)")
        assertTrue("too slow: $ms ms", ms < 5000)
    }
}
