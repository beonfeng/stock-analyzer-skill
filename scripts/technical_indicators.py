#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技术指标扩展模块 — 高级技术分析指标

包含：
- RSI 背离检测
- MACD 柱状图分析
- 成交量异动检测
- K 线形态识别
- 筹码分布计算
- 综合扩展指标
"""

import numpy as np
import pandas as pd

# K 线形态阈值常量
DOJI_BODY_RATIO = 0.1      # 十字星：实体/影线比例阈值
HAMMER_SHADOW_RATIO = 2     # 锤子线：下影线/实体比例
HAMMER_BODY_RATIO = 0.1     # 锤子线：实体/最高最低比例
ENGULFING_RATIO = 0.5       # 吞没形态：实体覆盖比例


def detect_rsi_divergence(close, rsi, lookback=20):
    """
    检测 RSI 背离。

    顶背离：价格创新高，但 RSI 未创新高 → 看跌信号
    底背离：价格创新低，但 RSI 未创新低 → 看涨信号

    Args:
        close: 收盘价序列（pandas.Series）
        rsi: RSI 序列（pandas.Series）
        lookback: 回看周期（默认 20）

    Returns:
        dict: {
            '类型': '顶背离' / '底背离' / '无背离',
            '信号': str,
            '可靠性': '高' / '中' / '低'
        }
    """
    if len(close) < lookback or len(rsi) < lookback:
        return {'类型': '无背离', '信号': '数据不足，无法判断', '可靠性': '低'}

    recent_close = close.iloc[-lookback:]
    recent_rsi = rsi.iloc[-lookback:]

    # 将回看窗口分为前半段和后半段
    half = lookback // 2
    first_close = recent_close.iloc[:half]
    second_close = recent_close.iloc[half:]
    first_rsi = recent_rsi.iloc[:half]
    second_rsi = recent_rsi.iloc[half:]

    first_close_max = first_close.max()
    second_close_max = second_close.max()
    first_rsi_max = first_rsi.max()
    second_rsi_max = second_rsi.max()

    first_close_min = first_close.min()
    second_close_min = second_close.min()
    first_rsi_min = first_rsi.min()
    second_rsi_min = second_rsi.min()

    # 顶背离：后半段价格新高，但 RSI 未新高
    if second_close_max > first_close_max and second_rsi_max < first_rsi_max:
        # 根据背离幅度判断可靠性
        price_diff = (second_close_max - first_close_max) / first_close_max
        rsi_diff = (first_rsi_max - second_rsi_max) / (first_rsi_max + 1e-10)
        if price_diff > 0.05 and rsi_diff > 0.1:
            reliability = '高'
        elif price_diff > 0.02 and rsi_diff > 0.05:
            reliability = '中'
        else:
            reliability = '低'
        return {
            '类型': '顶背离',
            '信号': '价格创新高但RSI未创新高，看跌信号，注意回调风险',
            '可靠性': reliability,
        }

    # 底背离：后半段价格新低，但 RSI 未新低
    if second_close_min < first_close_min and second_rsi_min > first_rsi_min:
        price_diff = (first_close_min - second_close_min) / first_close_min
        rsi_diff = (second_rsi_min - first_rsi_min) / (first_rsi_min + 1e-10)
        if price_diff > 0.05 and rsi_diff > 0.1:
            reliability = '高'
        elif price_diff > 0.02 and rsi_diff > 0.05:
            reliability = '中'
        else:
            reliability = '低'
        return {
            '类型': '底背离',
            '信号': '价格创新低但RSI未创新低，看涨信号，关注反弹机会',
            '可靠性': reliability,
        }

    return {'类型': '无背离', '信号': '价格与RSI同步，无明显背离', '可靠性': '低'}


def analyze_macd_histogram(dif_series, dea_series):
    """
    分析 MACD 柱状图。

    Args:
        dif_series: DIF 序列（pandas.Series）
        dea_series: DEA 序列（pandas.Series）

    Returns:
        dict: {
            '连续红柱天数': int,
            '连续绿柱天数': int,
            '柱状图斜率': float,
            '趋势判断': str,
            '信号': str
        }
    """
    length = min(len(dif_series), len(dea_series))
    dif = dif_series.iloc[-length:]
    dea = dea_series.iloc[-length:]

    # MACD 柱状图 = DIF - DEA
    histogram = dif - dea

    # 计算连续红柱/绿柱天数
    red_count = 0
    green_count = 0

    # 从最后一天往前数连续红柱
    for i in range(len(histogram) - 1, -1, -1):
        if histogram.iloc[i] > 0:
            red_count += 1
        else:
            break

    # 从最后一天往前数连续绿柱
    for i in range(len(histogram) - 1, -1, -1):
        if histogram.iloc[i] < 0:
            green_count += 1
        else:
            break

    # 柱状图斜率（最近 5 天的线性斜率）
    recent = histogram.iloc[-5:] if len(histogram) >= 5 else histogram
    if len(recent) >= 2:
        x = np.arange(len(recent), dtype=float)
        y = recent.values.astype(float)
        if np.any(np.isnan(y)):
            slope = 0.0
        else:
            # 最小二乘法线性拟合
            slope = np.polyfit(x, y, 1)[0]
    else:
        slope = 0.0

    # 趋势判断
    if red_count > 0:
        if slope > 0:
            trend = '红柱放大，多头增强'
            signal = '红柱持续放大，多头动能增强，看涨'
        else:
            trend = '红柱缩小，多头减弱'
            signal = '红柱持续缩小，多头动能减弱，注意变盘'
    elif green_count > 0:
        if slope < 0:
            trend = '绿柱放大，空头增强'
            signal = '绿柱持续放大，空头动能增强，看跌'
        else:
            trend = '绿柱缩小，空头减弱'
            signal = '绿柱持续缩小，空头动能减弱，关注反弹'
    else:
        trend = '无明显趋势'
        signal = 'MACD柱状图无明显方向'

    return {
        '连续红柱天数': red_count,
        '连续绿柱天数': green_count,
        '柱状图斜率': float(slope),
        '趋势判断': trend,
        '信号': signal,
    }


def detect_volume_anomaly(volume, ma5, ma20):
    """
    检测成交量异动。

    放量：当日成交量 > 5 日均量 × 1.5
    缩量：当日成交量 < 5 日均量 × 0.5
    天量：当日成交量 > 20 日均量 × 2.0
    地量：当日成交量 < 20 日均量 × 0.3

    Args:
        volume: 当日成交量
        ma5: 5 日均量
        ma20: 20 日均量

    Returns:
        dict: {
            '状态': '放量' / '缩量' / '天量' / '地量' / '正常',
            '倍数': float,
            '信号': str
        }
    """
    if ma5 <= 0 or ma20 <= 0:
        return {'状态': '正常', '倍数': 0.0, '信号': '均量数据异常'}

    ratio_5 = volume / ma5
    ratio_20 = volume / ma20

    # 天量优先于放量，地量优先于缩量
    if ratio_20 > 2.0:
        return {
            '状态': '天量',
            '倍数': round(ratio_20, 2),
            '信号': f'成交量为20日均量的{ratio_20:.1f}倍，天量异动，关注是否有重大消息或主力行为',
        }
    if ratio_20 < 0.3:
        return {
            '状态': '地量',
            '倍数': round(ratio_20, 2),
            '信号': f'成交量仅为20日均量的{ratio_20:.1f}倍，地量状态，市场交投清淡',
        }
    if ratio_5 > 1.5:
        return {
            '状态': '放量',
            '倍数': round(ratio_5, 2),
            '信号': f'成交量为5日均量的{ratio_5:.1f}倍，放量异动，关注价格方向',
        }
    if ratio_5 < 0.5:
        return {
            '状态': '缩量',
            '倍数': round(ratio_5, 2),
            '信号': f'成交量仅为5日均量的{ratio_5:.1f}倍，缩量状态，市场观望情绪浓厚',
        }

    return {
        '状态': '正常',
        '倍数': round(ratio_5, 2),
        '信号': '成交量处于正常范围',
    }


def identify_candlestick_patterns(df, lookback=5):
    """
    识别 K 线形态。

    支持形态：
    - 十字星：开盘价 ≈ 收盘价，上下影线较长
    - 锤子线：下影线 > 实体 2 倍，上影线很短
    - 倒锤子线：上影线 > 实体 2 倍，下影线很短
    - 看涨吞没：当日阳线实体完全包含前一日阴线实体
    - 看跌吞没：当日阴线实体完全包含前一日阳线实体
    - 乌云盖顶：阳线后出现高开低走阴线

    Args:
        df: 包含 '开盘'、'收盘'、'最高'、'最低' 列的 DataFrame
        lookback: 回看天数（默认 5）

    Returns:
        list: [{'形态': str, '信号': str, '可靠性': str}, ...]
    """
    patterns = []
    start = max(1, len(df) - lookback)
    eps = 1e-9  # 浮点容差

    for i in range(start, len(df)):
        row = df.iloc[i]
        o, c, h, l = row['开盘'], row['收盘'], row['最高'], row['最低']
        body = abs(c - o)
        upper_shadow = h - max(o, c)
        lower_shadow = min(o, c) - l
        total_range = h - l if h != l else 0.001  # 避免除零

        # 十字星：实体很小，上下影线较长
        if body < total_range * DOJI_BODY_RATIO and upper_shadow > body and lower_shadow > body:
            patterns.append({
                '形态': '十字星',
                '信号': '多空博弈激烈，可能变盘',
                '可靠性': '中',
            })

        # 锤子线：下影线 > 实体 2 倍，上影线很短
        if body > 0 and lower_shadow > body * HAMMER_SHADOW_RATIO and upper_shadow <= body * ENGULFING_RATIO + eps:
            patterns.append({
                '形态': '锤子线',
                '信号': '下影线长，下方支撑强，可能反弹',
                '可靠性': '中',
            })

        # 倒锤子线：上影线 > 实体 2 倍，下影线很短（与锤子线互斥）
        elif body > 0 and upper_shadow > body * HAMMER_SHADOW_RATIO and lower_shadow <= body * ENGULFING_RATIO + eps:
            patterns.append({
                '形态': '倒锤子线',
                '信号': '上影线长，上方压力大，但有反弹意愿',
                '可靠性': '中',
            })

        # 吞没形态：需要前一根 K 线
        if i > 0:
            prev = df.iloc[i - 1]
            prev_o, prev_c = prev['开盘'], prev['收盘']
            prev_body_top = max(prev_o, prev_c)
            prev_body_bottom = min(prev_o, prev_c)
            curr_body_top = max(o, c)
            curr_body_bottom = min(o, c)

            # 看涨吞没：前阴后阳，当日实体完全包含前一日实体
            if (prev_c < prev_o and c > o and
                    curr_body_top > prev_body_top and curr_body_bottom < prev_body_bottom):
                patterns.append({
                    '形态': '看涨吞没',
                    '信号': '阳线完全吞没前一日阴线，看涨反转',
                    '可靠性': '高',
                })

            # 看跌吞没：前阳后阴，当日实体完全包含前一日实体（与看涨吞没互斥）
            elif (prev_c > prev_o and c < o and
                    curr_body_top > prev_body_top and curr_body_bottom < prev_body_bottom):
                patterns.append({
                    '形态': '看跌吞没',
                    '信号': '阴线完全吞没前一日阳线，看跌反转',
                    '可靠性': '高',
                })

            # 乌云盖顶：阳线后出现高开低走阴线，阴线收盘价低于阳线实体中部
            elif (prev_c > prev_o and c < o and
                    o > prev_body_top and c < (prev_o + prev_c) / 2):
                patterns.append({
                    '形态': '乌云盖顶',
                    '信号': '高开低走阴线深入阳线实体，看跌反转',
                    '可靠性': '高',
                })

    return patterns


def calculate_chip_distribution(df, current_price):
    """
    计算筹码分布。

    Args:
        df: 包含 '收盘' 和 '成交量' 列的 DataFrame
        current_price: 当前价格

    Returns:
        dict: {
            '平均成本': float,
            '获利盘比例': float,
            '套牢盘比例': float,
            '筹码集中度': str
        }
    """
    prices = df['收盘'].values.astype(float)
    volumes = df['成交量'].values.astype(float)

    total_volume = volumes.sum()
    if total_volume == 0:
        return {
            '平均成本': 0.0,
            '获利盘比例': 0.0,
            '套牢盘比例': 1.0,
            '筹码集中度': '无法判断',
        }

    # 平均成本：成交量加权平均
    avg_cost = np.sum(prices * volumes) / total_volume

    # 获利盘比例：当前价格下方的筹码占比
    profit_mask = prices <= current_price
    profit_volume = volumes[profit_mask].sum()
    profit_ratio = profit_volume / total_volume

    # 套牢盘比例
    loss_ratio = 1.0 - profit_ratio

    # 筹码集中度：基于价格波动系数（变异系数 CV）
    mean_price = np.mean(prices)
    if mean_price > 0:
        cv = np.std(prices) / mean_price
    else:
        cv = 0

    if cv < 0.02:
        concentration = '高度集中'
    elif cv < 0.05:
        concentration = '较为集中'
    elif cv < 0.10:
        concentration = '较为分散'
    else:
        concentration = '非常分散'

    return {
        '平均成本': round(float(avg_cost), 4),
        '获利盘比例': round(float(profit_ratio), 4),
        '套牢盘比例': round(float(loss_ratio), 4),
        '筹码集中度': concentration,
    }


def calculate_extended_indicators(df, indicators):
    """
    综合技术指标扩展函数，调用所有扩展指标函数。

    Args:
        df: 包含 '开盘'、'收盘'、'最高'、'最低'、'成交量' 列的 DataFrame
        indicators: 基础指标字典（需包含 RSI6、DIF、DEA 等）

    Returns:
        dict: 扩展指标字典，包含 RSI背离、MACD柱状图、成交量异动、K线形态、筹码分布
    """
    result = {}

    close = df['收盘'].astype(float)
    volume = df['成交量'].astype(float)

    # 1. RSI 背离检测
    # 注意：此处重新计算 RSI 序列用于背离检测（需要完整序列而非单值），
    # 使用与 analyzer.py 相同的 Wilder 平滑算法（rolling mean）
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(6).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(6).mean()
    loss_safe = loss.replace(0, 1e-10)  # 避免除零
    rs = gain / loss_safe
    rsi_series = 100 - 100 / (1 + rs)
    result['RSI背离'] = detect_rsi_divergence(close, rsi_series, lookback=20)

    # 2. MACD 柱状图分析
    # 注意：此处需要完整的 DIF/DEA 序列用于柱状图分析（连续红柱天数、斜率等），
    # 与 analyzer.py 中的单值 DIF/DEA 计算目的不同（单值用于评级），
    # 因此需要重新计算完整序列，并非重复逻辑。
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    result['MACD柱状图'] = analyze_macd_histogram(dif, dea)

    # 3. 成交量异动检测
    ma5_vol = volume.rolling(5).mean().fillna(volume.mean()).iloc[-1] if len(volume) >= 5 else volume.mean()
    ma20_vol = volume.rolling(20).mean().fillna(volume.mean()).iloc[-1] if len(volume) >= 20 else volume.mean()
    result['成交量异动'] = detect_volume_anomaly(
        volume=volume.iloc[-1],
        ma5=ma5_vol,
        ma20=ma20_vol,
    )

    # 4. K 线形态识别
    result['K线形态'] = identify_candlestick_patterns(df, lookback=5)

    # 5. 筹码分布
    current_price = close.iloc[-1]
    result['筹码分布'] = calculate_chip_distribution(df, current_price)

    return result
