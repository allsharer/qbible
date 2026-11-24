package org.qbible.app.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import org.qbible.app.MainViewModel
import org.qbible.core.UserStore
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle

private fun whenText(iso: String): String = runCatching {
    OffsetDateTime.parse(iso).atZoneSameInstant(ZoneId.systemDefault())
        .format(DateTimeFormatter.ofLocalizedDateTime(FormatStyle.MEDIUM, FormatStyle.SHORT))
}.getOrDefault(iso)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SavedScreen(vm: MainViewModel) {
    var tab by rememberSaveable { mutableIntStateOf(0) }
    var editing by remember { mutableStateOf<UserStore.Bookmark?>(null) }
    var confirmClear by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { vm.refreshSaved() }

    Column(Modifier.fillMaxSize()) {
        TopAppBar(
            windowInsets = WindowInsets(0),
            title = { Text("Saved") },
            actions = {
                if (tab == 1 && vm.history.isNotEmpty()) TextButton(onClick = { confirmClear = true }) { Text("Clear history") }
            },
        )
        TabRow(selectedTabIndex = tab) {
            Tab(selected = tab == 0, onClick = { tab = 0 }, text = { Text("Bookmarks (${vm.bookmarks.size})") })
            Tab(selected = tab == 1, onClick = { tab = 1 }, text = { Text("History") })
        }
        if (tab == 0) {
            if (vm.bookmarks.isEmpty()) {
                Empty("No bookmarks yet. Use the bookmark button while reading, or select verses and bookmark them.")
            }
            LazyColumn(Modifier.fillMaxSize()) {
                items(vm.bookmarks, key = { it.id }) { b ->
                    ListItem(
                        headlineContent = { Text(b.reference.display()) },
                        supportingContent = { Text(if (b.label.isNotEmpty()) b.label else "Added ${whenText(b.createdAt)}") },
                        trailingContent = {
                            Row {
                                IconButton(onClick = { editing = b }) { Icon(Icons.Filled.Edit, contentDescription = "Edit label of ${b.reference.display()}") }
                                IconButton(onClick = { vm.removeBookmark(b) }) { Icon(Icons.Filled.Delete, contentDescription = "Remove bookmark ${b.reference.display()}") }
                            }
                        },
                        modifier = Modifier.clickable(onClickLabel = "Open ${b.reference.display()}") { vm.open(b.key) },
                    )
                }
            }
        } else {
            if (vm.history.isEmpty()) Empty("Passages you open appear here.")
            LazyColumn(Modifier.fillMaxSize()) {
                items(vm.history, key = { it.id }) { h ->
                    ListItem(
                        headlineContent = { Text(h.reference.display()) },
                        supportingContent = { Text(whenText(h.openedAt)) },
                        modifier = Modifier.clickable(onClickLabel = "Open ${h.reference.display()}") { vm.open(h.key) },
                    )
                }
            }
        }
    }

    editing?.let { b ->
        BookmarkDialog(
            display = b.reference.display(),
            existingLabel = b.label,
            onSave = { vm.saveBookmark(b.reference, it); editing = null },
            onRemove = { vm.removeBookmark(b); editing = null },
            onDismiss = { editing = null },
        )
    }
    if (confirmClear) {
        AlertDialog(
            onDismissRequest = { confirmClear = false },
            title = { Text("Clear reading history?") },
            text = { Text("This removes the list of passages you have opened. Bookmarks are kept.") },
            confirmButton = { TextButton(onClick = { vm.clearHistory(); confirmClear = false }) { Text("Clear") } },
            dismissButton = { TextButton(onClick = { confirmClear = false }) { Text("Cancel") } },
        )
    }
}

@Composable
private fun Empty(text: String) {
    Text(text, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.padding(24.dp))
}
