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
