package com.anchor.signalapp.model

data class Condition(
    val label: String,
    val met: Boolean,
    val group: String = ""
)

data class ChartPoint(
    val date: String,
    val price: Double,
    val ma20: Double,
    val ma50: Double,
    val ma100: Double,
    val rsi14: Double,
    val macdHist: Double,
    val marker: String = ""
)

data class AssetSignal(
    val symbol: String,
    val name: String,
    val price: Double,
    val changePct: Double,
    val action: String,
    val actionKr: String,
    val liveStatus: String,
    val riskScore: Int,
    val riskMax: Int,
    val recommendedAmount: Double,
    val recommendedShares: Double,
    val currentWeight: Double,
    val targetWeight: Double,
    val currentShares: Double,
    val avgPrice: Double,
    val positionValue: Double,
    val buyReady: Boolean,
    val sellReady: Boolean,
    val reason: String,
    val conditions: List<Condition>,
    val chart: List<ChartPoint>
)

data class AppSnapshot(
    val updatedAt: String,
    val marketLabel: String,
    val marketDetail: String,
    val assets: List<AssetSignal>
)
