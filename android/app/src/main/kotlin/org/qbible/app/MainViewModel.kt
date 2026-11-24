package org.qbible.app

import android.app.Application
import android.net.Uri
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.qbible.core.Bible
import org.qbible.core.Book
import org.qbible.core.Copying
import org.qbible.core.Hit
import org.qbible.core.PassageView
import org.qbible.core.QBibleException
import org.qbible.core.Reference
import org.qbible.core.UserStore
import org.qbible.core.chapterReference
import org.qbible.core.findReferences

enum class Tab { READ, BOOKS, SEARCH, SAVED, SETTINGS }

/** A passage a search query looks like (or mentions), offered as a link. */
data class Offer(val key: String, val display: String)

/**
 * All screen state, and every call into the core (always off the main thread).
 * There is no network code anywhere in the app.
 */
class MainViewModel(app: Application) : AndroidViewModel(app) {
    private val ctx get() = getApplication<Application>()
    private lateinit var data: AppData
    private val bible: Bible get() = data.bible
    private val user: UserStore get() = data.user
    val translation: String get() = bible.id

    // -- app ---------------------------------------------------------------------------
    var ready by mutableStateOf(false); private set
    var fatalError by mutableStateOf<String?>(null); private set
    var tab by mutableStateOf(Tab.READ)
    var prefs by mutableStateOf(Prefs.load(app)); private set

    /** One-off messages for the snackbar. */
    val messages = mutableStateListOf<String>()

    fun say(msg: String) { messages.add(msg) }

    fun updatePrefs(p: Prefs) {
        prefs = p
        p.save(ctx)
    }

    val books: List<Book> get() = bible.books
    fun verseCount(book: Book): List<Int> = bible.verseCounts[book.id].orEmpty()
    val packMeta: Map<String, String> get() = bible.meta

    // -- reading -----------------------------------------------------------------------
    var view by mutableStateOf<PassageView?>(null); private set
    var refText by mutableStateOf("")
    var refError by mutableStateOf<String?>(null); private set
    var selection by mutableStateOf<IntRange?>(null); private set
    private var anchor = 0
    var passageBookmark by mutableStateOf<UserStore.Bookmark?>(null); private set

    /** Scroll position to restore when the last-read passage reopens after a restart. */
    var restoreScroll: Pair<Int, Int>? = null; private set
    private val backStack = ArrayDeque<String>()

    init {
        viewModelScope.launch {
            try {
                data = withContext(Dispatchers.IO) { (ctx as QBibleApplication).data }
                val last = withContext(Dispatchers.IO) { runCatching { user.lastPosition() }.getOrNull() }
                val sp = ctx.getSharedPreferences(Prefs.FILE, 0)
                val key = last?.key ?: "GEN.1"
                if (sp.getString("scrollKey", null) == key) restoreScroll = sp.getInt("scrollIndex", 0) to sp.getInt("scrollOffset", 0)
                ready = true
                open(key, push = false, record = last == null)
            } catch (e: Exception) {
                fatalError = "The Bible text could not be opened: ${e.message}"
            }
        }
    }

    fun consumeRestoreScroll(): Pair<Int, Int>? = restoreScroll.also { restoreScroll = null }

    fun saveScroll(key: String, index: Int, offset: Int) {
        ctx.getSharedPreferences(Prefs.FILE, 0).edit().putString("scrollKey", key)
            .putInt("scrollIndex", index).putInt("scrollOffset", offset).apply()
    }

    /** Open what the user typed in the reference box; on error, stay put and explain. */
    fun goToTyped() {
        val text = refText
        viewModelScope.launch {
            val r = withContext(Dispatchers.IO) { runCatching { bible.passage(bible.parse(text)) } }
            r.onSuccess { show(it, push = true); refText = "" }
                .onFailure { refError = messageOf(it) }
        }
    }

    fun clearRefError() { refError = null }

    /** Open a stable key (`JHN.3.16`) or reference text. */
    fun open(keyOrText: String, push: Boolean = true, record: Boolean = true) {
        viewModelScope.launch {
            val r = withContext(Dispatchers.IO) { runCatching { bible.passage(keyOrText) } }
            r.onSuccess { show(it, push, record) }.onFailure { say(messageOf(it)) }
        }
    }

    fun open(ref: Reference) = open(ref.key())

