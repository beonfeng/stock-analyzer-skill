#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票综合分析工具 — 核心分析逻辑
"""

import datetime
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, Any

import pandas as pd
import numpy as np

from .market_utils import get_market_info, convert_price, is_us_stock, get_secid
from .utils import (_http_get, _http_get_safe, safe_num, safe_display,
    is_trading_day, print_request_stats, reset_request_stats,
    init_request_queue, tick_request_queue,
    memo_get, memo_set, get_session_request_stats)
from .alternative_sources import (fetch_quote_tencent, fetch_quote_sina,
    fetch_kline_tencent, fetch_kline_sina, fetch_fund_flow_tencent)
try:
    from .akshare_sources import (
        fetch_kline_akshare, fetch_quote_akshare,
        fetch_financial_report_akshare, fetch_company_profile_akshare,
        fetch_news_akshare, HAS_AKSHARE)
except ImportError:
    HAS_AKSHARE = False
    fetch_kline_akshare = None
    fetch_quote_akshare = None
    fetch_financial_report_akshare = None
    fetch_company_profile_akshare = None
    fetch_news_akshare = None
from .technical_indicators import calculate_extended_indicators
from .valuation_analysis import analyze_valuation_percentile
from .industry_analysis import analyze_industry_comparison
from .sentiment import analyze_sentiment, summarize_sentiment
from .risk_control import (
    calc_dynamic_stop_loss, calc_target_price,
    calc_support_resistance, calc_position_size,
    check_risk_rules, detect_board_type
)
from .comparison import compare_two_stocks, get_sector_stocks, analyze_sector


# ============================================================
# 模块级状态
# ============================================================

_last_analysis_time = 0  # 上次分析完成时间戳，用于连续调用冷却保护
_last_chart_data = {}   # 最近一次分析的图表数据（供 HTML 导出使用）


def get_last_chart_data():
    """返回最近一次分析的图表数据字典"""
    return _last_chart_data


# ============================================================
# 东方财富 API 封装
# ============================================================

def fetch_kline(code, days=500):
    """获取 K 线历史数据（东方财富 → 腾讯 → 新浪 多源回退）"""
    market_code, market_id, _ = get_market_info(code)

    # 方法1：东方财富 push2his（主数据源）
    try:
        end = datetime.date.today().strftime("%Y%m%d")
        start = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%Y%m%d")
        params = {
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f116",
            "ut": "7eea3edcaed734bea9cbfc24409ed989",
            "klt": "101", "fqt": "1",
            "secid": get_secid(code, market_id),
            "beg": start, "end": end,
        }
        # 港股 API 不稳定，需要更多重试
        if market_code == 'HK':
            j = _http_get("push2his.eastmoney.com", "/api/qt/stock/kline/get", params, timeout=20, retries=12)
        else:
            j = _http_get("push2his.eastmoney.com", "/api/qt/stock/kline/get", params)
        klines = j.get("data", {}).get("klines", [])
        if klines:
            rows = []
            for line in klines:
                parts = line.split(",")
                if len(parts) >= 11:
                    rows.append({
                        "日期": parts[0],
                        "开盘": safe_num(parts[1], 0.0),
                        "收盘": safe_num(parts[2], 0.0),
                        "最高": safe_num(parts[3], 0.0),
                        "最低": safe_num(parts[4], 0.0),
                        "成交量": safe_num(parts[5], 0.0),
                        "成交额": safe_num(parts[6], 0.0),
                        "振幅": safe_num(parts[7], 0.0),
                        "涨跌幅": safe_num(parts[8], 0.0),
                        "涨跌额": safe_num(parts[9], 0.0),
                        "换手率": safe_num(parts[10], 0.0),
                    })
            return pd.DataFrame(rows)
    except Exception:
        pass

    # 方法2（备选源）：AKShare K 线
    if HAS_AKSHARE and fetch_kline_akshare:
        try:
            df = fetch_kline_akshare(code, days=days)
            if df is not None and not df.empty:
                print(f"  [提示] K线数据来自 AKShare（东方财富 push2his 不可用）")
                return df
        except Exception:
            pass

    # 方法3（备选源）：腾讯财经 K 线
    try:
        df = fetch_kline_tencent(code, days=days)
        if df is not None and not df.empty:
            print(f"  [提示] K线数据来自腾讯财经（东方财富/AKShare 不可用）")
            return df
    except Exception:
        pass

    # 方法4（备选源）：新浪财经 K 线
    try:
        df = fetch_kline_sina(code, days=days)
        if df is not None and not df.empty:
            print(f"  [提示] K线数据来自新浪财经（所有主数据源不可用）")
            return df
    except Exception:
        pass

    return pd.DataFrame()


def fetch_realtime_quote(code):
    """获取实时行情 + 财务指标"""
    market_code, market_id, _ = get_market_info(code)

    # 方法1（优先）：直接查询单只股票 — O(1) 请求，适用于所有市场
    params2 = {
        "secid": get_secid(code, market_id),
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        "fields": "f43,f44,f45,f46,f47,f48,f50,f51,f52,f55,f57,f58,f60,f71,f92,f105,f115,f116,f117,f162,f167,f168,f169,f170,f171,f173,f177,f183,f184,f185,f186,f187,f188,f189,f190,f191,f192,f193",
        "invt": "2",
    }
    j2 = _http_get_safe("push2.eastmoney.com", "/api/qt/stock/get", params2)
    if j2 and j2.get("data"):
        data = j2["data"]

        def convert_field(field):
            """使用 convert_price 转换价格字段"""
            return convert_price(data.get(field), market_code)

        def direct(field):
            """获取直接可用的字段"""
            return safe_num(data.get(field, 0))

        # PE：f162 API 返回基点值（如 1534 = 15.34），需除以 100
        # 美股 f162 可能为 '-'，用 f92 作为备选
        pe_raw = data.get("f162", "-")
        if pe_raw == "-" or pe_raw is None:
            pe = direct("f92")  # f92 直接是 PE 值
        else:
            pe = direct("f162") / 100
            # PE 正常范围通常 ≥ 1（除去亏损/微利），若除以100后异常小（<0.5），
            # 说明 API 可能已修改格式不再返回基点值，此时回退到 f92 直接值
            if abs(pe) < 0.5 and pe != 0:
                pe = direct("f92")
                print(f"  [警告] PE 值异常小 ({pe:.4f})，f162 可能非基点格式，已回退到 f92")

        # PB：f167 API 返回基点值，需除以 100
        pb_raw = data.get("f167", "-")
        if pb_raw != "-" and pb_raw is not None:
            pb = direct("f167") / 100
            if abs(pb) < 0.01 and pb != 0:
                print(f"  [警告] PB 值异常小 ({pb})，f167 原始值={pb_raw}，可能不需要除以100")
        else:
            pb = 0

        # 每股收益：f115 常为 "-"，从 PE 反推更可靠
        eps_raw = data.get("f115", "-")
        if eps_raw == "-" or eps_raw is None:
            price_val = convert_field("f43")
            eps = (price_val / pe) if (price_val and pe and pe > 0) else 0
        else:
            eps = direct("f115")

        return {
            "f14": data.get("f58", ""),  # 名称
            "f2": convert_field("f43"),  # 最新价
            "f3": direct("f170") / 100,   # 涨跌幅（API 返回基点值，如 314 = 3.14%，需除以 100）
            # 注意：f170 除以 100 后若绝对值 < 0.01%，属于正常微幅波动，无需警告
            "f9": pe,   # PE
            "f23": pb,  # PB
            "f20": direct("f116"),  # 总市值（元）
            "f21": direct("f117"),  # 流通市值（元）
            "f37": direct("f173"),  # ROE（已经是百分比）
            "f49": direct("f186"),  # 毛利率（已经是百分比）
            "f40": direct("f183"),  # 营收（元）
            "f41": direct("f185"),  # 净利润同比（已经是百分比）
            "f34": direct("f188"),  # 资产负债率（已经是百分比）
            "f115": eps,  # 每股收益
            "market": market_code,  # 市场类型
        }
    # 方法2（备选）：从列表中查找 — O(n) 遍历，仅 A 股可用
    if market_code in ('SH', 'SZ'):
        params = {
            "pn": "1", "pz": "5000", "po": "1", "np": "1",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": "2", "invt": "2", "fid": "f12",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
            "fields": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,f21,f23,f24,f25,f22,f11,f62,f128,f136,f115,f152",
        }
        j = _http_get_safe("push2.eastmoney.com", "/api/qt/clist/get", params)
        items = j.get("data", {}).get("diff", []) if j else []
        # 构建字典索引 O(m+n) 替代 O(m×n) 遍历
        item_map = {str(item.get("f12", "")): item for item in items if item.get("f12")}
        if code in item_map:
            item_map[code]["market"] = market_code
            return item_map[code]

    # 方法3（备选源）：AKShare 实时行情
    if HAS_AKSHARE and fetch_quote_akshare:
        try:
            alt_quote = fetch_quote_akshare(code)
            if alt_quote and alt_quote.get("f2", 0) > 0:
                print(f"  [提示] 实时行情来自 AKShare（东方财富不可用）")
                return alt_quote
        except Exception:
            pass

    # 方法4（备选源）：腾讯财经 → 新浪财经
    # 东方财富 push2 不可用时自动切换，分散请求压力
    try:
        alt_quote = fetch_quote_tencent(code)
        if alt_quote and alt_quote.get("f2", 0) > 0:
            print(f"  [提示] 实时行情来自 {alt_quote.get('_source', '腾讯财经')}（东方财富不可用）")
            return alt_quote
    except Exception:
        pass

    try:
        alt_quote = fetch_quote_sina(code)
        if alt_quote and alt_quote.get("f2", 0) > 0:
            print(f"  [提示] 实时行情来自新浪财经（所有主数据源不可用）")
            return alt_quote
    except Exception:
        pass

    return {"market": market_code}


def fetch_fund_flow(code):
    """获取个股资金流向（fflow日K → push2 → 腾讯外盘/内盘 多源回退）

    方法1: push2his fflow/daykline — 完整超大单/大单/中单/小单分层数据
    方法2: push2 stock/get — 备选，仅主力汇总无分层
    方法3: 腾讯外盘/内盘 — 最终兜底估算
    返回格式: {
        "今日": {f62, f184, f66, f69, f72, f75, f78, f81, f84, f87},
        "3日": {f62}, "5日": {f62}, "10日": {f62}
    }
    """
    _, market_id, _ = get_market_info(code)
    secid = get_secid(code, market_id)

    # ── 方法1：fflow/daykline（完整分层数据，10日量级）──
    try:
        params = {
            "secid": secid,
            "ut": "fa5fd1943c7b386f172d6893dbfba10b",
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63",
            "klt": "101",
            "fqt": "1",
            "end": "20500101",
            "lmt": "10",
        }
        j = _http_get_safe("push2his.eastmoney.com", "/api/qt/stock/fflow/daykline/get", params)
        if j and j.get("data") and j["data"].get("klines"):
            klines = j["data"]["klines"]
            if klines:
                # 解析最新一天为「今日」详细数据
                # fflow 字段顺序：日期, 主力, 超大单, 大单, 中单, 小单,
                #                   主力占比, 超大占比, 大单占比, 中单占比, 小单占比, 收盘价, 涨跌幅
                latest = klines[-1].split(",")
                today_data = {
                    "f62": float(latest[1]),   # 主力净流入
                    "f184": float(latest[6]),  # 主力净流入占比
                    "f66": float(latest[2]),   # 超大单净流入
                    "f69": float(latest[7]),   # 超大单占比
                    "f72": float(latest[3]),   # 大单净流入
                    "f75": float(latest[8]),   # 大单占比
                    "f78": float(latest[4]),   # 中单净流入
                    "f81": float(latest[9]),   # 中单占比
                    "f84": float(latest[5]),   # 小单净流入
                    "f87": float(latest[10]),  # 小单占比
                }

                # 从日K计算 3日/5日/10日 累计主力净流入
                def _sum_period(days):
                    n = min(days, len(klines))
                    return sum(float(l.split(",")[1]) for l in klines[-n:])

                return {
                    "今日": today_data,
                    "3日": {"f62": _sum_period(3)},
                    "5日": {"f62": _sum_period(5)},
                    "10日": {"f62": _sum_period(10)},
                }
    except Exception:
        pass

    # ── 方法2：push2 stock/get（备选：仅主力汇总，无订单分层）──
    try:
        params = {
            "secid": secid,
            "ut": "7eea3edcaed734bea9cbfc24409ed989",
            "fields": "f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f267,f164,f174",
        }
        j = _http_get_safe("push2.eastmoney.com", "/api/qt/stock/get", params)
        if j and j.get("data"):
            data = j["data"]
            today_data = {
                "f62": data.get("f62", 0),
                "f184": data.get("f184", 0),
                "f66": data.get("f66", 0), "f69": data.get("f69", 0),
                "f72": data.get("f72", 0), "f75": data.get("f75", 0),
                "f78": data.get("f78", 0), "f81": data.get("f81", 0),
                "f84": data.get("f84", 0), "f87": data.get("f87", 0),
            }
            return {
                "今日": today_data,
                "3日": {"f62": data.get("f267", 0)},
                "5日": {"f62": data.get("f164", 0)},
                "10日": {"f62": data.get("f174", 0)},
            }
    except Exception:
        pass

    # ── 方法3：腾讯外盘/内盘估算（最终兜底）──
    try:
        tencent_flow = fetch_fund_flow_tencent(code)
        if tencent_flow:
            print(f"  [提示] 资金流向来自腾讯财经(外盘-内盘估算，已简化)")
            return tencent_flow
    except Exception:
        pass

    return {}


def fetch_north_flow():
    """获取北向资金数据（Memoization 跨分析缓存：市场级数据复用）

    使用 fflow/kline/get 端点获取沪股通/深股通指数走势，
    作为市场级北向资金情绪的参考指标。
    """
    cached = memo_get("north_flow")
    if cached is not None:
        return cached

    result = {}
    for symbol, secid in [("沪股通", "1.000016"), ("深股通", "0.399005")]:
        params = {
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63",
            "klt": "101", "lmt": "10",
            "ut": "fa5fd1943c7b386f172d6893dbfba10b",
            "secid": secid,
        }
        try:
            j = _http_get_safe("push2his.eastmoney.com", "/api/qt/stock/fflow/kline/get", params)
            klines = j.get("data", {}).get("klines", []) if j else []
            rows = []
            for line in klines:
                parts = line.split(",")
                if len(parts) >= 9:
                    rows.append({"日期": parts[0], "收盘": parts[2], "涨跌幅": parts[8]})
            result[symbol] = pd.DataFrame(rows)
        except Exception:
            pass  # 北向数据非核心功能，静默降级
    memo_set("north_flow", result)
    return result


# URL 参数白名单校验：仅允许字母数字和常见安全字符
_URL_PARAM_RE = __import__('re').compile(r'^[A-Za-z0-9_.@\-]+$')


def _safe_url_param(value):
    """校验 URL 参数仅含安全字符，防止路径穿越 / 注入"""
    if not isinstance(value, str) or not value:
        return False
    return bool(_URL_PARAM_RE.match(value))


def fetch_stock_news(code):
    """获取个股资讯（研报 + 公告，替代已下线的新闻 API）"""
    rows = []
    # 来源1：个股研报（reportapi 稳定可用）
    try:
        params = {
            "industryCode": "*", "pageSize": "15", "industry": "*",
            "rating": "*", "ratingChange": "*",
            "beginTime": (datetime.date.today() - datetime.timedelta(days=90)).strftime("%Y-%m-%d"),
            "endTime": datetime.date.today().strftime("%Y-%m-%d"),
            "pageNo": "1", "fields": "", "qType": "0",
            "orgCode": "", "code": code, "rcode": "",
            "p": "1", "pageNum": "1", "pageNumber": "1"
        }
        j = _http_get("reportapi.eastmoney.com", "/report/list", params)
        data = j.get("data", []) if isinstance(j, dict) else []
        if isinstance(data, list):
            for item in data[:10]:
                title = item.get("title", "") or item.get("infoCode", "")
                org = item.get("orgSName", "") or item.get("orgName", "")
                pub_date = (item.get("publishDate") or "")[:10]
                if title:
                    info_code = item.get("infoCode", "")
                    if info_code and _safe_url_param(str(info_code)):
                        url = f"https://data.eastmoney.com/report/zw/stock/{info_code}.html"
                    else:
                        url = ""
                    rows.append({
                        "新闻标题": f"[研报] {title}",
                        "发布时间": pub_date,
                        "文章来源": org,
                        "链接": url,
                    })
    except Exception as e:
        print(f"  [警告] 研报数据获取失败: {e}")

    # 来源2：公司公告（np-anotice-stock 稳定可用）
    try:
        market_code, _, _ = get_market_info(code)
        ann_type_map = {"SH": "SHA", "SZ": "SZA", "BJ": "BJA"}
        ann_type = ann_type_map.get(market_code, "SHA,SZA")
        params = {
            "sr": "-1", "page_size": "10", "page_index": "1",
            "ann_type": ann_type, "client_source": "web",
            "stock_list": code, "f_node": "0", "s_node": "0"
        }
        j = _http_get("np-anotice-stock.eastmoney.com", "/api/security/ann", params)
        data = j.get("data", {}).get("list", []) if isinstance(j, dict) else []
        for item in data[:10]:
            title = item.get("title", "") or item.get("noticeTitle", "")
            pub_date = (item.get("noticeDate") or "")[:10]
            if title:
                art_code = item.get("art_code", "")
                if art_code and _safe_url_param(str(art_code)):
                    url = f"https://np-anotice-stock.eastmoney.com/api/security/ann/detail?art_code={art_code}"
                else:
                    url = ""
                rows.append({
                    "新闻标题": f"[公告] {title}",
                    "发布时间": pub_date,
                    "文章来源": "巨潮资讯",
                    "链接": url,
                })
    except Exception as e:
        print(f"  [警告] 公告数据获取失败: {e}")

    if rows:
        print(f"  获取到 {len(rows)} 条资讯（研报+公告）")
    else:
        print(f"  [警告] 未获取到任何东方财富资讯数据")

    # 备选源：AKShare 个股新闻（当东方财富研报/公告均为空时）
    if not rows and HAS_AKSHARE and fetch_news_akshare:
        try:
            news_df = fetch_news_akshare(code)
            if news_df is not None and not news_df.empty:
                for _, item in news_df.iterrows():
                    rows.append({
                        "新闻标题": f"[资讯] {item.get('新闻标题', '')}",
                        "发布时间": str(item.get("发布时间", ""))[:10],
                        "文章来源": item.get("文章来源", "AKShare"),
                        "链接": item.get("链接", ""),
                    })
                print(f"  [提示] 资讯数据来自 AKShare（东方财富研报/公告不可用），共 {len(rows)} 条")
        except Exception as e:
            print(f"  [警告] AKShare 新闻获取失败: {e}")

    return pd.DataFrame(rows)


def fetch_industry_boards():
    """获取行业板块数据（Memoization 跨分析缓存：市场级数据复用）"""
    cached = memo_get("industry_boards")
    if cached is not None:
        return cached

    params = {
        "pn": "1", "pz": "50", "po": "1", "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2", "invt": "2", "fid": "f3",
        "fs": "m:90+t:2+f:!50",
        "fields": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,f21,f23,f24,f25,f22,f33,f11,f62,f128,f136,f104,f105,f115,f152",
    }
    j = _http_get_safe("push2.eastmoney.com", "/api/qt/clist/get", params)
    items = j.get("data", {}).get("diff", []) if j else []
    rows = []
    for item in items:
        rows.append({
            "板块": item.get("f14", ""),
            "涨跌幅": item.get("f3", 0),
            "总市值": item.get("f20", 0),
            "换手率": item.get("f8", 0),
            "上涨家数": item.get("f104", 0),
            "下跌家数": item.get("f105", 0),
        })
    result = pd.DataFrame(rows)
    memo_set("industry_boards", result)
    return result


def fetch_financial_report(code):
    """获取财务报表数据（现金流、资产负债表关键指标）"""
    if not code.isalnum():
        return []
    try:
        market_code, _, _ = get_market_info(code)
        # 港股财务报表接口不同，暂不支持
        if market_code == 'HK':
            return []
        # 获取现金流量表
        _market_suffix = {'SH': 'SH', 'SZ': 'SZ', 'BJ': 'BJ'}.get(market_code, 'SZ')
        params = {
            "type": "0", "sty": "APP_F10_FinanceSumFinance",
            "filter": f"(SECUCODE=\"{code}.{_market_suffix}\")",
            "p": "1", "ps": "5", "sr": "-1", "st": "REPORT_DATE",
            "source": "HSF10", "client": "PC",
        }
        j = _http_get_safe("datacenter.eastmoney.com", "/api/data/get", params, retries=5)
        if j and isinstance(j, dict) and j.get("result"):
            return j["result"].get("data", [])
    except Exception as e:
        print(f"  [警告] 东方财富财务报表获取失败: {e}")

    # 备选源：AKShare 财务报表（腾讯/新浪不覆盖此数据类）
    if HAS_AKSHARE and fetch_financial_report_akshare:
        try:
            fin_data = fetch_financial_report_akshare(code)
            if fin_data:
                print(f"  [提示] 财报数据来自 AKShare（东方财富 datacenter 不可用）")
                return fin_data
        except Exception as e:
            print(f"  [警告] AKShare 财务报表获取失败: {e}")

    return []


def fetch_company_profile(code):
    """
    获取公司概况：基本资料 + 主营业务构成。
    数据变化慢（季度更新），session 内跨分析 memo 复用。

    Args:
        code: 股票代码（如 '603195'）

    Returns:
        dict: {
            '基本信息': dict,   # 公司名称、行业、上市日期、员工数等
            '公司简介': str,     # 公司简介文字
            '经营范围': str,     # 经营范围文字
            '主营业务': list,    # [{'名称': str, '收入': float, '占比': float, '毛利率': float}, ...]
        }
    """
    # Session memo: 公司概况变化慢，同 session 内复用
    memo_key = f"company_profile_{code}"
    cached = memo_get(memo_key)
    if cached is not None:
        return cached

    result = {
        '基本信息': {},
        '公司简介': '',
        '经营范围': '',
        '主营业务': [],
        '股东结构': [],
    }

    if not code.isalnum():
        return result

    try:
        market_code, _, _ = get_market_info(code)
        # 港股接口不同，暂不支持
        if market_code == 'HK':
            return result
    except ValueError:
        return result

    _market_suffix = {'SH': 'SH', 'SZ': 'SZ', 'BJ': 'BJ'}.get(market_code, 'SZ')
    secucode = f"{code}.{_market_suffix}"

    # 1. 获取公司基本资料
    try:
        _code_prefix = {'SH': 'SH', 'SZ': 'SZ', 'BJ': 'BJ'}.get(market_code, 'SZ')
        params1 = {
            'code': f"{_code_prefix}{code}",
            'client_source': 'web',
        }
        j1 = _http_get_safe(
            'emweb.securities.eastmoney.com',
            '/PC_HSF10/CompanySurvey/CompanySurveyAjax',
            params1, retries=3
        )
        if j1 and isinstance(j1, dict):
            jbzl = j1.get('jbzl', {})
            fxxg = j1.get('fxxg', {})

            result['基本信息'] = {
                '公司名称': jbzl.get('gsmc', ''),
                '英文名称': jbzl.get('ywmc', ''),
                '所属行业': jbzl.get('sshy', ''),
                '证监会行业': jbzl.get('sszjhhy', ''),
                '法人代表': jbzl.get('frdb', ''),
                '董事长': jbzl.get('dsz', ''),
                '总经理': jbzl.get('zjl', ''),
                '注册资本': jbzl.get('zczb', ''),
                '员工人数': jbzl.get('gyrs', ''),
                '上市日期': fxxg.get('ssrq', ''),
                '成立日期': fxxg.get('clrq', ''),
            }
            result['公司简介'] = jbzl.get('gsjj', '').strip()
            result['经营范围'] = jbzl.get('jyfw', '').strip()
    except Exception as e:
        print(f"  [警告] 公司基本资料获取失败: {e}")

    # 2. 获取主营业务构成
    try:
        params2 = {
            'type': 'RPT_F10_FN_MAINOP',
            'sty': 'ALL',
            'filter': f'(SECUCODE="{secucode}")',
            'p': '1', 'ps': '50',
            'sr': '-1', 'st': 'REPORT_DATE',
            'source': 'HSF10', 'client': 'PC',
        }
        j2 = _http_get_safe('datacenter.eastmoney.com', '/api/data/get', params2, retries=3)
        if j2 and isinstance(j2, dict) and j2.get('result'):
            items = j2['result'].get('data', [])
            if items:
                # 按报告日期分组，取最新一期
                by_date = defaultdict(list)
                for item in items:
                    date = item.get('REPORT_DATE', '')[:10]
                    by_date[date].append(item)

                # API 返回 ISO 格式日期（如 "2024-03-31T00:00:00"），字符串比较等价于日期比较
                valid_dates = [k for k in by_date.keys() if k]
                if not valid_dates:
                    raise ValueError("无有效日期")
                latest_date = max(valid_dates)
                latest_items = by_date[latest_date]

                # 按产品分类（TYPE=2）为主维度，区域分类（TYPE=3）暂存
                product_items = [it for it in latest_items if it.get('MAINOP_TYPE') == '2']
                region_items = [it for it in latest_items if it.get('MAINOP_TYPE') == '3']

                # 若 TYPE=2 为空则回退到 TYPE=1（某些股票只有业务类型分类）
                if not product_items:
                    product_items = [it for it in latest_items if it.get('MAINOP_TYPE') == '1']

                # 产品维度去重：同 ITEM_NAME 仅保留 INCOME 最大的一条
                seen_names = set()
                deduped = []
                for it in sorted(product_items, key=lambda x: x.get('MAIN_BUSINESS_INCOME', 0), reverse=True):
                    name = it.get('ITEM_NAME', '')
                    if name in seen_names or not name:
                        continue
                    seen_names.add(name)
                    deduped.append(it)

                # 过滤特殊项目：内部抵消/其他(补充) 单独标记
                main_items = []
                special_items = []
                for it in deduped:
                    name = it.get('ITEM_NAME', '')
                    if '抵消' in name or '补充' in name:
                        special_items.append(it)
                    else:
                        main_items.append(it)

                # 以最终展示项目的收入总和为分母，确保百分比闭环
                total_income = sum(it.get('MAIN_BUSINESS_INCOME', 0) for it in main_items)

                # 保存财报报告期，供后续基本面章节标注数据时效
                result['财报报告期'] = latest_date

                for it in main_items:
                    name = it.get('ITEM_NAME', '')
                    income = it.get('MAIN_BUSINESS_INCOME', 0)
                    ratio = (income / total_income * 100) if total_income > 0 else 0
                    # GROSS_RPOFIT_RATIO 返回比率值（如 0.648 = 64.8%），需 ×100
                    gross_raw = it.get('GROSS_RPOFIT_RATIO', 0)
                    gross = (gross_raw or 0) * 100
                    result['主营业务'].append({
                        '名称': name,
                        '收入': income / 1e8,  # 转为亿元
                        '占比': ratio,
                        '毛利率': gross,
                        '报告期': latest_date,
                    })

                # 区域维度（单独存储，供后续使用）
                seen_regions = set()
                region_deduped = []
                for it in sorted(region_items, key=lambda x: x.get('MAIN_BUSINESS_INCOME', 0), reverse=True):
                    name = it.get('ITEM_NAME', '')
                    if name in seen_regions or not name:
                        continue
                    seen_regions.add(name)
                    region_deduped.append(it)
                result['区域收入'] = region_deduped
    except Exception as e:
        print(f"  [警告] 主营业务构成获取失败: {e}")

    # 3. 获取十大流通股东
    try:
        params3 = {
            'type': 'RPT_F10_EH_FREEHOLDERS',
            'sty': 'ALL',
            'filter': f'(SECUCODE="{secucode}")',
            'p': '1', 'ps': '30',
            'sr': '-1', 'st': 'END_DATE',
            'source': 'HSF10', 'client': 'PC',
        }
        j3 = _http_get_safe('datacenter.eastmoney.com', '/api/data/get', params3, retries=3)
        if j3 and isinstance(j3, dict) and j3.get('result'):
            items3 = j3['result'].get('data', [])
            if items3:
                by_date3 = defaultdict(list)
                for it in items3:
                    date = it.get('END_DATE', '')[:10]
                    by_date3[date].append(it)
                # API 返回 ISO 格式日期，字符串比较等价于日期比较
                valid_keys = [k for k in by_date3.keys() if k]
                if not valid_keys:
                    raise ValueError("无有效日期")
                latest3 = max(valid_keys)
                for it in sorted(by_date3[latest3], key=lambda x: x.get('HOLD_NUM', 0), reverse=True)[:10]:
                    result['股东结构'].append({
                        '名称': it.get('HOLDER_NAME', ''),
                        '持股数': it.get('HOLD_NUM', 0),
                        '占流通股比': it.get('FREE_HOLDNUM_RATIO', 0) or 0,
                        '股东性质': it.get('HOLDER_TYPE', ''),
                        '报告期': latest3,
                    })
    except Exception as e:
        print(f"  [警告] 十大流通股东获取失败: {e}")

    # 备选源：AKShare 公司概况（当东方财富返回数据不完整时）
    if (not result["基本信息"] or not result["基本信息"].get("公司名称")) \
            and HAS_AKSHARE and fetch_company_profile_akshare:
        try:
            ak_profile = fetch_company_profile_akshare(code)
            if ak_profile and ak_profile.get("基本信息"):
                print(f"  [提示] 公司概况来自 AKShare（东方财富 emweb/datacenter 不可用）")
                # 合并非空字段（AKShare 补充东方财富缺失的数据）
                for key in ["基本信息", "公司简介", "经营范围"]:
                    if not result[key] and ak_profile.get(key):
                        result[key] = ak_profile[key]
                if not result["主营业务"] and ak_profile.get("主营业务"):
                    result["主营业务"] = ak_profile["主营业务"]
                if not result["股东结构"] and ak_profile.get("股东结构"):
                    result["股东结构"] = ak_profile["股东结构"]
        except Exception as e:
            print(f"  [警告] AKShare 公司概况获取失败: {e}")

    memo_set(memo_key, result)
    return result


def fetch_tick_details(code):
    """获取逐笔成交明细（最近 200 条），用于大单异动检测。

    返回:
        dict: {
            'trades': [{'时间': str, '价格': float, '手数': int, '笔数': int}, ...],
            'total_vol': int,       # 总成交量(手)
            'large_trades': int,    # 大单笔数(>=50手)
            'large_vol': int,       # 大单成交量(手)
            'avg_vol': float,       # 平均每笔手数
            'max_vol': int,         # 最大单笔手数
        }
    """
    _, market_id, _ = get_market_info(code)
    secid = get_secid(code, market_id)

    try:
        params = {
            "secid": secid,
            "fields1": "f1,f2,f3,f4",
            "fields2": "f51,f52,f53,f54,f55",
            "pos": "-0",
            "lmt": "200",
        }
        j = _http_get_safe("push2.eastmoney.com", "/api/qt/stock/details/get", params)
        details = j.get("data", {}).get("details", []) if j else []
        if not details:
            return None

        trades = []
        total_vol = 0
        large_trades = 0
        large_vol = 0
        max_vol = 0

        for line in details:
            parts = line.split(",")
            if len(parts) < 4:
                continue
            vol = int(parts[2])  # 手
            price = float(parts[1])
            orders = int(parts[3]) if len(parts) > 3 else 0  # 成交笔数/单数

            trades.append({
                "时间": parts[0],
                "价格": price,
                "手数": vol,
                "笔数": orders,
            })
            total_vol += vol
            max_vol = max(max_vol, vol)
            if vol >= 50:
                large_trades += 1
                large_vol += vol

        avg_vol = total_vol / len(trades) if trades else 0

        # 分析大单时间聚集度（连续5分钟内的大单占比）
        large_clusters = 0
        window = []
        for t in sorted(trades, key=lambda x: x["时间"]):
            if t["手数"] >= 50:
                window.append(t)
                # 简单聚集检测：相邻大单间隔 < 5 秒
                if len(window) >= 3:
                    # 检查最后3个大单的时间跨度
                    times = [w["时间"] for w in window[-3:]]
                    large_clusters += 1
            else:
                window = []

        return {
            "trades": trades,
            "total_vol": total_vol,
            "large_trades": large_trades,
            "large_vol": large_vol,
            "avg_vol": round(avg_vol, 1),
            "max_vol": max_vol,
            "large_ratio": round(large_vol / total_vol * 100, 1) if total_vol > 0 else 0,
            "large_clusters": large_clusters,
        }
    except Exception:
        return None


def fetch_sector_fund_flow_panorama():
    """获取全市场板块资金流向全景（单次 clist 批量查询）。

    返回:
        list: [{'名称': str, '代码': str, '涨跌幅': float, '主力净流入': float, ...}, ...]
        按今日主力净流入降序排列
    """
    try:
        params = {
            "pn": "1", "pz": "120", "po": "0", "np": "1",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": "2", "invt": "2",
            "fid": "f62",
            "fs": "m:90+t:2",
            "fields": "f2,f3,f4,f12,f14,f62,f184,f66,f69,f72,f78,f84,f104,f128",
        }
        j = _http_get_safe("push2.eastmoney.com", "/api/qt/clist/get", params)
        items = j.get("data", {}).get("diff", []) if j else []
        if not items:
            return []

        result = []
        for item in items:
            if not isinstance(item, dict):
                continue
            result.append({
                "名称": item.get("f14", ""),
                "代码": str(item.get("f12", "")),
                "涨跌幅": safe_num(item.get("f3", 0)),
                "主力净流入": safe_num(item.get("f62", 0)),
                "主力占比": safe_num(item.get("f184", 0)),
                "超大单净流入": safe_num(item.get("f66", 0)),
                "大单净流入": safe_num(item.get("f72", 0)),
                "中单净流入": safe_num(item.get("f78", 0)),
                "小单净流入": safe_num(item.get("f84", 0)),
                "换手率": safe_num(item.get("f4", 0)),
            })

        return result
    except Exception:
        return []


def fetch_historical_financials(code):
    """获取近 5 年历史财务数据（利润表 + 现金流量表）。

    返回:
        dict: {
            'income': [{'报告期': str, '营业总收入': float, '归母净利润': float,
                        '营业成本': float, '营业利润': float}, ...],
            'cashflow': [{'报告期': str, '经营现金流': float}, ...],
        }
    """
    result = {"income": [], "cashflow": []}

    try:
        # 利润表
        params1 = {
            "type": "RPT_DMSK_FN_INCOME",
            "sty": "ALL",
            "filter": f'(SECUCODE="{code}.SZ")(REPORT_DATE>=\'2021-01-01\')',
            "p": "1", "ps": "20",
            "sr": "1", "st": "REPORT_DATE",
            "source": "HSF10", "client": "PC",
        }
        j1 = _http_get_safe("datacenter.eastmoney.com", "/api/data/get", params1)
        items1 = j1.get("result", {}).get("data", []) if j1 else []
        for item in items1:
            result["income"].append({
                "报告期": (item.get("REPORT_DATE") or "")[:10],
                "营业总收入": safe_num(item.get("TOTAL_OPERATE_INCOME", 0)),
                "营业成本": safe_num(item.get("TOTAL_OPERATE_COST", 0)),
                "营业利润": safe_num(item.get("OPERATE_PROFIT", 0)),
                "归母净利润": safe_num(item.get("PARENT_NETPROFIT", 0)),
            })

        # 现金流量表
        params2 = {
            "type": "RPT_DMSK_FN_CASHFLOW",
            "sty": "ALL",
            "filter": f'(SECUCODE="{code}.SZ")(REPORT_DATE>=\'2021-01-01\')',
            "p": "1", "ps": "20",
            "sr": "1", "st": "REPORT_DATE",
            "source": "HSF10", "client": "PC",
        }
        j2 = _http_get_safe("datacenter.eastmoney.com", "/api/data/get", params2)
        items2 = j2.get("result", {}).get("data", []) if j2 else []
        for item in items2:
            result["cashflow"].append({
                "报告期": (item.get("REPORT_DATE") or "")[:10],
                "经营现金流": safe_num(item.get("NETCASH_OPERATE", 0)),
            })
    except Exception:
        pass

    return result


# 常见股票名称映射（网络不稳定时的备用方案）
# 最后更新: 2026-06，新上市股票需手动添加
_STOCK_NAMES = {
    "000001": "平安银行", "000002": "万科A", "000063": "中兴通讯",
    "000100": "TCL科技", "000157": "中联重科", "000333": "美的集团",
    "000338": "潍柴动力", "000425": "徐工机械", "000538": "云南白药",
    "000568": "泸州老窖", "000636": "风华高科", "000625": "长安汽车", "000651": "格力电器",
    "000725": "京东方A", "000776": "广发证券", "000858": "五粮液",
    "000895": "双汇发展", "000938": "紫光股份", "000977": "浪潮信息",
    "002027": "分众传媒", "002049": "紫光国微", "002120": "韵达股份",
    "002142": "宁波银行", "002230": "科大讯飞", "002271": "东方雨虹",
    "002275": "桂林三金",
    "002304": "洋河股份", "002352": "顺丰控股", "002415": "海康威视",
    "002460": "赣锋锂业", "002475": "立讯精密", "002594": "比亚迪",
    "002714": "牧原股份", "002812": "恩捷股份", "002916": "深南电路",
    "300015": "爱尔眼科", "300059": "东方财富", "300124": "汇川技术",
    "300142": "沃森生物", "300274": "阳光电源", "300408": "三环集团",
    "300433": "蓝思科技", "300498": "温氏股份", "300750": "宁德时代",
    "300760": "迈瑞医疗", "300782": "卓胜微", "300896": "爱美客",
    "600000": "浦发银行", "600009": "上海机场", "600016": "民生银行",
    "600019": "宝钢股份", "600028": "中国石化", "600030": "中信证券",
    "600031": "三一重工", "600036": "招商银行", "600048": "保利发展",
    "600050": "中国联通", "600056": "中国医药", "600085": "同仁堂",
    "600089": "特变电工", "600104": "上汽集团", "600115": "东方航空",
    "600150": "中国船舶", "600176": "中国巨石", "600183": "生益科技",
    "600196": "复星医药", "600276": "恒瑞医药", "600309": "万华化学",
    "600346": "恒力石化", "600406": "国电南瑞", "600436": "片仔癀",
    "600438": "通威股份", "600519": "贵州茅台", "600570": "恒生电子",
    "600585": "海螺水泥", "600588": "用友网络", "600690": "海尔智家",
    "600745": "闻泰科技", "600809": "山西汾酒", "600837": "海通证券",
    "600887": "伊利股份", "600900": "长江电力", "600918": "中泰证券",
    "601012": "隆基绿能", "601088": "中国神华", "601100": "恒立液压",
    "601111": "中国国航", "601138": "工业富联", "601166": "兴业银行",
    "601225": "陕西煤业", "601236": "红塔证券", "601288": "农业银行",
    "601318": "中国平安", "601328": "交通银行", "601398": "工商银行",
    "601601": "中国太保", "601628": "中国人寿", "601668": "中国建筑",
    "601669": "中国电建", "601688": "华泰证券", "601766": "中国中车",
    "601818": "光大银行", "601857": "中国石油", "601881": "中国银河",
    "601888": "中国中免", "601899": "紫金矿业", "601919": "中远海控",
    "601985": "中国核电", "601988": "中国银行", "603019": "中科曙光",
    "603259": "药明康德", "603288": "海天味业", "603501": "韦尔股份",
    "603799": "华友钴业", "603882": "金域医学", "603986": "兆易创新",
    "688008": "澜起科技", "688012": "中微公司", "688036": "传音控股",
    "688111": "金山办公", "688169": "石头科技", "688187": "时代电气",
    "688256": "寒武纪", "688303": "大全能源", "688396": "华润微",
    "688561": "奇安信", "688599": "天合光能", "688981": "中芯国际",
}

# 反向映射：股票名称 -> 代码
_NAME_TO_CODE = {v: k for k, v in _STOCK_NAMES.items()}


def resolve_stock_code(input_str):
    """
    解析股票输入，支持代码或名称。

    Args:
        input_str: 股票代码（如 000333）或名称（如 美的集团）

    Returns:
        str: 股票代码

    Raises:
        ValueError: 输入为空或无法识别
    """
    input_str = input_str.strip()

    # 空输入检查
    if not input_str:
        raise ValueError("股票代码或名称不能为空")

    # 如果是纯数字，直接返回
    if input_str.isdigit():
        return input_str

    # 尝试从名称映射中查找（精确匹配）
    code = _NAME_TO_CODE.get(input_str)
    if code:
        return code

    # 模糊匹配（包含关系，但输入不能为空且至少2个字符）
    if len(input_str) >= 2:
        matches = [(name, code) for name, code in _NAME_TO_CODE.items()
                   if input_str in name or name in input_str]
        if len(matches) == 1:
            return matches[0][1]
        elif len(matches) > 1:
            names = '、'.join([m[0] for m in matches[:5]])
            raise ValueError(f"名称「{input_str}」匹配到多只股票：{names}，请使用代码")

    # 无法识别，抛出明确错误
    raise ValueError(f"无法识别股票代码或名称：{input_str}")

# 常见港股名称映射
_HK_STOCK_NAMES = {
    "00700": "腾讯控股", "09988": "阿里巴巴", "09618": "京东",
    "03690": "美团", "01810": "小米", "09888": "百度",
    "00941": "中国移动", "00388": "香港交易所", "02318": "中国平安",
    "01211": "比亚迪", "09999": "网易", "02020": "安踏体育",
    "01024": "快手", "06060": "众安在线", "00175": "吉利汽车",
    "02269": "药明生物", "00005": "汇丰控股", "01928": "金沙中国",
    "00883": "中国海洋石油", "02628": "中国人寿",
    "02015": "理想汽车", "09866": "蔚来", "09868": "小鹏汽车",
    "02382": "舜宇光学", "00027": "银河娱乐",
    "01398": "工商银行", "00939": "建设银行",
    "03988": "中国银行", "01288": "农业银行",
}

def get_stock_name(code, return_quote=False):
    """
    获取股票名称：先尝试 API，再用内置映射。

    Args:
        code: 股票代码
        return_quote: 如果为 True，返回 (name, quote) 元组，避免后续重复请求

    Returns:
        str: 股票名称（return_quote=False 时）
        tuple: (name, quote)（return_quote=True 时）
    """
    quote = None
    try:
        quote = fetch_realtime_quote(code)
        name = quote.get("f14", "")
        if name:
            if return_quote:
                return name, quote
            return name
    except Exception:
        pass
    # 根据市场类型选择映射表
    try:
        market_code, _, _ = get_market_info(code)
        if market_code == 'HK':
            name = _HK_STOCK_NAMES.get(code, code)
        else:
            name = _STOCK_NAMES.get(code, code)
    except ValueError:
        name = _STOCK_NAMES.get(code, code)

    if return_quote:
        return name, (quote if quote else {"market": ""})
    return name


# ============================================================
# 技术指标计算
# ============================================================

def calculate_indicators(df):
    """计算技术指标（纯 pandas 实现）

    注意：本函数计算基础指标用于快速访问（MA/MACD/KDJ/RSI/BOLL/ATR 等），
    完整指标在 technical_indicators.py 的 calculate_extended_indicators 中扩展
    （RSI 背离、MACD 柱状图分析、成交量异动、K 线形态、筹码分布等）。
    两处计算逻辑有意保持独立：本函数提供基础值供报告直接引用，
    extended_indicators 在此基础上做更深层次的分析。
    """
    if df.empty or len(df) < 30:
        return {}

    close = df["收盘"].astype(float)
    high = df["最高"].astype(float)
    low = df["最低"].astype(float)
    volume = df["成交量"].astype(float)
    indicators = {}

    # 均线
    for period in [5, 10, 20, 60, 120, 250]:
        if len(close) >= period:
            indicators[f"MA{period}"] = close.rolling(period).mean().iloc[-1]

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    indicators["DIF"] = dif.iloc[-1]
    indicators["DEA"] = dea.iloc[-1]
    indicators["MACD"] = (dif.iloc[-1] - dea.iloc[-1]) * 2
    # 前一日的 DIF/DEA（用于检测真正的金叉/死叉而非仅当前状态）
    if len(dif) >= 2:
        indicators["DIF_prev"] = dif.iloc[-2]
        indicators["DEA_prev"] = dea.iloc[-2]

    # KDJ
    low_min = low.rolling(9).min()
    high_max = high.rolling(9).max()
    rsv = (close - low_min) / (high_max - low_min).replace(0, 1e-10) * 100  # 避免除零
    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    indicators["K"] = k.iloc[-1]
    indicators["D"] = d.iloc[-1]
    indicators["J"] = 3 * k.iloc[-1] - 2 * d.iloc[-1]

    # RSI（delta/gain/loss 与周期无关，提前计算避免重复）
    delta = close.diff()
    gain = delta.where(delta > 0, 0)
    loss = (-delta.where(delta < 0, 0))
    for period in [6, 12, 24]:
        g = gain.rolling(period).mean()
        l = loss.rolling(period).mean()
        l_safe = l.replace(0, 1e-10)  # 避免除零
        rs = g / l_safe
        indicators[f"RSI{period}"] = (100 - 100 / (1 + rs)).iloc[-1]

    # 布林带
    if len(close) >= 20:
        mid = close.rolling(20).mean()
        std = close.rolling(20).std()
        indicators["BOLL_MID"] = mid.iloc[-1]
        indicators["BOLL_UP"] = (mid + 2 * std).iloc[-1]
        indicators["BOLL_DN"] = (mid - 2 * std).iloc[-1]

    # ATR (使用向量化操作，避免 pd.concat 中间 DataFrame)
    tr_a = high - low
    tr_b = (high - close.shift(1)).abs()
    tr_c = (low - close.shift(1)).abs()
    tr = np.maximum(tr_a, np.maximum(tr_b, tr_c))
    indicators["ATR14"] = tr.rolling(14).mean().iloc[-1]

    # 成交量均线
    for period in [5, 10, 20]:
        if len(volume) >= period:
            indicators[f"VOL_MA{period}"] = volume.rolling(period).mean().iloc[-1]

    # 原始成交量（供量价分析使用）
    indicators["成交量"] = volume.iloc[-1]

    # 涨跌幅统计
    indicators["最新价"] = close.iloc[-1]
    indicators["涨跌幅_今日"] = ((close.iloc[-1] / close.iloc[-2]) - 1) * 100 if len(close) >= 2 and close.iloc[-2] != 0 else 0
    if len(close) >= 5:
        indicators["涨跌幅_5日"] = ((close.iloc[-1] / close.iloc[-5]) - 1) * 100 if close.iloc[-5] != 0 else 0
    if len(close) >= 20:
        indicators["涨跌幅_20日"] = ((close.iloc[-1] / close.iloc[-20]) - 1) * 100 if close.iloc[-20] != 0 else 0
    if len(close) >= 60:
        indicators["涨跌幅_60日"] = ((close.iloc[-1] / close.iloc[-60]) - 1) * 100 if close.iloc[-60] != 0 else 0
    indicators["最高价_60日"] = high.tail(60).max() if len(high) >= 60 else high.max()
    indicators["最低价_60日"] = low.tail(60).min() if len(low) >= 60 else low.min()

    return indicators


# ============================================================
# 财务排雷与评级
# ============================================================

def calculate_financial_health(quote, financial_data):
    """计算财务健康指标（基于可用数据）"""
    result = {}

    # 从实时行情获取基本估值
    pe = safe_num(quote.get("f9", 0))  # 动态PE
    pb = safe_num(quote.get("f23", 0))  # PB
    roe = safe_num(quote.get("f37", 0))  # ROE
    gross_margin = safe_num(quote.get("f49", 0))  # 毛利率
    revenue = safe_num(quote.get("f40", 0))  # 营业收入（元）
    profit_growth = safe_num(quote.get("f41", 0))  # 净利润同比
    debt_ratio = safe_num(quote.get("f34", 0))  # 资产负债率

    result["PE"] = pe
    result["PB"] = pb
    result["ROE"] = roe
    result["毛利率"] = gross_margin
    result["营业收入"] = revenue
    result["净利润同比"] = profit_growth
    result["资产负债率"] = debt_ratio

    # 财务排雷评分（简化版，基于可用数据）
    red_flags = []
    warnings = []

    # 检测数据是否齐全：PE+PB+ROE+毛利率+营收+净利润同比+负债率 7 项中至少 3 项非零才有效
    data_indicators = [pe, pb, roe, gross_margin, revenue, profit_growth, debt_ratio]
    valid_count = sum(1 for v in data_indicators if v != 0)
    if valid_count < 3:
        result["排雷红灯"] = red_flags
        result["排雷预警"] = ["财务数据不全（备选数据源不提供完整财务指标），部分检查已跳过"]
        result["PE"] = pe
        result["PB"] = pb
        result["ROE"] = roe
        result["毛利率"] = gross_margin
        result["营业收入"] = revenue
        result["净利润同比"] = profit_growth
        result["资产负债率"] = debt_ratio
        return result

    # 1. 负债率检查
    if debt_ratio > 70:
        red_flags.append(f"资产负债率 {debt_ratio:.1f}% 过高（>70%）")
    elif debt_ratio > 60:
        warnings.append(f"资产负债率 {debt_ratio:.1f}% 偏高（>60%）")

    # 2. 估值检查
    if pe < 0:
        red_flags.append("市盈率为负（亏损状态）")
    elif pe > 100:
        warnings.append(f"市盈率 {pe:.1f} 偏高（>100）")

    # 3. 增长检查
    if profit_growth < -30:
        red_flags.append(f"净利润同比大幅下滑 {profit_growth:.1f}%")
    elif profit_growth < -10:
        warnings.append(f"净利润同比下滑 {profit_growth:.1f}%")

    result["排雷红灯"] = red_flags
    result["排雷预警"] = warnings

    return result


def calculate_rating(indicators, financial_health, fund_flow):
    """计算综合投资评级（1-5星）"""
    score = 0
    details = []

    # 1. 趋势评分（0-2分）
    price = indicators.get("最新价", 0)
    ma5 = indicators.get("MA5", 0)
    ma20 = indicators.get("MA20", 0)
    ma60 = indicators.get("MA60", 0)
    dif = indicators.get("DIF", 0)
    dea = indicators.get("DEA", 0)
    dif_prev = indicators.get("DIF_prev")
    dea_prev = indicators.get("DEA_prev")

    trend_score = 0
    if price > ma5 > ma20:
        trend_score += 1
        details.append("均线多头排列 +1")
    if price > ma60:
        trend_score += 0.5
        details.append("价格在60日均线上方 +0.5")
    # 真正的金叉穿越检测（与 calculate_weighted_score 保持一致）
    if (dif_prev is not None and dea_prev is not None
            and dif_prev <= dea_prev and dif > dea):
        trend_score += 0.5
        details.append("MACD金叉（真实上穿） +0.5")
    elif dif > dea:
        trend_score += 0.25
        details.append("MACD处于多头区域 +0.25")
    score += trend_score

    # 2. 超买超卖评分（0-1分）
    k_val = indicators.get("K", 50)
    rsi6 = indicators.get("RSI6", 50)
    if k_val < 20 and rsi6 < 30:
        score += 1
        details.append("KDJ/RSI超卖区 +1")
    elif k_val > 80 and rsi6 > 70:
        score -= 0.5
        details.append("KDJ/RSI超买区 -0.5")

    # 3. 资金面评分（0-1分）
    if fund_flow:
        main_today = safe_num(fund_flow.get("今日", {}).get("f62", 0))
        main_5d = safe_num(fund_flow.get("5日", {}).get("f62", 0))
        # 检查是否来自备选源（无多日拆分数据）
        is_alt_source = bool(fund_flow.get("今日", {}).get("_source", ""))
        if main_today > 0 and main_5d > 0:
            score += 1
            details.append("主力资金持续流入 +1")
        elif main_today > 0:
            if is_alt_source:
                score += 0.75  # 备选源缺乏多日数据，给稍低于满分的评价
                details.append("主力资金今日流入（多日数据不可用） +0.75")
            else:
                score += 0.5
                details.append("主力资金今日流入 +0.5")
        elif main_today < 0 and main_5d < 0:
            score -= 0.5
            details.append("主力资金持续流出 -0.5")

    # 4. 财务健康评分（0-1分）
    if financial_health:
        red_flags = financial_health.get("排雷红灯", [])
        warnings = financial_health.get("排雷预警", [])
        # 检测是否为数据不全（备选源不提供财务指标）
        has_incomplete = any("数据不全" in w for w in warnings)
        if has_incomplete:
            # 数据不全时不加减分，仅标注
            details.append("财务数据不全，部分指标无法评估")
        elif len(red_flags) == 0:
            score += 1
            details.append("财务排雷通过 +1")
        elif len(red_flags) <= 1:
            score += 0.5
            details.append("财务排雷1项红灯 +0.5")

    # 限制在1-5分范围
    score = max(1, min(5, score + 1))  # 基础1分 + 最高4分加成

    # 基本面保底：若财务健康且 PE 合理，评级不低于 2 星
    if financial_health:
        red_flags_bottom = financial_health.get("排雷红灯", [])
        pe_bottom = safe_num(financial_health.get("PE", 0))
        has_incomplete_bottom = any("数据不全" in w for w in financial_health.get("排雷预警", []))
        # PE 在 0-25 且无红灯且数据完整 → 基本面健康 → 最低 2 星
        if (0 < pe_bottom <= 25 and len(red_flags_bottom) == 0
                and not has_incomplete_bottom and score < 2):
            score = 2
            details.append("基本面健康，评级保底 2 星")

    # 转换为星级
    stars = round(score)
    star_str = "★" * stars + "☆" * (5 - stars)

    return {
        "分数": score,
        "星级": stars,
        "星级符号": star_str,
        "评分细节": details,
    }

def fmt_num(n):
    if pd.isna(n) or n == "-": return "-"
    if abs(n) >= 1e8: return f"{float(n)/1e8:.2f}亿"
    if abs(n) >= 1e4: return f"{n/1e4:.2f}万"
    return f"{n:,.2f}"

def fmt_pct(n):
    if pd.isna(n) or n == "-": return "-"
    return f"{n:.2f}%"


# ============================================================
# 单文件综合报告生成
# ============================================================

class ReportContext:
    """报告生成上下文，打包所有参数"""
    __slots__ = ['code', 'name', 'df', 'indicators', 'fund_flow', 'north_flow',
                 'quote', 'news_df', 'industry_df', 'financial_health', 'rating',
                 'extended_indicators', 'valuation_percentile', 'industry_comparison',
                 'weighted_score', 'stop_loss', 'target', 'support_resistance',
                 'position', 'risk_check', 'sentiment_result', 'company_profile',
                 'price', 'now', 'llm_interpretation',
                 'tick_analysis', 'sector_panorama', 'financial_trends']
    def __init__(self, **kwargs):
        for k in self.__slots__:
            if k not in kwargs:
                setattr(self, k, None)
        for k, v in kwargs.items():
            setattr(self, k, v)


def _section_title(ctx):
    """标题"""
    L = []
    L.append(f"# {ctx.name}（{ctx.code}）股票分析报告")
    L.append(f"\n> 生成时间：{ctx.now}")
    if ctx.df.empty:
        L.append("> 数据区间：暂无数据\n")
    else:
        L.append(f"> 数据区间：{ctx.df['日期'].iloc[0]} ~ {ctx.df['日期'].iloc[-1]}，共 {len(ctx.df)} 个交易日\n")
    return L


def _section_company_profile(ctx):
    """公司概况"""
    L = []
    if not ctx.company_profile:
        return L

    L.append("---\n## 公司概况\n")

    # 基本信息
    info = ctx.company_profile.get('基本信息', {})
    if info:
        L.append("### 基本信息\n")
        L.append("| 项目 | 内容 |")
        L.append("|------|------|")
        for label, key in [
            ("公司名称", "公司名称"),
            ("英文名称", "英文名称"),
            ("所属行业", "所属行业"),
            ("证监会行业", "证监会行业"),
            ("法人代表", "法人代表"),
            ("董事长", "董事长"),
            ("总经理", "总经理"),
            ("注册资本", "注册资本"),
            ("员工人数", "员工人数"),
            ("上市日期", "上市日期"),
            ("成立日期", "成立日期"),
        ]:
            val = info.get(key, '')
            if val:
                L.append(f"| {label} | {val} |")
        L.append("")

    # 公司简介
    desc = ctx.company_profile.get('公司简介', '')
    if desc:
        L.append("### 公司简介\n")
        L.append(f"{desc}\n")

    # 主营业务构成
    biz = ctx.company_profile.get('主营业务', [])
    if biz:
        L.append("### 主营业务构成\n")
        L.append("| 业务 | 收入(亿) | 占比 | 毛利率 |")
        L.append("|------|----------|------|--------|")
        for item in biz:
            name_str = item.get('名称', '') or ''
            income = item.get('收入', 0) or 0
            ratio = item.get('占比', 0) or 0
            gross = item.get('毛利率', 0) or 0
            L.append(f"| {name_str} | {income:.2f} | {ratio:.2f}% | {gross:.2f}% |")
        L.append("")

    # 股权结构
    holders = ctx.company_profile.get('股东结构', [])
    if holders:
        L.append("### 股权结构（前十大流通股东）\n")
        L.append("| 股东 | 持股(亿股) | 占流通股 | 性质 |")
        L.append("|------|-----------|----------|------|")
        for h in holders[:10]:
            h_name = h.get('名称', '') or ''
            h_shares = (h.get('持股数', 0) or 0) / 1e8
            h_ratio = h.get('占流通股比', 0) or 0
            h_type = h.get('股东性质', '') or ''
            L.append(f"| {h_name} | {h_shares:.2f} | {h_ratio:.2f}% | {h_type} |")
        L.append("")

        # 股权集中度分析
        top1_ratio = (holders[0].get('占流通股比', 0) or 0) if holders else 0
        top3_ratio = sum((h.get('占流通股比', 0) or 0) for h in holders[:3])
        if top1_ratio > 30:
            L.append(f"> **股权集中度**：第一大股东持股 {top1_ratio:.1f}%，前三合计 {top3_ratio:.1f}%，属于高度集中型股权结构。\n")
        elif top1_ratio > 15:
            L.append(f"> **股权集中度**：第一大股东持股 {top1_ratio:.1f}%，前三合计 {top3_ratio:.1f}%，属于相对集中型股权结构。\n")

    return L


def _section_company_analysis(ctx):
    """公司分析"""
    L = []
    if not (ctx.company_profile and (ctx.company_profile.get('主营业务') or ctx.company_profile.get('股东结构'))):
        return L

    L.append("---\n## 公司分析\n")

    biz = ctx.company_profile.get('主营业务', [])
    holders = ctx.company_profile.get('股东结构', [])
    info = ctx.company_profile.get('基本信息', {})

    # 机会分析
    L.append("### 最大机会\n")
    opportunities = []

    # 1. 检查是否有高增长业务（占比低但可能增长）
    if biz:
        main_biz = [b for b in biz if (b.get('占比', 0) or 0) > 1]
        small_biz = [b for b in biz if 0.5 < (b.get('占比', 0) or 0) < 15]
        if small_biz:
            names = '、'.join([(b.get('名称', '') or '') for b in small_biz[:2]])
            opportunities.append(f"**新业务成长空间**：{names} 等业务当前占比不高，若行业景气向上，有较大的增长弹性")

    # 2. 检查行业属性
    industry = info.get('所属行业', '')
    if industry:
        opportunities.append(f"**行业地位**：所属「{industry}」行业，需关注行业政策和景气度变化")

    # 3. 检查是否有境外业务
    overseas = [b for b in biz if '境外' in (b.get('名称', '') or '')]
    if overseas:
        overseas_pct = safe_num(overseas[0].get('占比', 100))
        if overseas_pct > 0 and overseas_pct < 5:
            opportunities.append(f"**海外市场**：境外收入占比仅 {overseas_pct:.1f}%，海外市场拓展潜力大")

    # 4. 检查毛利率趋势
    high_margin = [b for b in biz if (b.get('毛利率', 0) or 0) > 30]
    if high_margin:
        names = '、'.join([(b.get('名称', '') or '') for b in high_margin[:2]])
        opportunities.append(f"**高毛利业务**：{names} 毛利率较高，盈利能力强")

    for opp in opportunities:
        L.append(f"- {opp}")
    if not opportunities:
        L.append("- 暂无明显业务亮点，需结合行业趋势进一步分析")
    L.append("")

    # 风险分析
    L.append("### 最大风险\n")
    risks = []

    # 1. 股权集中风险
    if holders:
        top1 = holders[0].get('占流通股比', 0) or 0
        if top1 > 40:
            risks.append(f"**股权高度集中**：第一大股东持股 {top1:.1f}%，公司治理和决策依赖少数人，存在治理风险")

    # 2. 业务集中风险
    if biz:
        max_biz = max(biz, key=lambda x: (x.get('占比', 0) or 0))
        if (max_biz.get('占比', 0) or 0) > 40:
            risks.append(f"**业务集中**：{max_biz.get('名称', '') or ''} 收入占比 {(max_biz.get('占比', 0) or 0):.1f}%，单一业务依赖度高")

    # 3. 估值风险
    pe = safe_num(ctx.quote.get('f9', 0)) if ctx.quote else 0
    if pe > 80:
        risks.append(f"**估值偏高**：当前 PE {pe:.1f}，估值透支未来增长，面临估值压缩风险")

    # 4. 涨幅风险
    chg_60 = ctx.indicators.get('涨跌幅_60日', 0)
    if chg_60 > 50:
        risks.append(f"**短期涨幅过大**：近60日涨幅 {chg_60:.1f}%，获利盘积累，回调压力较大")

    # 5. 财务风险
    if ctx.financial_health:
        red_flags = ctx.financial_health.get('排雷红灯', [])
        if red_flags:
            risks.append(f"**财务排雷预警**：{'; '.join(red_flags[:2])}")

    for risk in risks:
        L.append(f"- {risk}")
    if not risks:
        L.append("- 暂无明显重大风险，整体基本面稳健")
    L.append("")

    # 核心洞察
    L.append("### 核心洞察\n")
    insights = []

    # 综合判断
    direction = ctx.weighted_score.get('direction', 'hold') if ctx.weighted_score else 'hold'
    score = ctx.weighted_score.get('score', 0) if ctx.weighted_score else 0
    stars = ctx.rating.get('星级', 3) if ctx.rating else 3

    if stars >= 4 and direction == 'buy':
        insights.append("综合评级较高且技术面看多，基本面与技术面共振，值得关注")
    elif stars >= 4 and direction == 'hold':
        insights.append("基本面优质但技术面尚未确认，建议等待技术信号配合")
    elif stars <= 2 and direction == 'sell':
        insights.append("基本面和技术面均偏弱，建议回避或减仓")
    else:
        insights.append("基本面与技术面信号分化，建议观望等待更明确的方向")

    # 估值判断（使用行业差异化阈值，与估价分位数分析保持一致）
    if pe > 0:
        from .valuation_analysis import _match_industry
        ind_name = (ctx.company_profile or {}).get('基本信息', {}).get('所属行业', '') if ctx.company_profile else ''
        ind_thresholds = _match_industry(ind_name)
        if ind_thresholds:
            pe_lo, pe_hi, _, _ = ind_thresholds
            if pe < pe_lo:
                insights.append(f"估值偏低（PE {pe:.1f}，低于{ind_name}合理区间{pe_lo}-{pe_hi}），具有安全边际")
            elif pe > pe_hi:
                insights.append(f"估值偏高（PE {pe:.1f}，高于{ind_name}合理区间{pe_lo}-{pe_hi}），需注意估值风险")
        else:
            if pe < 15:
                insights.append(f"估值偏低（PE {pe:.1f}），具有安全边际")
            elif pe > 50:
                insights.append(f"估值偏高（PE {pe:.1f}），需要业绩高增长支撑")

    for insight in insights:
        L.append(f"- {insight}")
    L.append("")

    return L


def _section_summary(ctx):
    """总结"""
    L = []
    L.append("---\n## 总结\n")

    # AI 执行摘要（--llm 启用时）
    if ctx.llm_interpretation:
        exec_summary = ctx.llm_interpretation.get("executive_summary", "")
        if exec_summary:
            L.append(f"> **🤖 AI 综述**：{exec_summary}\n")

    # 投资评级
    if ctx.rating:
        L.append(f"**综合评级：{ctx.rating['星级符号']}（{ctx.rating['星级']}/5星）**\n")

    # 涨跌
    chg_today = ctx.indicators.get("涨跌幅_今日", 0)
    chg_5d = ctx.indicators.get("涨跌幅_5日", 0)
    chg_20d = ctx.indicators.get("涨跌幅_20日", 0)
    chg_60d = ctx.indicators.get("涨跌幅_60日", 0)
    L.append(f"**最新价 {ctx.price} 元**，今日涨跌 {fmt_pct(chg_today)}。"
             f"近5日 {fmt_pct(chg_5d)}，近20日 {fmt_pct(chg_20d)}，近60日 {fmt_pct(chg_60d)}。")

    # 技术面一句话
    dif = ctx.indicators.get("DIF", 0)
    dea = ctx.indicators.get("DEA", 0)
    dif_prev = ctx.indicators.get("DIF_prev")
    dea_prev = ctx.indicators.get("DEA_prev")
    if (dif_prev is not None and dea_prev is not None
            and dif_prev <= dea_prev and dif > dea):
        macd_signal = "MACD金叉（看涨）"
    elif (dif_prev is not None and dea_prev is not None
            and dif_prev >= dea_prev and dif < dea):
        macd_signal = "MACD死叉（看跌）"
    else:
        macd_signal = "MACD多头区域" if dif > dea else "MACD空头区域"
    k_val = ctx.indicators.get("K", 50)
    kdj_signal = "KDJ超买" if k_val > 80 else "KDJ超卖" if k_val < 20 else "KDJ中性"
    ma5 = ctx.indicators.get("MA5", 0)
    ma20 = ctx.indicators.get("MA20", 0)
    ma60 = ctx.indicators.get("MA60", 0)
    trend_short = "短期多头" if ma5 > ma20 else "短期空头"
    trend_mid = "中期多头" if ma20 > ma60 else "中期空头"
    L.append(f"**技术面**：{macd_signal}，{kdj_signal}，均线{trend_short}、{trend_mid}。")

    # 资金面一句话
    if ctx.fund_flow:
        main_today = safe_num(ctx.fund_flow.get("今日", {}).get("f62", 0))
        main_5d = safe_num(ctx.fund_flow.get("5日", {}).get("f62", 0))
        is_alt = bool(ctx.fund_flow.get("今日", {}).get("_source", ""))
        fund_desc = "主力资金"
        if main_today > 0:
            fund_desc += f"今日净流入{fmt_num(main_today)}"
        elif main_today < 0:
            fund_desc += f"今日净流出{fmt_num(abs(main_today))}"
        if main_5d > 0:
            fund_desc += f"，5日净流入{fmt_num(main_5d)}"
        elif main_5d < 0:
            fund_desc += f"，5日净流出{fmt_num(abs(main_5d))}"
        elif is_alt:
            fund_desc += "，多日数据不可用（备选源限制）"
        L.append(f"**资金面**：{fund_desc}。")

    # 基本面一句话
    pe = safe_num(ctx.quote.get("f9", 0)) if ctx.quote else 0
    pb = safe_num(ctx.quote.get("f23", 0)) if ctx.quote else 0
    mv = ctx.quote.get("f20", 0) if ctx.quote else 0
    if pe != 0 or pb != 0:
        pe_str = f"{pe:.2f}" if pe != 0 else "-"
        pb_str = f"{pb:.2f}" if pb != 0 else "-"
        L.append(f"**基本面**：市盈率(动) {pe_str}，市净率 {pb_str}，总市值 {fmt_num(mv) if isinstance(mv,(int,float)) else mv}。")

    # 财务排雷一句话
    if ctx.financial_health:
        red_flags = ctx.financial_health.get("排雷红灯", [])
        warnings = ctx.financial_health.get("排雷预警", [])
        has_incomplete = any("数据不全" in w for w in warnings)
        if red_flags:
            L.append(f"**财务排雷**：发现 {len(red_flags)} 项红灯信号，需重点关注。")
        elif has_incomplete:
            L.append("**财务排雷**：财务数据不全（备选源限制），部分检查已跳过。")
        elif warnings:
            L.append(f"**财务排雷**：发现 {len(warnings)} 项预警，整体可控。")
        else:
            L.append("**财务排雷**：各项指标正常，无明显风险信号。")

    L.append("")
    return L


def _section_market_overview(ctx):
    """行情概览"""
    L = []
    L.append("\n---\n## 一、行情概览\n")
    if ctx.df.empty:
        L.append("> 暂无行情数据\n")
        return L
    last = ctx.df.iloc[-1]
    L.append("| 指标 | 数值 | 说明 |")
    L.append("|------|------|------|")
    for label, key, desc in [
        ("收盘价", "收盘", "当日最后一笔成交价"),
        ("开盘价", "开盘", "当日第一笔成交价"),
        ("最高价", "最高", "当日最高成交价"),
        ("最低价", "最低", "当日最低成交价"),
        ("成交量", "成交量", "当日成交的股数"),
        ("成交额", "成交额", "当日成交的总金额"),
        ("振幅", "振幅", "当日最高与最低的价差幅度"),
        ("涨跌幅", "涨跌幅", "相对前一日收盘价的变化百分比"),
        ("换手率", "换手率", "当日成交量占流通股的比例，越高越活跃"),
    ]:
        v = last.get(key, "-")
        if isinstance(v, (int, float)):
            if v == 0 and "跌幅" not in label and "量" not in label and "额" not in label:
                v = "-"  # 0 值对于振幅/换手率通常意味着数据缺失
            elif "量" in label:
                v = fmt_num(v)
            elif "额" in label:
                v = fmt_num(v) if v > 0 else "-"
            elif "幅" in label or "跌幅" in label or "手" in label:
                v = f"{v:.2f}%"
        L.append(f"| {label} | {v} | {desc} |")

    # 涨跌幅统计
    L.append("\n**区间涨跌幅**：\n")
    L.append("| 周期 | 涨跌幅 | 说明 |")
    L.append("|------|--------|------|")
    for pn, key, desc in [
        ("今日", "涨跌幅_今日", "相对昨日收盘"),
        ("5日", "涨跌幅_5日", "近一周"),
        ("20日", "涨跌幅_20日", "近一个月"),
        ("60日", "涨跌幅_60日", "近三个月"),
    ]:
        v = ctx.indicators.get(key)
        if v is not None:
            L.append(f"| {pn} | {fmt_pct(v)} | {desc} |")

    return L


def _section_technical_analysis(ctx):
    """技术分析"""
    L = []
    L.append("\n---\n## 二、技术分析\n")

    # 均线
    L.append("### 2.1 均线系统\n")
    L.append("均线（MA）是将过去 N 天的收盘价取平均值连成的曲线。")
    L.append("- 价格在均线上方 → 多头（看涨）；价格在均线下方 → 空头（看跌）")
    L.append("- 短期均线（MA5/MA10）反映短期趋势，长期均线（MA60/MA120/MA250）反映中长期趋势\n")
    L.append("| 均线 | 数值 | 位置 |")
    L.append("|------|------|------|")
    for p in [5, 10, 20, 60, 120, 250]:
        ma = ctx.indicators.get(f"MA{p}")
        if ma:
            L.append(f"| MA{p} | {ma:.2f} | {'价格在上（多头）' if ctx.price > ma else '价格在下（空头）'} |")
    # 检查长期均线是否缺失（新股或数据源回退时）
    missing_long = [p for p in [120, 250] if not ctx.indicators.get(f"MA{p}")]
    if missing_long:
        L.append(f"\n> ⚠️ 数据不足，MA{'/MA'.join(str(p) for p in missing_long)} 暂无（新上市或数据源回退）")

    # MACD
    L.append("\n### 2.2 MACD\n")
    L.append("MACD（指数平滑异同移动平均线）由 DIF 线和 DEA 线组成，用于判断趋势强弱和转折。")
    L.append("- **DIF**：短期EMA(12)与长期EMA(26)的差值，反映价格动能。DIF > 0 表示短期趋势强于长期")
    L.append("- **DEA**：DIF 的 9 日均线，用于平滑 DIF。DEA > 0 表示中期趋势向上")
    L.append("- **MACD柱**：(DIF - DEA) × 2，反映多空力量对比")
    L.append("  - 红柱（正值）：多头占优，柱子放大表示多头增强")
    L.append("  - 绿柱（负值）：空头占优，柱子放大表示空头增强")
    L.append("- **金叉**（DIF上穿DEA）→ 买入信号；**死叉**（DIF下穿DEA）→ 卖出信号\n")
    dif_val = ctx.indicators.get("DIF", 0)
    dea_val = ctx.indicators.get("DEA", 0)
    macd_val = ctx.indicators.get("MACD", 0)
    dif_prev = ctx.indicators.get("DIF_prev")
    dea_prev = ctx.indicators.get("DEA_prev")
    dif_signal = "短期趋势强于长期" if dif_val > 0 else "短期趋势弱于长期"
    dea_signal = "中期趋势向上" if dea_val > 0 else "中期趋势向下"
    # 使用真实穿越检测（与评分系统一致）
    if (dif_prev is not None and dea_prev is not None
            and dif_prev <= dea_prev and dif_val > dea_val):
        macd_signal = "金叉（看涨，真实上穿）"
    elif (dif_prev is not None and dea_prev is not None
            and dif_prev >= dea_prev and dif_val < dea_val):
        macd_signal = "死叉（看跌，真实下穿）"
    elif dif_val > dea_val:
        macd_signal = "多头区域（看涨）"
    else:
        macd_signal = "空头区域（看跌）"
    L.append(f"| 指标 | 数值 | 含义 | 信号 |")
    L.append(f"|------|------|------|------|")
    L.append(f"| DIF | {dif_val:.4f} | {dif_signal} | |")
    L.append(f"| DEA | {dea_val:.4f} | {dea_signal} | |")
    L.append(f"| MACD柱 | {macd_val:.4f} | {'红柱，多头占优' if macd_val > 0 else '绿柱，空头占优'} | {macd_signal} |")

    # KDJ
    L.append("\n### 2.3 KDJ\n")
    L.append("KDJ（随机指标）用于判断超买超卖状态，取值范围 0~100。")
    L.append("- **K值**：快速随机指标，反映短期价格波动")
    L.append("- **D值**：K值的移动平均线，反映中期趋势")
    L.append("- **J值**：K与D的偏离程度，波动最大，可提前预警拐点")
    L.append("- **K值 > 80**：超买区，价格偏高，可能回调")
    L.append("- **K值 < 20**：超卖区，价格偏低，可能反弹\n")
    kv, dv, jv = ctx.indicators.get("K",50), ctx.indicators.get("D",50), ctx.indicators.get("J",50)
    k_zone = "超买区（>80）" if kv > 80 else "超卖区（<20）" if kv < 20 else "中性区"
    d_zone = "超买区（>80）" if dv > 80 else "超卖区（<20）" if dv < 20 else "中性区"
    j_zone = "超买区（>80）" if jv > 80 else "超卖区（<20）" if jv < 20 else "中性区"
    L.append(f"| 指标 | 数值 | 区域 |")
    L.append(f"|------|------|------|")
    L.append(f"| K | {kv:.2f} | {k_zone} |")
    L.append(f"| D | {dv:.2f} | {d_zone} |")
    L.append(f"| J | {jv:.2f} | {j_zone} |")

    # RSI
    L.append("\n### 2.4 RSI\n")
    L.append("RSI（相对强弱指数）衡量一段时间内涨幅与跌幅的比值，取值 0~100。")
    L.append("- **> 80**：超买区，短期可能见顶，有回调风险")
    L.append("- **70-80**：强势区，多方占优，但接近超买")
    L.append("- **50-70**：中性偏多，多方略占优")
    L.append("- **30-50**：中性偏空，空方略占优")
    L.append("- **20-30**：弱势区，空方占优，可能超卖")
    L.append("- **< 20**：超卖区，短期可能见底，有反弹机会\n")
    L.append("| 周期 | 数值 | 区域 | 含义 |")
    L.append("|------|------|------|------|")
    for p in [6, 12, 24]:
        rsi = ctx.indicators.get(f"RSI{p}", 50)
        if rsi > 80:
            z = "超买区"
            desc = "短期可能见顶"
        elif rsi > 70:
            z = "强势区"
            desc = "多方占优，接近超买"
        elif rsi > 50:
            z = "中性偏多"
            desc = "多方略占优"
        elif rsi > 30:
            z = "中性偏空"
            desc = "空方略占优"
        elif rsi > 20:
            z = "弱势区"
            desc = "空方占优，可能超卖"
        else:
            z = "超卖区"
            desc = "短期可能见底"
        L.append(f"| RSI{p} | {rsi:.2f} | {z} | {desc} |")

    # 布林带
    L.append("\n### 2.5 布林带（BOLL）\n")
    L.append("布林带由三条轨道组成，用于判断价格波动区间和超买超卖状态。")
    L.append("- **上轨**（中轨+2倍标准差）：压力位，价格触及上轨可能回调")
    L.append("- **中轨**（20日均线）：趋势线，价格在中轨上方为多头，下方为空头")
    L.append("- **下轨**（中轨-2倍标准差）：支撑位，价格触及下轨可能反弹")
    L.append("- **带宽**：上下轨之间的距离，带宽收窄表示即将变盘，带宽扩大表示趋势延续\n")
    boll_up = ctx.indicators.get("BOLL_UP", 0)
    boll_mid = ctx.indicators.get("BOLL_MID", 0)
    boll_dn = ctx.indicators.get("BOLL_DN", 0)
    boll_width = (boll_up - boll_dn) / boll_mid * 100 if boll_mid > 0 else 0
    L.append(f"| 轨道 | 数值 | 含义 |")
    L.append(f"|------|------|------|")
    L.append(f"| 上轨 | {boll_up:.2f} | 压力位（超买线） |")
    L.append(f"| 中轨 | {boll_mid:.2f} | 20日均线（趋势线） |")
    L.append(f"| 下轨 | {boll_dn:.2f} | 支撑位（超卖线） |")
    L.append(f"| 带宽 | {boll_width:.2f}% | 波动率（越窄越可能变盘） |")
    if ctx.price:
        if ctx.price > boll_up:
            L.append(f"\n> 当前价格 {ctx.price} **突破上轨**，处于超买区域，注意回调风险")
        elif ctx.price > boll_mid:
            L.append(f"\n> 当前价格 {ctx.price} 在**中轨与上轨之间**，多头趋势")
        elif ctx.price > boll_dn:
            L.append(f"\n> 当前价格 {ctx.price} 在**下轨与中轨之间**，空头趋势")
        else:
            L.append(f"\n> 当前价格 {ctx.price} **跌破下轨**，处于超卖区域，可能反弹")

    # ATR
    atr = ctx.indicators.get("ATR14", 0)
    if atr:
        L.append(f"\n**ATR14**（14日平均真实波幅）：{atr:.2f} 元")
        L.append("- ATR 反映近期价格波动幅度，数值越大波动越剧烈")
        L.append("- 常用于计算止损位（如：止损价 = 当前价 - 2×ATR）")

    return L


def _section_fund_flow(ctx):
    """资金分析"""
    L = []
    L.append("\n---\n## 三、资金分析\n")

    if ctx.fund_flow:
        # 检查是否来自备选源
        today = ctx.fund_flow.get("今日", {})
        source_note = today.get("_source", "")
        if source_note:
            L.append(f"> 数据来源：{source_note}\n")

        L.append("资金流向反映市场中不同规模资金的买卖方向。")
        L.append("- **主力资金**（超大单+大单）：通常代表机构动向，对股价影响最大")
        L.append("- **超大单**（>100万元）：通常为大型机构或基金操作")
        L.append("- **大单**（20~100万元）：中型机构或大户操作")
        L.append("- **中单**（4~20万元）：小型机构或大户操作")
        L.append("- **小单**（<4万元）：散户操作")
        L.append("- **净流入**：买入金额 > 卖出金额，表示资金看好")
        L.append("- **净流出**：卖出金额 > 买入金额，表示资金撤离\n")

        field_labels = [
            ("f62", "f184", "主力（超大单+大单）"),
            ("f66", "f69", "超大单（>100万元）"),
            ("f72", "f75", "大单（20~100万元）"),
            ("f78", "f81", "中单（4~20万元）"),
            ("f84", "f87", "小单（<4万元）"),
        ]
        for period in ["今日", "3日", "5日", "10日"]:
            data = ctx.fund_flow.get(period)
            if not data:
                continue
            # 多日周期仅有主力净流入汇总，只显示一行避免全零行
            if period == "今日":
                L.append(f"### {period}资金流向\n")
                L.append("| 项目 | 净流入 | 占比 | 说明 |")
                L.append("|------|--------|------|------|")
                for fk, pk, label in field_labels:
                    val = safe_num(data.get(fk, 0))
                    raw_pct = data.get(pk)
                    if raw_pct is not None and raw_pct != 0 and str(raw_pct).strip() not in ("", "-", "N/A"):
                        pct = f"{safe_num(raw_pct):.2f}%"
                    else:
                        pct = "-"
                    desc = "资金看好" if val > 0 else "资金撤离" if val < 0 else "持平"
                    L.append(f"| {label} | {fmt_num(val)} | {pct} | {desc} |")
            else:
                L.append(f"### {period}资金流向\n")
                L.append("| 项目 | 净流入 | 说明 |")
                L.append("|------|--------|------|")
                val = safe_num(data.get("f62", 0))
                desc = "资金看好" if val > 0 else "资金撤离" if val < 0 else "持平"
                L.append(f"| 主力净流入 | {fmt_num(val)} | {desc} |")
            L.append("")
    else:
        L.append("> 暂无资金流向数据（网络不稳定，部分接口可能获取失败）\n")

    return L


def _section_fundamentals(ctx):
    """基本面分析"""
    L = []
    L.append("---\n## 五、基本面分析\n")

    if ctx.quote:
        # 标注财报报告期
        report_period = ""
        if ctx.company_profile:
            rp = ctx.company_profile.get('财报报告期', '')
            if rp:
                report_period = f"（基于 {rp} 财报）"
        L.append(f"> 以下财务数据来自最新财报{report_period}，部分指标为单季度数据\n")

        L.append("### 4.1 估值指标\n")
        L.append("| 指标 | 数值 | 说明 |")
        L.append("|------|------|------|")
        for label, key, desc in [
            ("市盈率(动态)", "f9", "股价/每股收益，越低越便宜，负值表示亏损"),
            ("市净率", "f23", "股价/每股净资产，<1为破净"),
            ("每股收益", "f115", "公司每股赚多少钱"),
            ("总市值", "f20", "公司总价值（股价×总股本）"),
            ("流通市值", "f21", "可在市场上交易的股票总价值"),
        ]:
            v = ctx.quote.get(key)
            if "市值" in label and isinstance(v, (int, float)):
                v = fmt_num(v)
            else:
                v = safe_display(v)
            L.append(f"| {label} | {v} | {desc} |")

        L.append("\n### 4.2 盈利与成长\n")
        L.append("| 指标 | 数值 | 说明 |")
        L.append("|------|------|------|")
        for label, key, desc, field_type in [
            ("加权净资产收益率", "f37", "公司用股东的钱赚钱的能力，越高越好", "pct"),
            ("毛利率", "f49", "收入扣除直接成本后的利润率", "pct"),
            ("营业收入", "f40", "公司总收入规模", "amount"),
            ("净利润同比", "f41", "净利润同比增长率", "pct"),
            ("资产负债率", "f34", "总负债/总资产，越高财务风险越大", "pct"),
        ]:
            raw = ctx.quote.get(key)
            if raw is not None and raw != 0 and str(raw).strip() not in ("", "-", "N/A", "--"):
                v = safe_num(raw)
                if field_type == "amount":
                    v = fmt_num(v) if abs(v) > 0 else "-"
                else:
                    v = f"{v:.2f}%"
            else:
                v = "-"
            L.append(f"| {label} | {v} | {desc} |")
    else:
        L.append("> 暂无基本面数据\n")

    return L


def _section_financial_screen(ctx):
    """财务排雷"""
    L = []
    if not ctx.financial_health:
        return L

    L.append("\n---\n## 六、财务排雷\n")
    L.append("财务排雷用于检查利润质量、现金流匹配度和潜在财务风险。\n")

    # 核心指标表
    L.append("### 5.1 核心指标\n")
    L.append("| 指标 | 数值 | 说明 |")
    L.append("|------|------|------|")
    for label, key, desc, fmt in [
        ("市盈率(动态)", "PE", "股价/每股收益，越低越便宜", "num"),
        ("市净率", "PB", "股价/每股净资产，<1为破净", "num"),
        ("ROE", "ROE", "净资产收益率，衡量盈利能力", "pct"),
        ("毛利率", "毛利率", "收入扣除直接成本后的利润率", "pct"),
        ("营业收入", "营业收入", "公司总收入规模", "amount"),
        ("净利润同比", "净利润同比", "净利润同比增长率", "pct"),
        ("资产负债率", "资产负债率", "总负债/总资产，越高财务风险越大", "pct"),
    ]:
        v = ctx.financial_health.get(key)
        if v is None:
            v = "-"
        elif isinstance(v, (int, float)):
            if v == 0:
                v = "-"  # 0 视为数据缺失
            elif fmt == "amount":
                v = fmt_num(v)
            elif fmt == "pct":
                v = f"{v:.2f}%"
            else:
                v = f"{v:.2f}"
        L.append(f"| {label} | {v} | {desc} |")

    # 排雷结果
    red_flags = ctx.financial_health.get("排雷红灯", [])
    warnings = ctx.financial_health.get("排雷预警", [])

    L.append("\n### 5.2 排雷结论\n")
    if red_flags:
        L.append("**红灯预警（需重点关注）：**")
        for flag in red_flags:
            L.append(f"- [!] {flag}")
    if warnings:
        L.append("\n**黄灯预警（整体可控）：**")
        for w in warnings:
            L.append(f"- [~] {w}")
    if not red_flags and not warnings:
        L.append("[OK] 各项指标正常，无明显财务风险信号。")

    # 估值检查
    pe_val = ctx.financial_health.get("PE", 0)
    # 年化涨幅计算：优先用 250 日数据，不足时用 60 日复合增长率近似
    # 数据不足时（<60天）不触发逆向定价检查，避免误判
    if len(ctx.df) >= 250:
        chg_1y = ((ctx.df["收盘"].iloc[-1] / ctx.df["收盘"].iloc[-250]) - 1) * 100
    elif len(ctx.df) >= 60:
        chg_60 = ctx.indicators.get("涨跌幅_60日", 0)
        chg_1y = ((1 + chg_60 / 100) ** 4.2 - 1) * 100  # 年化（60日 × 4.2 ≈ 252 个交易日）
    else:
        chg_1y = 0  # 数据不足，不触发逆向定价检查
    if pe_val > 80 or chg_1y > 200:
        L.append("\n### 5.3 逆向定价触发检查\n")
        L.append("当前估值或涨幅触发逆向定价条件，需特别关注价格是否透支未来增长：\n")
        L.append("| 触发项 | 阈值 | 当前数据 | 是否触发 |")
        L.append("|--------|------|----------|----------|")
        L.append(f"| PE-TTM | > 80 | {pe_val:.1f} | {'是' if pe_val > 80 else '否'} |")
        L.append(f"| 近似年涨幅 | > 200% | {chg_1y:.1f}% | {'是' if chg_1y > 200 else '否'} |")
        L.append("\n**建议**：高估值时需验证下一季度业绩能否支撑当前市值，否则面临估值压缩风险。")

    return L


def _section_news(ctx):
    """新闻动态"""
    L = []
    L.append("\n---\n## 八、新闻动态\n")
    if not ctx.news_df.empty:
        L.append("| 时间 | 标题 | 来源 |")
        L.append("|------|------|------|")
        for _, row in ctx.news_df.head(15).iterrows():
            url = row.get('链接', '')
            title = row['新闻标题']
            if url:
                title = f"[{title}]({url})"
            L.append(f"| {row['发布时间']} | {title} | {row['文章来源']} |")
    else:
        L.append("> 暂无近期新闻")

    return L


def _section_industry_board(ctx):
    """行业板块"""
    L = []
    L.append("\n---\n## 九、行业板块排名\n")
    if not ctx.industry_df.empty:
        L.append("当日行业板块涨跌排名（前20）：\n")
        L.append("| 排名 | 板块 | 涨跌幅 | 换手率 |")
        L.append("|------|------|--------|--------|")
        for i, (_, row) in enumerate(ctx.industry_df.head(20).iterrows(), 1):
            chg = row['涨跌幅']
            turnover = row.get('换手率', '-')
            L.append(f"| {i} | {row['板块']} | {fmt_pct(chg) if isinstance(chg,(int,float)) else chg} | {fmt_pct(turnover) if isinstance(turnover,(int,float)) else turnover} |")
    else:
        L.append("> 暂无行业数据")

    return L


def _section_extended_indicators(ctx):
    """扩展技术指标"""
    L = []
    if not ctx.extended_indicators:
        return L

    L.append("\n---\n## 十一、扩展技术指标\n")

    # RSI 背离
    rsi_div = ctx.extended_indicators.get('RSI背离', {})
    L.append("### 8.1 RSI 背离检测\n")
    L.append("RSI 背离是重要的趋势反转信号：")
    L.append("- **顶背离**：价格创新高但 RSI 未创新高，看跌信号")
    L.append("- **底背离**：价格创新低但 RSI 未创新低，看涨信号\n")
    L.append(f"- **检测结果**：{rsi_div.get('类型', '无背离')}")
    L.append(f"- **信号**：{rsi_div.get('信号', '无')}")
    L.append(f"- **可靠性**：{rsi_div.get('可靠性', '低')}")

    # MACD 柱状图
    macd_hist = ctx.extended_indicators.get('MACD柱状图', {})
    L.append("\n### 8.2 MACD 柱状图分析\n")
    L.append("MACD 柱状图反映多空动能的强弱变化：")
    L.append("- 红柱放大 → 多头增强；红柱缩小 → 多头减弱")
    L.append("- 绿柱放大 → 空头增强；绿柱缩小 → 空头减弱\n")
    L.append(f"- **连续红柱天数**：{macd_hist.get('连续红柱天数', 0)}")
    L.append(f"- **连续绿柱天数**：{macd_hist.get('连续绿柱天数', 0)}")
    L.append(f"- **趋势判断**：{macd_hist.get('趋势判断', '无')}")
    L.append(f"- **信号**：{macd_hist.get('信号', '无')}")

    # 成交量异动
    vol_anomaly = ctx.extended_indicators.get('成交量异动', {})
    L.append("\n### 8.3 成交量异动检测\n")
    L.append("成交量异动反映市场情绪和资金行为：")
    L.append("- 放量：可能有重大消息或主力行为")
    L.append("- 缩量：市场观望情绪浓厚\n")
    L.append(f"- **状态**：{vol_anomaly.get('状态', '正常')}")
    L.append(f"- **倍数**：{vol_anomaly.get('倍数', 0)}")
    L.append(f"- **信号**：{vol_anomaly.get('信号', '无')}")

    # K 线形态
    kline_patterns = ctx.extended_indicators.get('K线形态', [])
    L.append("\n### 8.4 K 线形态识别\n")
    if kline_patterns:
        L.append("| 形态 | 信号 | 可靠性 |")
        L.append("|------|------|--------|")
        for p in kline_patterns:
            L.append(f"| {p.get('形态', '')} | {p.get('信号', '')} | {p.get('可靠性', '')} |")
    else:
        L.append("近 5 个交易日未识别到典型 K 线形态。")

    # 筹码分布
    chip_dist = ctx.extended_indicators.get('筹码分布', {})
    L.append("\n### 8.5 筹码分布\n")
    L.append("筹码分布反映持仓成本结构：")
    L.append(f"- **平均成本**：{chip_dist.get('平均成本', 0):.2f} 元")
    L.append(f"- **获利盘比例**：{chip_dist.get('获利盘比例', 0) * 100:.1f}%")
    L.append(f"- **套牢盘比例**：{chip_dist.get('套牢盘比例', 0) * 100:.1f}%")
    L.append(f"- **筹码集中度**：{chip_dist.get('筹码集中度', '未知')}")

    return L


def _section_valuation_percentile(ctx):
    """估值分位数分析"""
    L = []
    if not ctx.valuation_percentile:
        return L

    L.append("\n---\n## 十二、估值分位数分析\n")
    L.append("估值分位数反映当前估值在近 5 年历史中的位置：")
    L.append("- 0%~20%：低估区间，可能存在投资机会")
    L.append("- 20%~40%：合理偏低")
    L.append("- 40%~60%：合理区间")
    L.append("- 60%~80%：合理偏高")
    L.append("- 80%~100%：高估区间，需注意风险\n")

    L.append("| 指标 | 当前值 | 分位数 | 估值区间 |")
    L.append("|------|--------|--------|----------|")
    for metric in ["PE", "PB", "股息率"]:
        info = ctx.valuation_percentile.get(metric, {})
        current = info.get('当前值', 0)
        percentile = info.get('分位数')
        zone = info.get('区间', '数据不足')
        pct_str = f"{percentile:.1f}%" if percentile is not None else "-"
        L.append(f"| {metric} | {current:.2f} | {pct_str} | {zone} |")

    summary = ctx.valuation_percentile.get('综合评价', '')
    if summary:
        L.append(f"\n**综合评价**：{summary}")

    return L


def _section_industry_comparison(ctx):
    """行业对比分析"""
    L = []
    if not ctx.industry_comparison:
        return L

    L.append("\n---\n## 十三、行业对比分析\n")

    industry_code = ctx.industry_comparison.get('行业', '')
    L.append(f"所属行业板块：{industry_code}\n")

    # 估值对比
    valuation_comp = ctx.industry_comparison.get('估值对比', {})
    L.append("### 10.1 估值对比\n")
    pe_rank = valuation_comp.get('PE排名', 0)
    pb_rank = valuation_comp.get('PB排名', 0)
    roe_rank = valuation_comp.get('ROE排名', 0)
    total_peers = len(valuation_comp.get('估值排名', []))
    if total_peers > 0:
        L.append(f"- **PE 排名**：第 {pe_rank}/{total_peers} 名（越低越便宜）")
        L.append(f"- **PB 排名**：第 {pb_rank}/{total_peers} 名（越低越便宜）")
        L.append(f"- **ROE 排名**：第 {roe_rank}/{total_peers} 名（越高越好）")
    else:
        L.append("> 暂无行业估值对比数据")

    # 行业景气度
    sentiment = ctx.industry_comparison.get('行业景气度', {})
    L.append("\n### 10.2 行业景气度\n")
    ind_chg = sentiment.get('涨跌幅', 0)
    ind_turnover = sentiment.get('换手率', 0)
    chg_str = f"{ind_chg:.2f}%" if ind_chg != 0 else "-"
    turnover_str = f"{ind_turnover:.2f}%" if ind_turnover != 0 else "-"
    L.append(f"- **涨跌幅**：{chg_str}")
    L.append(f"- **换手率**：{turnover_str}")
    L.append(f"- **资金流向**：{sentiment.get('资金流入', '未知')}")
    L.append(f"- **景气度评估**：{sentiment.get('景气度', '中性')}")

    # 龙头溢价
    leader = ctx.industry_comparison.get('龙头溢价', {})
    L.append("\n### 10.3 龙头溢价分析\n")
    if leader.get('龙头公司'):
        L.append(f"- **龙头公司**：{leader.get('龙头公司', '')}")
        L.append(f"- **龙头 PE**：{leader.get('龙头PE', 0):.2f}")
        L.append(f"- **行业平均 PE**：{leader.get('行业平均PE', 0):.2f}")
        L.append(f"- **溢价率**：{leader.get('溢价率', 0):.2f}%")
        L.append(f"- **溢价合理性**：{leader.get('溢价合理性', '数据不足')}")
    else:
        L.append("> 暂无龙头溢价数据")

    return L


def _section_counter_evidence(ctx):
    """反证清单与跟踪因子"""
    L = []
    L.append("\n---\n## 十四、反证清单与跟踪因子\n")
    L.append("以下事实出现时，应重新评估当前结论：\n")

    # 根据当前技术状态生成反证清单
    if ctx.indicators.get("DIF", 0) > ctx.indicators.get("DEA", 0):
        L.append("1. MACD 出现死叉（DIF 下穿 DEA）")
    else:
        L.append("1. MACD 出现金叉（DIF 上穿 DEA）")

    ma20 = ctx.indicators.get("MA20", 0)
    ma60 = ctx.indicators.get("MA60", 0)
    if ma20 > 0:
        if ctx.price > ma20:
            L.append(f"2. 股价跌破 20 日均线（当前 {ma20:.2f}）")
        else:
            L.append(f"2. 股价站上 20 日均线（当前 {ma20:.2f}）")
    else:
        L.append(f"2. 20 日均线数据不足，暂无法判断")

    if ma60 > 0:
        if ctx.price > ma60:
            L.append(f"3. 股价跌破 60 日均线（当前 {ma60:.2f}）")
        else:
            L.append(f"3. 股价站上 60 日均线（当前 {ma60:.2f}）")
    else:
        L.append(f"3. 60 日均线数据不足，暂无法判断")

    if ctx.financial_health:
        profit_growth = ctx.financial_health.get("净利润同比", 0)
        if profit_growth > 0:
            L.append(f"4. 下一季度净利润同比转负（当前 {profit_growth:.1f}%）")
        elif profit_growth < 0:
            L.append(f"4. 净利润同比继续下滑（当前 {profit_growth:.1f}%）")
        else:
            L.append("4. 净利润同比数据暂缺，待季报更新后补充")

    L.append("5. 主力资金连续 5 日以上净流出")
    L.append("6. 行业板块排名跌出前 30")

    # 关键因子跟踪
    L.append("\n**关键跟踪因子：**\n")
    L.append("| 因子 | 当前状态 | 信息源 | 更新频率 |")
    L.append("|------|----------|--------|----------|")
    L.append(f"| 均线趋势 | {'多头' if ctx.price > ma20 else '空头'} | K线数据 | 每日 |")
    dif_t = ctx.indicators.get('DIF', 0)
    dea_t = ctx.indicators.get('DEA', 0)
    dif_p = ctx.indicators.get('DIF_prev')
    dea_p = ctx.indicators.get('DEA_prev')
    if (dif_p is not None and dea_p is not None and dif_p <= dea_p and dif_t > dea_t):
        macd_track = "金叉"
    elif (dif_p is not None and dea_p is not None and dif_p >= dea_p and dif_t < dea_t):
        macd_track = "死叉"
    else:
        macd_track = "多头区域" if dif_t > dea_t else "空头区域"
    L.append(f"| MACD信号 | {macd_track} | K线数据 | 每日 |")
    L.append(f"| 主力资金 | {'流入' if ctx.fund_flow and safe_num(ctx.fund_flow.get('今日',{}).get('f62',0)) > 0 else '流出'} | 资金流向 | 每日 |")
    if ctx.financial_health:
        pg = ctx.financial_health.get('净利润同比')
        dr = ctx.financial_health.get('资产负债率')
        pg_display = f"{pg:.1f}%" if isinstance(pg, (int, float)) and pg != 0 else "-"
        dr_display = f"{dr:.1f}%" if isinstance(dr, (int, float)) and dr != 0 else "-"
        L.append(f"| 净利润增速 | {pg_display} | 财报 | 季度 |")
        L.append(f"| 资产负债率 | {dr_display} | 财报 | 季度 |")

    return L


def _section_weighted_score(ctx):
    """加权信号评分"""
    L = []
    if not ctx.weighted_score:
        return L

    L.append("\n---\n## 十五、加权信号评分\n")
    L.append(f"**综合评分：{ctx.weighted_score['score']:.2f}**（-10 到 +10）\n")
    L.append(f"**操作方向：{ctx.weighted_score['direction']}**")
    L.append(f"**置信度：{ctx.weighted_score['confidence']}**\n")

    L.append("**信号明细：**")
    for signal in ctx.weighted_score["signals"]:
        L.append(f"- {signal}")

    L.append(f"\n**多空统计：**")
    L.append(f"- 看多信号：{ctx.weighted_score['bullish_signals']} 个")
    L.append(f"- 看空信号：{ctx.weighted_score['bearish_signals']} 个")
    L.append(f"- 净信号数：{ctx.weighted_score['net_signals']}")

    return L


def _section_trade_suggestion(ctx):
    """操作建议"""
    L = []
    if not (ctx.stop_loss and ctx.target and ctx.position and ctx.weighted_score):
        return L

    L.append("\n---\n## 十六、操作建议\n")
    L.append(f"**方向：{ctx.weighted_score['direction']}**")
    L.append(f"**仓位：{ctx.position['position_pct']}%**（{ctx.position['description']}）\n")

    L.append("**止损/目标位：**")
    L.append(f"- 止损价：{ctx.stop_loss['stop_loss']}（{ctx.stop_loss['description']}）")
    L.append(f"- 目标价：{ctx.target['target_price']}（{ctx.target['description']}）")
    L.append(f"- 风险收益比：1:{ctx.target['risk_reward_ratio']}")

    return L


def _section_support_resistance(ctx):
    """支撑压力位"""
    L = []
    if not ctx.support_resistance:
        return L

    L.append("\n---\n## 十七、支撑压力位\n")

    if ctx.support_resistance.get("resistance"):
        L.append("**压力位：**")
        L.append("| 价格 | 来源 |")
        L.append("|------|------|")
        for r in ctx.support_resistance["resistance"][:5]:
            L.append(f"| {r['price']} | {r['source']} |")

    if ctx.support_resistance.get("support"):
        L.append("\n**支撑位：**")
        L.append("| 价格 | 来源 |")
        L.append("|------|------|")
        for s in ctx.support_resistance["support"][:5]:
            L.append(f"| {s['price']} | {s['source']} |")

    return L


def _section_sentiment(ctx):
    """新闻情感分析"""
    L = []
    if not ctx.sentiment_result:
        return L

    L.append("\n---\n## 十八、新闻情感分析\n")
    L.append(summarize_sentiment(ctx.sentiment_result))

    # 输出正/负面新闻标题及链接
    positive_news = ctx.sentiment_result.get("positive_news", [])
    negative_news = ctx.sentiment_result.get("negative_news", [])

    if positive_news:
        L.append("\n**正面新闻：**\n")
        for n in positive_news:
            title = n.get("新闻标题", n.get("title", ""))
            url = n.get("链接", n.get("url", ""))
            line = f"- [+] {title}"
            if url:
                line += f" — [查看]({url})"
            L.append(line)

    if negative_news:
        L.append("\n**负面新闻：**\n")
        for n in negative_news:
            title = n.get("新闻标题", n.get("title", ""))
            url = n.get("链接", n.get("url", ""))
            line = f"- [-] {title}"
            if url:
                line += f" — [查看]({url})"
            L.append(line)

    return L


def _section_risk_control(ctx):
    """风控提示"""
    L = []
    if not (ctx.risk_check and ctx.risk_check.get("warnings")):
        return L

    L.append("\n---\n## 十九、风控提示\n")
    for warning in ctx.risk_check["warnings"]:
        L.append(f"- [!] {warning}")

    return L


def _section_tick_analysis(ctx):
    """逐笔成交分析 — 大单异动检测"""
    L = []
    L.append("\n---\n## 四、逐笔成交分析\n")

    ta = ctx.tick_analysis
    if not ta or not ta.get("trades"):
        L.append("> 暂无逐笔成交数据\n")
        return L

    total = ta["total_vol"]
    large = ta["large_trades"]
    large_vol = ta["large_vol"]
    large_ratio = ta["large_ratio"]
    avg = ta["avg_vol"]
    max_v = ta["max_vol"]

    L.append("基于当日所有逐笔成交数据分析大单异动情况：\n")
    L.append("| 指标 | 数值 | 说明 |")
    L.append("|------|------|------|")
    L.append(f"| 分析笔数 | {len(ta['trades'])} 笔 | 最近逐笔成交样本 |")
    L.append(f"| 总成交量 | {total} 手 | 样本合计 |")
    L.append(f"| 平均每笔 | {avg} 手 | 单笔成交量均值 |")
    L.append(f"| 最大单笔 | {max_v} 手 | 单笔最大成交量 |")
    L.append(f"| 大单笔数 | {large} 笔（≥50手） | 占样本 {large_ratio}% |")
    L.append(f"| 大单成交 | {large_vol} 手 | 占总成交量 {large_ratio}% |")

    # 大单异动判断
    L.append("\n### 大单异动评估\n")
    signals = []
    if large_ratio > 50:
        signals.append("**大单主导**：超过 50% 的成交量来自 ≥50 手的大单，机构参与度极高")
    elif large_ratio > 30:
        signals.append("**机构活跃**：30%-50% 的成交量来自大单，机构有一定参与")
    elif large_ratio > 10:
        signals.append("**散户主导**：大单占比偏低（10%-30%），当前以散户交易为主")
    else:
        signals.append("**交投清淡**：大单占比不足 10%，机构参与度很低")

    if avg >= 30:
        signals.append("**平均单笔手数偏高**（≥30手），可能存在主力对倒或集中交易")
    elif avg <= 5:
        signals.append("**平均单笔手数偏低**（≤5手），散户化特征明显")

    if max_v >= 500:
        signals.append(f"**异常大单**：检测到单笔 {max_v} 手的超大单，需关注是否有重大消息")

    # 大单聚集检测
    clusters = ta.get("large_clusters", 0)
    if clusters >= 5:
        signals.append(f"**大单聚集**：检测到 {clusters} 次大单连续出现，主力可能在积极操作")
    elif clusters >= 2:
        signals.append(f"轻度聚集：{clusters} 次大单连续出现")

    if not signals:
        signals.append("未检测到明显的大单异动信号")

    for s in signals:
        L.append(f"- {s}")

    return L


def _section_sector_panorama(ctx):
    """板块资金全景 — 全市场板块资金流向排名"""
    L = []
    L.append("\n---\n## 十、板块资金全景\n")

    sp = ctx.sector_panorama
    if not sp:
        L.append("> 暂无板块资金数据\n")
        return L

    L.append(f"全市场 {len(sp)} 个行业板块资金流向全景（按今日主力净流入排序）：\n")

    # 资金流入前10
    inflows = [s for s in sp if s["主力净流入"] > 0][:10]
    outflows = sorted([s for s in sp if s["主力净流入"] < 0], key=lambda x: x["主力净流入"])[:10]

    if inflows:
        L.append("### 资金净流入 TOP 10\n")
        L.append("| 排名 | 板块 | 涨跌幅 | 主力净流入 | 主力占比 |")
        L.append("|------|------|--------|------------|----------|")
        for i, s in enumerate(inflows, 1):
            L.append(f"| {i} | {s['名称']} | {s['涨跌幅']:+.2f}% | {fmt_num(s['主力净流入'])} | {s['主力占比']:.2f}% |")

    if outflows:
        L.append(f"\n### 资金净流出 TOP 10\n")
        L.append("| 排名 | 板块 | 涨跌幅 | 主力净流出 | 主力占比 |")
        L.append("|------|------|--------|------------|----------|")
        for i, s in enumerate(outflows, 1):
            L.append(f"| {i} | {s['名称']} | {s['涨跌幅']:+.2f}% | {fmt_num(abs(s['主力净流入']))} | {s['主力占比']:.2f}% |")

    # 所属行业位置
    if ctx.company_profile:
        ind_name = ctx.company_profile.get("基本信息", {}).get("所属行业", "")
        if ind_name:
            L.append(f"\n### 所属行业定位\n")
            # 模糊匹配找到所属板块
            matched = None
            for s in sp:
                if ind_name in s["名称"] or s["名称"] in ind_name:
                    matched = s
                    break
            if matched:
                rank = next((i for i, s in enumerate(sp, 1) if s["名称"] == matched["名称"]), None)
                L.append(f"- **{ind_name}**：全市场排名第 {rank} 位（共 {len(sp)} 个板块）")
                flow_desc = "资金流入" if matched["主力净流入"] > 0 else "资金流出"
                L.append(f"- 今日{flow_desc} {fmt_num(abs(matched['主力净流入']))}，涨跌幅 {matched['涨跌幅']:+.2f}%")
            else:
                L.append(f"- **{ind_name}**：未在板块排名中找到精确匹配")
                # 显示相关板块
                related = [s for s in sp if any(w in s['名称'] for w in ind_name[:4])][:3]
                if related:
                    L.append(f"- 相关板块：{'、'.join(s['名称'] for s in related)}")

    return L


def _section_financial_trends(ctx):
    """历史财务趋势 — 近5年收入/利润/现金流走势"""
    L = []
    L.append("\n---\n## 七、历史财务趋势\n")

    ft = ctx.financial_trends
    if not ft or not ft.get("income"):
        L.append("> 暂无历史财务数据\n")
        return L

    income_data = ft.get("income", [])

    # 提取年度数据（12-31 报告期）
    annual = [item for item in income_data if item["报告期"].endswith("-12-31")]
    if len(annual) < 2:
        # 回退：使用全部数据
        annual = income_data

    L.append(f"基于近 {len(annual)} 个年度财报的关键指标趋势：\n")

    # 趋势表格
    L.append("| 报告期 | 营业总收入(亿) | 归母净利润(亿) | 净利率 | 营收增速 | 利润增速 |")
    L.append("|--------|---------------|---------------|--------|----------|----------|")
    prev_rev = None
    prev_profit = None
    for item in annual:
        rd = item["报告期"]
        rev = item["营业总收入"] / 1e8
        profit = item["归母净利润"] / 1e8
        margin = (profit / rev * 100) if rev > 0 else 0

        rev_growth = ((rev / prev_rev - 1) * 100) if prev_rev else None
        profit_growth = ((profit / prev_profit - 1) * 100) if prev_profit else None

        rev_g_str = f"{rev_growth:+.1f}%" if rev_growth is not None else "-"
        profit_g_str = f"{profit_growth:+.1f}%" if profit_growth is not None else "-"

        L.append(f"| {rd} | {rev:.2f} | {profit:.2f} | {margin:.1f}% | {rev_g_str} | {profit_g_str} |")
        prev_rev = rev
        prev_profit = profit

    # CAGR 计算
    if len(annual) >= 2:
        first = annual[0]
        last = annual[-1]
        years = len(annual) - 1
        rev_first = first["营业总收入"] / 1e8
        rev_last = last["营业总收入"] / 1e8
        profit_first = first["归母净利润"] / 1e8
        profit_last = last["归母净利润"] / 1e8

        rev_cagr = ((rev_last / rev_first) ** (1 / years) - 1) * 100 if rev_first > 0 else 0
        profit_cagr = ((profit_last / profit_first) ** (1 / years) - 1) * 100 if profit_first > 0 else 0

        L.append(f"\n### 成长性指标\n")
        L.append(f"- **营收 CAGR（{years}年）**：{rev_cagr:+.1f}%")
        L.append(f"- **利润 CAGR（{years}年）**：{profit_cagr:+.1f}%")

        # 趋势判断
        if rev_cagr > 20 and profit_cagr > 20:
            L.append("- **成长性**：高速增长，营收和利润同步快速扩张")
        elif rev_cagr > 10 and profit_cagr > 10:
            L.append("- **成长性**：稳健增长")
        elif rev_cagr > 0 and profit_cagr < rev_cagr:
            L.append("- **成长性**：增收不增利，利润增速落后于营收，成本端可能有压力")
        elif rev_cagr > 0 and profit_cagr <= 0:
            L.append("- **成长性**：增收不增利，盈利能力下降需关注")

    # 现金流质量
    cf_data = ft.get("cashflow", [])
    cf_annual = [item for item in cf_data if item["报告期"].endswith("-12-31")]
    if cf_annual and len(cf_annual) >= 2:
        L.append(f"\n### 现金流质量\n")
        L.append("| 报告期 | 经营现金流(亿) | 净利润(亿) | 现金流/净利润 |")
        L.append("|--------|---------------|-----------|---------------|")
        # Align cashflow with income data
        for i, cf_item in enumerate(cf_annual):
            rd = cf_item["报告期"]
            ocf = cf_item["经营现金流"] / 1e8
            # Find matching income
            inc_item = next((item for item in annual if item["报告期"] == rd), None)
            profit = inc_item["归母净利润"] / 1e8 if inc_item else 0
            ratio = (ocf / profit) if profit > 0 else 0
            quality = "优秀" if ratio > 1 else "良好" if ratio > 0.7 else "偏低" if ratio > 0 else "负值⚠"
            L.append(f"| {rd} | {ocf:.2f} | {profit:.2f} | {ratio:.2f}（{quality}） |")

        # 整体评价
        recent_ratios = []
        for i, cf_item in enumerate(cf_annual[-3:]):
            rd = cf_item["报告期"]
            inc_item = next((item for item in annual if item["报告期"] == rd), None)
            profit = inc_item["归母净利润"] / 1e8 if inc_item else 0
            ocf = cf_item["经营现金流"] / 1e8
            recent_ratios.append((ocf / profit) if profit > 0 else 0)

        avg_ratio = sum(recent_ratios) / len(recent_ratios) if recent_ratios else 0
        if avg_ratio > 1:
            L.append(f"\n- **现金流质量：优秀** — 近3年经营现金流持续大于净利润，利润含金量高")
        elif avg_ratio > 0.7:
            L.append(f"\n- **现金流质量：良好** — 经营现金流基本覆盖净利润")
        else:
            L.append(f"\n- **现金流质量：需关注** — 经营现金流与净利润差距较大")

    return L


def _section_ai_interpretation(ctx):
    """
    AI 增强解读（仅当 --llm 启用时生成）。

    包含：
    - 执行摘要（自然语言综述）
    - 指标矛盾检测
    - 技术信号白话解读
    - AI 建议跟踪因子
    """
    L = []
    if not ctx.llm_interpretation:
        return L

    data = ctx.llm_interpretation
    L.append("\n---\n## AI 增强解读\n")

    # 执行摘要
    exec_summary = data.get("executive_summary", "")
    if exec_summary:
        L.append(f"> {exec_summary}\n")

    # 矛盾检测
    contradictions = data.get("contradictions", [])
    if contradictions:
        L.append("### 指标矛盾警示\n")
        for c in contradictions:
            L.append(f"- ⚠️ {c}")
        L.append("")

    # 白话技术解读
    explanation = data.get("signal_explanation", "")
    if explanation:
        L.append("### 技术信号白话解读\n")
        L.append(f"{explanation}\n")

    # 重点关注因子
    factors = data.get("key_factors", [])
    if factors:
        L.append("### AI 建议跟踪因子\n")
        for f in factors:
            L.append(f"- {f}")
        L.append("")

    if any([exec_summary, contradictions, explanation, factors]):
        L.append("> ℹ️ 以上解读由 AI 模型生成，仅供参考，不构成投资建议。\n")
    return L


def _section_disclaimer(ctx):
    """风险提示"""
    L = []
    L.append("\n---\n## 风险提示\n")
    L.append("- 以上分析基于公开数据自动计算，请结合基本面和市场环境综合判断")
    L.append("- 技术指标存在滞后性，请结合自身风险承受能力做出投资决策")
    L.append("- 股市有风险，投资需谨慎")
    return L


def generate_report(code, name, df, indicators, fund_flow, north_flow, quote, news_df, industry_df,
                    financial_health=None, rating=None, extended_indicators=None,
                    valuation_percentile=None, industry_comparison=None,
                    weighted_score=None, stop_loss=None, target=None,
                    support_resistance=None, position=None, risk_check=None,
                    sentiment_result=None, company_profile=None,
                    llm_interpretation=None,
                    tick_analysis=None, sector_panorama=None, financial_trends=None):
    """生成单个综合分析报告"""
    ctx = ReportContext(
        code=code, name=name, df=df, indicators=indicators,
        fund_flow=fund_flow, north_flow=north_flow, quote=quote,
        news_df=news_df, industry_df=industry_df,
        financial_health=financial_health, rating=rating,
        extended_indicators=extended_indicators,
        valuation_percentile=valuation_percentile,
        industry_comparison=industry_comparison,
        weighted_score=weighted_score, stop_loss=stop_loss,
        target=target, support_resistance=support_resistance,
        position=position, risk_check=risk_check,
        sentiment_result=sentiment_result,
        company_profile=company_profile,
        llm_interpretation=llm_interpretation,
        tick_analysis=tick_analysis,
        sector_panorama=sector_panorama,
        financial_trends=financial_trends,
        price=indicators.get("最新价", 0),
        now=datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    )

    L = []
    for section_fn in [
        _section_title, _section_company_profile, _section_company_analysis,
        _section_summary, _section_market_overview, _section_technical_analysis,
        _section_fund_flow, _section_tick_analysis, _section_fundamentals,
        _section_financial_screen, _section_financial_trends,
        _section_news, _section_industry_board, _section_sector_panorama,
        _section_extended_indicators,
        _section_valuation_percentile, _section_industry_comparison,
        _section_ai_interpretation,  # AI 增强解读（--llm 启用时生成）
        _section_counter_evidence, _section_weighted_score,
        _section_trade_suggestion, _section_support_resistance,
        _section_sentiment, _section_risk_control, _section_disclaimer
    ]:
        L.extend(section_fn(ctx))

    return "\n".join(L)


# ============================================================
# 主流程
# ============================================================

# 注：_last_analysis_time 在模块顶部定义，此处不重复声明


def analyze_stock(code, output_dir=".", llm_enabled=False):
    # 分析间冷却保护：连续调用时强制间隔
    global _last_analysis_time
    elapsed_since_last = time.time() - _last_analysis_time
    if elapsed_since_last < 15:
        wait = 15 - elapsed_since_last
        print(f"  [冷却] 距离上次分析仅 {elapsed_since_last:.0f} 秒，等待 {wait:.0f} 秒...")
        time.sleep(wait)
    _last_analysis_time = time.time()

    # 重置会话请求统计
    reset_request_stats()

    print(f"\n{'='*60}")
    print(f"  分析股票: {code}")
    print(f"{'='*60}")

    # 交易日检查
    if not is_trading_day():
        print("  [提示] 今天不是交易日，数据为最近交易日的快照")

    us_mode = is_us_stock(code)
    if us_mode:
        print("  市场类型: 美股（通过东方财富 API 获取数据）")

    # 使用 return_quote=True 避免后续重复请求
    name, quote = get_stock_name(code, return_quote=True)
    print(f"  股票名称: {name}")

    out_path = Path(output_dir) / "分析报告"
    out_path.mkdir(parents=True, exist_ok=True)
    print(f"  输出目录: {out_path}")

    # ── 冷启动预热：预加载市场级数据 ──
    # 美股模式跳过 A 股专属的北向资金预热（节省 API 请求额度）
    print("  [预热] 预加载市场级数据...")
    try:
        fetch_industry_boards()
        if not us_mode:
            fetch_north_flow()
        print("  [预热] 完成（后续分析复用缓存，零额外请求）")
    except Exception:
        pass

    # ── 渐进降级：根据请求预算决定数据层级 ──
    stats = get_session_request_stats()
    available = 60 - stats["total_requests"]
    # Tier 4 (奢侈): 同行资金流向 — 需要 >30 次额度
    # Tier 3 (可选): 行业对比 — 需要 >25 次额度
    # Tier 2 (重要): 所有默认数据 — 需要 >10 次额度
    # Tier 1 (必须): K线 + 行情 + 财务 + 公司概况
    current_tier = 4 if available > 30 else (3 if available > 25 else (2 if available > 10 else 1))
    if current_tier < 4:
        print(f"  [降级] 可用请求额度仅 {available} 次，自动降级到 Tier {current_tier}")

    # ── 进度条初始化 ──
    total_steps = 9 if us_mode else (13 + (3 if current_tier >= 3 else 0))
    init_request_queue(total_steps)
    tick_request_queue("开始分析")

    print()
    print("[1] 获取 K 线数据...")
    df_hist = fetch_kline(code, days=500)
    if df_hist.empty:
        raise ValueError(f"无法获取 {code} 的 K 线数据，请检查股票代码是否正确或稍后重试")
    print(f"  获取到 {len(df_hist)} 条 K 线数据")
    tick_request_queue("K线")

    print("[2] 获取实时行情... [复用已有数据，无额外请求]")
    tick_request_queue("行情")

    if us_mode:
        fund_flow, north_flow, news_df, industry_df, financial_data = {}, {}, pd.DataFrame(), pd.DataFrame(), {}
        tick_analysis, sector_panorama, financial_trends = None, [], {}
        tick_request_queue("跳过美股专属")
    else:
        print("[3] 获取资金流向...")
        fund_flow = fetch_fund_flow(code)
        tick_request_queue("资金流向")

        print("[4] 获取北向资金... [Memo 跨分析缓存]")
        north_flow = fetch_north_flow()
        tick_request_queue("北向")

        print("[5] 获取新闻和行业数据...")
        news_df = fetch_stock_news(code)
        industry_df = fetch_industry_boards()
        tick_request_queue("新闻+行业")

        print("[6] 获取财务报表数据...")
        financial_data = fetch_financial_report(code)
        tick_request_queue("财务")

    print("[7] 获取公司概况...")
    company_profile = fetch_company_profile(code)
    tick_request_queue("公司概况")

    # ── 新增强：逐笔成交 + 板块全景 + 历史财务（A股专属）──
    if not us_mode:
        print("[7b] 获取逐笔成交...")
        tick_analysis = fetch_tick_details(code)
        tick_request_queue("逐笔成交")

        print("[7c] 获取板块资金全景...")
        sector_panorama = fetch_sector_fund_flow_panorama()
        tick_request_queue("板块全景")

        print("[7d] 获取历史财务趋势...")
        financial_trends = fetch_historical_financials(code)
        tick_request_queue("历史财务")

    print("[8] 计算技术指标...")
    indicators = calculate_indicators(df_hist)
    extended_indicators = calculate_extended_indicators(df_hist, indicators)
    tick_request_queue("技术指标")

    print("[9] 计算评分和风控...")
    weighted_score = calculate_weighted_score(indicators)
    price = indicators.get("最新价", 0)
    board_type = "main" if us_mode else detect_board_type(code)
    stop_loss = calc_dynamic_stop_loss(current_price=price, atr=indicators.get("ATR14", 0), board_type=board_type)
    target = calc_target_price(current_price=price, stop_loss=stop_loss["stop_loss"])
    support_resistance = calc_support_resistance(df_hist, price, indicators)
    position = calc_position_size(direction=weighted_score["direction"], score=weighted_score["score"],
                                   net_signals=weighted_score["net_signals"],
                                   has_bearish=weighted_score["bearish_signals"] > 0)
    is_st = "ST" in name.upper() if name else False
    risk_check = check_risk_rules(code=code, indicators=indicators, is_st=is_st, is_new_stock=False)
    tick_request_queue("评分+风控")

    if us_mode:
        sentiment_result = {"score": 0, "label": "N/A", "positive": 0, "negative": 0, "neutral": 0}
        financial_health = calculate_financial_health(quote, financial_data)
        rating = calculate_rating(indicators, financial_health, fund_flow)
        valuation_percentile = None
        industry_comparison = None
        tick_request_queue("美股完成")
    else:
        print("[10] 分析新闻情感...")
        sentiment_result = analyze_sentiment(news_df.to_dict("records") if not news_df.empty else [])
        financial_health = calculate_financial_health(quote, financial_data)
        rating = calculate_rating(indicators, financial_health, fund_flow)
        tick_request_queue("情感+财务")

        print("[11] 分析估值分位数...")
        # 提取行业信息用于差异化估值判断
        stock_industry = (company_profile.get('基本信息', {}) or {}).get('所属行业', '')
        valuation_percentile = analyze_valuation_percentile(code, quote, years=5, kline_data=df_hist, industry=stock_industry)
        tick_request_queue("估值分位")

        # ── 渐进降级：Tier <3 时跳过行业对比 ──
        if current_tier >= 3:
            print("[12] 分析行业对比...")
            industry_comparison = analyze_industry_comparison(code)
            tick_request_queue("行业对比")
        else:
            print("[12] 行业对比... [Tier {0} 降级跳过，节省请求额度]".format(current_tier))
            industry_comparison = None
            tick_request_queue("跳过行业对比")

    # ── LLM 增强解读 ──
    llm_interpretation = None
    if llm_enabled:
        try:
            from .llm_client import (detect_provider, build_analysis_prompt,
                                     call_llm, parse_llm_response,
                                     build_llm_context_from_report_ctx)
            provider, api_key, base_url = detect_provider()
            if provider.value != "unknown":
                # 构建临时 ctx 用于提取数据
                temp_ctx = ReportContext(
                    code=code, name=name, df=df_hist, indicators=indicators,
                    fund_flow=fund_flow, quote=quote,
                    financial_health=financial_health, rating=rating,
                    extended_indicators=extended_indicators,
                    valuation_percentile=valuation_percentile,
                    industry_comparison=industry_comparison,
                    weighted_score=weighted_score, stop_loss=stop_loss,
                    target=target, support_resistance=support_resistance,
                    position=position, risk_check=risk_check,
                    sentiment_result=sentiment_result,
                    company_profile=company_profile,
                    price=indicators.get("最新价", 0) if indicators else 0,
                )
                ctx_data = build_llm_context_from_report_ctx(temp_ctx)
                prompt = build_analysis_prompt(ctx_data)
                text = call_llm(provider, prompt, api_key=api_key,
                              base_url=base_url, timeout=25)
                if text:
                    llm_interpretation = parse_llm_response(text)
                    print("  [AI] LLM 增强解读已生成")
                else:
                    print("  [AI] LLM 调用未返回结果，降级为规则解读")
            else:
                print("  [AI] 未检测到可用 LLM provider（设置 ANTHROPIC_API_KEY 或 OPENAI_API_KEY），使用规则解读")
        except Exception as e:
            print(f"  [AI] LLM 调用异常: {e}，降级为规则解读")

    print("\n生成分析报告...")
    report = generate_report(
        code, name, df_hist, indicators, fund_flow, north_flow,
        quote, news_df, industry_df, financial_health, rating,
        extended_indicators, valuation_percentile, industry_comparison,
        weighted_score, stop_loss, target,
        support_resistance, position, risk_check, sentiment_result,
        company_profile, llm_interpretation,
        tick_analysis=tick_analysis,
        sector_panorama=sector_panorama,
        financial_trends=financial_trends,
    )
    today = datetime.date.today().strftime("%Y%m%d")
    report_file = (out_path / f"{code}-{name}-分析报告-{today}.md").resolve()
    report_file.write_text(report, encoding="utf-8")
    print(f"  [OK] {report_file.name}")

    # ── 提取图表数据（供 HTML 导出使用）──
    global _last_chart_data
    try:
        from .chart_data import extract_all_chart_data
        _last_chart_data = extract_all_chart_data(
            df=df_hist, indicators=indicators, quote=quote,
            fund_flow=fund_flow, valuation_percentile=valuation_percentile,
        )
    except Exception:
        _last_chart_data = {}

    # 打印请求统计
    print_request_stats()

    print(f"\n分析完成! 报告已保存至: {report_file}")
    return str(report_file)


# ============================================================
# 加权信号评分系统
# ============================================================

# 加权信号评分权重（总分归一化到 -10 ~ +10）
# 权重设计原则：趋势信号权重最高（2.0），因为趋势是核心驱动力；
# MACD/RSI 等动量信号次之（1.0~1.5），量价关系权重最低（0.5~1.0）
SIGNAL_WEIGHTS = {
    "ma_alignment_bull": 2.0,     # 均线多头排列 — 最强趋势信号，权重最高
    "ma_alignment_bear": -2.0,    # 均线空头排列 — 最强看空信号
    "macd_golden_cross": 1.5,     # MACD 金叉（DIF 真实上穿 DEA）— 趋势转折确认
    "macd_death_cross": -1.5,     # MACD 死叉（DIF 真实下穿 DEA）— 趋势转折确认
    "macd_bullish_region": 0.5,   # MACD 处于多头区域（持续状态非新交叉）— 半权重
    "macd_bearish_region": -0.5,  # MACD 处于空头区域（持续状态非新交叉）— 半权重
    "macd_hist_positive": 0.5,    # MACD 红柱 — 多头动能辅助确认
    "macd_hist_negative": -0.5,   # MACD 绿柱 — 空头动能辅助确认
    "rsi_oversold": 1.0,          # RSI 超卖（<30）— 超卖反弹机会
    "rsi_overbought": -1.0,       # RSI 超买（>70）— 超买回调风险
    "rsi_extreme_overbought": -2.0,  # RSI 严重超买（>80）— 高度危险信号，加重权重
    "rsi_extreme_oversold": 1.5,  # RSI 严重超卖（<20）— 强反弹信号，加重权重
    "boll_lower": 1.0,            # 触及布林下轨 — 短期超卖支撑
    "boll_upper": -1.0,           # 触及布林上轨 — 短期超买压力
    "bias_alert_high": -1.0,       # 乖离率正偏离预警（>5%）— 追高风险
    "bias_alert_low": 1.0,         # 乖离率负偏离预警（<-5%）— 超卖反弹机会
    "kdj_oversold": 1.0,           # KDJ 超卖（K<20）— 反弹机会
    "kdj_deep_oversold": 1.5,      # KDJ 深度超卖（K<10）— 强反弹信号
    "kdj_overbought": -1.0,        # KDJ 超买（K>80）— 回调风险
    "kdj_extreme_overbought": -2.0, # KDJ 严重超买（K>90）— 高度危险
    "volume_up": 1.0,              # 放量上涨 — 量价配合看多
    "volume_down_weak": -0.5,     # 缩量上涨 — 上涨动能不足
    "volume_down_panic": -1.5,    # 放量下跌 — 恐慌性抛售信号
    # 注：OBV（能量潮）暂未实现，待集成到技术指标计算后再启用
}


def calculate_weighted_score(indicators: Dict[str, float]) -> Dict[str, Any]:
    """
    计算加权信号评分。

    Args:
        indicators: 技术指标字典

    Returns:
        dict: {
            'score': float,
            'direction': 'buy' / 'sell' / 'hold',
            'confidence': '较高' / '中等' / '较低',
            'signals': list,
            'bullish_signals': int,
            'bearish_signals': int,
            'net_signals': int
        }
    """
    score = 0.0
    signals = []
    bullish_count = 0
    bearish_count = 0

    price = indicators.get("最新价", 0)
    ma5 = indicators.get("MA5", 0)
    ma10 = indicators.get("MA10", 0)
    ma20 = indicators.get("MA20", 0)
    ma60 = indicators.get("MA60", 0)
    dif = indicators.get("DIF", 0)
    dea = indicators.get("DEA", 0)
    rsi6 = indicators.get("RSI6", 50)
    k_val = indicators.get("K", 50)
    boll_up = indicators.get("BOLL_UP", 0)
    boll_dn = indicators.get("BOLL_DN", 0)
    vol_ma5 = indicators.get("VOL_MA5", 0)
    volume = indicators.get("成交量", 0)

    # 1. 均线排列判断
    # 提前计算间距，避免在 if/elif 分支中重复计算
    gap_5_10 = abs(ma5 - ma10) / ma10 * 100 if ma10 > 0 else 0
    gap_10_20 = abs(ma10 - ma20) / ma20 * 100 if ma20 > 0 else 0
    if ma5 > ma10 > ma20 > ma60:
        if gap_5_10 > 1 and gap_10_20 > 1:
            score += SIGNAL_WEIGHTS["ma_alignment_bull"]
            signals.append("均线多头排列 +2.0")
            bullish_count += 1
    elif ma5 < ma10 < ma20 < ma60:
        if gap_5_10 > 1 and gap_10_20 > 1:
            score += SIGNAL_WEIGHTS["ma_alignment_bear"]
            signals.append("均线空头排列 -2.0")
            bearish_count += 1

    # 2. MACD 信号（区分真正交叉与持续状态）
    dif = indicators.get("DIF", 0)
    dea = indicators.get("DEA", 0)
    dif_prev = indicators.get("DIF_prev")
    dea_prev = indicators.get("DEA_prev")

    # 检测真正的金叉：DIF 从下方上穿 DEA
    true_golden = (dif_prev is not None and dea_prev is not None
                   and dif_prev <= dea_prev and dif > dea)
    # 检测真正的死叉：DIF 从上方下穿 DEA
    true_death = (dif_prev is not None and dea_prev is not None
                  and dif_prev >= dea_prev and dif < dea)

    if true_golden:
        score += SIGNAL_WEIGHTS["macd_golden_cross"]
        signals.append("MACD金叉(真实上穿) +1.5")
        bullish_count += 1
    elif true_death:
        score += SIGNAL_WEIGHTS["macd_death_cross"]
        signals.append("MACD死叉(真实下穿) -1.5")
        bearish_count += 1
    elif dif > dea:
        score += SIGNAL_WEIGHTS.get("macd_bullish_region", 0.5)
        signals.append("MACD处于多头区域 +0.5")
        bullish_count += 1
    else:
        score += SIGNAL_WEIGHTS.get("macd_bearish_region", -0.5)
        signals.append("MACD处于空头区域 -0.5")
        bearish_count += 1

    # MACD 柱状图
    macd_hist = dif - dea
    if macd_hist > 0:
        score += SIGNAL_WEIGHTS["macd_hist_positive"]
        signals.append("MACD红柱 +0.5")
    else:
        score += SIGNAL_WEIGHTS["macd_hist_negative"]
        signals.append("MACD绿柱 -0.5")

    # 3. RSI 信号
    if rsi6 < 20:
        score += SIGNAL_WEIGHTS["rsi_extreme_oversold"]
        signals.append("RSI严重超卖(<20) +1.5")
        bullish_count += 1
    elif rsi6 < 30:
        score += SIGNAL_WEIGHTS["rsi_oversold"]
        signals.append("RSI超卖(<30) +1.0")
        bullish_count += 1
    elif rsi6 > 80:
        score += SIGNAL_WEIGHTS["rsi_extreme_overbought"]
        signals.append("RSI严重超买(>80) -2.0")
        bearish_count += 1
    elif rsi6 > 70:
        score += SIGNAL_WEIGHTS["rsi_overbought"]
        signals.append("RSI超买(>70) -1.0")
        bearish_count += 1

    # 3.5 KDJ 信号（超买超卖）
    # NaN 防护：KDJ 在数据不足时可能为 NaN，此时跳过信号检测
    if pd.isna(k_val):
        k_val = 50  # 中性值，不影响评分
    if k_val < 10:
        score += SIGNAL_WEIGHTS["kdj_deep_oversold"]
        signals.append("KDJ深度超卖(K<10) +1.5")
        bullish_count += 1
    elif k_val < 20:
        score += SIGNAL_WEIGHTS["kdj_oversold"]
        signals.append("KDJ超卖(K<20) +1.0")
        bullish_count += 1
    elif k_val > 90:
        score += SIGNAL_WEIGHTS["kdj_extreme_overbought"]
        signals.append("KDJ严重超买(K>90) -2.0")
        bearish_count += 1
    elif k_val > 80:
        score += SIGNAL_WEIGHTS["kdj_overbought"]
        signals.append("KDJ超买(K>80) -1.0")
        bearish_count += 1

    # 4. 布林带信号
    if price > 0:
        if boll_up > 0 and price >= boll_up * 0.98:
            score += SIGNAL_WEIGHTS["boll_upper"]
            signals.append("触及布林上轨 -1.0")
            bearish_count += 1
        elif boll_dn > 0 and price <= boll_dn * 1.02:
            score += SIGNAL_WEIGHTS["boll_lower"]
            signals.append("触及布林下轨 +1.0")
            bullish_count += 1

    # 5. 乖离率检查（区分正负方向）
    if ma20 > 0 and price > 0:
        bias = (price - ma20) / ma20 * 100
        if bias > 5:
            score += SIGNAL_WEIGHTS["bias_alert_high"]
            signals.append(f"乖离率正偏离({bias:.1f}%) -1.0")
            bearish_count += 1
        elif bias < -5:
            score += SIGNAL_WEIGHTS["bias_alert_low"]
            signals.append(f"乖离率负偏离({bias:.1f}%) +1.0")
            bullish_count += 1

    # 6. 量价关系
    if vol_ma5 > 0 and volume > 0:
        vol_ratio = volume / vol_ma5
        if vol_ratio > 1.5:
            # 放量
            chg = indicators.get("涨跌幅_今日", 0)
            if chg > 0:
                score += SIGNAL_WEIGHTS["volume_up"]
                signals.append("放量上涨 +1.0")
                bullish_count += 1
            else:
                score += SIGNAL_WEIGHTS["volume_down_panic"]
                signals.append("放量下跌 -1.5")
                bearish_count += 1
        elif vol_ratio < 0.5:
            chg = indicators.get("涨跌幅_今日", 0)
            if chg > 0:
                score += SIGNAL_WEIGHTS["volume_down_weak"]
                signals.append("缩量上涨 -0.5")

    # 归一化到 -10 到 +10
    score = max(-10, min(10, score))

    # 计算净信号数
    net_signals = bullish_count - bearish_count

    # 判断操作方向
    has_bearish = bearish_count > 0
    if score >= 5 and not has_bearish and net_signals >= 2:
        direction = "buy"
        confidence = "较高"
    elif score >= 3 and not has_bearish and net_signals >= 1:
        direction = "buy"
        confidence = "中等"
    elif score <= -5:
        direction = "sell"
        confidence = "较高"
    elif score <= -3:
        direction = "sell"
        confidence = "中等"
    else:
        direction = "hold"
        confidence = "较低"

    return {
        "score": round(score, 2),
        "direction": direction,
        "confidence": confidence,
        "signals": signals,
        "bullish_signals": bullish_count,
        "bearish_signals": bearish_count,
        "net_signals": net_signals,
    }


# ============================================================
# 便捷函数
# ============================================================

def compare_stocks_wrapper(code_a: str, code_b: str) -> Dict[str, Any]:
    """
    双股对比分析的便捷函数。

    Args:
        code_a: 股票 A 代码
        code_b: 股票 B 代码

    Returns:
        dict: 对比分析结果
    """
    reset_request_stats()

    # 获取股票 A 数据（复用 quote，避免重复请求）
    name_a, quote_a = get_stock_name(code_a, return_quote=True)
    df_a = fetch_kline(code_a, days=120)
    indicators_a = calculate_indicators(df_a)
    fund_flow_a = fetch_fund_flow(code_a)
    financial_data_a = fetch_financial_report(code_a)
    financial_health_a = calculate_financial_health(quote_a, financial_data_a)
    rating_a = calculate_rating(indicators_a, financial_health_a, fund_flow_a)

    stock_a = {
        "code": code_a,
        "name": name_a,
        "price": indicators_a.get("最新价", 0),
        "pe": safe_num(quote_a.get("f9", 0)) if quote_a else 0,
        "pb": safe_num(quote_a.get("f23", 0)) if quote_a else 0,
        "market_cap": safe_num(quote_a.get("f20", 0)) if quote_a else 0,
        "change_pct": indicators_a.get("涨跌幅_今日", 0),
        "indicators": indicators_a,
        "fund_flow": fund_flow_a,
        "quote": quote_a,
        "rating": rating_a,
    }

    # 获取股票 B 数据（复用 quote，避免重复请求）
    name_b, quote_b = get_stock_name(code_b, return_quote=True)
    df_b = fetch_kline(code_b, days=120)
    indicators_b = calculate_indicators(df_b)
    fund_flow_b = fetch_fund_flow(code_b)
    financial_data_b = fetch_financial_report(code_b)
    financial_health_b = calculate_financial_health(quote_b, financial_data_b)
    rating_b = calculate_rating(indicators_b, financial_health_b, fund_flow_b)

    stock_b = {
        "code": code_b,
        "name": name_b,
        "price": indicators_b.get("最新价", 0),
        "pe": safe_num(quote_b.get("f9", 0)) if quote_b else 0,
        "pb": safe_num(quote_b.get("f23", 0)) if quote_b else 0,
        "market_cap": safe_num(quote_b.get("f20", 0)) if quote_b else 0,
        "change_pct": indicators_b.get("涨跌幅_今日", 0),
        "indicators": indicators_b,
        "fund_flow": fund_flow_b,
        "quote": quote_b,
        "rating": rating_b,
    }

    print_request_stats()
    return compare_two_stocks(stock_a, stock_b)


def analyze_sector_wrapper(sector_name: str) -> Dict[str, Any]:
    """
    板块分析的便捷函数。

    Args:
        sector_name: 板块名称

    Returns:
        dict: 板块分析结果
    """
    codes = get_sector_stocks(sector_name)
    if not codes:
        return {"error": f"未知板块: {sector_name}"}

    stocks = []
    for code in codes:
        try:
            name, quote = get_stock_name(code, return_quote=True)
            change_pct = safe_num(quote.get("f3", 0)) if quote else 0
            stocks.append({
                "code": code,
                "name": name,
                "change_pct": change_pct,
            })
        except Exception:
            continue

    sector_data = {
        "sector_name": sector_name,
        "stocks": stocks,
    }

    return analyze_sector(sector_data)
