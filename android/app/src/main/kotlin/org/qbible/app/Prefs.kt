package org.qbible.app

import android.content.Context
import org.qbible.core.TextFmt

/** Display preferences, with the same choices and ranges as the browser interface (web/assets/js/prefs.js). */
data class Prefs(
    val fontSize: Int = 20,
    val fontFamily: String = "serif", // serif | sans
    val lineHeight: Float = 1.7f, // 1.3 .. 2.4
    val theme: String = "system", // system | light | dark
    val layout: String = "paragraphs", // paragraphs | verses
    val supplied: String = "italic", // italic | brackets | plain
    val verseNumbers: Boolean = true,
) {
    val suppliedStyle: TextFmt.Supplied
        get() = when (supplied) {
            "brackets" -> TextFmt.Supplied.BRACKETS
            "plain" -> TextFmt.Supplied.PLAIN
            else -> TextFmt.Supplied.ITALIC
        }

    fun save(context: Context) {
        context.getSharedPreferences(FILE, Context.MODE_PRIVATE).edit()
            .putInt("fontSize", fontSize).putString("fontFamily", fontFamily).putFloat("lineHeight", lineHeight)
            .putString("theme", theme).putString("layout", layout).putString("supplied", supplied)
            .putBoolean("verseNumbers", verseNumbers).apply()
    }

    companion object {
        const val FILE = "qbible_prefs"
        const val FONT_MIN = 14
        const val FONT_MAX = 32
        const val FONT_STEP = 2

        fun load(context: Context): Prefs {
            val p = context.getSharedPreferences(FILE, Context.MODE_PRIVATE)
            val d = Prefs()
            fun pick(key: String, allowed: List<String>, def: String) = p.getString(key, def).takeIf { it in allowed } ?: def
            return Prefs(
                fontSize = p.getInt("fontSize", d.fontSize).coerceIn(FONT_MIN, FONT_MAX),
                fontFamily = pick("fontFamily", listOf("serif", "sans"), d.fontFamily),
                lineHeight = p.getFloat("lineHeight", d.lineHeight).takeIf { it in 1.3f..2.4f } ?: d.lineHeight,
                theme = pick("theme", listOf("system", "light", "dark"), d.theme),
                layout = pick("layout", listOf("paragraphs", "verses"), d.layout),
                supplied = pick("supplied", listOf("italic", "brackets", "plain"), d.supplied),
                verseNumbers = p.getBoolean("verseNumbers", d.verseNumbers),
            )
        }
    }
}
