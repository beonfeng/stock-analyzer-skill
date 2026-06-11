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


# ============================================================
# 行业差异化估值阈值
# ============================================================
# 不同行业的 PB/PE 合理区间差异巨大（银行 PB=0.8 合理，白酒 PB=6 也合理）
# 以下阈值基于 A 股各行业历史估值中枢设定

_INDUSTRY_VALUATION = {
    # 行业关键词 → (PE合理下限, PE合理上限, PB合理下限, PB合理上限)
    "银行":    (5, 10,  0.5, 1.2),
    "保险":    (8, 15,  0.8, 1.5),
    "证券":    (12, 22, 1.0, 2.0),
    "房地产":  (8, 15,  0.5, 1.5),
    "家电":    (12, 22, 1.5, 4.0),
    "白酒":    (20, 40, 3.0, 10.0),
    "饮料":    (20, 38, 3.0, 8.0),
    "食品":    (18, 35, 2.5, 7.0),
    "半导体":  (30, 55, 2.5, 8.0),
    "芯片":    (30, 55, 2.5, 8.0),
    "电子":    (20, 40, 1.5, 5.0),
    "软件":    (25, 50, 2.0, 7.0),
    "计算机":  (25, 50, 2.0, 7.0),
    "医药":    (25, 45, 2.0, 6.0),
    "医疗":    (25, 45, 2.0, 6.0),
    "新能源":  (15, 35, 1.5, 5.0),
    "光伏":    (12, 28, 1.0, 4.0),
    "锂电池":  (15, 30, 1.5, 5.0),
    "汽车":    (10, 22, 1.0, 3.0),
    "整车":    (8, 18,  0.8, 2.5),
    "钢铁":    (8, 15,  0.6, 1.5),
    "煤炭":    (8, 15,  0.8, 2.0),
    "有色":    (12, 25, 1.0, 3.0),
    "化工":    (10, 20, 1.0, 2.5),
    "建筑":    (6, 12,  0.5, 1.5),
    "建材":    (10, 20, 1.0, 2.5),
    "电力":    (12, 22, 1.0, 2.5),
    "公用事业":(12, 20, 1.0, 2.0),
    "交通运输":(10, 18, 1.0, 2.0),
    "通信":    (15, 30, 1.5, 4.0),
    "传媒":    (15, 30, 1.5, 4.0),
    "军工":    (25, 50, 2.0, 6.0),
    "农业":    (15, 30, 1.5, 3.5),
    "零售":    (12, 25, 1.0, 3.0),
    "旅游":    (18, 35, 2.0, 5.0),
}

# 全市场通用阈值（无法匹配行业时使用）
_DEFAULT_PE_ZONES = [
    (15, "低估"),
    (25, "合理"),
    (40, "合理偏高"),
]
_DEFAULT_PB_ZONES = [
    (1.0, "破净或接近"),
    (2.0, "低估"),
    (4.0, "合理"),
    (8.0, "合理偏高"),
]


def _match_industry(industry_name):
    """根据行业名称匹配行业估值配置，返回 (pe_lo, pe_hi, pb_lo, pb_hi) 或 None"""
    if not industry_name:
        return None
    for keyword, thresholds in _INDUSTRY_VALUATION.items():
        if keyword in industry_name:
            return thresholds
    return None


