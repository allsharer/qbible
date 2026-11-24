package org.qbible.app.ui

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.unit.dp
import org.qbible.app.BuildConfig
import org.qbible.app.MainViewModel
import org.qbible.app.Prefs

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(vm: MainViewModel) {
    val p = vm.prefs
    val export = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri ->
        if (uri != null) vm.exportTo(uri)
    }
    val import = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) vm.importFrom(uri)
    }
    Column(Modifier.fillMaxSize()) {
        TopAppBar(windowInsets = WindowInsets(0), title = { Text("Settings") })
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp)) {
            Section("Text size")
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedButton(onClick = { vm.updatePrefs(p.copy(fontSize = (p.fontSize - Prefs.FONT_STEP).coerceAtLeast(Prefs.FONT_MIN))) },
                    enabled = p.fontSize > Prefs.FONT_MIN) { Text("A−") }
                Text("${p.fontSize}", style = MaterialTheme.typography.titleMedium)
                OutlinedButton(onClick = { vm.updatePrefs(p.copy(fontSize = (p.fontSize + Prefs.FONT_STEP).coerceAtMost(Prefs.FONT_MAX))) },
                    enabled = p.fontSize < Prefs.FONT_MAX) { Text("A+") }
            }
            Text(
                buildAnnotatedString { appendVerse("In the beginning God created the heaven and the earth. And the earth was without form, and void; and darkness [was] upon the face of the deep.", p.suppliedStyle) },
                style = readingStyle(p).copy(color = MaterialTheme.colorScheme.onBackground),
                modifier = Modifier.padding(vertical = 8.dp),
            )
            Choice("Font", listOf("serif" to "Serif", "sans" to "Sans-serif"), p.fontFamily) { vm.updatePrefs(p.copy(fontFamily = it)) }
            Choice("Line spacing", listOf(1.4f to "Compact", 1.7f to "Normal", 2.0f to "Relaxed"), p.lineHeight) { vm.updatePrefs(p.copy(lineHeight = it)) }
            Choice("Theme", listOf("system" to "Same as the phone", "light" to "Light", "dark" to "Dark"), p.theme) { vm.updatePrefs(p.copy(theme = it)) }
            Choice("Words supplied by the translators", listOf("italic" to "Italics (traditional)", "brackets" to "[Brackets]", "plain" to "Not marked"), p.supplied) {
                vm.updatePrefs(p.copy(supplied = it))
            }
            Choice("Layout", listOf("paragraphs" to "Paragraphs", "verses" to "One verse per line (easier with TalkBack)"), p.layout) { vm.updatePrefs(p.copy(layout = it)) }
            Row(
                Modifier.fillMaxWidth().heightIn(min = 48.dp)
                    .toggleable(value = p.verseNumbers, role = Role.Switch) { vm.updatePrefs(p.copy(verseNumbers = it)) },
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("Show verse numbers", Modifier.weight(1f), style = MaterialTheme.typography.bodyLarge)
                Switch(checked = p.verseNumbers, onCheckedChange = null)
            }

            Section("Your data")
            Text(
                "Bookmarks and reading history stay on this phone. They are not sent anywhere and are not included in cloud backups. " +
                    "You can save them to a file and load them on another phone.",
                style = MaterialTheme.typography.bodyMedium,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.padding(vertical = 8.dp)) {
                OutlinedButton(onClick = { export.launch("qbible-bookmarks.json") }) { Text("Export…") }
                OutlinedButton(onClick = { import.launch(arrayOf("application/json", "text/plain", "application/octet-stream")) }) { Text("Import…") }
            }

            Section("About")
            val m = vm.packMeta
            Text("qbible for Android ${BuildConfig.VERSION_NAME}", style = MaterialTheme.typography.titleSmall)
            Text(
                "No adverts, no tracking, no accounts. The app has no network permission and works entirely offline.",
                style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(vertical = 4.dp),
            )
            Text("${m["name"]} (${m["abbreviation"]})", style = MaterialTheme.typography.titleSmall, modifier = Modifier.padding(top = 8.dp))
            for (k in listOf("licence", "copyright", "attribution")) {
                m[k]?.takeIf { it.isNotBlank() }?.let { Text(it, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(vertical = 2.dp)) }
            }
            m["source_url"]?.let { Text("Source: $it", style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(vertical = 2.dp)) }
            Text(
                "qbible is free software under the MIT licence.",
                style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 8.dp, bottom = 24.dp),
            )
        }
    }
}

@Composable
private fun Section(title: String) {
    HorizontalDivider(Modifier.padding(top = 16.dp))
    Text(title, style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.primary,
        modifier = Modifier.padding(top = 12.dp, bottom = 4.dp).semantics { heading() })
}

@Composable
private fun <T> Choice(title: String, options: List<Pair<T, String>>, value: T, onPick: (T) -> Unit) {
    Text(title, style = MaterialTheme.typography.titleSmall, modifier = Modifier.padding(top = 12.dp).semantics { heading() })
    Column(Modifier.selectableGroup()) {
        for ((v, label) in options) {
            Row(
                Modifier.fillMaxWidth().heightIn(min = 48.dp).selectable(selected = v == value, role = Role.RadioButton) { onPick(v) },
                verticalAlignment = Alignment.CenterVertically,
            ) {
                RadioButton(selected = v == value, onClick = null)
                Text(label, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.padding(start = 12.dp))
            }
        }
    }
}
