#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图表 HTML/JS 模板模块 — 生成交互式图表 HTML + JavaScript

使用 Canvas 2D API 纯前端渲染，无外部依赖。
图表嵌入 HTML 报告中的 <div class="chart-container"> 区域，
所有数据以 JSON 格式嵌入 <script type="application/json"> 标签。

图表类型：
- K 线图：收盘价折线 + MA均线 + BOLL带 + 成交量柱状 + MACD
- 估值图：PE/PB 当前值 vs 历史分位数
- 资金流图：主力资金流入柱状 + 累计曲线
"""

import json
from typing import Any, Dict


# ============================================================
# 图表 HTML 容器生成
# ============================================================

def build_kline_chart_html(chart_data: Dict[str, Any]) -> str:
    """
    生成 K 线图完整 HTML（容器 + 数据 + 渲染脚本）。

    Chart layout:
    - 上区（60%）：收盘价折线 + MA5/MA10/MA20/MA60 + BOLL 上下轨
    - 中区（20%）：成交量柱状图
    - 下区（20%）：MACD 柱 + DIF/DEA 线
    """
    data_json = json.dumps(chart_data, ensure_ascii=False, default=str)
    chart_id = "chart-kline"

    return f"""
<div class="chart-container">
    <div class="chart-title">📈 K线走势图（近120日）</div>
    <canvas id="{chart_id}" width="860" height="480"></canvas>
    <div class="chart-legend">
        <span style="color:#e74c3c">── 收盘价</span>
        <span style="color:#f39c12">── MA5</span>
        <span style="color:#3498db">── MA20</span>
        <span style="color:#9b59b6">── MA60</span>
        <span style="color:#95a5a6;border-top:1px dashed #95a5a6">⋯ BOLL</span>
    </div>
</div>
<script type="application/json" id="{chart_id}-data">
{data_json}
</script>
"""


def build_valuation_chart_html(chart_data: Dict[str, Any]) -> str:
    """
    生成估值分位数图表 HTML。

    展示 PE/PB 当前值及其在近 5 年历史中的分位数位置。
    """
    data_json = json.dumps(chart_data, ensure_ascii=False, default=str)
    chart_id = "chart-valuation"

    pe_val = chart_data.get("pe_current", 0)
    pb_val = chart_data.get("pb_current", 0)
    pe_pct = chart_data.get("pe_percentile")
    pb_pct = chart_data.get("pb_percentile")
    pe_zone = chart_data.get("pe_zone", "")
    pb_zone = chart_data.get("pb_zone", "")

    pe_pct_str = f"{pe_pct:.0f}% ({pe_zone})" if pe_pct is not None else "N/A"
    pb_pct_str = f"{pb_pct:.0f}% ({pb_zone})" if pb_pct is not None else "N/A"

    return f"""
<div class="chart-container">
    <div class="chart-title">📊 估值分位数（近5年）</div>
    <div class="valuation-grid">
        <div class="valuation-card">
            <div class="valuation-label">市盈率 PE</div>
            <div class="valuation-value">{pe_val:.1f}</div>
            <div class="valuation-meta">分位数: {pe_pct_str}</div>
        </div>
        <div class="valuation-card">
            <div class="valuation-label">市净率 PB</div>
            <div class="valuation-value">{pb_val:.2f}</div>
            <div class="valuation-meta">分位数: {pb_pct_str}</div>
        </div>
    </div>
    <canvas id="{chart_id}" width="860" height="200"></canvas>
</div>
<script type="application/json" id="{chart_id}-data">
{data_json}
</script>
"""


def build_fund_flow_chart_html(chart_data: Dict[str, Any]) -> str:
    """
    生成资金流向图表 HTML。

    展示主力资金多周期净流入柱状图。
    """
    data_json = json.dumps(chart_data, ensure_ascii=False, default=str)
    chart_id = "chart-fundflow"

    main_today = chart_data.get("main_today", 0)
    main_5d = chart_data.get("main_5d", 0)

    direction = "流入" if main_today > 0 else "流出" if main_today < 0 else "平衡"
    color = "#27ae60" if main_today > 0 else "#e74c3c" if main_today < 0 else "#95a5a6"

    return f"""
