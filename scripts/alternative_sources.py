#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
备选数据源模块 — 分散 API 请求到多个免费数据源，避免单一来源封锁

当东方财富 API 被封时，自动切换到：
- 腾讯财经 (qt.gtimg.cn / web.ifzq.gtimg.cn) — 实时行情 + K线（含 PE/PB/市值）
- 新浪财经 (hq.sinajs.cn / money.finance.sina.com.cn) — 仅价格/成交量（降级备选）

设计原则：
- 每个函数返回与东方财富 API 兼容的格式
- HTTP 直连，无额外依赖
- 静默降级：失败返回 None，由调用方决定是否回退到东方财富
"""

import re
import json
import gzip
import http.client
import random
import pandas as pd
import numpy as np


# ============================================================
# 本地工具函数（避免循环导入）
# ============================================================

def _local_safe_num(val, default=0.0):
    """安全数值转换（本地版）"""
    if val is None or val == "-" or val == "":
        return default
    if isinstance(val, str) and val.strip() in ("N/A", "--", "nan", "NaN", "NA", "null"):
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _http_fetch(host, path, headers=None, timeout=10, encoding='utf-8'):
    """简易 HTTP GET（不依赖 utils.py），用于备选源"""
    if headers is None:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
        }
    ua_pool = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    ]
    headers["User-Agent"] = random.choice(ua_pool)

    try:
        conn = http.client.HTTPSConnection(host, timeout=timeout)
        conn.request("GET", path, headers=headers)
        resp = conn.getresponse()
        data = resp.read()

        if resp.getheader('Content-Encoding') == 'gzip' or data[:2] == b'\x1f\x8b':
            data = gzip.decompress(data)

        text = None
        for enc in [encoding, 'gbk', 'gb2312', 'utf-8']:
            try:
                text = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            text = data.decode('latin-1')

        conn.close()
        return text
    except Exception:
        return None


# ============================================================
# 市场类型识别（本地版，避免循环导入）
# ============================================================

def _get_market_prefix(code):
    """根据股票代码返回市场前缀"""
    if code.startswith('6'):
        return "SH"
    elif code.startswith(('0', '3', '2')):
        return "SZ"
    elif code.startswith(('8', '4')):
        return "BJ"
    return "SH"


# ============================================================
# 腾讯财经 — 实时行情（首选备选源，数据最完整）
# ============================================================

# 腾讯实时行情字段索引（v_格式，~ 分隔，参考 https://qt.gtimg.cn/）
_TENCENT_FIELDS = {
    "name": 1, "code": 2, "current": 3, "prev_close": 4,
    "open": 5, "volume": 6, "outer": 7, "inner": 8,
    "change": 31, "pct": 32, "high": 33, "low": 34,
    "volume2": 36, "amount": 37, "turnover": 38,
    "pe": 39, "amplitude": 43,
    "total_mktcap": 44, "circ_mktcap": 45, "pb": 46,
    "high52": 47, "low52": 48,
}


def fetch_quote_tencent(code):
    """
    从腾讯财经获取实时行情，返回东方财富兼容格式。

    腾讯接口提供 PE/PB/总市值/流通市值/换手率，数据完整度很高。

    Args:
        code: 股票代码 (如 '600519')

    Returns:
        dict: 东方财富兼容格式，含 _source='腾讯财经' 标记
        None: 请求失败
    """
    market = _get_market_prefix(code)
    prefix_map = {"SH": "sh", "SZ": "sz", "BJ": "bj"}
    prefix = prefix_map.get(market, "sh")
    symbol = f"{prefix}{code}"

    raw = _http_fetch("qt.gtimg.cn", f"/q={symbol}", encoding='gbk')
    if not raw:
        return None

    match = re.search(r'v_\w+="(.+)"', raw)
    if not match:
        return None

    parts = match.group(1).split("~")
    if len(parts) < 48:
        return None

    def field(key):
        idx = _TENCENT_FIELDS.get(key, -1)
        return parts[idx] if 0 <= idx < len(parts) else ""

    name = field("name")
    current = _local_safe_num(field("current"))
    prev_close = _local_safe_num(field("prev_close"))
    open_price = _local_safe_num(field("open"))
    high = _local_safe_num(field("high"))
    low = _local_safe_num(field("low"))
    volume = _local_safe_num(field("volume"))        # 手
    amount = _local_safe_num(field("amount")) * 1e4   # 万→元
    pct = _local_safe_num(field("pct"))
    pe = _local_safe_num(field("pe"))
    pb = _local_safe_num(field("pb"))
    turnover = _local_safe_num(field("turnover"))
    amplitude = _local_safe_num(field("amplitude"))
    total_mktcap = _local_safe_num(field("total_mktcap")) * 1e8   # 亿→元
    circ_mktcap = _local_safe_num(field("circ_mktcap")) * 1e8

    return {
        "f14": name,           # 名称
        "f2": current,         # 最新价
        "f3": pct,             # 涨跌幅%
        "f4": current - prev_close if prev_close > 0 else 0,
        "f5": volume * 100,    # 手→股
        "f6": amount,          # 成交额(元)
        "f8": turnover,        # 换手率%
        "f9": pe, "f23": pb,
        "f15": high, "f16": low,
        "f17": open_price, "f18": prev_close,
        "f20": total_mktcap, "f21": circ_mktcap,
        "f43": amplitude,
        "f37": 0, "f49": 0, "f40": 0,   # ROE/毛利率/营收(腾讯不提供)
        "f41": 0, "f34": 0, "f115": 0,  # 净利润同比/负债率/每股收益
        "market": market,
        "_source": "腾讯财经",
    }


# ============================================================
# 新浪财经 — 实时行情（降级备选，仅价格/成交量）
# ============================================================

def fetch_quote_sina(code):
    """
    从新浪财经获取实时行情，返回东方财富兼容格式。

    注意：新浪仅提供价格/成交量，不提供 PE/PB/市值。
    仅在腾讯和东方财富均不可用时作为最后备选。

    Args:
        code: 股票代码 (如 '600519')

    Returns:
        dict: 东方财富兼容格式（PE/PB/市值为 0），含 _source='新浪财经' 标记
        None: 请求失败
    """
    market = _get_market_prefix(code)
    prefix_map = {"SH": "sh", "SZ": "sz", "BJ": "bj"}
    prefix = prefix_map.get(market, "sh")
    symbol = f"{prefix}{code}"

    raw = _http_fetch("hq.sinajs.cn", f"/list={symbol}",
                      headers={"Referer": "https://finance.sina.com.cn"},
                      encoding='gbk')
    if not raw:
        return None

    match = re.search(r'"([^"]*)"', raw)
    if not match:
        return None

    parts = match.group(1).split(",")
    if len(parts) < 33:
        return None

    name = parts[0]
    open_price = _local_safe_num(parts[1])
    prev_close = _local_safe_num(parts[2])
    current = _local_safe_num(parts[3])
    high = _local_safe_num(parts[4])
    low = _local_safe_num(parts[5])
    volume = _local_safe_num(parts[8])
    amount = _local_safe_num(parts[9])

    change = current - prev_close if prev_close > 0 else 0
    pct = (change / prev_close * 100) if prev_close > 0 else 0

    return {
        "f14": name, "f2": current, "f3": pct, "f4": change,
        "f5": volume, "f6": amount,
        "f15": high, "f16": low,
        "f17": open_price, "f18": prev_close,
        "f8": 0, "f9": 0, "f23": 0, "f20": 0, "f21": 0,
        "f37": 0, "f49": 0, "f40": 0, "f41": 0, "f34": 0,
        "f115": 0, "f43": 0,
        "market": market,
        "_source": "新浪财经",
    }


# ============================================================
# 腾讯财经 — K线数据（前复权日线）
# ============================================================

def fetch_kline_tencent(code, days=500):
    """
    从腾讯财经获取前复权日线 K 线数据。

    Args:
        code: 股票代码
        days: 回溯天数

    Returns:
        pd.DataFrame: 列 ['日期','开盘','收盘','最高','最低','成交量','成交额','涨跌幅']
        None: 请求失败
    """
    market = _get_market_prefix(code)
    prefix_map = {"SH": "sh", "SZ": "sz", "BJ": "bj"}
    prefix = prefix_map.get(market, "sh")
    symbol = f"{prefix}{code}"

    raw = _http_fetch("web.ifzq.gtimg.cn",
                      f"/appstock/app/fqkline/get?param={symbol},day,,,{days},qfq")
    if not raw:
        return None

    try:
        j = json.loads(raw)
    except json.JSONDecodeError:
        return None

    kline_data = j.get("data", {}).get(symbol, {})
    qfqday = kline_data.get("qfqday", []) or kline_data.get("day", [])

    if not qfqday:
        return None

    rows = []
    for line in qfqday:
        if len(line) < 6:
            continue
        # 腾讯格式: [日期, 开盘, 收盘, 最高, 最低, 成交量(手)]
        rows.append({
            "日期": line[0],
            "开盘": _local_safe_num(line[1]),
            "收盘": _local_safe_num(line[2]),
            "最高": _local_safe_num(line[3]),
            "最低": _local_safe_num(line[4]),
            "成交量": int(_local_safe_num(line[5]) * 100),  # 手→股
            "成交额": 0,
            "涨跌幅": 0.0,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return None

    if len(df) > 1:
        prev = df["收盘"].shift(1)
        df["涨跌幅"] = ((df["收盘"] - prev) / prev * 100).fillna(0).round(2)

    df["_source"] = "腾讯财经"
    return df


# ============================================================
# 新浪财经 — K线数据（日线）
# ============================================================

def fetch_kline_sina(code, days=500):
    """
    从新浪财经获取日线 K 线数据。

    Args:
        code: 股票代码
        days: 回溯天数

    Returns:
        pd.DataFrame: 列 ['日期','开盘','收盘','最高','最低','成交量','成交额','涨跌幅']
        None: 请求失败
    """
    market = _get_market_prefix(code)
    prefix_map = {"SH": "sh", "SZ": "sz", "BJ": "bj"}
    prefix = prefix_map.get(market, "sh")
    symbol = f"{prefix}{code}"

    raw = _http_fetch("money.finance.sina.com.cn",
                      f"/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
                      f"?symbol={symbol}&scale=240&ma=no&datalen={days}",
                      headers={"Referer": "https://finance.sina.com.cn"},
                      encoding='utf-8')
    if not raw:
        return None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None

    if not data or not isinstance(data, list):
        return None

    rows = []
    for item in data:
        rows.append({
            "日期": item.get("day", ""),
            "开盘": _local_safe_num(item.get("open", 0)),
            "收盘": _local_safe_num(item.get("close", 0)),
            "最高": _local_safe_num(item.get("high", 0)),
            "最低": _local_safe_num(item.get("low", 0)),
            "成交量": int(_local_safe_num(item.get("volume", 0))),
            "成交额": 0,
            "涨跌幅": 0.0,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return None

    if len(df) > 1:
        prev = df["收盘"].shift(1)
        df["涨跌幅"] = ((df["收盘"] - prev) / prev * 100).fillna(0).round(2)

    df["_source"] = "新浪财经"
    return df


# ============================================================
# 多源统一接口
# ============================================================

def get_quote_alternatives(code):
    """
    按优先级依次尝试获取实时行情：腾讯 > 新浪。
    返回 (quote_dict, source_name)，均失败返回 (None, None)
    """
    result = fetch_quote_tencent(code)
    if result:
        return result, "腾讯财经"

    result = fetch_quote_sina(code)
    if result:
        return result, "新浪财经"

    return None, None


def get_kline_alternatives(code, days=500):
    """
    按优先级依次尝试获取 K 线数据：腾讯 > 新浪。
    返回 (DataFrame, source_name)，均失败返回 (None, None)
    """
    df = fetch_kline_tencent(code, days=days)
    if df is not None:
        return df, "腾讯财经"

    df = fetch_kline_sina(code, days=days)
    if df is not None:
        return df, "新浪财经"

    return None, None


# ============================================================
# 数据源健康检查
# ============================================================

def check_source_health():
    """快速检查各备选数据源是否可用。返回 {source_name: bool}"""
    results = {}

    raw = _http_fetch("qt.gtimg.cn", "/q=sh600519", timeout=5)
    results["腾讯实时行情"] = raw is not None and "贵州茅台" in raw

    raw = _http_fetch("hq.sinajs.cn", "/list=sh600519",
                      headers={"Referer": "https://finance.sina.com.cn"},
                      timeout=5, encoding='gbk')
    results["新浪实时行情"] = raw is not None and "贵州茅台" in raw

    raw = _http_fetch("web.ifzq.gtimg.cn",
                      "/appstock/app/fqkline/get?param=sh600519,day,,,5,qfq", timeout=5)
    results["腾讯K线"] = raw is not None and "qfqday" in raw

    raw = _http_fetch("money.finance.sina.com.cn",
                      "/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
                      "?symbol=sh600519&scale=240&ma=no&datalen=5",
                      headers={"Referer": "https://finance.sina.com.cn"}, timeout=5)
    results["新浪K线"] = raw is not None and raw.startswith("[")

    return results


# ============================================================
# 单元测试
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("备选数据源测试")
    print("=" * 60)

    print("\n--- 数据源健康检查 ---")
    health = check_source_health()
    for name, ok in health.items():
        print(f"  {'[OK]' if ok else '[FAIL]'} {name}")

    print("\n--- 腾讯实时行情 (600519 贵州茅台) ---")
    q = fetch_quote_tencent("600519")
    if q:
        print(f"  名称: {q['f14']}, 最新价: {q['f2']}, PE: {q['f9']:.1f}, PB: {q['f23']:.2f}")
        print(f"  总市值: {q['f20']/1e8:.0f}亿, 来源: {q.get('_source','-')}")
    else:
        print("  获取失败")

    print("\n--- 腾讯 K 线 (600519 近5日) ---")
    kline = fetch_kline_tencent("600519", days=5)
    if kline is not None and not kline.empty:
        print(kline.tail().to_string())
    else:
        print("  获取失败")

    print("\n--- 新浪实时行情 (601166 兴业银行) ---")
    q = fetch_quote_sina("601166")
    if q:
        print(f"  名称: {q['f14']}, 最新价: {q['f2']}, 来源: {q.get('_source','-')}")
    else:
        print("  获取失败")

    print("\n--- 统一接口 get_quote_alternatives (000001 平安银行) ---")
    alt, src = get_quote_alternatives("000001")
    if alt:
        print(f"  名称: {alt['f14']}, 最新价: {alt['f2']}, 来源: {src}")
    else:
        print("  全部失败")

    print("\n" + "=" * 60)
    print("测试完成")
