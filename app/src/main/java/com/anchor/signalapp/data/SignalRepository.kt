package com.anchor.signalapp.data

import android.content.Context
import com.anchor.signalapp.model.AppSnapshot
import com.anchor.signalapp.model.AssetSignal
import com.anchor.signalapp.model.ChartPoint
import com.anchor.signalapp.model.Condition
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

class SignalRepository(private val context: Context) {
    fun load(): Result<AppSnapshot> = runCatching {
        val raw = if (AppConfig.REMOTE_JSON_URL.isNotBlank()) {
            downloadJson(AppConfig.REMOTE_JSON_URL)
        } else {
            context.assets.open("sample_signal.json").bufferedReader().use { it.readText() }
        }
        parseSnapshot(raw)
    }

    private fun downloadJson(urlString: String): String {
        val connection = (URL(urlString).openConnection() as HttpURLConnection).apply {
            connectTimeout = 7000
            readTimeout = 7000
            requestMethod = "GET"
            setRequestProperty("Cache-Control", "no-cache")
        }
        return try {
            if (connection.responseCode !in 200..299) error("HTTP ${connection.responseCode}")
            connection.inputStream.bufferedReader().use { it.readText() }
        } finally {
            connection.disconnect()
        }
    }

    private fun parseSnapshot(raw: String): AppSnapshot {
        val root = JSONObject(raw)
        val assetsJson = root.getJSONArray("assets")
        val assets = buildList {
            for (i in 0 until assetsJson.length()) add(parseAsset(assetsJson.getJSONObject(i)))
        }
        return AppSnapshot(
            updatedAt = root.optString("updated_at", "-"),
            marketLabel = root.optString("market_label", "시장 상태"),
            marketDetail = root.optString("market_detail", ""),
            assets = assets
        )
    }

    private fun parseAsset(obj: JSONObject): AssetSignal {
        val conditions = mutableListOf<Condition>()
        val arr: JSONArray = obj.optJSONArray("conditions") ?: JSONArray()
        for (i in 0 until arr.length()) {
            val c = arr.getJSONObject(i)
            conditions += Condition(c.optString("label"), c.optBoolean("met"), c.optString("group"))
        }
        val chart = mutableListOf<ChartPoint>()
        val chartArr: JSONArray = obj.optJSONArray("chart") ?: JSONArray()
        for (i in 0 until chartArr.length()) {
            val p = chartArr.getJSONObject(i)
            chart += ChartPoint(
                date = p.optString("date"),
                price = p.optDouble("price", 0.0),
                ma20 = p.optDouble("ma20", 0.0),
                ma50 = p.optDouble("ma50", 0.0),
                ma100 = p.optDouble("ma100", 0.0),
                rsi14 = p.optDouble("rsi14", 0.0),
                macdHist = p.optDouble("macd_hist", 0.0),
                marker = p.optString("marker", "")
            )
        }
        return AssetSignal(
            symbol = obj.optString("symbol"),
            name = obj.optString("name"),
            price = obj.optDouble("price", 0.0),
            changePct = obj.optDouble("change_pct", 0.0),
            action = obj.optString("action", "HOLD"),
            actionKr = obj.optString("action_kr", "보유"),
            liveStatus = obj.optString("live_status", ""),
            riskScore = obj.optInt("risk_score", 0),
            riskMax = obj.optInt("risk_max", 8),
            recommendedAmount = obj.optDouble("recommended_amount", 0.0),
            recommendedShares = obj.optDouble("recommended_shares", 0.0),
            currentWeight = obj.optDouble("current_weight", 0.0),
            targetWeight = obj.optDouble("target_weight", 0.0),
            currentShares = obj.optDouble("current_shares", 0.0),
            avgPrice = obj.optDouble("avg_price", 0.0),
            positionValue = obj.optDouble("position_value", 0.0),
            buyReady = obj.optBoolean("buy_ready", false),
            sellReady = obj.optBoolean("sell_ready", false),
            reason = obj.optString("reason", ""),
            conditions = conditions,
            chart = chart
        )
    }
}
