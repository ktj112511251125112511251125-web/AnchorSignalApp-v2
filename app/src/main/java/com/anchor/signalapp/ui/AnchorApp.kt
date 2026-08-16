package com.anchor.signalapp.ui

import androidx.compose.animation.AnimatedContent
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.ArrowBack
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Schedule
import androidx.compose.material.icons.rounded.Shield
import androidx.compose.material.icons.rounded.TrendingUp
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.anchor.signalapp.model.AssetSignal
import com.anchor.signalapp.model.ChartPoint
import com.anchor.signalapp.ui.theme.*
import com.anchor.signalapp.viewmodel.MainViewModel
import java.text.NumberFormat
import java.util.Locale

@Composable
fun AnchorApp(vm: MainViewModel = viewModel()) {
    val state by vm.state.collectAsState()
    var selected by remember { mutableStateOf<AssetSignal?>(null) }
    Surface(Modifier.fillMaxSize(), color = Ink) {
        AnimatedContent(targetState = selected, label = "screen") { asset ->
            if (asset == null) {
                HomeScreen(state.loading, state.snapshot?.updatedAt, state.snapshot?.marketLabel,
                    state.snapshot?.marketDetail, state.snapshot?.assets.orEmpty(), state.error,
                    onRefresh = vm::refresh, onAssetClick = { selected = it })
            } else DetailScreen(asset, onBack = { selected = null })
        }
    }
}

@Composable
private fun HomeScreen(loading: Boolean, updatedAt: String?, marketLabel: String?, marketDetail: String?, assets: List<AssetSignal>, error: String?, onRefresh: () -> Unit, onAssetClick: (AssetSignal) -> Unit) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 18.dp)) {
        Spacer(Modifier.height(22.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("ANCHOR", color = Green, fontSize = 12.sp, fontWeight = FontWeight.Bold, letterSpacing = 2.sp)
                Text("Signal Console", fontSize = 30.sp, fontWeight = FontWeight.Black)
                Text("UPRO · QLD · TQQQ", color = TextMuted, fontSize = 13.sp)
            }
            FilledTonalIconButton(onClick = onRefresh) { Icon(Icons.Rounded.Refresh, "새로고침") }
        }
        Spacer(Modifier.height(22.dp))
        MarketHero(marketLabel ?: "시장 상태", marketDetail ?: "", updatedAt ?: "-")
        if (loading) LinearProgressIndicator(Modifier.fillMaxWidth().padding(top = 12.dp))
        if (error != null) Text(error, color = Red, modifier = Modifier.padding(top = 12.dp))
        Spacer(Modifier.height(24.dp))
        Text("오늘의 전략 신호", fontSize = 18.sp, fontWeight = FontWeight.Bold)
        Text("실제 전략 JSON · 주문수량 · 비중 · 위험점수 · 차트", color = TextMuted, fontSize = 12.sp)
        Spacer(Modifier.height(12.dp))
        assets.forEach { asset -> SignalCard(asset) { onAssetClick(asset) }; Spacer(Modifier.height(12.dp)) }
        Spacer(Modifier.height(28.dp))
        Text("※ 전략 신호 확인용 앱 · 실제 주문은 사용자가 최종 판단", color = TextMuted, fontSize = 11.sp)
        Spacer(Modifier.height(30.dp))
    }
}

@Composable
private fun MarketHero(title: String, detail: String, updatedAt: String) {
    Card(shape = RoundedCornerShape(28.dp), colors = CardDefaults.cardColors(containerColor = Panel2)) {
        Column(Modifier.padding(22.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(44.dp).clip(RoundedCornerShape(14.dp)).background(Green.copy(alpha = .12f)), contentAlignment = Alignment.Center) { Icon(Icons.Rounded.TrendingUp, null, tint = Green) }
                Spacer(Modifier.width(14.dp))
                Column(Modifier.weight(1f)) { Text("MARKET MODE", color = TextMuted, fontSize = 11.sp, fontWeight = FontWeight.Bold); Text(title, fontSize = 22.sp, fontWeight = FontWeight.ExtraBold) }
            }
            if (detail.isNotBlank()) { Spacer(Modifier.height(14.dp)); Text(detail, color = TextMuted, fontSize = 13.sp) }
            Spacer(Modifier.height(16.dp))
            Row(verticalAlignment = Alignment.CenterVertically) { Icon(Icons.Rounded.Schedule, null, tint = TextMuted, modifier = Modifier.size(15.dp)); Spacer(Modifier.width(6.dp)); Text("업데이트 $updatedAt", color = TextMuted, fontSize = 11.sp) }
        }
    }
}

