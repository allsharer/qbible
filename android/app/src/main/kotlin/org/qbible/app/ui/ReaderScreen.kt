package org.qbible.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowLeft
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import org.qbible.app.MainViewModel
import org.qbible.app.Prefs
import org.qbible.core.PassageView
import org.qbible.core.Reference
import org.qbible.core.TextFmt

/** What the reading list shows, in order. */
private sealed interface Item {
    data class Title(val text: String) : Item
    data class ChapterHeading(val chapter: Int) : Item
    data class Paragraph(val indices: List<Int>) : Item
    data class VerseRow(val index: Int) : Item
    data object Footer : Item
}

private fun buildItems(v: PassageView, p: Prefs): List<Item> {
    val out = ArrayList<Item>()
    out.add(Item.Title(v.reference.display()))
    val multi = !v.passage.isSingleChapter
    var current: MutableList<Int>? = null
    var lastChapter = -1
    for ((i, verse) in v.verses.withIndex()) {
        val newChapter = verse.chapter != lastChapter
        if (newChapter && multi) {
            current = null
            out.add(Item.ChapterHeading(verse.chapter))
        }
        lastChapter = verse.chapter
        if (p.layout == "verses") {
            out.add(Item.VerseRow(i))
            continue
        }
        if (current == null || newChapter || TextFmt.startsParagraph(verse.text)) {
            current = ArrayList()
            out.add(Item.Paragraph(current))
        }
        current.add(i)
    }
    out.add(Item.Footer)
    return out
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReaderScreen(vm: MainViewModel) {
    val view = vm.view
    val context = LocalContext.current
    val clipboard = LocalClipboardManager.current
    var bookmarkFor by remember { mutableStateOf<Reference?>(null) }
    var menu by remember { mutableStateOf(false) }

    fun copy(selectionOnly: Boolean) {
        val (display, text) = vm.shareText(selectionOnly) ?: return
        clipboard.setText(AnnotatedString(text))
        vm.say("Copied $display")
    }

    fun share(selectionOnly: Boolean) {
        val (display, text) = vm.shareText(selectionOnly) ?: return
        shareText(context, display, text)
    }

    Column(Modifier.fillMaxSize()) {
        TopAppBar(
            windowInsets = WindowInsets(0),
            title = {
                Column {
                    Text(view?.reference?.display() ?: "qbible", maxLines = 1)
                    Text("King James Version", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            },
            actions = {
                if (view != null) {
                    IconButton(onClick = { vm.step(-1) }, enabled = view.previous != null) {
                        Icon(Icons.AutoMirrored.Filled.KeyboardArrowLeft,
                            contentDescription = view.previous?.let { "Previous chapter, ${it.display()}" } ?: "No previous chapter")
                    }
                    IconButton(onClick = { vm.step(1) }, enabled = view.next != null) {
                        Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight,
                            contentDescription = view.next?.let { "Next chapter, ${it.display()}" } ?: "No next chapter")
                    }
                    val bm = vm.passageBookmark
                    IconButton(onClick = { bookmarkFor = view.reference }) {
                        Icon(if (bm != null) QIcons.BookmarkFilled else QIcons.Bookmark,
                            contentDescription = if (bm != null) "Edit bookmark for ${view.reference.display()}" else "Bookmark ${view.reference.display()}")
                    }
                    IconButton(onClick = { menu = true }) { Icon(Icons.Filled.MoreVert, contentDescription = "More options") }
                    DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                        DropdownMenuItem(text = { Text("Copy ${view.reference.display()}") }, leadingIcon = { Icon(QIcons.Copy, null) },
                            onClick = { menu = false; copy(false) })
                        DropdownMenuItem(text = { Text("Share ${view.reference.display()}") }, leadingIcon = { Icon(Icons.Filled.Share, null) },
                            onClick = { menu = false; share(false) })
                        if (isPartialChapter(view)) {
                            DropdownMenuItem(text = { Text("Read all of ${view.passage.book.singularName} ${view.passage.start.first}") },
                                onClick = { menu = false; vm.wholeChapter() })
                        }
                    }
                }
            },
        )
        ReferenceBox(vm)
        if (view == null) return@Column
        val items = remember(view, vm.prefs.layout) { buildItems(view, vm.prefs) }
        val key = view.reference.key()
        val listState = remember(key) {
            val r = vm.consumeRestoreScroll()
            LazyListState(r?.first ?: 0, r?.second ?: 0)
        }
        LaunchedEffect(key) {
            snapshotFlow { listState.firstVisibleItemIndex to listState.firstVisibleItemScrollOffset }.collect { (i, o) ->
                delay(400)
                vm.saveScroll(key, i, o)
            }
        }
        LazyColumn(
            state = listState,
            modifier = Modifier.weight(1f).fillMaxWidth(),
            contentPadding = PaddingValues(start = 20.dp, end = 20.dp, bottom = 24.dp),
        ) {
            items(items) { item -> ReaderItem(vm, view, item) }
        }
        val sel = vm.selection
        if (sel != null) {
            val ref = vm.selectionReference()
            SelectionBar(
                display = ref?.display() ?: "",
                onCopy = { copy(true) },
                onShare = { share(true) },
                onBookmark = { bookmarkFor = ref },
                onClose = { vm.clearSelection() },
            )
        }
    }

    bookmarkFor?.let { ref ->
        BookmarkDialog(
            display = ref.display(),
            existingLabel = vm.findBookmark(ref)?.label,
            onSave = { vm.saveBookmark(ref, it); bookmarkFor = null; vm.clearSelection() },
            onRemove = vm.findBookmark(ref)?.let { b -> { vm.removeBookmark(b); bookmarkFor = null } },
            onDismiss = { bookmarkFor = null },
        )
    }
}

private fun isPartialChapter(v: PassageView): Boolean =
    v.passage.isSingleChapter && v.reference.startVerse != null

@Composable
private fun ReferenceBox(vm: MainViewModel) {
    val focus = LocalFocusManager.current
    val error = vm.refError
    OutlinedTextField(
        value = vm.refText,
        onValueChange = { vm.refText = it; vm.clearRefError() },
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp),
        singleLine = true,
        label = { Text("Go to passage") },
        placeholder = { Text("e.g. John 3:16, gen 1, ps 23, mar 4:1-") },
        isError = error != null,
        supportingText = error?.let { { Text(it, modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite }) } },
        keyboardOptions = KeyboardOptions(
            capitalization = KeyboardCapitalization.None, autoCorrectEnabled = false, imeAction = ImeAction.Go,
        ),
        keyboardActions = KeyboardActions(onGo = { vm.goToTyped(); focus.clearFocus() }),
        trailingIcon = {
            IconButton(onClick = { vm.goToTyped(); focus.clearFocus() }, enabled = vm.refText.isNotBlank()) {
                Icon(Icons.AutoMirrored.Filled.ArrowForward, contentDescription = "Open passage")
            }
        },
    )
}

