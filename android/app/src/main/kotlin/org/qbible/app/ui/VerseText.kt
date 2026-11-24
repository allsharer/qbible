package org.qbible.app.ui

import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.BaselineShift
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import org.qbible.app.Prefs
import org.qbible.core.Search
import org.qbible.core.TextFmt

/** The reading text style chosen in Settings (scales with the system font size too, as it is in sp). */
fun readingStyle(p: Prefs, scale: Float = 1f): TextStyle = TextStyle(
    fontSize = (p.fontSize * scale).sp,
    lineHeight = (p.fontSize * scale * p.lineHeight).sp,
    fontFamily = if (p.fontFamily == "sans") FontFamily.SansSerif else FontFamily.Serif,
)

/** Append verse text, showing supplied words as italics, [brackets] or plain. */
fun AnnotatedString.Builder.appendVerse(raw: String, supplied: TextFmt.Supplied) {
    for (part in TextFmt.parts(raw)) appendPart(part.text, part.supplied, supplied)
}

private fun AnnotatedString.Builder.appendPart(text: String, isSupplied: Boolean, style: TextFmt.Supplied) {
    when {
        !isSupplied || style == TextFmt.Supplied.PLAIN -> append(text)
        style == TextFmt.Supplied.BRACKETS -> append("[$text]")
        else -> withStyle(SpanStyle(fontStyle = FontStyle.Italic)) { append(text) }
    }
}

/** Search-result text: matches highlighted (colour and weight, not colour alone). */
fun AnnotatedString.Builder.appendSegments(
    segments: List<Search.Segment>,
    supplied: TextFmt.Supplied,
    highlight: Color,
    onHighlight: Color,
) {
    // Brackets must wrap a whole supplied run even when a match splits it.
    var i = 0
    while (i < segments.size) {
        val s = segments[i]
        if (s.supplied && supplied == TextFmt.Supplied.BRACKETS) {
            append("[")
            while (i < segments.size && segments[i].supplied) {
                val t = segments[i]
                if (t.match) withStyle(SpanStyle(background = highlight, color = onHighlight, fontWeight = FontWeight.Bold)) { append(t.text) }
                else append(t.text)
                i++
            }
            append("]")
            continue
        }
        val base = if (s.supplied && supplied == TextFmt.Supplied.ITALIC) SpanStyle(fontStyle = FontStyle.Italic) else SpanStyle()
        val style = if (s.match) base.merge(SpanStyle(background = highlight, color = onHighlight, fontWeight = FontWeight.Bold)) else base
        withStyle(style) { append(s.text) }
        i++
    }
}

fun verseNumberStyle(color: Color) = SpanStyle(
    color = color, fontSize = 0.62.em, fontWeight = FontWeight.Bold, baselineShift = BaselineShift.Superscript,
)

@Composable
fun rememberReading() = LocalReadingColors.current
