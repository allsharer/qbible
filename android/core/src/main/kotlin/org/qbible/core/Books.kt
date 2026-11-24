package org.qbible.core

import org.json.JSONObject

/** One canonical book (port of `qbible/books.py`). Ids are stable USFM codes. */
data class Book(
    val id: String,
    val order: Int,
    val name: String,
    val slug: String,
    val osis: String,
    val testament: String, // "OT" or "NT"
    val aliases: List<String>,
) {
    /** Name used when referring to one chapter ("Psalm 23"). */
    val singularName: String get() = if (id == "PSA") "Psalm" else name

    override fun toString(): String = id
}

private val ORDINAL_WORDS = mapOf(
    "first" to "1", "1st" to "1", "i" to "1",
    "second" to "2", "2nd" to "2", "ii" to "2",
    "third" to "3", "3rd" to "3", "iii" to "3",
)
private val ORDINAL_RE = Regex("^(first|second|third|1st|2nd|3rd|iii|ii|i)${Py.S}+(?=[a-z])")
private val DOT_SPACE_RE = Regex("[. _]")
private val WS_RUN_RE = Regex("${Py.S}+")
private val KEY_DROP_RE = Regex("[${Py.WS_CHARS}'-]")
private val LEADING_DIGIT_RE = Regex("^${Py.D}")
private const val PREFIX_MIN = 3

/** Normalise a book name for lookup: case, ordinals, spaces and dots. */
fun bookKey(text: String): String {
    var t = text.trim().lowercase().replace("’", "'")
    t = DOT_SPACE_RE.replace(t, " ")
    t = WS_RUN_RE.replace(t, " ").trim()
    val m = ORDINAL_RE.find(t)
    if (m != null) t = ORDINAL_WORDS.getValue(m.groupValues[1]) + t.substring(m.range.last + 1)
    return KEY_DROP_RE.replace(t, "")
}

/** All known books, with alias lookup. Built from `books.json`; nothing is hard-coded. */
class BookCatalogue(books: List<Book>, private val unknownBookHint: String = DEFAULT_HINT) : Iterable<Book> {
    val books: List<Book> = books.sortedBy { it.order }
    private val byId = this.books.associateBy { it.id }
    private val bySlug = this.books.associateBy { it.slug }
    private val lookup = HashMap<String, Book>()
    private val names = this.books.map { bookKey(it.name) to it }

    init {
        for (b in this.books) {
            val keys = linkedSetOf(bookKey(b.id), bookKey(b.name), bookKey(b.slug), bookKey(b.osis))
            b.aliases.forEach { keys.add(bookKey(it)) }
            for (key in keys) {
                val other = lookup[key]
                require(other == null || other == b) { "Book alias '$key' is ambiguous: ${other!!.id} and ${b.id}" }
                lookup[key] = b
            }
        }
    }

    override fun iterator(): Iterator<Book> = books.iterator()
    val size: Int get() = books.size

    fun get(bookId: String): Book =
        byId[bookId.uppercase()] ?: throw UnknownBookException("Unknown book id: $bookId")

    fun getOrNull(bookId: String): Book? = byId[bookId.uppercase()]

    fun bySlug(slug: String): Book? = bySlug[slug.lowercase()]

    /** Resolve a full name, id or listed alias; no prefix guessing. */
    fun exact(text: String): Book? = lookup[bookKey(text)]

    /**
     * Resolve a user-entered book name: exact names, ids and aliases first, then
     * an unambiguous prefix (at least three letters) of a full book name.
     */
    fun resolve(text: String): Book {
        val key = bookKey(text)
        if (key.isEmpty()) throw UnknownBookException("No book name given.")
        lookup[key]?.let { return it }
        val letters = LEADING_DIGIT_RE.replaceFirst(key, "")
        if (letters.codePointCount(0, letters.length) >= 2) {
            val matches = names.filter { it.first.startsWith(key) }.map { it.second }
            if (matches.size == 1 && letters.codePointCount(0, letters.length) >= PREFIX_MIN) return matches[0]
            if (matches.size > 1) {
                val list = matches.joinToString(", ") { it.name }
                throw UnknownBookException("'${text.trim()}' is ambiguous. Did you mean: $list?", matches)
            }
        }
        throw UnknownBookException("Unknown book: '${text.trim()}'.$unknownBookHint")
    }

    companion object {
        /** The desktop message points at `qbible books`; the app passes its own hint. */
        const val DEFAULT_HINT = " Run 'qbible books' to list book names."

        fun fromJson(json: String, unknownBookHint: String = DEFAULT_HINT): BookCatalogue {
            val root = JSONObject(json)
            val arr = root.getJSONArray("books")
            val list = (0 until arr.length()).map { i ->
                val b = arr.getJSONObject(i)
                val al = b.getJSONArray("aliases")
                Book(
                    id = b.getString("id"),
                    order = b.getInt("order"),
                    name = b.getString("name"),
                    slug = b.getString("slug"),
                    osis = b.getString("osis"),
                    testament = b.getString("testament"),
                    aliases = (0 until al.length()).map { al.getString(it) },
                )
            }
            return BookCatalogue(list, unknownBookHint)
        }
    }
}
