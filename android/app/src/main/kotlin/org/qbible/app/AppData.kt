package org.qbible.app

import android.content.Context
import android.database.sqlite.SQLiteCursor
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteProgram
import org.qbible.core.Bible
import org.qbible.core.BookCatalogue
import org.qbible.core.SqlDb
import org.qbible.core.UserStore
import java.io.File

/**
 * Opens the bundled data: the read-only KJV pack (copied once from the APK's
 * assets into app storage) and the per-user database of bookmarks and history.
 * Nothing here touches the network.
 */
class AppData(context: Context) {
    val catalogue: BookCatalogue = BookCatalogue.fromJson(
        context.assets.open("books.json").use { it.readBytes().toString(Charsets.UTF_8) },
        unknownBookHint = " Open Books to see every book name.",
    )

    private val packDb: SQLiteDatabase = SQLiteDatabase.openDatabase(
        installPack(context).path, null,
        SQLiteDatabase.OPEN_READONLY or SQLiteDatabase.NO_LOCALIZED_COLLATORS,
    )
    val bible: Bible = Bible(AndroidDb(packDb), catalogue)

    private val userDb: SQLiteDatabase = SQLiteDatabase.openOrCreateDatabase(context.getDatabasePath(USER_DB).also {
        it.parentFile?.mkdirs()
    }, null)
    val user: UserStore = UserStore(AndroidDb(userDb), catalogue)

    companion object {
        const val PACK_ASSET = "kjv-android.sqlite"
        const val USER_DB = "user.sqlite"

        /**
         * Copy the pack out of the APK on first run (or after an app update),
         * atomically, into no-backup storage. Older copies are removed.
         */
        private fun installPack(context: Context): File {
            val dir = File(context.noBackupFilesDir, "translations").apply { mkdirs() }
            // A new name for every install or update of the app, so an updated pack is always copied.
            @Suppress("DEPRECATION")
            val stamp = context.packageManager.getPackageInfo(context.packageName, 0).lastUpdateTime
            val target = File(dir, "kjv-${BuildConfig.VERSION_CODE}-$stamp.sqlite")
            if (!target.isFile) {
                val tmp = File(dir, "${target.name}.tmp")
                context.assets.open(PACK_ASSET).use { input ->
                    tmp.outputStream().use { out -> input.copyTo(out, 1 shl 16); out.fd.sync() }
                }
                check(tmp.length() > 0 && tmp.renameTo(target)) { "Could not install the Bible text." }
            }
            dir.listFiles()?.filter { it.name != target.name }?.forEach { it.delete() }
            return target
        }
    }
}

/** [SqlDb] on android.database.sqlite, binding typed parameters (not strings). */
class AndroidDb(private val db: SQLiteDatabase) : SqlDb {
    private fun bind(p: SQLiteProgram, args: List<Any?>) {
        args.forEachIndexed { i, a ->
            when (a) {
                null -> p.bindNull(i + 1)
                is Int -> p.bindLong(i + 1, a.toLong())
                is Long -> p.bindLong(i + 1, a)
                is Double -> p.bindDouble(i + 1, a)
                is String -> p.bindString(i + 1, a)
                else -> throw IllegalArgumentException("Unsupported SQL argument ${a::class.java}")
            }
        }
    }

    override fun query(sql: String, args: List<Any?>): List<List<Any?>> {
        val factory = SQLiteDatabase.CursorFactory { _, driver, editTable, query ->
            bind(query, args)
            SQLiteCursor(driver, editTable, query)
        }
        return db.rawQueryWithFactory(factory, sql, null, "").use { c ->
            val n = c.columnCount
            val out = ArrayList<List<Any?>>(c.count.coerceAtLeast(0))
            while (c.moveToNext()) {
                out.add((0 until n).map { i ->
                    when (c.getType(i)) {
                        android.database.Cursor.FIELD_TYPE_NULL -> null
                        android.database.Cursor.FIELD_TYPE_INTEGER -> c.getLong(i)
                        android.database.Cursor.FIELD_TYPE_FLOAT -> c.getDouble(i)
                        android.database.Cursor.FIELD_TYPE_BLOB -> c.getBlob(i)
                        else -> c.getString(i)
                    }
                })
            }
            out
        }
    }

    override fun execute(sql: String, args: List<Any?>): Int =
        db.compileStatement(sql).use { st ->
            bind(st, args)
            val head = sql.trimStart().take(6).uppercase()
            if (head == "UPDATE" || head == "DELETE" || head == "INSERT") st.executeUpdateDelete() else { st.execute(); 0 }
        }

    override fun insert(sql: String, args: List<Any?>): Long =
        db.compileStatement(sql).use { st -> bind(st, args); st.executeInsert() }

    override fun <T> transaction(block: () -> T): T {
        db.beginTransaction() // exclusive, like the desktop's BEGIN IMMEDIATE
        try {
            val r = block()
            db.setTransactionSuccessful()
            return r
        } finally {
            db.endTransaction()
        }
    }
}
