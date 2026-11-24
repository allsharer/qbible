package org.qbible.app.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color

// Warm, high-contrast reading palettes. Text/background pairs exceed WCAG AA
// (body text: about 15:1 light and 13:1 dark; accents above 4.5:1).
private val Light = lightColorScheme(
    primary = Color(0xFF6B4E16), onPrimary = Color.White,
    primaryContainer = Color(0xFFF6DFB0), onPrimaryContainer = Color(0xFF261900),
    secondary = Color(0xFF5E5A50), onSecondary = Color.White,
    secondaryContainer = Color(0xFFE9E1CF), onSecondaryContainer = Color(0xFF1F1B13),
    background = Color(0xFFFFFBF5), onBackground = Color(0xFF1E1B16),
    surface = Color(0xFFFFFBF5), onSurface = Color(0xFF1E1B16),
    surfaceVariant = Color(0xFFEEE6D8), onSurfaceVariant = Color(0xFF4A4539),
    surfaceContainer = Color(0xFFF5EEE3), surfaceContainerHigh = Color(0xFFEFE8DC),
    outline = Color(0xFF7B7567), error = Color(0xFFB3261E), onError = Color.White,
)
private val Dark = darkColorScheme(
    primary = Color(0xFFE6C17D), onPrimary = Color(0xFF3F2D00),
    primaryContainer = Color(0xFF574000), onPrimaryContainer = Color(0xFFFFDEA6),
    secondary = Color(0xFFCFC6B4), onSecondary = Color(0xFF353024),
    secondaryContainer = Color(0xFF4C4639), onSecondaryContainer = Color(0xFFECE2CF),
    background = Color(0xFF151311), onBackground = Color(0xFFE9E2D8),
    surface = Color(0xFF151311), onSurface = Color(0xFFE9E2D8),
    surfaceVariant = Color(0xFF4A4539), onSurfaceVariant = Color(0xFFCEC6B5),
    surfaceContainer = Color(0xFF221F1B), surfaceContainerHigh = Color(0xFF2C2925),
    outline = Color(0xFF979080), error = Color(0xFFF2B8B5), onError = Color(0xFF601410),
)

/** Colours outside the Material scheme. */
@Immutable
data class ReadingColors(val highlight: Color, val onHighlight: Color, val selected: Color, val verseNumber: Color)

val LocalReadingColors = staticCompositionLocalOf {
    ReadingColors(Color(0xFFFFE08A), Color.Black, Color(0xFFF6DFB0), Color(0xFF6B4E16))
}

@Composable
fun QBibleTheme(theme: String, content: @Composable () -> Unit) {
    val dark = when (theme) {
        "light" -> false
        "dark" -> true
        else -> isSystemInDarkTheme()
    }
    val scheme: ColorScheme = if (dark) Dark else Light
    val reading = if (dark) {
        ReadingColors(highlight = Color(0xFF6E5600), onHighlight = Color.White, selected = Color(0xFF4B3A10), verseNumber = Color(0xFFE6C17D))
    } else {
        ReadingColors(highlight = Color(0xFFFFE08A), onHighlight = Color.Black, selected = Color(0xFFF6DFB0), verseNumber = Color(0xFF6B4E16))
    }
    androidx.compose.runtime.CompositionLocalProvider(LocalReadingColors provides reading) {
        MaterialTheme(colorScheme = scheme, content = content)
    }
}
