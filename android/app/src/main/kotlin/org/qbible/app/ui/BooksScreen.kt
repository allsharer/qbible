package org.qbible.app.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import org.qbible.app.MainViewModel
import org.qbible.core.Book
import org.qbible.core.Reference
import org.qbible.core.chapterReference

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BooksScreen(vm: MainViewModel) {
    val book = vm.booksSelected
    Column(Modifier.fillMaxSize()) {
        TopAppBar(
            windowInsets = WindowInsets(0),
            title = { Text(book?.name ?: "Books") },
            navigationIcon = {
                if (book != null) IconButton(onClick = { vm.booksSelected = null }) {
                    Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back to all books")
                }
            },
        )
        if (book == null) BookList(vm) else ChapterGrid(vm, book)
    }
}

@Composable
private fun BookList(vm: MainViewModel) {
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(bottom = 16.dp)) {
        for ((testament, title) in listOf("OT" to "Old Testament", "NT" to "New Testament")) {
            item(key = testament) {
                Text(title, style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.padding(start = 16.dp, top = 16.dp, bottom = 4.dp).semantics { heading() })
            }
            items(vm.books.filter { it.testament == testament }, key = { it.id }) { b ->
                val n = vm.verseCount(b).size
                ListItem(
                    headlineContent = { Text(b.name) },
                    supportingContent = { Text(if (n == 1) "1 chapter" else "$n chapters") },
                    modifier = Modifier.clickable(onClickLabel = "Choose a chapter of ${b.name}") {
                        if (n == 1) vm.open(chapterReference(b, 1)) else vm.booksSelected = b
                    },
                )
            }
        }
    }
}

@Composable
private fun ChapterGrid(vm: MainViewModel, book: Book) {
    val counts = vm.verseCount(book)
    LazyVerticalGrid(
        columns = GridCells.Adaptive(64.dp),
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(12.dp),
    ) {
        item(span = { GridItemSpan(maxLineSpan) }) {
            TextButton(onClick = { vm.open(Reference(book)) }) { Text("Read the whole of ${book.name}") }
        }
        items(counts.indices.toList()) { i ->
            val c = i + 1
            OutlinedButton(
                onClick = { vm.open(chapterReference(book, c)) },
                modifier = Modifier.padding(4.dp).fillMaxWidth().heightIn(min = 48.dp)
                    .semantics { contentDescription = "${book.singularName} $c, ${counts[i]} verses" },
                contentPadding = PaddingValues(0.dp),
            ) { Text("$c") }
        }
    }
}
