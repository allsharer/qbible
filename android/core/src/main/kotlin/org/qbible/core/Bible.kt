package org.qbible.core

import kotlin.math.ln

/** One verse as stored (raw text, with `[supplied]` words and `¶`). */
data class Verse(val bookId: String, val chapter: Int, val verse: Int, val text: String)

/** `id = order × 1 000 000 + chapter × 1000 + verse` (translation pack schema v1). */
fun verseId(order: Int, chapter: Int, verse: Int): Long = order * 1_000_000L + chapter * 1000L + verse

/** A resolved passage with its verses and the neighbouring chapters. */
data class PassageView(
    val passage: Passage,
    val verses: List<Verse>,
    val previous: Reference?,
    val next: Reference?,
) {
    val reference: Reference get() = passage.reference
}

data class Hit(
    val verse: Verse,
    val key: String,
    val display: String,
    val segments: List<Search.Segment>,
    val contextBefore: List<Verse> = emptyList(),
    val contextAfter: List<Verse> = emptyList(),
)

data class SearchResult(
    val query: String,
    val mode: String,
    val sort: String,
    val terms: List<Search.Term>,
    val total: Int,
    val offset: Int,
    val limit: Int,
    val hits: List<Hit>,
) {
    val hasMore: Boolean get() = offset + hits.size < total
}

/**
 * A read-only translation pack in the Android format: schema v1 with the FTS5
 * index replaced by the FTS4 table `verses_fts4` (see android/tools/make_android_pack.py).
 * Port of `qbible/repository.py` and the execution half of `qbible/search.py`.
 */
class Bible(private val db: SqlDb, val catalogue: BookCatalogue) {
    val meta: Map<String, String> = db.query("SELECT key, value FROM meta").associate { it.str(0) to it.str(1) }

    init {
        if (meta["format"] != "qbible-translation-pack") throw DataException("This file is not a qbible translation pack.")
        if (meta["schema_version"] != "1") throw DataException("Unsupported translation pack schema ${meta["schema_version"]}.")
        if (meta["search_index"] != FTS_TABLE || meta["search_index_format"] != "fts4-tokens-v1") {
            throw DataException("The translation pack has no Android search index (verses_fts4).")
        }
    }

    val id: String get() = meta["id"] ?: ""
    val name: String get() = meta["name"] ?: id
    val abbreviation: String get() = meta["abbreviation"] ?: id.uppercase()

    val verseCounts: Map<String, List<Int>> by lazy {
        val out = LinkedHashMap<String, MutableList<Int>>()
        for (r in db.query(
            "SELECT c.book_id, c.verses FROM chapters c JOIN books b ON b.id = c.book_id ORDER BY b.ord, c.chapter"
        )) out.getOrPut(r.str(0)) { ArrayList() }.add(r.int(1))
        out
    }

    /** Books present in this translation, in canonical order. */
    val books: List<Book> by lazy { db.query("SELECT id FROM books ORDER BY ord").map { catalogue.get(it.str(0)) } }

    private val chapterSequence: List<Pair<Book, Int>> by lazy {
        books.flatMap { b -> (1..verseCounts.getValue(b.id).size).map { b to it } }
    }
    private val chapterIndex: Map<Pair<String, Int>, Int> by lazy {
        chapterSequence.withIndex().associate { (i, bc) -> (bc.first.id to bc.second) to i }
    }

    fun hasBook(book: Book): Boolean = book.id in verseCounts

    fun parse(text: String): Reference = parseReference(text, catalogue)

    /** Accept a stable key (`JHN.3.16`) or a human reference. */
    fun parseAny(textOrKey: String): Reference =
        try { parseKey(textOrKey, catalogue) } catch (e: Exception) { parse(textOrKey) }

    fun resolve(ref: Reference): Passage = resolveReference(ref, verseCounts)

    fun isValid(ref: Reference): Boolean = try { resolve(ref); true } catch (e: Exception) { false }

    fun passageVerses(p: Passage): List<Verse> {
        val o = p.book.order
        return db.query(
            "SELECT book_id, chapter, verse, text FROM verses WHERE id BETWEEN ? AND ? ORDER BY id",
            listOf(verseId(o, p.start.first, p.start.second), verseId(o, p.end.first, p.end.second)),
        ).map { Verse(it.str(0), it.int(1), it.int(2), it.str(3)) }
    }

    fun versesByIds(ids: List<Long>): Map<Long, Verse> {
        val out = HashMap<Long, Verse>()
        for (chunk in ids.chunked(500)) {
            val marks = chunk.joinToString(",") { "?" }
            for (r in db.query("SELECT id, book_id, chapter, verse, text FROM verses WHERE id IN ($marks)", chunk)) {
                out[r.long(0)] = Verse(r.str(1), r.int(2), r.int(3), r.str(4))
            }
        }
        return out
    }

    /** The chapter before (step = -1) or after (step = 1), crossing books. */
    fun adjacentChapter(book: Book, chapter: Int, step: Int): Reference? {
        val i = chapterIndex[book.id to chapter] ?: return null
        val j = i + step
        if (j < 0 || j >= chapterSequence.size) return null
        val (b, c) = chapterSequence[j]
        return chapterReference(b, c)
    }

    fun passage(ref: Reference, wholeBookAsFirstChapter: Boolean = false): PassageView {
        val r = if (ref.isWholeBook && wholeBookAsFirstChapter) chapterReference(ref.book, 1) else ref
        val p = resolve(r)
        return PassageView(p, passageVerses(p), adjacentChapter(p.book, p.start.first, -1), adjacentChapter(p.book, p.end.first, 1))
    }

    fun passage(text: String): PassageView = passage(parseAny(text))

    // ------------------------------------------------------------------------------ search