    private suspend fun show(v: PassageView, push: Boolean, record: Boolean = true) {
        val current = view
        if (push && current != null && current.reference.key() != v.reference.key()) {
            backStack.addLast(current.reference.key())
            while (backStack.size > 50) backStack.removeFirst()
        }
        view = v
        selection = null
        refError = null
        tab = Tab.READ
        passageBookmark = withContext(Dispatchers.IO) {
            if (record) runCatching { user.record(translation, v.reference) }
            runCatching { user.findBookmark(translation, v.reference) }.getOrNull()
        }
    }

    fun step(delta: Int) {
        val v = view ?: return
        (if (delta < 0) v.previous else v.next)?.let { open(it) }
    }

    fun wholeChapter() {
        val v = view ?: return
        open(chapterReference(v.passage.book, v.passage.start.first))
    }

    /** True if Back was handled inside the app. */
    fun back(): Boolean {
        if (tab == Tab.BOOKS && booksSelected != null) { booksSelected = null; return true }
        if (tab != Tab.READ) { tab = Tab.READ; return true }
        if (selection != null) { selection = null; return true }
        val prev = backStack.removeLastOrNull() ?: return false
        open(prev, push = false)
        return true
    }

    fun tapVerse(index: Int) {
        val sel = selection
        selection = when {
            sel == null -> { anchor = index; index..index }
            sel.first == index && sel.last == index -> null
            else -> minOf(anchor, index)..maxOf(anchor, index)
        }
    }

    fun clearSelection() { selection = null }

    fun selectionReference(): Reference? {
        val v = view ?: return null
        val s = selection ?: return null
        return Copying.rangeReference(v.passage.book, v.verses[s.first], v.verses[s.last])
    }

    /** Text for copying or sharing: the selected verses, or the whole passage. */
    fun shareText(selectionOnly: Boolean): Pair<String, String>? {
        val v = view ?: return null
        val s = selection
        return if (selectionOnly && s != null) {
            val display = selectionReference()!!.display()
            display to Copying.text(v.verses.subList(s.first, s.last + 1), display, bible.abbreviation, prefs.suppliedStyle)
        } else {
            val display = v.reference.display()
            display to Copying.text(v.verses, display, bible.abbreviation, prefs.suppliedStyle)
        }
    }

    // -- bookmarks and history -----------------------------------------------------------
    val bookmarks = mutableStateListOf<UserStore.Bookmark>()
    val history = mutableStateListOf<UserStore.HistoryEntry>()

    fun refreshSaved() {
        viewModelScope.launch {
            val (b, h) = withContext(Dispatchers.IO) { user.bookmarks() to user.history(UserStore.MAX_HISTORY) }
            bookmarks.clear(); bookmarks.addAll(b)
            history.clear(); history.addAll(h)
        }
    }

    fun findBookmark(ref: Reference): UserStore.Bookmark? = runCatching { user.findBookmark(translation, ref) }.getOrNull()

    fun saveBookmark(ref: Reference, label: String) {
        viewModelScope.launch {
            val r = withContext(Dispatchers.IO) {
                runCatching {
                    val existing = user.findBookmark(translation, ref)
                    if (existing != null) user.updateBookmarkLabel(existing.id, label) to false
                    else user.addBookmark(translation, ref, label)
                }
            }
            r.onSuccess { (b, created) ->
                say(if (created) "Bookmarked ${ref.display()}" else "Bookmark updated")
                if (view?.reference?.key() == b.key) passageBookmark = b
                refreshSaved()
            }.onFailure { say(messageOf(it)) }
        }
    }

    fun removeBookmark(b: UserStore.Bookmark) {
        viewModelScope.launch {
            val r = withContext(Dispatchers.IO) { runCatching { user.removeBookmark(b.id) } }
            r.onSuccess {
                if (passageBookmark?.id == b.id) passageBookmark = null
                say("Removed bookmark ${b.reference.display()}")
                refreshSaved()
            }.onFailure { say(messageOf(it)) }
        }
    }

    fun clearHistory() {
        viewModelScope.launch {
            withContext(Dispatchers.IO) { user.clearHistory() }
            say("Reading history cleared")
            refreshSaved()
        }
    }

