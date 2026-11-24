package org.qbible.app.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import org.qbible.app.MainViewModel

private val MODES = listOf("auto" to "All words", "phrase" to "Exact phrase", "any" to "Any word")
private val SCOPES = listOf(null to "Whole Bible", "OT" to "Old Testament", "NT" to "New Testament")
private val SORTS = listOf("canonical" to "Bible order", "relevance" to "Relevance")

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SearchScreen(vm: MainViewModel) {
    val focus = LocalFocusManager.current
    val colors = rememberReading()
    fun go() { focus.clearFocus(); vm.runSearch() }

    Column(Modifier.fillMaxSize()) {
        TopAppBar(windowInsets = WindowInsets(0), title = { Text("Search") })
        OutlinedTextField(
            value = vm.searchQuery,
            onValueChange = { vm.searchQuery = it },
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
            singleLine = true,
            label = { Text("Words or \"exact phrase\"") },
            placeholder = { Text("faith -dead, \"fear not\", believ*") },
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search, autoCorrectEnabled = false),
            keyboardActions = KeyboardActions(onSearch = { go() }),
            trailingIcon = { IconButton(onClick = { go() }) { Icon(Icons.Filled.Search, contentDescription = "Search") } },
        )
        Row(
            Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            OptionChip("Match", MODES, vm.searchMode) { vm.searchMode = it; if (vm.searchQuery.isNotBlank()) vm.runSearch() }
            OptionChip("Scope", SCOPES, vm.searchTestament) { vm.searchTestament = it; if (vm.searchQuery.isNotBlank()) vm.runSearch() }
            OptionChip("Order", SORTS, vm.searchSort) { vm.searchSort = it; if (vm.searchQuery.isNotBlank()) vm.runSearch() }
        }
        vm.searchStatus?.let {
            Text(
                it, style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 6.dp).semantics { liveRegion = LiveRegionMode.Polite },
            )
        }
        if (vm.searchOffers.isNotEmpty()) {
            Card(
                Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer),
            ) {
                Column(Modifier.padding(horizontal = 12.dp, vertical = 4.dp)) {
                    Text(
                        if (vm.searchOffers.size == 1) "Looking for a passage?" else "Passages mentioned:",
                        style = MaterialTheme.typography.labelLarge, modifier = Modifier.padding(top = 6.dp),
                    )
                    for (o in vm.searchOffers) TextButton(onClick = { vm.open(o.key) }) { Text("Open ${o.display}") }
                }
            }
        }
        LazyColumn(Modifier.weight(1f).fillMaxWidth(), contentPadding = PaddingValues(bottom = 24.dp)) {
            items(vm.searchHits, key = { it.key }) { hit ->
                Column(
                    Modifier.fillMaxWidth()
                        .clickable(onClickLabel = "Open ${hit.display}") { vm.open(hit.key) }
                        .padding(horizontal = 16.dp, vertical = 10.dp),
                ) {
                    Text(hit.display, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary, modifier = Modifier.semantics { heading() })
                    Text(
                        buildAnnotatedString { appendSegments(hit.segments, vm.prefs.suppliedStyle, colors.highlight, colors.onHighlight) },
                        style = readingStyle(vm.prefs, 0.85f).copy(color = MaterialTheme.colorScheme.onBackground),
                    )
                }
                HorizontalDivider()
            }
            if (vm.searchHasMore) item {
                Box(Modifier.fillMaxWidth().padding(16.dp)) {
                    OutlinedButton(onClick = { vm.moreResults() }, enabled = !vm.searchBusy, modifier = Modifier.fillMaxWidth()) {
                        Text("Show more results (${vm.searchTotal - vm.searchHits.size} more)")
                    }
                }
            }
            item {
                Text(
                    "Tips: words are all required; \"quotes\" match an exact phrase; -word excludes; believ* matches beginnings. " +
                        "You can also type a reference, such as john 3:16.",
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(16.dp),
                )
            }
        }
    }
}

@Composable
private fun <T> OptionChip(name: String, options: List<Pair<T, String>>, value: T, onPick: (T) -> Unit) {
    var open by remember { mutableStateOf(false) }
    val label = options.firstOrNull { it.first == value }?.second ?: options.first().second
    Box {
        FilterChip(
            selected = value != options.first().first,
            onClick = { open = true },
            label = { Text(label) },
            trailingIcon = { Icon(Icons.Filled.ArrowDropDown, contentDescription = null) },
            modifier = Modifier.semantics { contentDescription = "$name: $label" },
        )
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            for ((v, l) in options) DropdownMenuItem(text = { Text(l) }, onClick = { open = false; onPick(v) })
        }
    }
}
