package com.anchor.signalapp

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.core.view.WindowCompat
import com.anchor.signalapp.ui.AnchorApp
import com.anchor.signalapp.ui.theme.AnchorSignalTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, true)
        setContent { AnchorSignalTheme { AnchorApp() } }
    }
}
