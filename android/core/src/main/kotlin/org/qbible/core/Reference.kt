package org.qbible.core

import org.qbible.core.Py.D
import org.qbible.core.Py.NOT_D
import org.qbible.core.Py.S

/**
 * Scripture reference parsing, validation, formatting and detection
 * (port of `qbible/reference.py`; see that file for the accepted forms).
 * Invalid references are never clamped or redirected.
 */

/** Books with one chapter: a bare number after these names is a verse ("Jude 3"), except "1". */
val SINGLE_CHAPTER_BOOKS = setOf("OBA", "PHM", "2JN", "3JN", "JUD")

/** A parsed reference; `null` fields mean "the whole" book or chapter. */
data class Reference(
    val book: Book,
    val startChapter: Int? = null,
    val startVerse: Int? = null,
    val endChapter: Int? = null,
    val endVerse: Int? = null,
) {
    val isWholeBook: Boolean get() = startChapter == null
    val hasVerses: Boolean get() = startVerse != null

    /** Stable machine key, e.g. `JHN.3.16-JHN.3.21` (identical to the desktop app). */
    fun key(): String {
        val b = book.id
        if (startChapter == null) return b
        val start = "$b.$startChapter" + (if (startVerse != null && startVerse != 0) ".$startVerse" else "")
        if (endChapter == null || (endChapter == startChapter && endVerse == startVerse)) return start
        val end = "$b.$endChapter" + (if (endVerse != null && endVerse != 0) ".$endVerse" else "")
        return "$start-$end"
    }

    fun display(): String = formatReference(this)
}

/** A reference resolved against a translation: concrete, inclusive bounds. */
data class Passage(val reference: Reference, val start: Pair<Int, Int>, val end: Pair<Int, Int>) {
    val book: Book get() = reference.book
    val chapters: IntRange get() = start.first..end.first
    val isSingleChapter: Boolean get() = start.first == end.first
    fun display(): String = reference.display()
    fun key(): String = reference.key()
}

private const val DASHES = "‐‑‒–—―−"
private val SPLIT_RE = Regex(
    "$S*((?:[1-3](?:st|nd|rd)?[${Py.WS_CHARS}.\\-]*)?$NOT_D+?)$S*\\.?$S*($D.*?)?$S*",
    RegexOption.IGNORE_CASE,
)
private val HAS_LETTER_RE = Regex("[A-Za-z]")
private val WS_RUN_RE = Regex("$S+")

private enum class Kind { C, C_OPEN, C_C, C_V, C_V_OPEN, C_V_V, C_V_C_V }

private val NUM_PATTERNS = listOf(
    Kind.C to Regex("($D+)"),
    Kind.C_OPEN to Regex("($D+)-"),
    Kind.C_C to Regex("($D+)-($D+)"),
    Kind.C_V to Regex("($D+):($D+)"),
    Kind.C_V_OPEN to Regex("($D+):($D+)-"),
    Kind.C_V_V to Regex("($D+):($D+)-($D+)"),
    Kind.C_V_C_V to Regex("($D+):($D+)-($D+):($D+)"),
)
private const val MAX_NUMBER = 999

private fun normaliseInput(text: String): String {
    var t = text.replace(' ', ' ')
    for (d in DASHES) t = t.replace(d, '-')
    t = WS_RUN_RE.replace(t, " ").trim()
    return t.trimEnd('.', ';', ',')
}

private val SEP_RE = Regex("$S*([:.\\-])$S*")
private val VERSE_WORD_RE = Regex("($D)$S*(?:vv?\\.?|verses?)$S*($D)")
private val C_SPACE_V_RE = Regex("^($D+) ($D+)")
private val END_SPACE_RE = Regex("-($D+) ($D+)$")

private fun normaliseNumbers(nums: String): String {
    var n = nums.trim().lowercase()
    n = SEP_RE.replace(n, "$1")
    n = VERSE_WORD_RE.replace(n, "$1:$2")
    n = n.replace(".", ":")
    n = C_SPACE_V_RE.replace(n, "$1:$2")
    n = END_SPACE_RE.replace(n, "-$1:$2")
    return n
}