@Composable
private fun ReaderItem(vm: MainViewModel, view: PassageView, item: Item) {
    val p = vm.prefs
    val colors = rememberReading()
    val sel = vm.selection
    when (item) {
        is Item.Title -> Text(
            item.text,
            style = MaterialTheme.typography.headlineMedium.copy(fontFamily = readingStyle(p).fontFamily),
            modifier = Modifier.padding(top = 12.dp, bottom = 8.dp).semantics { heading() },
        )
        is Item.ChapterHeading -> Text(
            "${view.passage.book.singularName} ${item.chapter}",
            style = MaterialTheme.typography.titleLarge,
            color = MaterialTheme.colorScheme.primary,
            modifier = Modifier.padding(top = 20.dp, bottom = 4.dp).semantics { heading() },
        )
        is Item.Paragraph -> {
            val ranges = ArrayList<Triple<Int, Int, Int>>() // start, end, verse index
            val text = buildAnnotatedString {
                for (i in item.indices) {
                    val v = view.verses[i]
                    val start = length
                    val selected = sel != null && i in sel
                    if (selected) pushStyle(SpanStyle(background = colors.selected))
                    if (p.verseNumbers) {
                        withStyle(verseNumberStyle(colors.verseNumber)) { append(v.verse.toString()) }
                        append(" ")
                    }
                    appendVerse(v.text, p.suppliedStyle)
                    // Keep the space inside the highlight when the next verse is selected too.
                    if (selected && sel != null && i + 1 in sel && i != item.indices.last()) {
                        append(" ")
                        pop()
                    } else {
                        if (selected) pop()
                        append(" ")
                    }
                    ranges.add(Triple(start, length, i))
                }
            }
            var layout by remember { mutableStateOf<TextLayoutResult?>(null) }
            Text(
                text,
                style = readingStyle(p).copy(color = MaterialTheme.colorScheme.onBackground),
                onTextLayout = { layout = it },
                modifier = Modifier
                    .padding(vertical = 6.dp)
                    .pointerInput(item, ranges.size) {
                        detectTapGestures { pos ->
                            val off = layout?.getOffsetForPosition(pos) ?: return@detectTapGestures
                            ranges.firstOrNull { off >= it.first && off < it.second }?.let { vm.tapVerse(it.third) }
                        }
                    }
                    .semantics {
                        customActions = item.indices.map { i ->
                            val n = view.verses[i].verse
                            CustomAccessibilityAction(if (sel != null && i in sel) "Unselect verse $n" else "Select verse $n") {
                                vm.tapVerse(i); true
                            }
                        }
                    },
            )
        }
        is Item.VerseRow -> {
            val i = item.index
            val v = view.verses[i]
            val selected = sel != null && i in sel
            Row(
                Modifier
                    .fillMaxWidth()
                    .background(if (selected) colors.selected else MaterialTheme.colorScheme.background)
                    .clickable(onClickLabel = if (selected) "Unselect verse" else "Select verse") { vm.tapVerse(i) }
                    .semantics { this.selected = selected }
                    .padding(vertical = 4.dp),
            ) {
                if (p.verseNumbers) {
                    Text(
                        v.verse.toString(),
                        style = readingStyle(p, 0.7f).copy(fontWeight = FontWeight.Bold, color = colors.verseNumber),
                        modifier = Modifier.widthIn(min = 32.dp).padding(end = 6.dp, top = 2.dp),
                    )
                }
                Text(
                    buildAnnotatedString { appendVerse(v.text, p.suppliedStyle) },
                    style = readingStyle(p).copy(color = MaterialTheme.colorScheme.onBackground),
                )
            }
        }
        Item.Footer -> Column(Modifier.fillMaxWidth().padding(top = 24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            if (isPartialChapter(view)) {
                TextButton(onClick = { vm.wholeChapter() }) {
                    Text("Read all of ${view.passage.book.singularName} ${view.passage.start.first}")
                }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                val prev = view.previous
                val next = view.next
                if (prev != null) OutlinedButton(onClick = { vm.open(prev) }) { Text("‹ ${prev.display()}") } else Spacer(Modifier)
                if (next != null) OutlinedButton(onClick = { vm.open(next) }) { Text("${next.display()} ›") } else Spacer(Modifier)
            }
            Text(
                "Tap a verse to select it; tap another to select a range.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = 16.dp),
            )
        }
    }
}

@Composable
private fun SelectionBar(display: String, onCopy: () -> Unit, onShare: () -> Unit, onBookmark: () -> Unit, onClose: () -> Unit) {
    Surface(color = MaterialTheme.colorScheme.secondaryContainer, tonalElevation = 3.dp) {
        Row(Modifier.fillMaxWidth().padding(start = 16.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(
                display, style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.weight(1f).semantics { liveRegion = LiveRegionMode.Polite },
            )
            IconButton(onClick = onCopy) { Icon(QIcons.Copy, contentDescription = "Copy $display") }
            IconButton(onClick = onShare) { Icon(Icons.Filled.Share, contentDescription = "Share $display") }
            IconButton(onClick = onBookmark) { Icon(QIcons.Bookmark, contentDescription = "Bookmark $display") }
            IconButton(onClick = onClose) { Icon(Icons.Filled.Close, contentDescription = "Clear selection") }
        }
    }
}

@Composable
fun BookmarkDialog(
    display: String,
    existingLabel: String?,
    onSave: (String) -> Unit,
    onRemove: (() -> Unit)?,
    onDismiss: () -> Unit,
) {
    var label by remember { mutableStateOf(existingLabel ?: "") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (existingLabel != null) "Bookmark: $display" else "Bookmark $display") },
        text = {
            OutlinedTextField(
                value = label,
                onValueChange = { if (it.length <= 200) label = it },
                label = { Text("Label (optional)") },
                singleLine = true,
            )
        },
        confirmButton = { TextButton(onClick = { onSave(label) }) { Text("Save") } },
        dismissButton = {
            Row {
                if (onRemove != null) TextButton(onClick = onRemove) { Text("Remove") }
                TextButton(onClick = onDismiss) { Text("Cancel") }
            }
        },
    )
}
