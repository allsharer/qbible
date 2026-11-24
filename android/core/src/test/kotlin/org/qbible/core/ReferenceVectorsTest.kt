package org.qbible.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.io.File

/** spec/reference-cases.json: the same display, key and error code as the desktop app. */
class ReferenceVectorsTest {
    private val cases = TestData.json(File(TestData.spec, "reference-cases.json"))
    private val bible = TestData.bible

    private fun resolveText(text: String): Passage = bible.resolve(bible.parse(text))

    @Test
    fun validCases() {
        val valid = cases.getJSONArray("valid").objects()
        assertTrue(valid.size >= 90)
        val failures = valid.mapNotNull { c ->
            val input = c.getString("input")
            try {
                val p = resolveText(input)
                if (p.display() != c.getString("display") || p.key() != c.getString("key")) {
                    "$input -> ${p.display()} / ${p.key()} (want ${c.getString("display")} / ${c.getString("key")})"
                } else null
            } catch (e: QBibleException) {
                "$input -> error ${e.code}: ${e.message}"
            }
        }
        assertEquals(failures.joinToString("\n"), 0, failures.size)
        println("reference-cases.json: ${valid.size} valid cases passed")
    }

    @Test
    fun invalidCases() {
        val invalid = cases.getJSONArray("invalid").objects()
        val failures = invalid.mapNotNull { c ->
            val input = c.getString("input")
            try {
                val p = resolveText(input)
                "$input -> ${p.display()} (want error ${c.getString("code")})"
            } catch (e: QBibleException) {
                if (e.code != c.getString("code")) "$input -> ${e.code} (want ${c.getString("code")}): ${e.message}" else null
            }
        }
        assertEquals(failures.joinToString("\n"), 0, failures.size)
        println("reference-cases.json: ${invalid.size} invalid cases passed")
    }

    /** The user's standard abbreviations (tests/test_reference.py: test_standard_three_letter_abbreviations). */
    @Test
    fun standardThreeLetterAbbreviations() {
        val table = mapOf(
            "GEN" to "gen", "EXO" to "exo", "LEV" to "lev", "NUM" to "num", "DEU" to "deu",
            "JOS" to "jos", "JDG" to "jdg", "RUT" to "rut", "1SA" to "1sa", "2SA" to "2sa",
            "1KI" to "1ki", "2KI" to "2ki", "1CH" to "1ch", "2CH" to "2ch", "EZR" to "ezr",
            "NEH" to "neh", "EST" to "est", "JOB" to "job", "PSA" to "psa", "PRO" to "pro",
            "ECC" to "ecc", "SNG" to "sng sol", "ISA" to "isa", "JER" to "jer", "LAM" to "lam",
            "EZK" to "eze ezk", "DAN" to "dan", "HOS" to "hos", "JOL" to "joe jol", "AMO" to "amo",
            "OBA" to "oba", "JON" to "jon", "MIC" to "mic", "NAM" to "nah nam", "HAB" to "hab",
            "ZEP" to "zep", "HAG" to "hag", "ZEC" to "zec", "MAL" to "mal",
            "MAT" to "mat", "MRK" to "mar mrk", "LUK" to "luk", "JHN" to "joh jhn", "ACT" to "act",
            "ROM" to "rom", "1CO" to "1co", "2CO" to "2co", "GAL" to "gal", "EPH" to "eph",
            "PHP" to "php phi", "COL" to "col", "1TH" to "1th", "2TH" to "2th", "1TI" to "1ti",
            "2TI" to "2ti", "TIT" to "tit", "PHM" to "phm phl", "HEB" to "heb", "JAS" to "jam jas",
            "1PE" to "1pe", "2PE" to "2pe", "1JN" to "1jo 1jn", "2JN" to "2jo 2jn", "3JN" to "3jo 3jn",
            "JUD" to "jud", "REV" to "rev",
        )
        assertEquals(66, table.size)
        for ((id, abbrevs) in table) for (a in abbrevs.split(" ")) {
            assertEquals(a, id, TestData.catalogue.resolve(a).id)
            assertEquals(a, id, TestData.catalogue.resolve(a.uppercase()).id)
        }
    }

    @Test
    fun handoverTable() {
        // The reference input rules the user set on 2026-11-23 (HANDOVER.md).
        val expect = mapOf(
            "mar 4:15" to "Mark 4:15", "mar 4:1-15" to "Mark 4:1-15", "mar 4:1-4:15" to "Mark 4:1-15",
            "mar 4:1-5:2" to "Mark 4:1-5:2", "mar 4:1-" to "Mark 4:1-41", "mar 4v15" to "Mark 4:15",
            "mar 4v1-5v2" to "Mark 4:1-5:2", "MAR 4V1-5:2" to "Mark 4:1-5:2", "1sa 4:1" to "1 Samuel 4:1",
            "1sam 4:1" to "1 Samuel 4:1", "1s 4:1" to "1 Samuel 4:1", "gen" to "Genesis", "gene" to "Genesis",
            "genes" to "Genesis", "genesi" to "Genesis", "GENESIS" to "Genesis", "jn 3:16" to "John 3:16",
            "ps 23" to "Psalm 23", "ge 1:1" to "Genesis 1:1", "mk 1:1" to "Mark 1:1",
        )
        for ((input, display) in expect) assertEquals(input, display, resolveText(input).display())
    }

    @Test
    fun ambiguousPrefixListsCandidates() {
        try {
            TestData.catalogue.resolve("Jo")
            fail("expected ambiguity")
        } catch (e: UnknownBookException) {
            assertTrue(e.candidates.map { it.name }.containsAll(listOf("John", "Job", "Joel", "Jonah", "Joshua")))
        }
    }

    @Test
    fun keysRoundTrip() {
        for (k in listOf("JHN", "JHN.3", "JHN.3.16", "JHN.3.16-JHN.3.21", "GEN.1.1-GEN.2.3", "PSA.22-PSA.23")) {
            assertEquals(k, parseKey(k, TestData.catalogue).key())
        }
    }
}