/** Parse [text] into a [Reference] (not yet validated against a translation). */
fun parseReference(text: String?, books: BookCatalogue): Reference {
    if (text == null || text.isBlank()) {
        throw ReferenceSyntaxException("Enter a scripture reference, for example 'John 3:16'.")
    }
    if (text.codePointCount(0, text.length) > 200) throw ReferenceSyntaxException("That reference is too long.")
    val t = normaliseInput(text)
    val m = SPLIT_RE.matchEntire(t)
    if (m == null || !HAS_LETTER_RE.containsMatchIn(m.groupValues[1])) {
        throw ReferenceSyntaxException("'${text.trim()}' does not look like a scripture reference.")
    }
    val book = books.resolve(m.groupValues[1])
    val nums = m.groups[2]?.value
    if (nums.isNullOrEmpty()) return Reference(book)

    val n = normaliseNumbers(nums)
    if (',' in n || ';' in n) {
        throw ReferenceSyntaxException(
            "Lists of separate verses are not supported; use one reference or range at a time."
        )
    }
    var kind: Kind? = null
    var raw: List<String> = emptyList()
    for ((k, pat) in NUM_PATTERNS) {
        val mm = pat.matchEntire(n)
        if (mm != null) {
            kind = k
            raw = mm.groupValues.drop(1)
            break
        }
    }
    if (kind == null) throw ReferenceSyntaxException("Cannot understand the chapter and verse part '${nums.trim()}'.")
    val big = raw.map { pyInt(it) ?: Long.MAX_VALUE }
    if (big.any { it > MAX_NUMBER }) throw ReferenceSyntaxException("Chapter and verse numbers must be below 1000.")
    if (big.any { it == 0L }) throw ReferenceSyntaxException("Chapter and verse numbers start at 1.")
    val v = big.map { it.toInt() }

    val single = book.id in SINGLE_CHAPTER_BOOKS
    return when (kind) {
        Kind.C -> {
            val c = v[0]
            if (single && c != 1) Reference(book, 1, c, 1, c) else Reference(book, c, null, c, null)
        }
        Kind.C_OPEN -> {
            if (!single) {
                throw ReferenceSyntaxException("Give a verse to start from, for example '${book.name} ${v[0]}:1-'.")
            }
            Reference(book, 1, v[0], 1, null)
        }
        Kind.C_C -> if (single) Reference(book, 1, v[0], 1, v[1]) else Reference(book, v[0], null, v[1], null)
        Kind.C_V -> Reference(book, v[0], v[1], v[0], v[1])
        Kind.C_V_OPEN -> Reference(book, v[0], v[1], v[0], null) // end verse filled in by resolve
        Kind.C_V_V -> Reference(book, v[0], v[1], v[0], v[2])
        Kind.C_V_C_V -> Reference(book, v[0], v[1], v[2], v[3])
    }
}

private val KEY_RE = Regex("([0-9A-Z]{3})(?:\\.($D+)(?:\\.($D+))?)?(?:-([0-9A-Z]{3})\\.($D+)(?:\\.($D+))?)?")

/** Inverse of [Reference.key]. */
fun parseKey(key: String?, books: BookCatalogue): Reference {
    val m = KEY_RE.matchEntire(key ?: "") ?: throw ReferenceSyntaxException("Invalid reference key: '$key'")
    val g = m.groups
    fun num(i: Int): Int? = g[i]?.value?.let {
        val n = pyInt(it) ?: Long.MAX_VALUE
        if (n > Int.MAX_VALUE) throw ReferenceSyntaxException("Invalid reference key: '$key'")
        n.toInt()
    }
    val book = books.get(g[1]!!.value)
    val b2 = g[4]?.value
    if (b2 != null && b2 != book.id) throw ReferenceSyntaxException("References spanning several books are not supported.")
    val c1 = num(2) ?: return Reference(book)
    val v1 = num(3)
    val c2 = num(5) ?: return Reference(book, c1, v1, c1, v1)
    return Reference(book, c1, v1, c2, num(6))
}

/**
 * Validate [ref] against a versification (book id -> verses per chapter) and
 * return concrete bounds, or throw a precise error.
 */
