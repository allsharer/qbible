package org.qbible.core

import org.qbible.core.Py.ALNUM
import org.qbible.core.Py.NOT_ALNUM
import org.qbible.core.Py.NOT_S

/**
 * Search query language and highlighting (port of `qbible/search.py`).
 *
 * Query syntax (`auto` mode): `faith hope` (all words), `"faith without works"`
 * (exact phrase), `love -fear` (exclusion), `belie*` (prefix). Other modes:
 * `phrase`, `all`, `any`.
 *
 * The desktop builds one FTS5 expression. Android's SQLite has FTS4 instead,
 * and whether FTS4 accepts AND/NOT/parentheses depends on a compile option, so
 * here each term becomes its own simple FTS4 MATCH (a single quoted phrase) and
 * the terms are combined with SQL INTERSECT / UNION / EXCEPT. User text never
 * reaches SQL or FTS syntax: only `[a-z0-9]` tokens are used, as bound parameters.
 */
object Search {
    val MODES = listOf("auto", "phrase", "all", "any")
    val SORTS = listOf("canonical", "relevance")
    const val MAX_QUERY_LENGTH = 300
    const val MAX_TERMS = 16
    const val MAX_LIMIT = 500

    private val TERM_RE = Regex("(-?)\"([^\"]*)\"?|($NOT_S+)")

    data class Term(
        val tokens: List<String>,
        val phrase: Boolean = false,
        val prefix: Boolean = false,
        val negate: Boolean = false,
    ) {
        fun describe(): String {
            var s = tokens.joinToString(" ") + if (prefix) "*" else ""
            if (phrase) s = "\"$s\""
            return (if (negate) "-" else "") + s
        }

        /**
         * FTS4 MATCH strings for this term. A phrase (or single token) is one
         * quoted string; FTS4 treats a trailing `*` inside the quotes as a prefix
         * on the last token, as FTS5's `"a" + "b" *` does.
         */
        fun fts4Queries(): List<String> {
            val star = if (prefix) "*" else ""
            return if (phrase || tokens.size == 1) {
                listOf("\"" + tokens.joinToString(" ") + star + "\"")
            } else {
                // Several separate tokens that must all occur (FTS5: ("a" "b")).
                tokens.mapIndexed { i, t -> "\"" + t + (if (i == tokens.lastIndex) star else "") + "\"" }
            }
        }

        /** The phrases this term contributes to BM25 ranking, in FTS5 order. */
        internal fun phrases(): List<Phrase> =
            if (phrase || tokens.size == 1) listOf(Phrase(tokens, prefix))
            else tokens.mapIndexed { i, t -> Phrase(listOf(t), prefix && i == tokens.lastIndex) }
    }

    internal data class Phrase(val tokens: List<String>, val prefix: Boolean) {
        val fts4: String get() = "\"" + tokens.joinToString(" ") + (if (prefix) "*" else "") + "\""

        /** Number of occurrences in a token stream (FTS5 xInst counts each start position). */
        fun count(doc: List<String>): Int {
            val n = tokens.size
            var hits = 0
            for (i in 0..doc.size - n) {
                var ok = true
                for (j in 0 until n) {
                    val d = doc[i + j]
                    val t = tokens[j]
                    val match = if (prefix && j == n - 1) d.startsWith(t) else d == t
                    if (!match) { ok = false; break }
                }
                if (ok) hits++
            }
            return hits
        }
    }

