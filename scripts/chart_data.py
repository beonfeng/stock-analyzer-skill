#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图表数据提取模块 — 从 ReportContext 提取结构化数据供前端图表渲染

将 DataFrame 和指标字典中的关键数据提取为 JSON-serializable 格式，
嵌入 HTML 报告中的 <script type="application/json"> 标签。

提取的图表类型：
- K线图：收盘价 + MA均线 + BOLL带 + 成交量 + MACD
- 估值图：PE/PB 历史分位数（如有历史数据）
- 资金流图：主力资金每日净流入 + 累计净流入
"""

import json
from typing import Any, Dict, List, Optional

import pandas as pd
import numpy as np


def safe_num(val, default=0.0) -> float:
    """安全数值转换"""
    if val is None:
        return default
    if isinstance(val, (int, float, np.integer, np.floating)):
        if np.isnan(float(val)) or np.isinf(float(val)):
            return default
        return float(val)
    return default


def _serialize(obj):
    """确保对象可 JSON 序列化"""
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj) if not np.isnan(obj) and not np.isinf(obj) else 0.0
    if isinstance(obj, pd.Timestamp):
        return str(obj)[:10]
    return obj


# ============================================================
# K 线图数据提取
# ============================================================

def extract_kline_chart_data(
    df: pd.DataFrame,
    indicators: Optional[Dict] = None,
    days: int = 120,
) -> Dict[str, Any]:
    """
    从 K 线 DataFrame 和指标字典提取前端 K 线图数据。

    Args:
        df: K线 DataFrame，列包含 [日期/开盘/收盘/最高/最低/成交量/成交额]
        indicators: 技术指标字典（可选，含 MA/BOLL/MACD 等）
        days: 取最近 N 个交易日

    Returns:
        dict: {
            'dates': [...],              # 日期列表
            'close': [...],              # 收盘价
            'volume': [...],             # 成交量（万股）
            'ma5': [...],                # 5日均线
            'ma10': [...],               # 10日均线
            'ma20': [...],               # 20日均线
            'ma60': [...],               # 60日均线
            'boll_up': [...],            # 布林上轨
            'boll_mid': [...],           # 布林中轨
            'boll_dn': [...],            # 布林下轨
            'macd_dif': [...],           # MACD DIF
            'macd_dea': [...],           # MACD DEA
            'macd_hist': [...],          # MACD 柱
            'name': str,                 # 股票名称
            'code': str,                 # 股票代码
            'latest_price': float,       # 最新价
        }
    """
    if df is None or df.empty:
        return {"dates": [], "close": [], "volume": [], "name": "", "code": ""}

    ind = indicators or {}

    # 取最近 N 日
    df_tail = df.tail(days).copy()
    if "日期" not in df_tail.columns:
        return {"dates": [], "close": [], "volume": [], "name": "", "code": ""}

    dates = df_tail["日期"].astype(str).tolist()
    close = [safe_num(v) for v in df_tail.get("收盘", [])]
    volume = [safe_num(v) / 100 for v in df_tail.get("成交量", [])]  # 股→手

    # MA 均线（如果有 indicators 则直接用，否则从收盘价计算）
    def _ma(series, window):
        if len(series) >= window:
            return series.rolling(window=window).mean().tolist()
        return [None] * len(series)

    close_series = df_tail["收盘"].astype(float) if "收盘" in df_tail.columns else None

    ma5 = ind.get("MA5_list") if "MA5_list" in ind else (
        _ma(close_series, 5) if close_series is not None else [None] * len(dates))
    ma10 = ind.get("MA10_list") if "MA10_list" in ind else (
        _ma(close_series, 10) if close_series is not None else [None] * len(dates))
    ma20 = ind.get("MA20_list") if "MA20_list" in ind else (
        _ma(close_series, 20) if close_series is not None else [None] * len(dates))
    ma60 = ind.get("MA60_list") if "MA60_list" in ind else (
        _ma(close_series, 60) if close_series is not None else [None] * len(dates))

    # BOLL 带
    boll_up = ind.get("BOLL_UP_list", [None] * len(dates))
    boll_mid = ind.get("BOLL_MID_list", ma20)  # 布林中轨 ≈ MA20
    boll_dn = ind.get("BOLL_DN_list", [None] * len(dates))

    # MACD
    dif = ind.get("DIF_list", [None] * len(dates))
    dea = ind.get("DEA_list", [None] * len(dates))
    macd_hist = ind.get("MACD_list", [None] * len(dates))

    # 序列化（处理 NaN）
    def _safe_list(lst, size):
        """确保列表长度一致，NaN → None"""
        if lst is None:
            return [None] * size
        result = []
        for v in lst[:size]:
            if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
                result.append(None)
            else:
                result.append(round(float(v), 2) if isinstance(v, (int, float, np.floating)) else v)
        while len(result) < size:
            result.append(None)
        return result[:size]

    n = len(dates)
    return {
        "dates": dates,
        "close": _safe_list(close, n),
        "volume": _safe_list(volume, n),
        "ma5": _safe_list(ma5, n),
        "ma10": _safe_list(ma10, n),
        "ma20": _safe_list(ma20, n),
        "ma60": _safe_list(ma60, n),
        "boll_up": _safe_list(boll_up, n),
        "boll_mid": _safe_list(boll_mid if boll_mid else ma20, n),
        "boll_dn": _safe_list(boll_dn, n),
        "macd_dif": _safe_list(dif, n),
        "macd_dea": _safe_list(dea, n),
        "macd_hist": _safe_list(macd_hist, n),
        "name": str(ind.get("name", "")),
        "code": str(ind.get("code", "")),
        "latest_price": safe_num(close[-1]) if close else 0,
    }


# ============================================================
# 估值分位数图数据提取
# ============================================================

def extract_valuation_chart_data(
    quote: Optional[Dict] = None,
    valuation_percentile: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    从行情和估值分位数数据提取估值图数据。

    Returns:
        dict: {
            'pe_current': float,
            'pe_percentile': float or None,
            'pe_zone': str,
            'pe_history': [[date, value], ...],  # PE 历史序列
            'pb_current': float,
            'pb_percentile': float or None,
            'pb_zone': str,
            'pb_history': [[date, value], ...],  # PB 历史序列
        }
    """
    q = quote or {}
    vp = valuation_percentile or {}

    result = {
        "pe_current": safe_num(q.get("f9", 0)),
        "pe_percentile": None,
        "pe_zone": "",
        "pe_history": [],
        "pb_current": safe_num(q.get("f23", 0)),
        "pb_percentile": None,
        "pb_zone": "",
        "pb_history": [],
        "dividend_yield": safe_num(q.get("f92", 0)),
    }

    if isinstance(vp, dict):
        pe_pct = vp.get("pe_percentile")
        if pe_pct is not None and pe_pct != "N/A":
            try:
                result["pe_percentile"] = float(str(pe_pct).replace("%", ""))
            except (ValueError, TypeError):
                pass
        result["pe_zone"] = str(vp.get("pe_zone", ""))

        pb_pct = vp.get("pb_percentile")
        if pb_pct is not None and pb_pct != "N/A":
            try:
                result["pb_percentile"] = float(str(pb_pct).replace("%", ""))
            except (ValueError, TypeError):
                pass
        result["pb_zone"] = str(vp.get("pb_zone", ""))

        # PE 历史序列
        pe_hist = vp.get("pe_history")
        if isinstance(pe_hist, list) and pe_hist:
            result["pe_history"] = [
                [str(h[0])[:10], safe_num(h[1])]
                for h in pe_hist[:252]  # 最多 5 年（252 个交易日）
                if len(h) >= 2
            ]

        # PB 历史序列
        pb_hist = vp.get("pb_history")
        if isinstance(pb_hist, list) and pb_hist:
            result["pb_history"] = [
                [str(h[0])[:10], safe_num(h[1])]
                for h in pb_hist[:252]
                if len(h) >= 2
            ]

    return result


