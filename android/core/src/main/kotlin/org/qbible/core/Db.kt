package org.qbible.core

/**
 * The small slice of SQLite the core needs. The app implements it with
 * `android.database.sqlite`; the JVM tests implement it with sqlite-jdbc.
 *
 * Values are bound as typed parameters (Long, Int, Double, String or null),
 * never spliced into SQL. Rows come back as lists of Long, Double, String,
 * ByteArray or null.
 */
interface SqlDb {
    fun query(sql: String, args: List<Any?> = emptyList()): List<List<Any?>>

    /** Runs a statement and returns the number of rows changed. */
    fun execute(sql: String, args: List<Any?> = emptyList()): Int

    /** Runs an INSERT and returns the new rowid. */
    fun insert(sql: String, args: List<Any?> = emptyList()): Long

    /** Runs [block] in an exclusive (IMMEDIATE) transaction; rolls back if it throws. */
    fun <T> transaction(block: () -> T): T
}

internal fun List<Any?>.long(i: Int): Long = (this[i] as Number).toLong()
internal fun List<Any?>.int(i: Int): Int = (this[i] as Number).toInt()
internal fun List<Any?>.str(i: Int): String = this[i] as String