    fun parseQuery(query: String?, mode: String = "auto"): List<Term> {
        if (mode !in MODES) throw SearchQueryException("Unknown search mode '$mode'. Use one of: ${MODES.joinToString(", ")}.")
        var q = (query ?: "").trim()
        if (q.isEmpty()) throw SearchQueryException("Enter a word or phrase to search for.")
        if (q.codePointCount(0, q.length) > MAX_QUERY_LENGTH) {
            throw SearchQueryException("Search text is too long (maximum $MAX_QUERY_LENGTH characters).")
        }
        q = q.replace('“', '"').replace('”', '"')

        val terms = ArrayList<Term>()
        when (mode) {
            "phrase" -> {
                val toks = TextFmt.tokens(q)
                if (toks.isNotEmpty()) terms.add(Term(toks, phrase = true))
            }
            "all", "any" -> TextFmt.tokens(q).forEach { terms.add(Term(listOf(it))) }
            else -> for (m in TERM_RE.findAll(q)) {
                val neg = m.groups[1]?.value ?: ""
                val quoted = m.groups[2]?.value
                if (quoted != null) {
                    val toks = TextFmt.tokens(quoted)
                    if (toks.isNotEmpty()) terms.add(Term(toks, phrase = true, negate = neg.isNotEmpty()))
                    continue
                }
                var word = m.groups[3]!!.value
                val negate = word.startsWith("-") && word.length > 1
                if (negate) word = word.substring(1)
                val prefix = word.endsWith("*")
                val toks = TextFmt.tokens(word)
                if (toks.isEmpty()) continue
                // "brother's" -> tokens (brother, s): keep them adjacent.
                terms.add(Term(toks, phrase = toks.size > 1, prefix = prefix, negate = negate))
            }
        }
        if (terms.isEmpty()) throw SearchQueryException("The search must contain at least one letter or number.")
        if (terms.size > MAX_TERMS) throw SearchQueryException("Too many search terms (maximum $MAX_TERMS).")
        if (terms.all { it.negate }) {
            throw SearchQueryException("A search needs at least one word to look for, not only excluded words.")
        }
        return terms
    }

    // ------------------------------------------------------------------------- highlighting

    private fun tokenPattern(tok: String): String =
        tok.split("ae").joinToString("(?:ae|æ)") { Regex.escape(it).takeIf { e -> it.isNotEmpty() } ?: "" }

    fun highlightRegex(terms: List<Term>): Regex? {
        val pats = terms.filter { !it.negate }.map { t ->
            val body = t.tokens.joinToString("$NOT_ALNUM+") { tokenPattern(it) }
            val end = if (t.prefix) "$ALNUM*" else ""
            "(?<!$ALNUM)$body$end(?!$ALNUM)"
        }
        if (pats.isEmpty()) return null
        return Regex(pats.joinToString("|") { "(?:$it)" }, RegexOption.IGNORE_CASE)
    }

    /** One display segment of a verse; clients style it, never parse markup. */
    data class Segment(val text: String, val supplied: Boolean, val match: Boolean)

    /** Display segments of [raw] verse text, with matches of [rx] marked. */
    fun segments(raw: String, rx: Regex?): List<Segment> {
        val ps = TextFmt.parts(raw)
        val plain = ps.joinToString("") { it.text }
        var spans: List<IntRange> = emptyList()
        if (rx != null) {
            val searchable = sameLengthFold(plain)
            spans = rx.findAll(searchable).filter { it.range.last + 1 > it.range.first }.map { it.range }.toList()
        }
        val out = ArrayList<Segment>()
        var pos = 0
        for (p in ps) {
            val start = pos
            val end = pos + p.text.length
            val cuts = sortedSetOf(start, end)
            for (s in spans) {
                val a = s.first
                val b = s.last + 1
                if (a in (start + 1) until end) cuts.add(a)
                if (b in (start + 1) until end) cuts.add(b)
            }
            val bounds = cuts.toList()
            for (i in 0 until bounds.size - 1) {
                val a = bounds[i]
                val b = bounds[i + 1]
                val hit = spans.any { it.first <= a && b <= it.last + 1 }
                val seg = Segment(plain.substring(a, b), p.supplied, hit)
                val last = out.lastOrNull()
                if (last != null && last.supplied == seg.supplied && last.match == seg.match) {
                    out[out.lastIndex] = last.copy(text = last.text + seg.text)
                } else {
                    out.add(seg)
                }
            }
            pos = end
        }
        return out
    }

    private fun sameLengthFold(text: String): String {
        val sb = StringBuilder(text.length)
        for (ch in text) {
            if (ch == 'æ' || ch == 'Æ') { sb.append(ch); continue } // matched by (?:ae|æ)
            val f = TextFmt.fold(ch.toString())
            sb.append(if (f.length == 1) f else ch.toString())
        }
        return sb.toString()
    }
}