    fun exportTo(uri: Uri) {
        viewModelScope.launch {
            val r = withContext(Dispatchers.IO) {
                runCatching {
                    val json = user.exportJson()
                    ctx.contentResolver.openOutputStream(uri, "wt")!!.use { it.write(json.toByteArray()) }
                }
            }
            say(if (r.isSuccess) "Bookmarks and history exported" else "Export failed: ${r.exceptionOrNull()?.message}")
        }
    }

    fun importFrom(uri: Uri) {
        viewModelScope.launch {
            val r = withContext(Dispatchers.IO) {
                runCatching {
                    val bytes = ctx.contentResolver.openInputStream(uri)!!.use { it.readBytes() }
                    if (bytes.size > 5_000_000) throw IllegalArgumentException("That file is too large to be a qbible export.")
                    user.importJson(bytes.toString(Charsets.UTF_8))
                }
            }
            r.onSuccess {
                say("Imported ${it.bookmarksAdded} bookmarks and ${it.historyAdded} history entries" +
                    if (it.skipped > 0) " (${it.skipped} unreadable entries skipped)" else "")
                refreshSaved()
                view?.let { v -> passageBookmark = withContext(Dispatchers.IO) { findBookmark(v.reference) } }
            }.onFailure { say(messageOf(it)) }
        }
    }

    // -- books -------------------------------------------------------------------------
    var booksSelected by mutableStateOf<Book?>(null)

    // -- search ------------------------------------------------------------------------
    var searchQuery by mutableStateOf("")
    var searchMode by mutableStateOf("auto")
    var searchTestament by mutableStateOf<String?>(null)
    var searchSort by mutableStateOf("canonical")
    val searchHits = mutableStateListOf<Hit>()
    var searchTotal by mutableStateOf(0); private set
    var searchStatus by mutableStateOf<String?>(null); private set
    var searchBusy by mutableStateOf(false); private set
    var searchOffers by mutableStateOf<List<Offer>>(emptyList()); private set
    private var searchRan: List<Any?>? = null

    val searchHasMore: Boolean get() = searchHits.size < searchTotal

    fun runSearch() {
        val q = searchQuery.trim()
        val params = listOf(q, searchMode, searchTestament, searchSort)
        searchRan = params
        searchHits.clear()
        searchTotal = 0
        searchOffers = emptyList()
        if (q.isEmpty()) { searchStatus = "Enter a word or phrase to search the Bible."; return }
        searchStatus = "Searching…"
        viewModelScope.launch {
            searchOffers = withContext(Dispatchers.IO) { offersFor(q) }
            loadPage(params)
        }
    }

    fun moreResults() {
        val p = searchRan ?: return
        viewModelScope.launch { loadPage(p) }
    }

    private suspend fun loadPage(params: List<Any?>) {
        searchBusy = true
        val offset = searchHits.size
        val r = withContext(Dispatchers.IO) {
            runCatching {
                bible.search(params[0] as String, mode = params[1] as String, testament = params[2] as String?,
                    sort = params[3] as String, limit = PAGE, offset = offset)
            }
        }
        searchBusy = false
        if (searchRan != params) return // a newer search replaced this one
        r.onSuccess { res ->
            searchHits.addAll(res.hits)
            searchTotal = res.total
            val terms = res.terms.joinToString(" ") { it.describe() }
            searchStatus = when {
                res.total == 0 -> "No verses match $terms. Try fewer words, a different spelling, or “Any word”."
                res.total == 1 -> "1 verse matches $terms."
                else -> "${"%,d".format(res.total)} verses match $terms" +
                    (if (searchHits.size < res.total) " (showing ${searchHits.size})." else ".")
            }
        }.onFailure { searchStatus = messageOf(it) }
    }

    /** The query as a passage ("john 3:16"), or passages mentioned in it. */
    private fun offersFor(q: String): List<Offer> {
        runCatching { bible.resolve(bible.parse(q)) }.getOrNull()?.let { return listOf(Offer(it.key(), it.display())) }
        return runCatching {
            findReferences(q, data.catalogue, bible::isValid).map { Offer(it.reference.key(), it.reference.display()) }.distinct()
        }.getOrDefault(emptyList())
    }

    private fun messageOf(e: Throwable): String = when (e) {
        is QBibleException -> e.message ?: e.code
        else -> "Something went wrong: ${e.message ?: e.javaClass.simpleName}"
    }

    companion object {
        const val PAGE = 25
    }
}