    private fun scope(book: Book?, testament: String?): Pair<Long, Long> = when {
        book != null -> book.order * 1_000_000L to book.order * 1_000_000L + 999_999L
        testament == "OT" -> 1_000_000L to 39_999_999L
        testament == "NT" -> 40_000_000L to 66_999_999L
        else -> 0L to (1L shl 62)
    }

    /** SQL (a compound SELECT of docids) and its arguments for the parsed terms. */
    internal fun matchSql(terms: List<Search.Term>, mode: String): Pair<String, List<Any?>> {
        val args = ArrayList<Any?>()
        fun select(t: Search.Term): String {
            val qs = t.fts4Queries()
            args.addAll(qs)
            val one = "SELECT docid FROM $FTS_TABLE WHERE $FTS_TABLE MATCH ?"
            return if (qs.size == 1) one else "SELECT docid FROM (" + qs.joinToString(" INTERSECT ") { one } + ")"
        }
        val pos = terms.filter { !it.negate }.map { select(it) }
        val sql = StringBuilder(pos.joinToString(if (mode == "any") " UNION " else " INTERSECT "))
        for (t in terms.filter { it.negate }) sql.append(" EXCEPT ").append(select(t))
        return sql.toString() to args
    }

    fun search(
        query: String,
        mode: String = "auto",
        limit: Int = 20,
        offset: Int = 0,
        sort: String = "canonical",
        book: Book? = null,
        testament: String? = null,
        context: Int = 0,
    ): SearchResult {
        if (sort !in Search.SORTS) throw SearchQueryException("Unknown sort order '$sort'. Use one of: ${Search.SORTS.joinToString(", ")}.")
        if (limit < 1 || limit > Search.MAX_LIMIT) throw SearchQueryException("The result limit must be between 1 and ${Search.MAX_LIMIT}.")
        if (offset < 0) throw SearchQueryException("The result offset cannot be negative.")
        if (testament != null && testament != "OT" && testament != "NT") throw SearchQueryException("Testament must be OT or NT.")
        if (context < 0 || context > 5) throw SearchQueryException("Context must be between 0 and 5 verses.")

        val terms = Search.parseQuery(query, mode)
        val (match, matchArgs) = matchSql(terms, mode)
        val (lo, hi) = scope(book, testament)
        val inScope = "SELECT docid FROM ($match) WHERE docid BETWEEN ? AND ?"
        val scopeArgs = matchArgs + listOf(lo, hi)

        val total: Int
        val ids: List<Long>
        if (sort == "relevance") {
            val ranked = rankBm25(terms, inScope, scopeArgs)
            total = ranked.size
            ids = ranked.drop(offset).take(limit)
        } else {
            total = db.query("SELECT count(*) FROM ($inScope)", scopeArgs)[0].int(0)
            ids = db.query("$inScope ORDER BY docid LIMIT ? OFFSET ?", scopeArgs + listOf(limit.toLong(), offset.toLong()))
                .map { it.long(0) }
        }

        val verses = versesByIds(ids)
        val rx = Search.highlightRegex(terms)
        val hits = ids.map { i ->
            val v = verses.getValue(i)
            val ref = Reference(catalogue.get(v.bookId), v.chapter, v.verse, v.chapter, v.verse)
            var before = emptyList<Verse>()
            var after = emptyList<Verse>()
            if (context > 0) {
                val near = versesByIds((-context..context).filter { it != 0 }.map { i + it })
                before = (-context..-1).mapNotNull { near[i + it] }
                after = (1..context).mapNotNull { near[i + it] }
            }
            Hit(v, ref.key(), ref.display(), Search.segments(v.text, rx), before, after)
        }
        return SearchResult(query, mode, sort, terms, total, offset, limit, hits)
    }

    private val indexRows: Double by lazy { (meta["search_index_rows"] ?: error("no row count")).toDouble() }
    private val indexTokens: Double by lazy { (meta["search_index_tokens"] ?: error("no token count")).toDouble() }

    /**
     * Every matching docid ordered as FTS5's `ORDER BY bm25(verses_fts), rowid`.
     *
     * This is SQLite's FTS5 bm25() (k1 = 1.2, b = 0.75), computed from the same
     * statistics: rows and tokens in the whole index, documents containing each
     * phrase, phrase occurrences and token count of each matching verse.
     */
    private fun rankBm25(terms: List<Search.Term>, inScope: String, args: List<Any?>): List<Long> {
        val k1 = 1.2
        val b = 0.75
        // FTS5 numbers phrases in expression order: the wanted terms, then the excluded ones.
        val phrases = terms.filter { !it.negate }.flatMap { it.phrases() } + terms.filter { it.negate }.flatMap { it.phrases() }
        val idf = phrases.map { ph ->
            val nHit = db.query("SELECT count(*) FROM $FTS_TABLE WHERE $FTS_TABLE MATCH ?", listOf(ph.fts4))[0].long(0)
            val v = ln((indexRows - nHit + 0.5) / (nHit + 0.5))
            if (v <= 0.0) 1e-6 else v
        }
        val avgdl = indexTokens / indexRows
        val scored = db.query("SELECT docid, body FROM $FTS_TABLE WHERE docid IN ($inScope)", args).map { r ->
            val doc = r.str(1).split(' ').filter { it.isNotEmpty() }
            val d = doc.size.toDouble()
            var score = 0.0
            for (i in phrases.indices) {
                val f = phrases[i].count(doc).toDouble()
                score += idf[i] * ((f * (k1 + 1.0)) / (f + k1 * (1 - b + b * d / avgdl)))
            }
            r.long(0) to -1.0 * score
        }
        return scored.sortedWith(compareBy<Pair<Long, Double>> { it.second }.thenBy { it.first }).map { it.first }
    }

    companion object {
        const val FTS_TABLE = "verses_fts4"
    }
}