def _get_zone_for_industry(value, low, high, below_low_label, mid_label, above_high_label):
    """通用区间判断辅助：低/中/高 三档，带行业定制标签"""
    if value <= 0:
        return "数据缺失" if value == 0 else "亏损/净资产为负"
    if value < low:
        return below_low_label
    elif value <= high:
        return mid_label
    else:
        return above_high_label


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
    count_equal = np.sum(np.abs(arr - cv) < 1e-6)
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
    获取历史估值数据（已弃用）。

    东方财富 K 线 API 不返回 PE/PB 历史序列（仅提供实时值）。
    估值分位数功能暂时不可用，调用方应使用 _estimate_zone_from_value 经验判断。
    待实现：可通过逐日计算 总市值=股价×总股本 来重建 PE 历史序列。

    保留函数签名以兼容调用方，始终返回空结果。
    """
    return {'PE': [], 'PB': [], '股息率': []}


def analyze_valuation_percentile(code, current_quote, years=5, kline_data=None, industry=None):
    """
    估值分位数分析主函数。

    流程：
    1. 从 current_quote 提取当前 PE/PB/股息率
    2. 获取历史估值数据（当前 API 不返回历史序列，使用行业经验判断）
    3. 计算分位数
    4. 返回完整分析结果

    Args:
        code: 股票代码（如 '600519'）
        current_quote: 当前行情字典（来自 fetch_realtime_quote）
            需包含 'f9'（PE）、'f23'（PB）等字段
        years: 历史回溯年数（默认 5）
        kline_data: 已获取的 K 线 DataFrame（可选）
        industry: 所属行业名称（如 '家电行业'），用于行业差异化估值判断

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
    # 股息率：优先从 f163（股息率 TP:2 格式）获取，f168 为备选（分红送转）
    # 注意：f115 是「每股收益」而非股息率，不要误用
    current_dividend = _safe_float(current_quote.get("f163", 0)) or _safe_float(current_quote.get("f168", 0))

    # 2. 获取历史估值数据（如果已提供 kline_data，跳过重复请求）
    if kline_data is not None and not kline_data.empty:
        historical = {'PE': [], 'PB': [], '股息率': []}
    else:
        historical = fetch_historical_valuation(code, years=years)

    # 3. 计算分位数和区间
    result = {}

    for metric_name, current_val, hist_list in [
        ("PE", current_pe, historical.get('PE', [])),
        ("PB", current_pb, historical.get('PB', [])),
        ("股息率", current_dividend, historical.get('股息率', [])),
    ]:
        if hist_list and len(hist_list) > 0:
            try:
                percentile = calculate_percentile(current_val, hist_list)
                zone = get_valuation_zone(percentile)
            except (ValueError, TypeError):
                percentile = None
                zone = "数据不足"
        else:
            # 无历史数据，使用行业差异化经验判断
            percentile = None
            zone = _estimate_zone_from_value(metric_name, current_val, industry)

        result[metric_name] = {
            '当前值': current_val,
            '分位数': percentile,
            '区间': zone,
        }

    # 4. 综合评价
    result['综合评价'] = _generate_summary(result)

    return result


def _estimate_zone_from_value(metric_name, value, industry=None):
    """
    基于绝对值进行经验判断（无历史分位数时的回退方案）。

    优先使用行业差异化阈值（_INDUSTRY_VALUATION），无法匹配行业时
    使用全市场通用阈值。

    Args:
        metric_name: 指标名称（'PE'/'PB'/'股息率'）
        value: 当前值
        industry: 所属行业名称（如 '家电行业'），用于匹配差异化阈值

    Returns:
        str: 估值区间描述
    """
    if metric_name == "股息率":
        if value <= 0:
            return "无分红"
        elif value < 1:
            return "偏低"
        elif value < 3:
            return "合理"
        elif value < 5:
            return "较高"
        else:
            return "高股息"

    if abs(value) < 1e-6 or (isinstance(value, float) and np.isnan(value)):
        return "数据缺失"

    # 尝试匹配行业差异化阈值
    ind_thresholds = _match_industry(industry) if industry else None

    if metric_name == "PE":
        if value < 0:
            return "亏损"
        if ind_thresholds:
            pe_lo, pe_hi, _, _ = ind_thresholds
            return _get_zone_for_industry(
                value, pe_lo, pe_hi,
                f"低估（{industry}PE<{pe_lo}）",
                f"合理（{industry}PE {pe_lo}-{pe_hi}）",
                f"高估（{industry}PE>{pe_hi}）",
            )
        # 通用阈值
        if value < 15:
            return "低估（全市场通用）"
        elif value < 25:
            return "合理（全市场通用）"
        elif value < 40:
            return "合理偏高（全市场通用）"
        else:
            return "高估（全市场通用）"

    elif metric_name == "PB":
        if value < 0:
            return "净资产为负"
        if ind_thresholds:
            _, _, pb_lo, pb_hi = ind_thresholds
            return _get_zone_for_industry(
                value, pb_lo, pb_hi,
                f"低估（{industry}PB<{pb_lo}）",
                f"合理（{industry}PB {pb_lo}-{pb_hi}）",
                f"高估（{industry}PB>{pb_hi}）",
            )
        # 通用阈值
        if value < 1:
            return "破净（全市场通用）"
        elif value < 2:
            return "低估（全市场通用）"
        elif value < 4:
            return "合理（全市场通用）"
        elif value < 8:
            return "合理偏高（全市场通用）"
        else:
            return "高估（全市场通用）"

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