@Composable
private fun SignalCard(asset: AssetSignal, onClick: () -> Unit) {
    val accent = actionColor(asset.action)
    Card(Modifier.fillMaxWidth().clickable(onClick = onClick), shape = RoundedCornerShape(24.dp), colors = CardDefaults.cardColors(containerColor = Panel)) {
        Column(Modifier.padding(20.dp)) {
            Row(verticalAlignment = Alignment.Top) {
                Column(Modifier.weight(1f)) { Text(asset.symbol, fontSize = 24.sp, fontWeight = FontWeight.Black); Text(asset.name, color = TextMuted, fontSize = 12.sp) }
                StatusPill(asset.actionKr, accent)
            }
            Spacer(Modifier.height(18.dp))
            Row(verticalAlignment = Alignment.Bottom) {
                Text("$${"%,.2f".format(Locale.US, asset.price)}", fontSize = 30.sp, fontWeight = FontWeight.Bold)
                Spacer(Modifier.width(10.dp)); Text("${if (asset.changePct >= 0) "+" else ""}${"%.2f".format(asset.changePct)}%", color = if (asset.changePct >= 0) Green else Red, fontWeight = FontWeight.Bold)
            }
            Spacer(Modifier.height(16.dp)); RiskBar(asset.riskScore, asset.riskMax); Spacer(Modifier.height(14.dp))
            Row {
                MiniMetric("현재 비중", "${"%.1f".format(asset.currentWeight)}%", Modifier.weight(1f)); Spacer(Modifier.width(8.dp))
                MiniMetric("목표 비중", "${"%.1f".format(asset.targetWeight)}%", Modifier.weight(1f)); Spacer(Modifier.width(8.dp))
                MiniMetric("조건", "${asset.conditions.count { it.met }}/${asset.conditions.size}", Modifier.weight(1f))
            }
            Spacer(Modifier.height(10.dp))
            Text("추천 ${dollar(asset.recommendedAmount)} · ${"%,.4f".format(Locale.US, asset.recommendedShares)}주", color = accent, fontSize = 12.sp, fontWeight = FontWeight.Bold)
            if (asset.liveStatus.isNotBlank()) { Spacer(Modifier.height(6.dp)); Text(asset.liveStatus, color = TextMuted, fontSize = 12.sp) }
        }
    }
}

