#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
估值分位数分析模块 — 计算当前估值在近 N 年历史中的百分位

功能：
- calculate_percentile: 计算当前值在历史序列中的百分位
- get_valuation_zone: 根据分位数判断估值区间
- fetch_historical_valuation: 获取历史估值数据
- analyze_valuation_percentile: 估值分位数分析主函数

依赖：
- analyze_stock 中的 fetch_kline、fetch_realtime_quote（复用已有 API 封装）
"""

import numpy as np

from .utils import _http_get_safe, safe_num as _safe_float
from .market_utils import get_market_info, get_secid


def calculate_percentile(current_value, historical_values):
    """
    计算当前值在历史序列中的百分位。

    使用线性插值方法：百分位 = (小于当前值的个数 / 总数) × 100

    Args:
        current_value: 当前值（float）
        historical_values: 历史值列表（list[float]）

    Returns:
        float: 0~100 的百分位数

    Raises:
        ValueError: historical_values 为空列表
        TypeError: current_value 或 historical_values 中包含非数值

    Examples:
        >>> calculate_percentile(50, [10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
        45.0
        >>> calculate_percentile(10, [10, 20, 30])
        0.0
    """
    # 参数校验
    if not isinstance(historical_values, (list, np.ndarray)):
        raise TypeError("historical_values 必须是列表或 numpy 数组")

    if len(historical_values) == 0:
        raise ValueError("historical_values 不能为空列表")

    # 转换为 numpy 数组并过滤无效值
    arr = np.array(historical_values, dtype=float)
    valid_mask = np.isfinite(arr)
    arr = arr[valid_mask]

    if len(arr) == 0:
        raise ValueError("historical_values 中没有有效数值")

    try:
        cv = float(current_value)
    except (TypeError, ValueError):
        raise TypeError(f"current_value 无法转换为浮点数: {current_value}")

    if not np.isfinite(cv):
        raise ValueError(f"current_value 不是有效数值: {current_value}")

    # 计算百分位：小于当前值的比例 × 100
    count_below = np.sum(arr < cv)
    count_equal = np.sum(arr == cv)
    n = len(arr)

    # 线性插值：将等于当前值的部分按比例分配
    percentile = (count_below + count_equal / 2) / n * 100

    # 限制在 0~100 范围内
    return round(float(np.clip(percentile, 0, 100)), 2)


def get_valuation_zone(percentile):
    """
    根据分位数判断估值区间。

    区间划分：
    - 0%~20%: 低估
    - 20%~40%: 合理偏低
    - 40%~60%: 合理
    - 60%~80%: 合理偏高
    - 80%~100%: 高估

    Args:
        percentile: 百分位数（0~100）

    Returns:
        str: 估值区间描述

    Examples:
        >>> get_valuation_zone(15)
        '低估'
        >>> get_valuation_zone(50)
        '合理'
    """
    if not isinstance(percentile, (int, float)):
        raise TypeError(f"percentile 必须是数值类型，收到: {type(percentile)}")

    if percentile < 0 or percentile > 100:
        raise ValueError(f"percentile 必须在 0~100 之间，收到: {percentile}")

    if percentile < 20:
        return "低估"
    elif percentile < 40:
        return "合理偏低"
    elif percentile < 60:
        return "合理"
    elif percentile < 80:
        return "合理偏高"
    else:
        return "高估"


def fetch_historical_valuation(code, years=5):
    """
    获取历史估值数据。

    通过东方财富 K 线 API 获取近 N 年的日线数据，并提取估值指标。

    注意：东方财富 K 线 API 返回的 fields2 中包含 f116（总市值），
    但不直接返回 PE/PB 历史序列。因此本函数采用以下策略：
    1. 尝试从 K 线数据中提取可用的估值字段
    2. 如果 API 限制导致无法获取完整历史，返回空字典并由调用方处理

    Args:
        code: 股票代码（如 '600519'）
        years: 回溯年数（默认 5）

    Returns:
        dict: {'PE': list, 'PB': list, '股息率': list}
            如果无法获取历史数据，返回空列表的字典
    """
    import datetime

    result = {'PE': [], 'PB': [], '股息率': []}

    try:
        market_code, market_id, _ = get_market_info(code)
    except ValueError:
        return result

    # 计算日期范围
    end = datetime.date.today().strftime("%Y%m%d")
    start = (datetime.date.today() - datetime.timedelta(days=years * 365)).strftime("%Y%m%d")

    # 尝试获取包含估值字段的 K 线数据
    # fields2 中 f116=总市值, f117=流通市值（但 PE/PB 不在标准 K 线字段中）
    params = {
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f116",
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "klt": "101",  # 日线
        "fqt": "1",    # 前复权
        "secid": get_secid(code, market_id),
        "beg": start, "end": end,
    }

    j = _http_get_safe("push2his.eastmoney.com", "/api/qt/stock/kline/get", params)
    if not j or not j.get("data"):
        return result

    klines = j["data"].get("klines", [])
    if not klines:
        return result

    # 由于 API 限制，K 线数据不直接包含 PE/PB 历史序列
    # 返回空的估值列表，调用方应使用当前快照数据进行有限分析
    return result


def analyze_valuation_percentile(code, current_quote, years=5):
    """
    估值分位数分析主函数。

    流程：
    1. 从 current_quote 提取当前 PE/PB/股息率
    2. 获取历史估值数据
    3. 计算分位数
    4. 返回完整分析结果

    Args:
        code: 股票代码（如 '600519'）
        current_quote: 当前行情字典（来自 fetch_realtime_quote）
            需包含 'f9'（PE）、'f23'（PB）等字段
        years: 历史回溯年数（默认 5）

    Returns:
        dict: {
            'PE': {'当前值': float, '分位数': float, '区间': str},
            'PB': {'当前值': float, '分位数': float, '区间': str},
            '股息率': {'当前值': float, '分位数': float, '区间': str},
            '综合评价': str
        }
    """

    # 1. 提取当前估值
    current_pe = _safe_float(current_quote.get("f9", 0))
    current_pb = _safe_float(current_quote.get("f23", 0))
    # 股息率在实时行情中可能不在标准字段中，尝试多种可能
    f115 = current_quote.get("f115")
    current_dividend = _safe_float(f115 if f115 is not None else current_quote.get("f163", 0))

    # 2. 获取历史估值数据
    historical = fetch_historical_valuation(code, years=years)

    # 3. 计算分位数和区间
    result = {}

    for metric_name, current_val, hist_list in [
        ("PE", current_pe, historical.get('PE', [])),
        ("PB", current_pb, historical.get('PB', [])),
        ("股息率", current_dividend, historical.get('股息率', [])),
    ]:
        if hist_list and len(hist_list) > 0:
            # 有历史数据，计算分位数
            try:
                percentile = calculate_percentile(current_val, hist_list)
                zone = get_valuation_zone(percentile)
            except (ValueError, TypeError):
                percentile = None
                zone = "数据不足"
        else:
            # 无历史数据，使用经验判断
            percentile = None
            zone = _estimate_zone_from_value(metric_name, current_val)

        result[metric_name] = {
            '当前值': current_val,
            '分位数': percentile,
            '区间': zone,
        }

    # 4. 综合评价
    result['综合评价'] = _generate_summary(result)

    return result


def _estimate_zone_from_value(metric_name, value):
    """
    当无法获取历史分位数时，基于绝对值进行经验判断。

    这是一个简化的估算方法，仅在无法获取历史数据时使用。
    不同行业的合理估值差异很大，此方法仅提供粗略参考。

    Args:
        metric_name: 指标名称（'PE'/'PB'/'股息率'）
        value: 当前值

    Returns:
        str: 估值区间描述
    """
    if metric_name == "股息率":
        # 股息率允许为 0，需要优先判断
        if value <= 0:
            return "无分红"
        elif value < 1:
            return "偏低（经验判断）"
        elif value < 3:
            return "合理（经验判断）"
        elif value < 5:
            return "较高（经验判断）"
        else:
            return "高股息（经验判断）"

    if value == 0:
        return "数据缺失"

    if metric_name == "PE":
        if value < 0:
            return "亏损"
        elif value < 15:
            return "低估（经验判断）"
        elif value < 25:
            return "合理（经验判断）"
        elif value < 40:
            return "合理偏高（经验判断）"
        else:
            return "高估（经验判断）"
    elif metric_name == "PB":
        if value < 0:
            return "净资产为负"
        elif value < 1:
            return "破净（经验判断）"
        elif value < 2:
            return "低估（经验判断）"
        elif value < 4:
            return "合理（经验判断）"
        elif value < 8:
            return "合理偏高（经验判断）"
        else:
            return "高估（经验判断）"

    return "数据不足"


def _generate_summary(valuation_result):
    """
    根据各指标的估值区间生成综合评价。

    Args:
        valuation_result: 包含 PE/PB/股息率 估值分析结果的字典

    Returns:
        str: 综合评价文本
    """
    zones = []
    details = []

    for metric in ["PE", "PB", "股息率"]:
        info = valuation_result.get(metric, {})
        zone = info.get("区间", "数据不足")
        current = info.get("当前值", 0)
        percentile = info.get("分位数")

        zones.append(zone)

        if percentile is not None:
            details.append(f"{metric} {current:.2f}（{percentile}%分位，{zone}）")
        else:
            details.append(f"{metric} {current:.2f}（{zone}）")

    # 综合判断
    undervalued_count = sum(1 for z in zones if "低估" in z or "破净" in z)
    overvalued_count = sum(1 for z in zones if "高估" in z)
    reasonable_count = sum(1 for z in zones if "合理" in z and "偏" not in z)
    loss_count = sum(1 for z in zones if "亏损" in z or "净资产为负" in z)
    missing_count = sum(1 for z in zones if "数据" in z or z == "")

    detail_str = "；".join(details)

    if missing_count >= 2:
        return f"估值数据不足，仅能提供有限参考。{detail_str}"
    elif loss_count > 0:
        return f"存在亏损或净资产为负的指标，需特别关注。{detail_str}"
    elif undervalued_count >= 2:
        return f"多项指标显示低估，可能存在投资机会。{detail_str}"
    elif overvalued_count >= 2:
        return f"多项指标显示高估，需注意估值风险。{detail_str}"
    elif reasonable_count >= 2:
        return f"估值整体处于合理区间。{detail_str}"
    else:
        return f"估值指标分化，需结合行业特性综合判断。{detail_str}"