# ============================================================
# 资金流向图数据提取
# ============================================================

def extract_fund_flow_chart_data(
    fund_flow: Optional[Dict] = None,
    df: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """
    从资金流向数据和 K 线提取资金流图表数据。

    注意：东方财富资金流向接口只返回今日/3日/5日/10日累计值，
    不提供每日明细，因此图表数据有限。如有每日主力净流入序列则使用，
    否则仅展示累计值。

    Returns:
        dict: {
            'main_today': float,         # 今日主力净流入（万元）
            'main_3d': float,            # 3日主力净流入（万元）
            'main_5d': float,            # 5日主力净流入（万元）
            'main_10d': float,           # 10日主力净流入（万元）
            'dates': [...],              # 近20日日期（从 K 线获取）
            'daily_flows': [...],        # 每日主力净流入（如有）
            'cumulative': [...],         # 累计主力净流入（如有）
        }
    """
    ff = fund_flow or {}

    def _get(key, sub_key="f62"):
        """安全提取资金流数据，单位转为万元"""
        try:
            if isinstance(ff, dict):
                val = ff.get(key, {})
                if isinstance(val, dict):
                    return safe_num(val.get(sub_key, 0)) / 1e4
            return 0.0
        except Exception:
            return 0.0

    # 日期列表从 K 线获取
    dates = []
    if df is not None and not df.empty and "日期" in df.columns:
        dates = df["日期"].astype(str).tail(20).tolist()

    return {
        "main_today": _get("今日"),
        "main_3d": _get("3日"),
        "main_5d": _get("5日"),
        "main_10d": _get("10日"),
        "dates": dates,
        "daily_flows": [],  # 东方财富不提供每日明细
        "cumulative": [],   # 同上
    }


# ============================================================
# 统一提取接口
# ============================================================

def extract_all_chart_data(
    df: Optional[pd.DataFrame] = None,
    indicators: Optional[Dict] = None,
    quote: Optional[Dict] = None,
    fund_flow: Optional[Dict] = None,
    valuation_percentile: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    一次性提取所有图表数据。

    Returns:
        dict: {
            'kline': {...},
            'valuation': {...},
            'fund_flow': {...},
        }
    """
    return {
        "kline": extract_kline_chart_data(df, indicators),
        "valuation": extract_valuation_chart_data(quote, valuation_percentile),
        "fund_flow": extract_fund_flow_chart_data(fund_flow, df),
    }


# ============================================================
# 模块自测
# ============================================================

if __name__ == "__main__":
    import sys
    sys.path.insert(0, "..")

    print("=" * 60)
    print("图表数据提取测试")
    print("=" * 60)

    # 模拟 K 线数据
    dates = pd.date_range("2024-01-01", periods=120, freq="B")
    np.random.seed(42)
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

    # 提取 K 线数据
    kline = extract_kline_chart_data(df)
    print(f"\nK 线数据: {len(kline['dates'])} 个交易日")
    print(f"  日期范围: {kline['dates'][0]} ~ {kline['dates'][-1]}")
    print(f"  最新价: {kline['latest_price']:.2f}")
    print(f"  JSON 大小: {len(json.dumps(kline, default=_serialize))} 字符")

    # 提取估值数据
    val = extract_valuation_chart_data(
        {"f9": 25.5, "f23": 3.2, "f92": 1.5},
        {"pe_percentile": "45%", "pe_zone": "合理", "pb_percentile": "30%", "pb_zone": "偏低"},
    )
    print(f"\n估值数据: PE={val['pe_current']} ({val['pe_zone']}), PB={val['pb_current']} ({val['pb_zone']})")
    print(f"  PE 分位数: {val['pe_percentile']}%")

    # 提取资金流数据
    ff = extract_fund_flow_chart_data(
        {"今日": {"f62": 50000000}, "5日": {"f62": 120000000}},
        df,
    )
    print(f"\n资金流数据: 今日={ff['main_today']:.0f}万, 5日={ff['main_5d']:.0f}万")

    print("\n" + "=" * 60)
    print("测试完成")
