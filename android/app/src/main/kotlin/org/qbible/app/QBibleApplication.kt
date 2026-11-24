package org.qbible.app

import android.app.Application

class QBibleApplication : Application() {
    /** Opened on first use, off the main thread (see MainViewModel). */
    val data: AppData by lazy { AppData(this) }
}
