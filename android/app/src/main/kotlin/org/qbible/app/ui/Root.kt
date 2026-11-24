package org.qbible.app.ui

import android.content.Context
import android.content.Intent
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import org.qbible.app.MainViewModel
import org.qbible.app.Tab

private data class NavItem(val tab: Tab, val label: String, val icon: ImageVector)

private val NAV = listOf(
    NavItem(Tab.READ, "Read", QIcons.Book),
    NavItem(Tab.BOOKS, "Books", QIcons.Contents),
    NavItem(Tab.SEARCH, "Search", Icons.Filled.Search),
    NavItem(Tab.SAVED, "Saved", QIcons.Bookmark),
    NavItem(Tab.SETTINGS, "Settings", Icons.Filled.Settings),
)

@Composable
fun QBibleRoot(vm: MainViewModel, onExit: () -> Unit) {
    QBibleTheme(vm.prefs.theme) {
        val snackbar = remember { SnackbarHostState() }
        LaunchedEffect(Unit) {
            snapshotFlow { vm.messages.firstOrNull() }.collect { m ->
                if (m != null) {
                    vm.messages.removeAt(0)
                    snackbar.showSnackbar(m)
                }
            }
        }
        BackHandler { if (!vm.back()) onExit() }

        Scaffold(
            snackbarHost = { SnackbarHost(snackbar) },
            bottomBar = {
                if (vm.ready) NavigationBar {
                    for (item in NAV) {
                        NavigationBarItem(
                            selected = vm.tab == item.tab,
                            onClick = {
                                if (item.tab == Tab.SAVED) vm.refreshSaved()
                                if (item.tab == Tab.BOOKS && vm.tab == Tab.BOOKS) vm.booksSelected = null
                                vm.tab = item.tab
                            },
                            icon = { Icon(item.icon, contentDescription = null) },
                            label = { Text(item.label) },
                        )
                    }
                }
            },
        ) { padding ->
            Box(
                Modifier.fillMaxSize().padding(padding).consumeWindowInsets(padding).imePadding()
            ) {
                val fatal = vm.fatalError
                when {
                    fatal != null -> Message("qbible cannot start", fatal)
                    !vm.ready -> Column(
                        Modifier.fillMaxSize(), verticalArrangement = Arrangement.Center,
                        horizontalAlignment = Alignment.CenterHorizontally,
                    ) {
                        CircularProgressIndicator()
                        Text("Preparing the Bible text…", Modifier.padding(16.dp))
                    }
                    else -> when (vm.tab) {
                        Tab.READ -> ReaderScreen(vm)
                        Tab.BOOKS -> BooksScreen(vm)
                        Tab.SEARCH -> SearchScreen(vm)
                        Tab.SAVED -> SavedScreen(vm)
                        Tab.SETTINGS -> SettingsScreen(vm)
                    }
                }
            }
        }
    }
}

@Composable
fun Message(title: String, body: String) {
    Column(Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.Center) {
        Text(title, style = MaterialTheme.typography.headlineSmall, modifier = Modifier.semantics { heading() })
        Text(body, style = MaterialTheme.typography.bodyLarge, textAlign = TextAlign.Start, modifier = Modifier.padding(top = 12.dp))
    }
}

fun shareText(context: Context, subject: String, text: String) {
    val send = Intent(Intent.ACTION_SEND).setType("text/plain")
        .putExtra(Intent.EXTRA_SUBJECT, subject)
        .putExtra(Intent.EXTRA_TEXT, text)
    context.startActivity(Intent.createChooser(send, "Share $subject"))
}