@Composable
private fun DetailScreen(asset: AssetSignal, onBack: () -> Unit) {
    val accent = actionColor(asset.action)
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(18.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            FilledTonalIconButton(onClick = onBack) { Icon(Icons.Rounded.ArrowBack, "뒤로") }
            Spacer(Modifier.width(12.dp)); Column(Modifier.weight(1f)) { Text(asset.symbol, fontSize = 28.sp, fontWeight = FontWeight.Black); Text(asset.name, color = TextMuted, fontSize = 12.sp) }; StatusPill(asset.actionKr, accent)
        }
        Spacer(Modifier.height(22.dp))
        Card(shape = RoundedCornerShape(28.dp), colors = CardDefaults.cardColors(containerColor = Panel2)) {
            Column(Modifier.padding(22.dp)) {
                Text("현재 판단", color = TextMuted, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                Text(asset.liveStatus.ifBlank { asset.actionKr }, color = accent, fontSize = 22.sp, fontWeight = FontWeight.Black)
                Spacer(Modifier.height(10.dp)); Text(asset.reason.ifBlank { "전략 판단 상세 사유가 여기에 표시됩니다." }, color = TextMuted, fontSize = 13.sp)
            }
        }
        Spacer(Modifier.height(14.dp))
        Card(shape = RoundedCornerShape(24.dp), colors = CardDefaults.cardColors(containerColor = Panel)) {
            Column(Modifier.padding(20.dp)) {
                Text("실제 주문 / 계좌", fontWeight = FontWeight.Bold); Spacer(Modifier.height(12.dp))
                BigMetric("추천 금액", dollar(asset.recommendedAmount)); BigMetric("추천 수량", "${"%,.4f".format(Locale.US, asset.recommendedShares)} 주")
                BigMetric("현재 보유", "${"%,.4f".format(Locale.US, asset.currentShares)} 주"); BigMetric("평균단가", dollar(asset.avgPrice)); BigMetric("평가금액", dollar(asset.positionValue))
                BigMetric("현재 → 목표 비중", "${"%.1f".format(asset.currentWeight)}% → ${"%.1f".format(asset.targetWeight)}%")
                BigMetric("BUY / SELL Ready", "${if (asset.buyReady) "ON" else "OFF"} / ${if (asset.sellReady) "ON" else "OFF"}")
            }
        }
        Spacer(Modifier.height(14.dp)); StrategyChartCard(asset)
        Spacer(Modifier.height(14.dp))
        Card(shape = RoundedCornerShape(24.dp), colors = CardDefaults.cardColors(containerColor = Panel)) {
            Column(Modifier.padding(20.dp)) { Row(verticalAlignment = Alignment.CenterVertically) { Icon(Icons.Rounded.Shield, null, tint = accent); Spacer(Modifier.width(8.dp)); Text("리스크 게이트", fontWeight = FontWeight.Bold) }; Spacer(Modifier.height(14.dp)); RiskBar(asset.riskScore, asset.riskMax) }
        }
        Spacer(Modifier.height(14.dp)); Text("전략 조건", fontSize = 18.sp, fontWeight = FontWeight.Bold); Spacer(Modifier.height(8.dp))
        asset.conditions.forEach { condition ->
            Row(Modifier.fillMaxWidth().padding(vertical = 9.dp), verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Rounded.CheckCircle, null, tint = if (condition.met) Green else TextMuted, modifier = Modifier.size(20.dp)); Spacer(Modifier.width(10.dp))
                Column(Modifier.weight(1f)) { Text(condition.label, color = if (condition.met) TextMain else TextMuted); if (condition.group.isNotBlank()) Text(condition.group, color = TextMuted, fontSize = 10.sp) }
                Text(if (condition.met) "충족" else "미충족", color = if (condition.met) Green else TextMuted, fontSize = 12.sp, fontWeight = FontWeight.Bold)
            }
            HorizontalDivider(color = Color.White.copy(alpha = .05f))
        }
        Spacer(Modifier.height(30.dp))
    }
}

