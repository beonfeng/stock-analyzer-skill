#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
风控模块
包含动态止损/目标位、支撑压力位、仓位建议、风控铁律
"""

from typing import Dict, Any, Optional
import pandas as pd


# A 股不同板块的涨跌停幅度
LIMIT_RATIOS = {
    "main": 0.10,    # 主板 ±10%
    "gem": 0.20,     # 创业板 ±20%
    "star": 0.20,    # 科创板 ±20%
    "bj": 0.30,      # 北交所 ±30%
}


def detect_board_type(code: str) -> str:
    """
    判断 A 股板块类型。

    Args:
        code: 股票代码

    Returns:
        str: 'main' / 'gem' / 'star' / 'bj'
    """
    code = str(code).strip()
    if code.startswith("688"):
        return "star"
    elif code.startswith("300"):
        return "gem"
    elif code.startswith("8") or code.startswith("4"):
        return "bj"
    else:
        return "main"


def calc_dynamic_stop_loss(
    current_price: float,
    atr: float,
    board_type: str = "main",
    method: str = "atr"
) -> Dict[str, Any]:
    """
    计算动态止损位。

    Args:
        current_price: 当前价格
        atr: ATR（平均真实波幅）
        board_type: 板块类型
        method: 计算方法 ('atr' / 'percentage')

    Returns:
        dict: {
            'stop_loss': float,
            'stop_pct': float,
            'method': str,
            'description': str
        }
    """
    limit_ratio = LIMIT_RATIOS.get(board_type, 0.10)
    max_stop_pct = limit_ratio * 0.70  # 止损不超过涨跌停的 70%

    if method == "atr" and atr > 0:
        # ATR 方法：止损 = 当前价 - 2 x ATR
        atr_stop = current_price - 2 * atr
        stop_pct = (current_price - atr_stop) / current_price

        # 如果 ATR 止损幅度超过限制，使用百分比止损
        if stop_pct > max_stop_pct:
            stop_price = current_price * (1 - max_stop_pct)
            stop_pct = max_stop_pct
        else:
            stop_price = atr_stop
    else:
        # 百分比方法：默认 5%
        stop_pct = min(0.05, max_stop_pct)
        stop_price = current_price * (1 - stop_pct)

    return {
        "stop_loss": round(stop_price, 2),
        "stop_pct": round(stop_pct * 100, 2),
        "method": method,
        "description": f"止损价 {stop_price:.2f}，幅度 {stop_pct*100:.2f}%",
    }


def calc_target_price(
    current_price: float,
    stop_loss: float,
    risk_reward_ratio: float = 2.5
) -> Dict[str, Any]:
    """
    计算目标价位。

    Args:
        current_price: 当前价格
        stop_loss: 止损价
        risk_reward_ratio: 风险收益比（默认 2.5）

    Returns:
        dict: {
            'target_price': float,
            'upside_pct': float,
            'risk_reward_ratio': float,
            'description': str
        }
    """
    risk = current_price - stop_loss
    if risk <= 0:
        return {
            "target_price": current_price,
            "upside_pct": 0.0,
            "risk_reward_ratio": 0.0,
            "description": "止损价高于当前价，无法计算目标位",
        }

    target = current_price + risk * risk_reward_ratio
    upside_pct = (target - current_price) / current_price * 100

    return {
        "target_price": round(target, 2),
        "upside_pct": round(upside_pct, 2),
        "risk_reward_ratio": risk_reward_ratio,
        "description": f"目标价 {target:.2f}，预期涨幅 {upside_pct:.2f}%",
    }


def calc_support_resistance(
    df: pd.DataFrame,
    current_price: float,
    indicators: Dict[str, float]
) -> Dict[str, Any]:
    """
    计算支撑位和压力位。

    综合布林带、均线、近期高低点计算。

    Args:
        df: K线数据 DataFrame
        current_price: 当前价格
        indicators: 技术指标字典

    Returns:
        dict: {
            'resistance': [{'price': float, 'source': str}, ...],
            'support': [{'price': float, 'source': str}, ...]
        }
    """
    resistance = []
    support = []

    # 1. 布林带
    boll_up = indicators.get("BOLL_UP", 0)
    boll_mid = indicators.get("BOLL_MID", 0)
    boll_dn = indicators.get("BOLL_DN", 0)

    if boll_up > current_price:
        resistance.append({"price": round(boll_up, 2), "source": "布林上轨"})
    if boll_mid > current_price:
        resistance.append({"price": round(boll_mid, 2), "source": "布林中轨"})
    elif boll_mid < current_price:
        support.append({"price": round(boll_mid, 2), "source": "布林中轨"})
    if boll_dn < current_price:
        support.append({"price": round(boll_dn, 2), "source": "布林下轨"})

    # 2. 均线
    for ma_key in ["MA20", "MA60", "MA120", "MA250"]:
        ma_val = indicators.get(ma_key, 0)
        if ma_val <= 0:
            continue
        if ma_val > current_price:
            resistance.append({"price": round(ma_val, 2), "source": ma_key})
        else:
            support.append({"price": round(ma_val, 2), "source": ma_key})

    # 3. 近期高低点
    high_20 = 0
    low_20 = 0
    if len(df) >= 20:
        recent_20 = df.tail(20)
        high_20 = recent_20["最高"].max()
        low_20 = recent_20["最低"].min()

        if high_20 > current_price:
            resistance.append({"price": round(high_20, 2), "source": "20日最高"})
        if low_20 < current_price:
            support.append({"price": round(low_20, 2), "source": "20日最低"})

    if len(df) >= 60:
        recent_60 = df.tail(60)
        high_60 = recent_60["最高"].max()
        low_60 = recent_60["最低"].min()

        if high_60 > current_price and abs(high_60 - high_20) > 0.01:
            resistance.append({"price": round(high_60, 2), "source": "60日最高"})
        if low_60 < current_price and abs(low_60 - low_20) > 0.01:
            support.append({"price": round(low_60, 2), "source": "60日最低"})

    # 4. 斐波那契回撤（基于近期高低点）
    if len(df) >= 20 and high_20 > low_20:
        swing_high = high_20
        swing_low = low_20
        fib_range = swing_high - swing_low

        for ratio, name in [(0.382, "38.2%"), (0.5, "50%"), (0.618, "61.8%")]:
            fib_price = swing_high - fib_range * ratio
            if fib_price > current_price:
                resistance.append({"price": round(fib_price, 2), "source": f"斐波那契{name}"})
            elif fib_price < current_price:
                support.append({"price": round(fib_price, 2), "source": f"斐波那契{name}"})

    # 去重并排序（价格相同时合并 source 信息）
    def _dedup(items, reverse=False):
        merged = {}
        for item in items:
            p = item["price"]
            if p in merged:
                existing_sources = set(merged[p]["source"].split(" / "))
                existing_sources.add(item["source"])
                merged[p]["source"] = " / ".join(sorted(existing_sources))
            else:
                merged[p] = {"price": p, "source": item["source"]}
        return sorted(merged.values(), key=lambda x: x["price"], reverse=reverse)

    resistance = _dedup(resistance, reverse=False)
    support = _dedup(support, reverse=True)

    return {
        "resistance": resistance[:5],  # 最多 5 个压力位
        "support": support[:5],        # 最多 5 个支撑位
    }


def calc_position_size(
    direction: str,
    score: float,
    net_signals: int,
    has_bearish: bool
) -> Dict[str, Any]:
    """
    计算仓位建议。

    Args:
        direction: 操作方向 ('buy' / 'sell' / 'hold')
        score: 技术面评分
        net_signals: 净信号数（看多信号数 - 看空信号数）
        has_bearish: 是否存在看空信号

    Returns:
        dict: {
            'position_pct': int,
            'confidence': str,
            'description': str
        }
    """
    if direction == "sell" or score <= -5:
        return {
            "position_pct": 0,
            "confidence": "较高" if score <= -5 else "中等",
            "description": "建议空仓，等待企稳信号",
        }

    if direction == "hold" or (score < 3) or has_bearish:
        return {
            "position_pct": 0,
            "confidence": "较低",
            "description": "建议观望，信号不明确或存在矛盾",
        }

    # 买入信号
    if score >= 5 and not has_bearish and net_signals >= 2:
        return {
            "position_pct": 15,
            "confidence": "较高",
            "description": "建议仓位 10-20%，信号较强",
        }

    if score >= 3 and not has_bearish and net_signals >= 1:
        return {
            "position_pct": 8,
            "confidence": "中等",
            "description": "建议仓位 5-10%，信号中等",
        }

    return {
        "position_pct": 0,
        "confidence": "较低",
        "description": "建议观望，信号不足",
    }


def check_risk_rules(
    code: str,
    indicators: Dict[str, float],
    is_st: bool = False,
    is_new_stock: bool = False
) -> Dict[str, Any]:
    """
    执行风控铁律检查。

    Args:
        code: 股票代码
        indicators: 技术指标字典
        is_st: 是否为 ST 股票
        is_new_stock: 是否为次新股

    Returns:
        dict: {
            'warnings': list,
            'blocked': bool
        }
    """
    warnings = []
    price = indicators.get("最新价", 0)
    ma20 = indicators.get("MA20", 0)
    ma5 = indicators.get("MA5", 0)
    ma10 = indicators.get("MA10", 0)

    # 1. 乖离率检查（价格偏离 MA20 > 5%）
    if price <= 0:
        print("  [提示] 价格数据异常，跳过乖离率检查")
    if ma20 > 0 and price > 0:
        bias = (price - ma20) / ma20 * 100
        if bias > 5:
            warnings.append(f"乖离率 {bias:.1f}% > 5%，不建议追高")
        elif bias < -5:
            warnings.append(f"乖离率 {bias:.1f}% < -5%，超卖区域")

    # 2. 均线间距检查（间距 < 1% 不认定为有效排列）
    if ma5 > 0 and ma10 > 0 and ma20 > 0:
        gap_5_10 = abs(ma5 - ma10) / ma10 * 100
        gap_10_20 = abs(ma10 - ma20) / ma20 * 100
        if gap_5_10 < 1 and gap_10_20 < 1:
            warnings.append("均线间距过小（<1%），不认定为有效排列")

    # 3. ST 股票警告
    if is_st:
        warnings.append("该股票为 ST/*ST，存在退市风险，请特别注意")

    # 4. 次新股警告
    if is_new_stock:
        warnings.append("该股票为次新股（上市不足 1 年），波动较大，请注意风险")

    return {
        "warnings": warnings,
        "blocked": is_st,  # ST 股票标记为高风险
    }
