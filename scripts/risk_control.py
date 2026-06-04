#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
风控模块
包含动态止损/目标位、支撑压力位、仓位建议、风控铁律
"""

from typing import Dict, Any, Optional
import pandas as pd
import numpy as np


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

        if high_60 > current_price and high_60 != high_20:
            resistance.append({"price": round(high_60, 2), "source": "60日最高"})
        if low_60 < current_price and low_60 != low_20:
            support.append({"price": round(low_60, 2), "source": "60日最低"})

    # 4. 斐波那契回撤（基于近期高低点）
    if len(df) >= 20:
        swing_high = high_20
        swing_low = low_20
        fib_range = swing_high - swing_low

        for ratio, name in [(0.382, "38.2%"), (0.5, "50%"), (0.618, "61.8%")]:
            fib_price = swing_high - fib_range * ratio
            if fib_price > current_price:
                resistance.append({"price": round(fib_price, 2), "source": f"斐波那契{name}"})
            elif fib_price < current_price:
                support.append({"price": round(fib_price, 2), "source": f"斐波那契{name}"})

    # 去重并排序
    resistance = sorted(
        [{"price": r["price"], "source": r["source"]} for r in
         {item["price"]: item for item in resistance}.values()],
        key=lambda x: x["price"]
    )
    support = sorted(
        [{"price": s["price"], "source": s["source"]} for s in
         {item["price"]: item for item in support}.values()],
        key=lambda x: x["price"],
        reverse=True
    )

    return {
        "resistance": resistance[:5],  # 最多 5 个压力位
        "support": support[:5],        # 最多 5 个支撑位
    }
