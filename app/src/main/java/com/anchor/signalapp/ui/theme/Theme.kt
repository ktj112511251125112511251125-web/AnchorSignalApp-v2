package com.anchor.signalapp.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

val Ink = Color(0xFF08111F)
val Panel = Color(0xFF0F1B2D)
val Panel2 = Color(0xFF152238)
val TextMain = Color(0xFFF3F7FF)
val TextMuted = Color(0xFF8EA2C0)
val Green = Color(0xFF2EE6A6)
val Red = Color(0xFFFF5A66)
val Gold = Color(0xFFFFD166)
val Blue = Color(0xFF6EA8FE)

private val AnchorColors = darkColorScheme(
    primary = Green,
    secondary = Blue,
    background = Ink,
    surface = Panel,
    surfaceVariant = Panel2,
    onPrimary = Ink,
    onBackground = TextMain,
    onSurface = TextMain
)

@Composable
fun AnchorSignalTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = AnchorColors, content = content)
}
