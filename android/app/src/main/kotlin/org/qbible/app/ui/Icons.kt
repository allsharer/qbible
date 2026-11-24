package org.qbible.app.ui

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.unit.dp

/**
 * The few icons that material-icons-core lacks, drawn here as simple strokes
 * (so the app does not need the very large material-icons-extended library).
 */
object QIcons {
    private fun icon(name: String, filled: Boolean, vararg paths: String): ImageVector =
        ImageVector.Builder(name, 24.dp, 24.dp, 24f, 24f).apply {
            for (d in paths) {
                addPath(
                    PathParser().parsePathString(d).toNodes(),
                    fill = if (filled) SolidColor(Color.Black) else null,
                    stroke = SolidColor(Color.Black),
                    strokeLineWidth = 2f,
                    strokeLineCap = StrokeCap.Round,
                    strokeLineJoin = StrokeJoin.Round,
                )
            }
        }.build()

    val Book = icon("book", false,
        "M3,5.5 C6,4.5 9,4.5 12,6.5 C15,4.5 18,4.5 21,5.5 L21,19 C18,18 15,18 12,20 C9,18 6,18 3,19 Z",
        "M12,6.5 L12,20")
    val Bookmark = icon("bookmark", false, "M6.5,3.5 L17.5,3.5 L17.5,20.5 L12,16.5 L6.5,20.5 Z")
    val BookmarkFilled = icon("bookmark_filled", true, "M6.5,3.5 L17.5,3.5 L17.5,20.5 L12,16.5 L6.5,20.5 Z")
    val Copy = icon("copy", false, "M9,8 L19,8 L19,20 L9,20 Z", "M5,16 L5,4 L15,4")
    val Contents = icon("contents", false, "M4,6 L20,6", "M4,12 L20,12", "M4,18 L14,18")
}
