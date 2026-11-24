package org.qbible.core

import java.text.Normalizer

/**
 * Verse text conventions (port of `qbible/textfmt.py`).
 *
 * Stored text is exactly as published: `[word]` marks translator-supplied words,
 * a leading `¶` marks a paragraph, and ’ and æ are preserved.
 */
object TextFmt {
    const val PILCROW = "¶"
    private val SUPPLIED_RE = Regex("\\[([^\\[\\]]*)\\]")
    private val TOKEN_RE = Regex("[a-z0-9]+")

    data class Part(val text: String, val supplied: Boolean = false)

    fun startsParagraph(raw: String): Boolean = raw.trimStart().startsWith(PILCROW)

    fun stripPilcrow(raw: String): String = raw.replace(PILCROW, "").trim()

    /** Split raw verse text into plain and translator-supplied parts. */
    fun parts(raw: String): List<Part> {
        val text = stripPilcrow(raw)
        val out = ArrayList<Part>()
        var pos = 0
        for (m in SUPPLIED_RE.findAll(text)) {
            if (m.range.first > pos) out.add(Part(text.substring(pos, m.range.first)))
            val inner = m.groupValues[1]
            if (inner.isNotEmpty()) out.add(Part(inner, true))
            pos = m.range.last + 1
        }
        if (pos < text.length) out.add(Part(text.substring(pos)))
        return out
    }

    /** Reading text without brackets or pilcrows. */
    fun plain(raw: String): String = parts(raw).joinToString("") { it.text }

    enum class Supplied { ITALIC, BRACKETS, PLAIN }

    /** Plain-text rendering, with supplied words in brackets if asked (italic is not possible in plain text). */
    fun render(raw: String, supplied: Supplied = Supplied.PLAIN): String =
        parts(raw).joinToString("") { p ->
            if (p.supplied && supplied == Supplied.BRACKETS) "[${p.text}]" else p.text
        }

    private val FOLD = mapOf(
        '’' to "'", '‘' to "'", 'ʼ' to "'", '`' to "'",
        'æ' to "ae", 'Æ' to "Ae", 'œ' to "oe", 'Œ' to "Oe",
    )

    /**
     * Fold ligatures, curly apostrophes and diacritics; keep everything else.
     *
     * Python drops characters whose canonical combining class is non-zero; Java
     * has no portable API for that, so non-spacing marks (Mn) are dropped. The
     * two agree on all Latin text (and on every verse of the KJV, which the
     * tests check token by token).
     */
    fun fold(text: String): String {
        val sb = StringBuilder(text.length)
        for (ch in text) sb.append(FOLD[ch] ?: ch)
        val nfkd = Normalizer.normalize(sb, Normalizer.Form.NFKD)
        val out = StringBuilder(nfkd.length)
        for (ch in nfkd) if (Character.getType(ch) != Character.NON_SPACING_MARK.toInt()) out.append(ch)
        return out.toString()
    }

    /** Normalised text stored in the full-text index (never displayed). */
    fun searchText(raw: String): String = fold(plain(raw)).lowercase()

    /** Search tokens, exactly as the desktop FTS5 index splits text. */
    fun tokens(text: String): List<String> = TOKEN_RE.findAll(fold(text).lowercase()).map { it.value }.toList()
}
