package org.qbible.app

import android.graphics.Color
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.runtime.DisposableEffect
import org.qbible.app.ui.QBibleRoot

class MainActivity : ComponentActivity() {
    private val vm: MainViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            val dark = when (vm.prefs.theme) {
                "light" -> false
                "dark" -> true
                else -> isSystemInDarkTheme()
            }
            // System bar icons follow the app's theme, which may differ from the phone's.
            DisposableEffect(dark) {
                val lightScrim = Color.argb(0xE6, 0xFF, 0xFF, 0xFF)
                val darkScrim = Color.argb(0x80, 0x1B, 0x1B, 0x1B)
                enableEdgeToEdge(
                    statusBarStyle = if (dark) SystemBarStyle.dark(Color.TRANSPARENT)
                    else SystemBarStyle.light(Color.TRANSPARENT, Color.TRANSPARENT),
                    navigationBarStyle = if (dark) SystemBarStyle.dark(darkScrim)
                    else SystemBarStyle.light(lightScrim, darkScrim),
                )
                onDispose {}
            }
            QBibleRoot(vm, onExit = { finish() })
        }
    }
}