fun resolveReference(ref: Reference, verseCounts: Map<String, List<Int>>): Passage {
    val book = ref.book
    val counts = verseCounts[book.id]
    if (counts.isNullOrEmpty()) throw InvalidChapterException("${book.name} is not available in this translation.")
    val nCh = counts.size

    fun checkChapter(c: Int) {
        if (c < 1 || c > nCh) {
            val plural = if (nCh == 1) "chapter" else "chapters"
            throw InvalidChapterException("${book.name} has $nCh $plural; there is no chapter $c.")
        }
    }

    fun checkVerse(c: Int, v: Int) {
        val n = counts[c - 1]
        if (v < 1 || v > n) throw InvalidVerseException("${chapterName(book, c)} has $n verses; there is no verse $v.")
    }

    val sc0 = ref.startChapter ?: return Passage(ref, 1 to 1, nCh to counts.last())
    val sc = sc0
    val ec = ref.endChapter ?: sc
    checkChapter(sc)
    checkChapter(ec)
    val sv = ref.startVerse ?: 1
    val ev = ref.endVerse ?: counts[ec - 1]
    if (ref.startVerse != null) checkVerse(sc, sv)
    if (ref.endVerse != null) checkVerse(ec, ev)
    if (ec < sc || (ec == sc && ev < sv)) {
        throw ReferenceSyntaxException("The range in '${formatReference(ref)}' ends before it begins.")
    }
    var r = ref
    if (ref.startVerse != null && ref.endVerse == null) {
        // Open-ended verse range ("Mark 4:1-"): name the real last verse ("Mark 4:1-41").
        r = Reference(book, sc, sv, ec, ev)
    }
    return Passage(r, sc to sv, ec to ev)
}

internal fun chapterName(book: Book, chapter: Int): String = "${book.singularName} $chapter"

/** Human-readable canonical form, e.g. `John 3:16-21` or `Psalm 23`. */
fun formatReference(ref: Reference): String {
    val b = ref.book
    val sc = ref.startChapter ?: return b.name
    val sv = ref.startVerse
    val ec = ref.endChapter ?: sc
    val ev = ref.endVerse
    if (sv == null) {
        return if (ec == sc) chapterName(b, sc) else "${b.name} $sc-$ec"
    }
    if (ec == sc) {
        return if (ev == null || ev == sv) "${chapterName(b, sc)}:$sv" else "${chapterName(b, sc)}:$sv-$ev"
    }
    return "${b.name} $sc:$sv-$ec:$ev"
}

fun chapterReference(book: Book, chapter: Int): Reference = Reference(book, chapter, null, chapter, null)

// ------------------------------------------------------------------------------- detection

private val FIND_RE = Regex(
    "(?<![\\p{L}\\p{N}_:])" + // Python: (?<![\w:])
        "((?:(?:[1-3]|I{1,3}|First|Second|Third)$S*)?[A-Za-z][A-Za-z]*\\.?(?:$S+of$S+[A-Za-z]+)?)" +
        "$S*" +
        "($D{1,3})" +
        "(?:[:.]($D{1,3})(?:$S*[-–—]$S*($D{1,3})(?:[:.]($D{1,3}))?)?)?" +
        // Same set as the look-behind, written in this order because Android's ICU regex
        // engine rejects "(?![\\p{L}\\p{N}_:])" at this point ("Incorrect Unicode property").
        "(?![_:\\p{L}\\p{N}])"
)

data class FoundReference(val start: Int, val end: Int, val text: String, val reference: Reference)

/**
 * Find confidently recognisable references in free text: a chapter *and*
 * verse with a known name or abbreviation (`Rom 8:28`), or a full book name
 * with a chapter (`Psalm 23`). [isValid] filters out nonexistent passages.
 */
fun findReferences(text: String, books: BookCatalogue, isValid: ((Reference) -> Boolean)? = null): List<FoundReference> {
    val found = ArrayList<FoundReference>()
    var pos = 0
    while (pos <= text.length) {
        val m = FIND_RE.find(text, pos) ?: break
        val ref = foundToReference(m, books)
        if (ref != null && (isValid == null || isValid(ref))) {
            found.add(FoundReference(m.range.first, m.range.last + 1, m.value, ref))
            pos = m.range.last + 1
        } else {
            pos = m.range.first + 1
        }
    }
    return found
}

private fun foundToReference(m: MatchResult, books: BookCatalogue): Reference? {
    val bookText = m.groupValues[1]
    val book = books.exact(bookText) ?: return null
    val lower = bookText.trimEnd('.').lowercase()
    val fullName = lower == book.name.lowercase() || lower == book.singularName.lowercase()
    val c = pyInt(m.groupValues[2])!!.toInt()
    val vText = m.groups[3]?.value
    if (vText == null) {
        if (!fullName || book.id in SINGLE_CHAPTER_BOOKS) return null
        return Reference(book, c, null, c, null)
    }
    val v = pyInt(vText)!!.toInt()
    val v2 = m.groups[4]?.value?.let { pyInt(it)!!.toInt() }
    val v3 = m.groups[5]?.value?.let { pyInt(it)!!.toInt() }
    if (v3 != null) return Reference(book, c, v, v2, v3)
    if (v2 != null) return Reference(book, c, v, c, v2)
    return Reference(book, c, v, c, v)
}
