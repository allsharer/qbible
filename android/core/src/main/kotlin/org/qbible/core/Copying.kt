package org.qbible.core

/**
 * Plain text for copying or sharing verses with their reference, in the same
 * shape as the browser interface (`passageText` in web/assets/js/app.js):
 *
 *     For God so loved the world, ...
 *     — John 3:16 (KJV)
 *
 * or, for several verses, a heading line then numbered verses (with `[n]`
 * chapter markers when the selection spans chapters).
 */
object Copying {
    /** Reference for a contiguous run of verses within one book. */
    fun rangeReference(book: Book, first: Verse, last: Verse): Reference =
        if (first.chapter == last.chapter && first.verse == last.verse) {
            Reference(book, first.chapter, first.verse, first.chapter, first.verse)
        } else {
            Reference(book, first.chapter, first.verse, last.chapter, last.verse)
        }

    fun text(
        verses: List<Verse>,
        display: String,
        abbreviation: String,
        supplied: TextFmt.Supplied = TextFmt.Supplied.PLAIN,
    ): String {
        require(verses.isNotEmpty())
        fun plainOf(v: Verse) = TextFmt.render(v.text, if (supplied == TextFmt.Supplied.BRACKETS) supplied else TextFmt.Supplied.PLAIN)
        if (verses.size == 1) return "${plainOf(verses[0])}\n— $display ($abbreviation)"
        val lines = ArrayList<String>()
        val multiChapter = verses.first().chapter != verses.last().chapter
        var lastChapter: Int? = null
        for (v in verses) {
            if (multiChapter && v.chapter != lastChapter) lines.add("[${v.chapter}]")
            lastChapter = v.chapter
            lines.add("${v.verse} ${plainOf(v)}")
        }
        return "$display ($abbreviation)\n" + lines.joinToString("\n")
    }
}
