package org.qbible.core

/**
 * Character classes equivalent to Python's Unicode-aware `re` classes.
 *
 * Python's `\s`, `\d` and `\w` match Unicode characters; Java's match ASCII
 * only (unless UNICODE_CHARACTER_CLASS, which Android's ICU regex engine does
 * not support). The ported patterns use these explicit classes instead, so
 * they behave the same on the JVM and on Android.
 */
internal object Py {
    /** Body of Python's `\s` (str.isspace): ASCII controls, U+0085 and every Z* character. */
    const val WS_CHARS = "\\t\\n\\x0B\\f\\r\\x1C-\\x1F\\x85\\p{Z}"
    const val S = "[$WS_CHARS]"
    const val NOT_S = "[^$WS_CHARS]"

    /** Python's `\d`: Unicode decimal digits. */
    const val D = "\\p{Nd}"
    const val NOT_D = "[^\\p{Nd}]"

    /** Python's `\w` (alphanumerics and underscore). */
    const val W = "[\\p{L}\\p{N}_]"

    /** Python's `[^\W_]` (alphanumerics only) and its complement `[\W_]`. */
    const val ALNUM = "[\\p{L}\\p{N}]"
    const val NOT_ALNUM = "[^\\p{L}\\p{N}]"
}

/** Python's `int()` on a run of decimal digits, refusing values that do not fit. */
internal fun pyInt(digits: String): Long? {
    val sb = StringBuilder()
    for (ch in digits) {
        val d = Character.digit(ch, 10)
        if (d < 0) return null
        sb.append(('0' + d))
    }
    val s = sb.toString().trimStart('0')
    if (s.isEmpty()) return 0
    if (s.length > 15) return Long.MAX_VALUE // far beyond any limit the callers check
    return s.toLong()
}
