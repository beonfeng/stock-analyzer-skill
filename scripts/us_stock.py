#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
美股数据模块 — 通过 yfinance 获取美股行情

提供与东方财富 API 相同接口的数据获取函数，
使下游的 calculate_indicators() 等函数无需修改即可兼容美股。
"""

import re
import datetime

try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False

import pandas as pd
import numpy as np

from scripts.market_utils import is_us_stock


def check_yfinance():
    """检查 yfinance 是否已安装"""
    if not HAS_YFINANCE:
        raise ImportError(
            "yfinance 未安装。请运行: pip install yfinance\n"
            "安装后即可分析美股（如 AAPL、TSLA、NVDA）。"
        )


def fetch_us_kline(ticker: str, days: int = 500) -> pd.DataFrame:
    """
    获取美股 K 线历史数据。

    返回与 fetch_kline() 相同列名的 DataFrame：
    日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额, 振幅, 涨跌幅, 涨跌额, 换手率

    Args:
        ticker: 美股 ticker（如 AAPL）
        days: 获取天数

    Returns:
        pd.DataFrame
    """
    check_yfinance()

    stock = yf.Ticker(ticker)
    # yfinance 的 period 参数：1y 约 252 个交易日，足够 500 天
    period = "2y" if days > 252 else "1y"
    df = stock.history(period=period, auto_adjust=True)

    if df.empty:
        raise ValueError(f"无法获取 {ticker} 的 K 线数据，请检查 ticker 是否正确")

    # 取最近 days 条
    df = df.tail(days).copy()

    # 重命名列以匹配现有格式
    result = pd.DataFrame()
    result["日期"] = df.index.strftime("%Y-%m-%d")
    result["开盘"] = df["Open"].values
    result["收盘"] = df["Close"].values
    result["最高"] = df["High"].values
    result["最低"] = df["Low"].values
    result["成交量"] = df["Volume"].values
    result["成交额"] = (df["Close"] * df["Volume"]).values  # 近似成交额
    result["振幅"] = ((df["High"] - df["Low"]) / df["Close"].shift(1) * 100).values
    result["涨跌幅"] = (df["Close"].pct_change() * 100).values
    result["涨跌额"] = (df["Close"].diff()).values
    result["换手率"] = 0.0  # yfinance 无换手率数据

    result = result.reset_index(drop=True)
    # 填充 NaN（第一行涨跌幅等）
    result = result.fillna(0)

    return result


def fetch_us_realtime_quote(ticker: str) -> dict:
    """
    获取美股实时行情。

    返回与 fetch_realtime_quote() 兼容的 dict，key 使用 f 编号。

    Args:
        ticker: 美股 ticker

    Returns:
        dict
    """
    check_yfinance()

    stock = yf.Ticker(ticker)
    info = stock.info

    if not info or "regularMarketPrice" not in info and "currentPrice" not in info:
        # 尝试用 fast_info 获取
        try:
            fast = stock.fast_info
            price = fast.last_price
            market_cap = fast.market_cap
        except Exception:
            raise ValueError(f"无法获取 {ticker} 的实时行情")
    else:
        price = info.get("regularMarketPrice") if info.get("regularMarketPrice") is not None else info.get("currentPrice", 0)
        market_cap = info.get("marketCap", 0)

    # 映射为东方财富字段格式
    pe = info.get("trailingPE") if info.get("trailingPE") is not None else info.get("forwardPE", 0)
    pb = info.get("priceToBook", 0)
    roe = info.get("returnOnEquity", 0)
    if roe is not None and roe != 0:
        roe = roe * 100  # 小数转百分比
    gross_margin = info.get("grossMargins", 0)
    if gross_margin is not None and gross_margin != 0:
        gross_margin = gross_margin * 100
    revenue = info.get("totalRevenue", 0)
    profit_growth = info.get("earningsGrowth", 0)
    if profit_growth is not None and profit_growth != 0:
        profit_growth = profit_growth * 100
    debt_ratio = info.get("debtToEquity", 0)

    return {
        "f14": info.get("shortName", ticker),  # 股票名称
        "f2": price,  # 最新价
        "f3": info.get("regularMarketChangePercent", 0),  # 涨跌幅
        "f9": pe,  # 市盈率
        "f23": pb,  # 市净率
        "f20": market_cap,  # 总市值
        "f21": market_cap,  # 流通市值（近似）
        "f37": roe,  # ROE
        "f49": gross_margin,  # 毛利率
        "f40": revenue,  # 营收
        "f41": profit_growth,  # 净利润同比
        "f34": debt_ratio,  # 资产负债率
        "market": "us",
        "_currency": info.get("currency", "USD"),
        "_exchange": info.get("exchange", ""),
        "_sector": info.get("sector", ""),
        "_industry": info.get("industry", ""),
    }


def fetch_us_financials(ticker: str) -> dict:
    """
    获取美股财务报表数据。

    Args:
        ticker: 美股 ticker

    Returns:
        dict，包含 income_stmt、balance_sheet 等
    """
    check_yfinance()

    stock = yf.Ticker(ticker)

    result = {
        "income_stmt": None,
        "balance_sheet": None,
        "cashflow": None,
    }

    try:
        income = stock.income_stmt
        if income is not None and not income.empty:
            result["income_stmt"] = income
    except Exception:
        pass

    try:
        bs = stock.balance_sheet
        if bs is not None and not bs.empty:
            result["balance_sheet"] = bs
    except Exception:
        pass

    try:
        cf = stock.cashflow
        if cf is not None and not cf.empty:
            result["cashflow"] = cf
    except Exception:
        pass

    return result


def get_us_stock_name(ticker: str) -> str:
    """
    获取美股公司名称。

    Args:
        ticker: 美股 ticker

    Returns:
        公司简称
    """
    check_yfinance()

    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        return info.get("shortName", info.get("longName", ticker))
    except Exception:
        return ticker


def calculate_us_financial_health(quote: dict, financials: dict) -> dict:
    """
    基于美股数据计算财务健康指标。

    Args:
        quote: fetch_us_realtime_quote 返回的 dict
        financials: fetch_us_financials 返回的 dict

    Returns:
        dict，与 calculate_financial_health 兼容的格式
    """
    health = {}

    pe = quote.get("f9", 0)
    pb = quote.get("f23", 0)
    roe = quote.get("f37", 0)
    debt_ratio = quote.get("f34", 0)
    profit_growth = quote.get("f41", 0)

    health["市盈率"] = pe if pe else 0
    health["市净率"] = pb if pb else 0
    health["ROE"] = roe if roe else 0
    health["资产负债率"] = debt_ratio if debt_ratio else 0
    health["净利润同比"] = profit_growth if profit_growth else 0

    # 排雷逻辑
    red_flags = []
    warnings = []

    if pe and pe > 100:
        warnings.append(f"市盈率偏高（{pe:.1f}）")
    if pe and pe < 0:
        red_flags.append("市盈率为负（亏损）")

    if debt_ratio and debt_ratio > 200:
        warnings.append(f"资产负债率偏高（{debt_ratio:.1f}%）")

    if roe and roe < 0:
        red_flags.append("ROE 为负")

    health["排雷红灯"] = red_flags
    health["排雷预警"] = warnings

    return health