<div class="chart-container">
    <div class="chart-title">💰 主力资金流向</div>
    <div class="fund-summary">
        <span>今日主力<span style="color:{color};font-weight:bold"> {direction} {abs(main_today):.0f} 万</span></span>
        <span style="margin-left:24px">5日累计: {main_5d:+.0f} 万</span>
    </div>
    <canvas id="{chart_id}" width="860" height="250"></canvas>
</div>
<script type="application/json" id="{chart_id}-data">
{data_json}
</script>
"""


# ============================================================
# 统一的图表渲染 JavaScript（Canvas 2D）
# ============================================================

_CHART_RENDERER_JS = """
<script>
(function() {
    'use strict';

    // ============================================================
    // 微型图表引擎（Canvas 2D）
    // ============================================================

    const CHART_COLORS = {
        price: '#e74c3c',
        ma5: '#f39c12',
        ma10: '#e67e22',
        ma20: '#3498db',
        ma60: '#9b59b6',
        boll: '#95a5a6',
        volumeUp: '#ef5350',
        volumeDown: '#26a69a',
        macdBar: '#7f8c8d',
        dif: '#e74c3c',
        dea: '#3498db',
        grid: '#ecf0f1',
        text: '#7f8c8d',
        fundIn: '#27ae60',
        fundOut: '#e74c3c',
    };

    function clearCanvas(canvas) {
        var ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        return ctx;
    }

    function drawGrid(ctx, w, h, xCount, yCount, pad) {
        ctx.strokeStyle = '#f0f0f0';
        ctx.lineWidth = 0.5;
        for (var i = 0; i <= yCount; i++) {
            var y = pad.top + (h - pad.top - pad.bottom) * i / yCount;
            ctx.beginPath();
            ctx.moveTo(pad.left, y);
            ctx.lineTo(w - pad.right, y);
            ctx.stroke();
        }
    }

    function drawLine(ctx, data, xScale, yScale, pad, color, width) {
        if (!data || data.length < 2) return;
        ctx.strokeStyle = color;
        ctx.lineWidth = width || 1.5;
        ctx.beginPath();
        var started = false;
        for (var i = 0; i < data.length; i++) {
            if (data[i] === null || data[i] === undefined) { started = false; continue; }
            var x = pad.left + i * xScale;
            var y = yScale(data[i]);
            if (!started) { ctx.moveTo(x, y); started = true; }
            else { ctx.lineTo(x, y); }
        }
        ctx.stroke();
    }

    function drawBars(ctx, data, xScale, yScale, yZero, pad, barW, upColor, downColor) {
        if (!data || data.length < 2) return;
        for (var i = 1; i < data.length; i++) {
            if (data[i] === null || data[i-1] === null) continue;
            var x = pad.left + i * xScale;
            var y = yScale(data[i]);
            var color = data[i] >= data[i-1] ? (upColor || CHART_COLORS.volumeUp) : (downColor || CHART_COLORS.volumeDown);
            ctx.fillStyle = color;
            ctx.fillRect(x - barW/2, y, barW, yZero - y);
        }
    }

    // ============================================================
    // K 线图渲染（价格 + MA + BOLL + 成交量 + MACD）
    // ============================================================
    function renderKlineChart() {
        var el = document.getElementById('chart-kline-data');
        var canvas = document.getElementById('chart-kline');
        if (!el || !canvas) return;
        try {
            var data = JSON.parse(el.textContent);
            if (!data.dates || data.dates.length < 2) return;
        } catch(e) { return; }

        var W = canvas.width, H = canvas.height;
        var ctx = clearCanvas(canvas);
        var pad = {top: 10, right: 20, bottom: 10, left: 50};

        // 区域划分
        var priceH = H * 0.55;
        var volH = H * 0.20;
        var macdH = H * 0.25;

        var n = data.dates.length;
        var xScale = (W - pad.left - pad.right) / (n - 1);

        // --- 上区：价格 + MA + BOLL ---
        var priceMin = Infinity, priceMax = -Infinity;
        [data.close, data.ma5, data.ma10, data.ma20, data.ma60, data.boll_up, data.boll_dn].forEach(function(arr) {
            if (!arr) return;
            arr.forEach(function(v) { if (v !== null && v !== undefined) { priceMin = Math.min(priceMin, v); priceMax = Math.max(priceMax, v); } });
        });
        if (priceMin === Infinity) return;
        var pricePad = (priceMax - priceMin) * 0.08;
        priceMin -= pricePad; priceMax += pricePad;

        var priceY = function(v) { return pad.top + priceH - ((v - priceMin) / (priceMax - priceMin)) * (priceH - pad.top - 5); };

        drawGrid(ctx, W, priceH, 5, 4, {top: pad.top, right: pad.right, bottom: 0, left: pad.left});

        // BOLL 带
        drawLine(ctx, data.boll_up, xScale, priceY, {top: pad.top, right: pad.right, bottom: 0, left: pad.left}, '#bdc3c7', 0.8);
        drawLine(ctx, data.boll_dn, xScale, priceY, {top: pad.top, right: pad.right, bottom: 0, left: pad.left}, '#bdc3c7', 0.8);

        // MAs
        drawLine(ctx, data.ma5, xScale, priceY, {top: pad.top, right: pad.right, bottom: 0, left: pad.left}, CHART_COLORS.ma5, 1);
        drawLine(ctx, data.ma20, xScale, priceY, {top: pad.top, right: pad.right, bottom: 0, left: pad.left}, CHART_COLORS.ma20, 1.5);
        drawLine(ctx, data.ma60, xScale, priceY, {top: pad.top, right: pad.right, bottom: 0, left: pad.left}, CHART_COLORS.ma60, 1);

        // 收盘价（最粗）
        drawLine(ctx, data.close, xScale, priceY, {top: pad.top, right: pad.right, bottom: 0, left: pad.left}, CHART_COLORS.price, 2);

        // Y 轴标签
        ctx.fillStyle = CHART_COLORS.text;
        ctx.font = '9px sans-serif';
        for (var i = 0; i <= 4; i++) {
            var price = priceMin + (priceMax - priceMin) * i / 4;
            ctx.fillText(price.toFixed(1), 2, pad.top + priceH - (priceH - pad.top) * i / 4 + 3);
        }

        // --- 中区：成交量 ---
        var volY = pad.top + priceH;
        var volMin = 0, volMax = Math.max.apply(null, data.volume.filter(function(v) { return v !== null; })) || 1;
        volMax *= 1.15;
        var volScale = function(v) { return volY + volH - 2 - ((v - volMin) / (volMax - volMin)) * (volH - 4); };
        var barW = Math.max(1, xScale * 0.7);

        drawGrid(ctx, W, volH, 2, 3, {top: 2, right: pad.right, bottom: 2, left: pad.left});
        ctx.fillStyle = '#7f8c8d';
        data.volume.forEach(function(v, i) {
            if (v === null) return;
            var x = pad.left + i * xScale;
            var h = ((v - volMin) / (volMax - volMin)) * (volH - 4);
            ctx.fillRect(x - barW/2, volY + volH - 2 - h, barW, Math.max(0.5, h));
        });

        // --- 下区：MACD ---
        var macdY = volY + volH;
        var macdAll = (data.macd_hist || []).concat(data.macd_dif || []).concat(data.macd_dea || []).filter(function(v) { return v !== null; });
        var macdMin = macdAll.length ? Math.min.apply(null, macdAll) : -1;
        var macdMax = macdAll.length ? Math.max.apply(null, macdAll) : 1;
        var macdAbs = Math.max(Math.abs(macdMin), Math.abs(macdMax)) * 1.2;
        var macdScale = function(v) { return macdY + macdH/2 - (v / macdAbs) * (macdH/2 - 4); };
        var macdZero = macdY + macdH/2;

        // 零轴
        ctx.strokeStyle = '#ddd';
        ctx.lineWidth = 0.5;
        ctx.beginPath();
        ctx.moveTo(pad.left, macdZero);
        ctx.lineTo(W - pad.right, macdZero);
        ctx.stroke();

        // MACD 柱状图
        (data.macd_hist || []).forEach(function(v, i) {
            if (v === null) return;
            var x = pad.left + i * xScale;
            var h = Math.abs(v) / macdAbs * (macdH/2 - 4);
            ctx.fillStyle = v >= 0 ? '#ef5350' : '#26a69a';
            ctx.fillRect(x - barW/2, v >= 0 ? macdZero - h : macdZero, barW, Math.max(0.5, h));
        });

        // DIF/DEA 线
        drawLine(ctx, data.macd_dif || [], xScale, macdScale, {top: 0, right: pad.right, bottom: 0, left: pad.left}, CHART_COLORS.dif, 1);
        drawLine(ctx, data.macd_dea || [], xScale, macdScale, {top: 0, right: pad.right, bottom: 0, left: pad.left}, CHART_COLORS.dea, 1);

        // 区标签
        ctx.fillStyle = '#666';
        ctx.font = 'bold 10px sans-serif';
        ctx.fillText('MACD', pad.left, macdY + 12);
        ctx.fillText('VOL', pad.left, volY + 12);
    }

    // ============================================================
    // 估值分位数图渲染
    // ============================================================
    function renderValuationChart() {
        var el = document.getElementById('chart-valuation-data');
        var canvas = document.getElementById('chart-valuation');
        if (!el || !canvas) return;
        try {
            var data = JSON.parse(el.textContent);
        } catch(e) { return; }

        var W = canvas.width, H = canvas.height;
        var ctx = clearCanvas(canvas);
        var pad = {top: 15, right: 60, bottom: 20, left: 50};

        // 绘制历史 PB 走势对比
        var history = data.pb_history || data.pe_history || [];
        if (history.length < 2) {
            ctx.fillStyle = '#999';
            ctx.font = '13px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('（历史估值序列数据不可用，请参考上方分位数卡片）', W/2, H/2);
            return;
        }

        var vals = history.map(function(h) { return h[1]; });
        var vMin = Math.min.apply(null, vals) * 0.9;
        var vMax = Math.max.apply(null, vals) * 1.1;
        var n = history.length;
        var xScale = (W - pad.left - pad.right) / (n - 1);

        var yScale = function(v) { return pad.top + (H - pad.top - pad.bottom) - ((v - vMin) / (vMax - vMin)) * (H - pad.top - pad.bottom); };

        drawGrid(ctx, W, H, 5, 4, pad);

        // 历史走势
        ctx.strokeStyle = '#3498db';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        for (var i = 0; i < n; i++) {
            var x = pad.left + i * xScale;
            var y = yScale(history[i][1]);
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        ctx.stroke();

        // 当前值线
        var currentVal = data.pb_current || data.pe_current || 0;
        if (currentVal > 0) {
            var cy = yScale(currentVal);
            ctx.strokeStyle = '#e74c3c';
            ctx.lineWidth = 1;
            ctx.setLineDash([4, 4]);
            ctx.beginPath();
            ctx.moveTo(pad.left, cy);
            ctx.lineTo(W - pad.right, cy);
            ctx.stroke();
            ctx.setLineDash([]);

            ctx.fillStyle = '#e74c3c';
            ctx.font = 'bold 10px sans-serif';
            ctx.fillText('当前: ' + currentVal.toFixed(1), W - pad.right - 60, cy - 4);
        }

        // Y 轴标签
        ctx.fillStyle = '#7f8c8d';
        ctx.font = '9px sans-serif';
        for (var j = 0; j <= 4; j++) {
            ctx.fillText((vMin + (vMax - vMin) * j / 4).toFixed(1), 2, pad.top + (H - pad.top - pad.bottom) * (1 - j/4) + 3);
        }

        // 标题
        var label = data.pb_history && data.pb_history.length > 0 ? 'PB 历史走势' : 'PE 历史走势';
        ctx.fillStyle = '#666';
        ctx.font = '11px sans-serif';
        ctx.fillText(label, pad.left, pad.top - 2);
    }

    // ============================================================
    // 资金流向图渲染
    // ============================================================
    function renderFundFlowChart() {
        var el = document.getElementById('chart-fundflow-data');
        var canvas = document.getElementById('chart-fundflow');
        if (!el || !canvas) return;
        try {
            var data = JSON.parse(el.textContent);
        } catch(e) { return; }

        var W = canvas.width, H = canvas.height;
        var ctx = clearCanvas(canvas);
        var pad = {top: 15, right: 30, bottom: 20, left: 60};

        // 绘制多周期柱状图
        var periods = [
            {label: '今日', value: data.main_today || 0},
            {label: '3日', value: data.main_3d || 0},
            {label: '5日', value: data.main_5d || 0},
            {label: '10日', value: data.main_10d || 0},
        ];

        var maxAbs = Math.max.apply(null, periods.map(function(p) { return Math.abs(p.value); })) || 1;
        maxAbs *= 1.3;

        var barArea = (W - pad.left - pad.right) * 0.7;
        var barX = pad.left + (W - pad.left - pad.right - barArea) / 2;
        var barW = Math.min(60, barArea / periods.length * 0.7);
        var gap = barArea / periods.length;

        // 零轴
        var zeroY = pad.top + (H - pad.top - pad.bottom) / 2;
        ctx.strokeStyle = '#aaa';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(pad.left, zeroY);
        ctx.lineTo(W - pad.right, zeroY);
        ctx.stroke();

        // 柱状图
        periods.forEach(function(p, i) {
            var h = (Math.abs(p.value) / maxAbs) * ((H - pad.top - pad.bottom) / 2 - 10);
            var x = barX + i * gap;
            var y = p.value >= 0 ? zeroY - h : zeroY;
            ctx.fillStyle = p.value >= 0 ? CHART_COLORS.fundIn : CHART_COLORS.fundOut;
            ctx.fillRect(x - barW/2, y, barW, Math.max(1, h));

            // 数值标签
            ctx.fillStyle = '#333';
            ctx.font = 'bold 11px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText((p.value >= 0 ? '+' : '') + p.value.toFixed(0) + '万', x, y - 4);

            // 周期标签
            ctx.fillStyle = '#666';
            ctx.font = '10px sans-serif';
            ctx.fillText(p.label, x, zeroY + 14);
        });

        // 图例
        ctx.fillStyle = CHART_COLORS.fundIn;
        ctx.fillRect(W - pad.right - 140, pad.top, 10, 10);
        ctx.fillStyle = '#333';
        ctx.font = '10px sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText('净流入', W - pad.right - 125, pad.top + 9);
        ctx.fillStyle = CHART_COLORS.fundOut;
        ctx.fillRect(W - pad.right - 65, pad.top, 10, 10);
        ctx.fillText('净流出', W - pad.right - 50, pad.top + 9);
    }

    // ============================================================
    // 初始化
    // ============================================================
    try { renderKlineChart(); } catch(e) { console.error('Kline chart:', e); }
    try { renderFundFlowChart(); } catch(e) { console.error('Fund flow chart:', e); }
    try { renderValuationChart(); } catch(e) { console.error('Valuation chart:', e); }

})();
</script>
"""


# ============================================================
# 图表 CSS
# ============================================================

_CHART_CSS = """
<style>
.chart-container {
    width: 100%;
    max-width: 900px;
    margin: 28px 0;
    background: #fafbfc;
    border: 1px solid #e1e4e8;
    border-radius: 8px;
    padding: 16px 20px;
    box-sizing: border-box;
}
.chart-container canvas {
    display: block;
    width: 100% !important;
    height: auto !important;
    max-width: 860px;
}
.chart-title {
    font-size: 15px;
    font-weight: 600;
    color: #24292e;
    margin-bottom: 10px;
    padding-bottom: 8px;
    border-bottom: 1px solid #eee;
}
.chart-legend {
    font-size: 11px;
    color: #666;
    margin-top: 8px;
    display: flex;
    flex-wrap: wrap;
    gap: 14px;
}
.chart-legend span {
    display: inline-flex;
    align-items: center;
}
.valuation-grid {
    display: flex;
    gap: 16px;
    margin-bottom: 12px;
}
.valuation-card {
    flex: 1;
    background: #fff;
    border: 1px solid #e1e4e8;
    border-radius: 6px;
    padding: 12px 16px;
    text-align: center;
}
.valuation-label {
    font-size: 12px;
    color: #666;
}
.valuation-value {
    font-size: 28px;
    font-weight: 700;
    color: #24292e;
    margin: 4px 0;
}
.valuation-meta {
    font-size: 11px;
    color: #999;
}
.fund-summary {
    font-size: 13px;
    color: #555;
    margin-bottom: 10px;
    padding: 8px 12px;
    background: #fff;
    border-radius: 4px;
}
@media print {
    .chart-container {
        break-inside: avoid;
        border: 1px solid #ccc;
    }
}
</style>
"""


# ============================================================
# 统一图表 HTML 生成
# ============================================================

def build_all_charts_html(chart_data: Dict[str, Any]) -> str:
    """
    生成所有图表的完整 HTML 片段。

    Args:
        chart_data: extract_all_chart_data() 的返回结果

    Returns:
        str: 包含 CSS + 图表容器 + 数据 + 渲染脚本的完整 HTML
    """
    parts = [_CHART_CSS]

    kline = chart_data.get("kline", {})
    if kline and kline.get("dates"):
        parts.append(build_kline_chart_html(kline))

    fund = chart_data.get("fund_flow", {})
    if fund:
        parts.append(build_fund_flow_chart_html(fund))

    val = chart_data.get("valuation", {})
    if val and (val.get("pe_current", 0) > 0 or val.get("pb_current", 0) > 0):
        parts.append(build_valuation_chart_html(val))

    parts.append(_CHART_RENDERER_JS)

    return "\n".join(parts)


# ============================================================
# 模块自测
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("图表模板测试")
    print("=" * 60)

    # 模拟数据
    import sys
    sys.path.insert(0, "..")
    from scripts.chart_data import extract_all_chart_data
    import pandas as pd
    import numpy as np

    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=120, freq="B")
    price = 100 + np.cumsum(np.random.randn(120) * 2)
    df = pd.DataFrame({
        "日期": dates.strftime("%Y-%m-%d"),
        "开盘": price + np.random.randn(120) * 0.5,
        "收盘": price,
        "最高": price + np.abs(np.random.randn(120) * 1),
        "最低": price - np.abs(np.random.randn(120) * 1),
        "成交量": np.random.randint(1e7, 5e8, 120),
        "成交额": np.random.randint(1e9, 5e10, 120),
    })

    chart_data = extract_all_chart_data(df)
    html = build_all_charts_html(chart_data)

    print(f"\n生成 HTML 长度: {len(html)} 字符")
    print(f"  - 图表 CSS: {len(_CHART_CSS)} 字符")
    print(f"  - 渲染 JS: {len(_CHART_RENDERER_JS)} 字符")

    # 保存示例
    sample_path = "chart_sample.html"
    full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>图表示例</title>
</head>
<body style="max-width:920px;margin:0 auto;padding:20px;font-family:sans-serif">
<h2>Stock Analyzer 图表示例</h2>
{html}
</body>
</html>"""
    with open(sample_path, "w", encoding="utf-8") as f:
        f.write(full_html)
    print(f"\n示例 HTML 已保存: {sample_path}")

    print("\n" + "=" * 60)
    print("测试完成")
