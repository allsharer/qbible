package org.qbible.core

import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.sql.Connection
import java.sql.DriverManager
import java.sql.ResultSet
import java.sql.Statement

/** Locations passed in by Gradle (see core/build.gradle.kts). */
object TestData {
    val repoRoot = File(System.getProperty("qbible.repoRoot") ?: "../..")
    val assetsDir = File(System.getProperty("qbible.assetsDir") ?: "../build/qbible-assets")
    val testDir = File(System.getProperty("qbible.testDir") ?: "../build/qbible-test")
    val spec = File(repoRoot, "spec")

    val catalogue: BookCatalogue by lazy {
        BookCatalogue.fromJson(File(repoRoot, "qbible/resources/books.json").readText())
    }

    /** The Android KJV pack, opened read-only through JDBC. */
    val bible: Bible by lazy { Bible(JdbcDb.open(File(assetsDir, "kjv-android.sqlite"), readOnly = true), catalogue) }

    fun json(file: File): JSONObject = JSONObject(file.readText())
}

fun JSONArray.objects(): List<JSONObject> = (0 until length()).map { getJSONObject(it) }
fun JSONArray.strings(): List<String> = (0 until length()).map { getString(it) }
fun JSONObject.optStringOrNull(k: String): String? = if (isNull(k) || !has(k)) null else getString(k)

/** [SqlDb] over sqlite-jdbc, standing in for android.database.sqlite in JVM tests. */
class JdbcDb(private val conn: Connection) : SqlDb {
    companion object {
        fun open(file: File, readOnly: Boolean = false): JdbcDb {
            val props = java.util.Properties()
            if (readOnly) props["open_mode"] = "1" // SQLITE_OPEN_READONLY
            return JdbcDb(DriverManager.getConnection("jdbc:sqlite:${file.path}", props))
        }
    }

    private fun bind(st: java.sql.PreparedStatement, args: List<Any?>) {
        args.forEachIndexed { i, a ->
            when (a) {
                null -> st.setNull(i + 1, java.sql.Types.NULL)
                is Int -> st.setLong(i + 1, a.toLong())
                is Long -> st.setLong(i + 1, a)
                is Double -> st.setDouble(i + 1, a)
                is String -> st.setString(i + 1, a)
                else -> error("unsupported ${a::class}")
            }
        }
    }

    private fun value(rs: ResultSet, i: Int): Any? = when (val o = rs.getObject(i)) {
        is Int -> o.toLong()
        else -> o
    }

    override fun query(sql: String, args: List<Any?>): List<List<Any?>> =
        conn.prepareStatement(sql).use { st ->
            bind(st, args)
            st.executeQuery().use { rs ->
                val n = rs.metaData.columnCount
                val out = ArrayList<List<Any?>>()
                while (rs.next()) out.add((1..n).map { value(rs, it) })
                out
            }
        }

    override fun execute(sql: String, args: List<Any?>): Int =
        conn.prepareStatement(sql).use { st -> bind(st, args); st.executeUpdate() }

    override fun insert(sql: String, args: List<Any?>): Long =
        conn.prepareStatement(sql, Statement.RETURN_GENERATED_KEYS).use { st ->
            bind(st, args)
            st.executeUpdate()
            conn.createStatement().use { s -> s.executeQuery("SELECT last_insert_rowid()").use { it.next(); it.getLong(1) } }
        }

    private var depth = 0
    override fun <T> transaction(block: () -> T): T {
        if (depth > 0) return block()
        conn.autoCommit = false
        depth++
        try {
            val r = block()
            conn.commit()
            return r
        } catch (e: Throwable) {
            conn.rollback()
            throw e
        } finally {
            depth--
            conn.autoCommit = true
        }
    }

    fun close() = conn.close()
}