@Composable
private fun StrategyChartCard(asset: AssetSignal) {
    var mode by remember { mutableStateOf("PRICE") }
    Card(shape = RoundedCornerShape(24.dp), colors = CardDefaults.cardColors(containerColor = Panel)) {
        Column(Modifier.padding(18.dp)) {
            Text("전략 차트", fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(10.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf("PRICE" to "가격/MA", "RSI" to "RSI", "MACD" to "MACD").forEach { (key, label) ->
                    FilterChip(selected = mode == key, onClick = { mode = key }, label = { Text(label, fontSize = 11.sp) })
                }
            }
            Spacer(Modifier.height(8.dp))
            if (asset.chart.size < 2) Text("차트 데이터가 없습니다.", color = TextMuted, modifier = Modifier.padding(vertical = 40.dp)) else {
                SignalChart(asset.chart, mode, Modifier.fillMaxWidth().height(230.dp))
                val last = asset.chart.last()
                Spacer(Modifier.height(8.dp))
                Text("${last.date} · P ${"%.2f".format(last.price)} · MA20 ${"%.2f".format(last.ma20)} · RSI ${"%.1f".format(last.rsi14)} · MACD ${"%.3f".format(last.macdHist)}", color = TextMuted, fontSize = 10.sp)
                Text("BUY/SELL 표시는 JSON의 marker 값을 사용", color = TextMuted, fontSize = 10.sp)
            }
        }
    }
}

@Composable
private fun SignalChart(points: List<ChartPoint>, mode: String, modifier: Modifier = Modifier) {
    val primary = when (mode) { "RSI" -> points.map { it.rsi14 }; "MACD" -> points.map { it.macdHist }; else -> points.map { it.price } }
    val extra1 = if (mode == "PRICE") points.map { it.ma20 } else emptyList()
    val extra2 = if (mode == "PRICE") points.map { it.ma100 } else emptyList()
    val all = (primary + extra1 + extra2).filter { it.isFinite() }
    val minV = all.minOrNull() ?: 0.0; val maxV = all.maxOrNull() ?: 1.0; val span = (maxV - minV).takeIf { it > 0.000001 } ?: 1.0
    Canvas(modifier = modifier.clip(RoundedCornerShape(16.dp)).background(Panel2).padding(8.dp)) {
        fun y(v: Double) = size.height - (((v - minV) / span).toFloat() * size.height)
        fun line(values: List<Double>, color: Color, width: Float) {
            if (values.size < 2) return
            val path = Path()
            values.forEachIndexed { i, v -> val x = i.toFloat() / (values.size - 1).toFloat() * size.width; val yy = y(v); if (i == 0) path.moveTo(x, yy) else path.lineTo(x, yy) }
            drawPath(path, color, style = Stroke(width = width))
        }
        line(primary, Blue, 4f)
        if (mode == "PRICE") { line(extra1, Green, 2.5f); line(extra2, Gold, 2.5f) }
        if (mode == "RSI") {
            listOf(30.0, 50.0, 70.0).filter { it in minV..maxV }.forEach { v -> val yy = y(v); drawLine(TextMuted.copy(alpha = .35f), Offset(0f, yy), Offset(size.width, yy), strokeWidth = 1f) }
        }
        if (mode == "MACD" && 0.0 in minV..maxV) { val yy = y(0.0); drawLine(TextMuted.copy(alpha = .45f), Offset(0f, yy), Offset(size.width, yy), strokeWidth = 1f) }
        points.forEachIndexed { i, p ->
            val marker = p.marker.uppercase(); if (marker.startsWith("BUY") || marker.startsWith("SELL")) {
                val x = i.toFloat() / (points.size - 1).toFloat() * size.width
                val value = when (mode) { "RSI" -> p.rsi14; "MACD" -> p.macdHist; else -> p.price }
                drawCircle(if (marker.startsWith("BUY")) Green else Red, radius = 7f, center = Offset(x, y(value)))
            }
        }
    }
}

@Composable private fun StatusPill(text: String, color: Color) = Surface(color = color.copy(alpha = .14f), shape = RoundedCornerShape(50.dp)) { Text(text, color = color, fontWeight = FontWeight.ExtraBold, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 13.dp, vertical = 8.dp)) }
@Composable private fun RiskBar(score: Int, max: Int) { val ratio = if (max <= 0) 0f else (score.toFloat() / max).coerceIn(0f, 1f); val c = when { ratio >= .75f -> Red; ratio >= .45f -> Gold; else -> Green }; Column { Row { Text("위험점수", color = TextMuted, fontSize = 12.sp); Spacer(Modifier.weight(1f)); Text("$score / $max", color = c, fontWeight = FontWeight.Bold, fontSize = 12.sp) }; Spacer(Modifier.height(7.dp)); LinearProgressIndicator(progress = { ratio }, modifier = Modifier.fillMaxWidth().height(8.dp).clip(RoundedCornerShape(8.dp)), color = c, trackColor = Color.White.copy(alpha = .08f)) } }
@Composable private fun MiniMetric(label: String, value: String, modifier: Modifier = Modifier) { Box(modifier.clip(RoundedCornerShape(16.dp)).background(Panel2).padding(12.dp)) { Column { Text(label, color = TextMuted, fontSize = 10.sp); Spacer(Modifier.height(4.dp)); Text(value, fontWeight = FontWeight.Bold, fontSize = 13.sp) } } }
@Composable private fun BigMetric(label: String, value: String) { Row(Modifier.fillMaxWidth().padding(vertical = 7.dp)) { Text(label, color = TextMuted, modifier = Modifier.weight(1f)); Text(value, fontWeight = FontWeight.Bold) } }
private fun actionColor(action: String): Color = when (action.uppercase()) { "BUY", "BUY_MORE", "READY" -> Green; "SELL", "SELL_ALL", "SELL_PARTIAL", "EMERGENCY_SELL" -> Red; "WAIT", "WATCH" -> Gold; else -> Blue }
private fun dollar(v: Double): String = NumberFormat.getCurrencyInstance(Locale.US).format(v)
