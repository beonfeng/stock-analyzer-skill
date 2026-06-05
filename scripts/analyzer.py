#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票综合分析工具 — 核心分析逻辑
"""

import datetime
from pathlib import Path
from typing import Dict, Any

import pandas as pd
import numpy as np

from .market_utils import get_market_info, convert_price, is_hk_stock, get_secid
from .utils import _http_get, _http_get_safe
from .technical_indicators import calculate_extended_indicators
from .valuation_analysis import analyze_valuation_percentile
from .industry_analysis import analyze_industry_comparison
from .sentiment import analyze_sentiment, summarize_sentiment
from .risk_control import (
    calc_dynamic_stop_loss, calc_target_price,
    calc_support_resistance, calc_position_size,
    check_risk_rules, detect_board_type
)
from .comparison import compare_two_stocks, generate_comparison_table, get_sector_stocks, analyze_sector


# ============================================================
# 东方财富 API 封装
# ============================================================

def fetch_kline(code, days=500):
    """获取 K 线历史数据"""
    market_code, market_id, _ = get_market_info(code)
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
    # 港股接口不稳定，增加重试次数和超时时间
    if market_code == 'HK':
        j = _http_get("push2his.eastmoney.com", "/api/qt/stock/kline/get", params, timeout=20, retries=12)
    else:
        j = _http_get("push2his.eastmoney.com", "/api/qt/stock/kline/get", params)
    klines = j.get("data", {}).get("klines", [])
    if not klines:
        return pd.DataFrame()
    rows = []
    for line in klines:
        parts = line.split(",")
        if len(parts) >= 11:
            rows.append({
                "日期": parts[0],
                "开盘": float(parts[1]),
                "收盘": float(parts[2]),
                "最高": float(parts[3]),
                "最低": float(parts[4]),
                "成交量": float(parts[5]),
                "成交额": float(parts[6]),
                "振幅": float(parts[7]),
                "涨跌幅": float(parts[8]),
                "涨跌额": float(parts[9]),
                "换手率": float(parts[10]),
            })
    return pd.DataFrame(rows)


def fetch_realtime_quote(code):
    """获取实时行情 + 财务指标"""
    market_code, market_id, _ = get_market_info(code)

    # 方法1：从列表中查找（仅支持 A 股）
    if market_code != 'HK':
        params = {
            "pn": "1", "pz": "5000", "po": "1", "np": "1",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": "2", "invt": "2", "fid": "f12",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
            "fields": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,f21,f23,f24,f25,f22,f11,f62,f128,f136,f115,f152",
        }
        j = _http_get_safe("82.push2.eastmoney.com", "/api/qt/clist/get", params)
        items = j.get("data", {}).get("diff", []) if j else []
        for item in items:
            if str(item.get("f12", "")) == code:
                item["market"] = market_code
                return item

    # 方法2：直接查询单只股票
    params2 = {
        "secid": get_secid(code, market_id),
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        "fields": "f43,f44,f45,f46,f47,f48,f50,f51,f52,f55,f57,f58,f60,f62,f71,f92,f105,f116,f117,f162,f167,f168,f169,f170,f171,f173,f177,f183,f184,f185,f186,f187,f188,f189,f190,f191,f192,f193",
        "invt": "2",
    }
    j2 = _http_get_safe("push2.eastmoney.com", "/api/qt/stock/get", params2)
    if j2 and j2.get("data"):
        data = j2["data"]

        def safe_float(v, default=0):
            """安全转换为浮点数"""
            if v is None or v == "-":
                return default
            try:
                return float(v)
            except (ValueError, TypeError):
                return default

        def convert_field(field):
            """使用 convert_price 转换价格字段"""
            return convert_price(data.get(field), market_code)

        def direct(field):
            """获取直接可用的字段"""
            return safe_float(data.get(field, 0))

        return {
            "f14": data.get("f58", ""),  # 名称
            "f2": convert_field("f43"),  # 最新价
            "f3": direct("f170") / 100,   # 涨跌幅 -- 需要除以100
            "f9": direct("f162") / 100,   # PE -- 需要除以100
            "f23": direct("f167") / 100,  # PB -- 需要除以100
            "f20": direct("f116"),  # 总市值（元）
            "f21": direct("f117"),  # 流通市值（元）
            "f37": direct("f173"),  # ROE（已经是百分比）
            "f49": direct("f186"),  # 毛利率（已经是百分比）
            "f40": direct("f183"),  # 营收（元）
            "f41": direct("f185"),  # 净利润同比（已经是百分比）
            "f34": direct("f188"),  # 资产负债率（已经是百分比）
            "market": market_code,  # 市场类型
        }
    return {"market": market_code}


def fetch_fund_flow(code):
    """获取个股资金流向"""
    result = {}
    indicator_map = {"今日": "f62", "3日": "f267", "5日": "f164", "10日": "f174"}
    for label, fid in indicator_map.items():
        params = {
            "fid": fid, "po": "1", "pz": "5000", "pn": "1", "np": "1",
            "fltt": "2", "invt": "2",
            "ut": "b2884a393a59ad64002292a3e90d46a5",
            "fs": "m:0+t:6+f:!2,m:0+t:13+f:!2,m:0+t:80+f:!2,m:1+t:2+f:!2,m:1+t:23+f:!2,m:0+t:7+f:!2,m:1+t:3+f:!2",
            "fields": "f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f124",
        }
        j = _http_get_safe("push2.eastmoney.com", "/api/qt/clist/get", params)
        items = j.get("data", {}).get("diff", []) if j else []
        for item in items:
            if str(item.get("f12", "")) == code:
                result[label] = item
                break
    return result


def fetch_north_flow():
    """获取北向资金数据"""
    result = {}
    for symbol in ["沪股通", "深股通"]:
        params = {
            "fields1": "f1,f2,f3,f4",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63",
            "klt": "101", "lmt": "10",
            "ut": "b2884a393a59ad64002292a3e90d46a5",
        }
        if symbol == "沪股通":
            params["secid"] = "1.000300"
        else:
            params["secid"] = "0.399001"
        try:
            j = _http_get("push2his.eastmoney.com", "/api/qt/stock/kline/get", params)
            klines = j.get("data", {}).get("klines", [])
            rows = []
            for line in klines:
                parts = line.split(",")
                if len(parts) >= 6:
                    rows.append({"日期": parts[0], "收盘": parts[2], "涨跌幅": parts[8]})
            result[symbol] = pd.DataFrame(rows)
        except Exception:
            pass
    return result


def fetch_stock_news(code):
    """获取个股新闻"""
    try:
        host = "np-listapi.eastmoney.com"
        path = f"/api/news/get"
        params = {"page_index": "1", "page_size": "20", "columns": "title,source,publish_date",
                  "source": "web", "client": "web", "biz": "web_news_col",
                  "column": "350", "filter": f'(code="{code}")'}
        j = _http_get(host, path, params)
        items = j.get("data", {}).get("list", [])
        rows = []
        for item in items:
            rows.append({
                "新闻标题": item.get("title", ""),
                "发布时间": item.get("publish_date", ""),
                "文章来源": item.get("source", ""),
            })
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()


def fetch_industry_boards():
    """获取行业板块数据"""
    params = {
        "pn": "1", "pz": "50", "po": "1", "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2", "invt": "2", "fid": "f3",
        "fs": "m:90+t:2+f:!50",
        "fields": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,f21,f23,f24,f25,f22,f33,f11,f62,f128,f136,f115,f152",
    }
    j = _http_get_safe("82.push2.eastmoney.com", "/api/qt/clist/get", params)
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
    return pd.DataFrame(rows)


def fetch_financial_report(code):
    """获取财务报表数据（现金流、资产负债表关键指标）"""
    try:
        market_code, _, _ = get_market_info(code)
        # 港股财务报表接口不同，暂不支持
        if market_code == 'HK':
            return []
        # 获取现金流量表
        params = {
            "type": "0", "sty": "APP_F10_FinanceSumFinance",
            "filter": f"(SECUCODE=\"{code}.{'SH' if market_code == 'SH' else 'SZ'}\")",
            "p": "1", "ps": "5", "sr": "-1", "st": "REPORT_DATE",
            "source": "HSF10", "client": "PC",
        }
        j = _http_get_safe("datacenter.eastmoney.com", "/api/data/get", params, retries=5)
        if j and isinstance(j, dict) and j.get("result"):
            return j["result"].get("data", [])
        return []
    except Exception:
        return []


# 常见股票名称映射（网络不稳定时的备用方案）
_STOCK_NAMES = {
    "000001": "平安银行", "000002": "万科A", "000063": "中兴通讯",
    "000100": "TCL科技", "000157": "中联重科", "000333": "美的集团",
    "000338": "潍柴动力", "000425": "徐工机械", "000538": "云南白药",
    "000568": "泸州老窖", "000636": "风华高科", "000625": "长安汽车", "000651": "格力电器",
    "000725": "京东方A", "000776": "广发证券", "000858": "五粮液",
    "000895": "双汇发展", "000938": "紫光股份", "000977": "浪潮信息",
    "002027": "分众传媒", "002049": "紫光国微", "002120": "韵达股份",
    "002142": "宁波银行", "002230": "科大讯飞", "002271": "东方雨虹",
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
        for name, code in _NAME_TO_CODE.items():
            if input_str in name or name in input_str:
                return code

    # 如果都找不到，返回原值（让后续处理报错）
    return input_str

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

def get_stock_name(code):
    """获取股票名称：先尝试 API，再用内置映射"""
    try:
        quote = fetch_realtime_quote(code)
        name = quote.get("f14", "")
        if name:
            return name
    except Exception:
        pass
    # 根据市场类型选择映射表
    try:
        market_code, _, _ = get_market_info(code)
        if market_code == 'HK':
            return _HK_STOCK_NAMES.get(code, code)
    except ValueError:
        pass
    return _STOCK_NAMES.get(code, code)


# ============================================================
# 技术指标计算
# ============================================================

def calculate_indicators(df):
    """计算技术指标（纯 pandas 实现）"""
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

    # KDJ
    low_min = low.rolling(9).min()
    high_max = high.rolling(9).max()
    rsv = (close - low_min) / (high_max - low_min) * 100
    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    indicators["K"] = k.iloc[-1]
    indicators["D"] = d.iloc[-1]
    indicators["J"] = 3 * k.iloc[-1] - 2 * d.iloc[-1]

    # RSI
    for period in [6, 12, 24]:
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
        rs = gain / loss
        indicators[f"RSI{period}"] = (100 - 100 / (1 + rs)).iloc[-1]

    # 布林带
    if len(close) >= 20:
        mid = close.rolling(20).mean()
        std = close.rolling(20).std()
        indicators["BOLL_MID"] = mid.iloc[-1]
        indicators["BOLL_UP"] = (mid + 2 * std).iloc[-1]
        indicators["BOLL_DN"] = (mid - 2 * std).iloc[-1]

    # ATR
    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    indicators["ATR14"] = tr.rolling(14).mean().iloc[-1]

    # 成交量均线
    for period in [5, 10, 20]:
        if len(volume) >= period:
            indicators[f"VOL_MA{period}"] = volume.rolling(period).mean().iloc[-1]

    # 涨跌幅统计
    indicators["最新价"] = close.iloc[-1]
    indicators["涨跌幅_今日"] = ((close.iloc[-1] / close.iloc[-2]) - 1) * 100 if len(close) >= 2 else 0
    if len(close) >= 5:
        indicators["涨跌幅_5日"] = ((close.iloc[-1] / close.iloc[-5]) - 1) * 100
    if len(close) >= 20:
        indicators["涨跌幅_20日"] = ((close.iloc[-1] / close.iloc[-20]) - 1) * 100
    if len(close) >= 60:
        indicators["涨跌幅_60日"] = ((close.iloc[-1] / close.iloc[-60]) - 1) * 100
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
    revenue_growth = safe_num(quote.get("f40", 0))  # 营收同比
    profit_growth = safe_num(quote.get("f41", 0))  # 净利润同比
    debt_ratio = safe_num(quote.get("f34", 0))  # 资产负债率

    result["PE"] = pe
    result["PB"] = pb
    result["ROE"] = roe
    result["毛利率"] = gross_margin
    result["营收同比"] = revenue_growth
    result["净利润同比"] = profit_growth
    result["资产负债率"] = debt_ratio

    # 财务排雷评分（简化版，基于可用数据）
    red_flags = []
    warnings = []

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

    trend_score = 0
    if price > ma5 > ma20:
        trend_score += 1
        details.append("均线多头排列 +1")
    if price > ma60:
        trend_score += 0.5
        details.append("价格在60日均线上方 +0.5")
    if dif > dea:
        trend_score += 0.5
        details.append("MACD金叉 +0.5")
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
        if main_today > 0 and main_5d > 0:
            score += 1
            details.append("主力资金持续流入 +1")
        elif main_today > 0:
            score += 0.5
            details.append("主力资金今日流入 +0.5")
        elif main_today < 0 and main_5d < 0:
            score -= 0.5
            details.append("主力资金持续流出 -0.5")

    # 4. 财务健康评分（0-1分）
    if financial_health:
        red_flags = financial_health.get("排雷红灯", [])
        if len(red_flags) == 0:
            score += 1
            details.append("财务排雷通过 +1")
        elif len(red_flags) <= 1:
            score += 0.5
            details.append("财务排雷1项红灯 +0.5")

    # 限制在1-5分范围
    score = max(1, min(5, score + 1))  # 基础1分 + 最高4分加成

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
    if abs(n) >= 1e8: return f"{n/1e8:.2f}亿"
    if abs(n) >= 1e4: return f"{n/1e4:.2f}万"
    return f"{n:,.2f}"

def fmt_pct(n):
    if pd.isna(n) or n == "-": return "-"
    return f"{n:.2f}%"

def safe_num(v, default=0):
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


# ============================================================
# 单文件综合报告生成
# ============================================================

def generate_report(code, name, df, indicators, fund_flow, north_flow, quote, news_df, industry_df,
                    financial_health=None, rating=None, extended_indicators=None,
                    valuation_percentile=None, industry_comparison=None,
                    weighted_score=None, stop_loss=None, target=None,
                    support_resistance=None, position=None, risk_check=None,
                    sentiment_result=None):
    """生成单个综合分析报告"""
    L = []
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    price = indicators.get("最新价", 0)

    # ── 标题 ──
    L.append(f"# {name}（{code}）股票分析报告")
    L.append(f"\n> 生成时间：{now}")
    L.append(f"> 数据区间：{df['日期'].iloc[0]} ~ {df['日期'].iloc[-1]}，共 {len(df)} 个交易日\n")

    # ── 总结 ──
    L.append("---\n## 总结\n")

    # 投资评级
    if rating:
        L.append(f"**综合评级：{rating['星级符号']}（{rating['星级']}/5星）**\n")

    # 涨跌
    chg_today = indicators.get("涨跌幅_今日", 0)
    chg_5d = indicators.get("涨跌幅_5日", 0)
    chg_20d = indicators.get("涨跌幅_20日", 0)
    chg_60d = indicators.get("涨跌幅_60日", 0)
    L.append(f"**最新价 {price} 元**，今日涨跌 {fmt_pct(chg_today)}。"
             f"近5日 {fmt_pct(chg_5d)}，近20日 {fmt_pct(chg_20d)}，近60日 {fmt_pct(chg_60d)}。")

    # 技术面一句话
    dif = indicators.get("DIF", 0)
    dea = indicators.get("DEA", 0)
    macd_signal = "MACD金叉（看涨）" if dif > dea else "MACD死叉（看跌）"
    k_val = indicators.get("K", 50)
    kdj_signal = "KDJ超买" if k_val > 80 else "KDJ超卖" if k_val < 20 else "KDJ中性"
    ma5 = indicators.get("MA5", 0)
    ma20 = indicators.get("MA20", 0)
    ma60 = indicators.get("MA60", 0)
    trend_short = "短期多头" if ma5 > ma20 else "短期空头"
    trend_mid = "中期多头" if ma20 > ma60 else "中期空头"
    L.append(f"**技术面**：{macd_signal}，{kdj_signal}，均线{trend_short}、{trend_mid}。")

    # 资金面一句话
    if fund_flow:
        main_today = safe_num(fund_flow.get("今日", {}).get("f62", 0))
        main_5d = safe_num(fund_flow.get("5日", {}).get("f62", 0))
        fund_desc = "主力资金"
        if main_today > 0:
            fund_desc += f"今日净流入{fmt_num(main_today)}"
        elif main_today < 0:
            fund_desc += f"今日净流出{fmt_num(abs(main_today))}"
        if main_5d > 0:
            fund_desc += f"，5日净流入{fmt_num(main_5d)}"
        elif main_5d < 0:
            fund_desc += f"，5日净流出{fmt_num(abs(main_5d))}"
        L.append(f"**资金面**：{fund_desc}。")

    # 基本面一句话
    pe = quote.get("f9", "")
    pb = quote.get("f23", "")
    mv = quote.get("f20", 0)
    if pe or pb:
        L.append(f"**基本面**：市盈率(动) {pe}，市净率 {pb}，总市值 {fmt_num(mv) if isinstance(mv,(int,float)) else mv}。")

    # 财务排雷一句话
    if financial_health:
        red_flags = financial_health.get("排雷红灯", [])
        warnings = financial_health.get("排雷预警", [])
        if red_flags:
            L.append(f"**财务排雷**：发现 {len(red_flags)} 项红灯信号，需重点关注。")
        elif warnings:
            L.append(f"**财务排雷**：发现 {len(warnings)} 项预警，整体可控。")
        else:
            L.append("**财务排雷**：各项指标正常，无明显风险信号。")

    L.append("")

    # ── 一、行情概览 ──
    L.append("\n---\n## 一、行情概览\n")
    last = df.iloc[-1]
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
            if "量" in label: v = fmt_num(v)
            elif "额" in label: v = fmt_num(v)
            elif "幅" in label or "跌幅" in label or "手" in label: v = f"{v}%"
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
        v = indicators.get(key)
        if v is not None:
            L.append(f"| {pn} | {fmt_pct(v)} | {desc} |")

    # ── 二、技术分析 ──
    L.append("\n---\n## 二、技术分析\n")

    # 均线
    L.append("### 2.1 均线系统\n")
    L.append("均线（MA）是将过去 N 天的收盘价取平均值连成的曲线。")
    L.append("- 价格在均线上方 → 多头（看涨）；价格在均线下方 → 空头（看跌）")
    L.append("- 短期均线（MA5/MA10）反映短期趋势，长期均线（MA60/MA120/MA250）反映中长期趋势\n")
    L.append("| 均线 | 数值 | 位置 |")
    L.append("|------|------|------|")
    for p in [5, 10, 20, 60, 120, 250]:
        ma = indicators.get(f"MA{p}")
        if ma:
            L.append(f"| MA{p} | {ma:.2f} | {'价格在上（多头）' if price > ma else '价格在下（空头）'} |")

    # MACD
    L.append("\n### 2.2 MACD\n")
    L.append("MACD（指数平滑异同移动平均线）由 DIF 线和 DEA 线组成，用于判断趋势强弱和转折。")
    L.append("- **DIF**：短期EMA(12)与长期EMA(26)的差值，反映价格动能")
    L.append("- **DEA**：DIF 的 9 日均线，用于平滑 DIF")
    L.append("- **金叉**（DIF上穿DEA）→ 买入信号；**死叉**（DIF下穿DEA）→ 卖出信号")
    L.append("- MACD柱 = (DIF - DEA) × 2，柱子由负转正 → 多头增强\n")
    dif_val = indicators.get("DIF", 0)
    dea_val = indicators.get("DEA", 0)
    macd_val = indicators.get("MACD", 0)
    L.append(f"| 指标 | 数值 | 信号 |")
    L.append(f"|------|------|------|")
    L.append(f"| DIF | {dif_val:.4f} | |")
    L.append(f"| DEA | {dea_val:.4f} | |")
    L.append(f"| MACD柱 | {macd_val:.4f} | {'金叉（看涨）' if dif_val > dea_val else '死叉（看跌）'} |")

    # KDJ
    L.append("\n### 2.3 KDJ\n")
    L.append("KDJ（随机指标）用于判断超买超卖状态，取值范围 0~100。")
    L.append("- **K值 > 80**：超买区，价格偏高，可能回调")
    L.append("- **K值 < 20**：超卖区，价格偏低，可能反弹")
    L.append("- **J值**波动最大，可提前预警拐点\n")
    kv, dv, jv = indicators.get("K",50), indicators.get("D",50), indicators.get("J",50)
    zone = "超买区（>80）" if kv > 80 else "超卖区（<20）" if kv < 20 else "中性区"
    L.append(f"| 指标 | 数值 | 区域 |")
    L.append(f"|------|------|------|")
    L.append(f"| K | {kv:.2f} | |")
    L.append(f"| D | {dv:.2f} | |")
    L.append(f"| J | {jv:.2f} | {zone} |")

    # RSI
    L.append("\n### 2.4 RSI\n")
    L.append("RSI（相对强弱指数）衡量一段时间内涨幅与跌幅的比值，取值 0~100。")
    L.append("- **> 80**：超买，短期可能见顶；**< 20**：超卖，短期可能见底")
    L.append("- **50 以上**：多方占优；**50 以下**：空方占优\n")
    for p in [6, 12, 24]:
        rsi = indicators.get(f"RSI{p}", 50)
        z = "超买（>80）" if rsi > 80 else "超卖（<20）" if rsi < 20 else "中性"
        L.append(f"- RSI{p}：{rsi:.2f}（{z}）")

    # 布林带
    L.append("\n### 2.5 布林带（BOLL）\n")
    L.append("布林带由三条轨道组成：中轨（20日均线）、上轨（中轨+2倍标准差）、下轨（中轨-2倍标准差）。")
    L.append("- 价格触及上轨 → 可能超买回调；触及下轨 → 可能超卖反弹")
    L.append("- 带宽收窄 → 即将变盘；带宽扩大 → 趋势延续\n")
    boll_up = indicators.get("BOLL_UP", 0)
    boll_mid = indicators.get("BOLL_MID", 0)
    boll_dn = indicators.get("BOLL_DN", 0)
    L.append(f"| 轨道 | 数值 |")
    L.append(f"|------|------|")
    L.append(f"| 上轨 | {boll_up:.2f} |")
    L.append(f"| 中轨 | {boll_mid:.2f} |")
    L.append(f"| 下轨 | {boll_dn:.2f} |")
    if price:
        if price > boll_up:
            L.append(f"\n> 当前价格 {price} **突破上轨**，注意回调风险")
        elif price < boll_dn:
            L.append(f"\n> 当前价格 {price} **跌破下轨**，可能超卖")
        else:
            L.append(f"\n> 当前价格 {price} 在布林带内部运行")

    # ATR
    atr = indicators.get("ATR14", 0)
    if atr:
        L.append(f"\n**ATR14**（14日平均真实波幅）：{atr:.2f} 元。ATR 越大说明近期波动越剧烈。")

    # ── 三、资金分析 ──
    L.append("\n---\n## 三、资金分析\n")

    if fund_flow:
        L.append("资金流向反映市场中不同规模资金的买卖方向。主力资金（超大单+大单）通常代表机构动向。")
        L.append("- 主力净流入 → 机构看好，可能推动上涨")
        L.append("- 主力净流出 → 机构撤离，可能带来下跌\n")

        field_labels = [
            ("f62", "f184", "主力（超大单+大单）"),
            ("f66", "f69", "超大单（>100万元）"),
            ("f72", "f75", "大单（20~100万元）"),
            ("f78", "f81", "中单（4~20万元）"),
            ("f84", "f87", "小单（<4万元）"),
        ]
        for period in ["今日", "3日", "5日", "10日"]:
            data = fund_flow.get(period)
            if not data:
                continue
            L.append(f"### {period}资金流向\n")
            L.append("| 项目 | 净流入 | 占比 |")
            L.append("|------|--------|------|")
            for fk, pk, label in field_labels:
                val = safe_num(data.get(fk, 0))
                pct = data.get(pk, "-")
                L.append(f"| {label} | {fmt_num(val)} | {pct} |")
            L.append("")
    else:
        L.append("> 暂无资金流向数据（网络不稳定，部分接口可能获取失败）\n")

    # ── 四、基本面分析 ──
    L.append("---\n## 四、基本面分析\n")

    if quote:
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
            v = quote.get(key, "-")
            if "市值" in label and isinstance(v, (int, float)): v = fmt_num(v)
            L.append(f"| {label} | {v} | {desc} |")

        L.append("\n### 4.2 盈利与成长\n")
        L.append("| 指标 | 数值 | 说明 |")
        L.append("|------|------|------|")
        for label, key, desc in [
            ("加权净资产收益率", "f37", "公司用股东的钱赚钱的能力，越高越好"),
            ("毛利率", "f49", "收入扣除直接成本后的利润率"),
            ("营业收入", "f40", "公司总收入规模"),
            ("净利润同比", "f41", "净利润同比增长率"),
            ("资产负债率", "f34", "总负债/总资产，越高财务风险越大"),
        ]:
            v = quote.get(key, "-")
            if isinstance(v, (int, float)):
                # 如果值超过1000，可能是原始数值而非百分比，显示为金额
                if abs(v) > 1000:
                    v = fmt_num(v)
                else:
                    v = f"{v:.2f}%"
            L.append(f"| {label} | {v} | {desc} |")
    else:
        L.append("> 暂无基本面数据\n")

    # ── 五、财务排雷 ──
    if financial_health:
        L.append("\n---\n## 五、财务排雷\n")
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
            ("营业收入", "营收同比", "公司总收入规模", "amount"),
            ("净利润同比", "净利润同比", "净利润同比增长率", "pct"),
            ("资产负债率", "资产负债率", "总负债/总资产，越高财务风险越大", "pct"),
        ]:
            v = financial_health.get(key, "-")
            if isinstance(v, (int, float)):
                if fmt == "amount":
                    v = fmt_num(v)
                elif fmt == "pct":
                    v = f"{v:.2f}%"
                else:
                    v = f"{v:.2f}"
            L.append(f"| {label} | {v} | {desc} |")

        # 排雷结果
        red_flags = financial_health.get("排雷红灯", [])
        warnings = financial_health.get("排雷预警", [])

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
        pe_val = financial_health.get("PE", 0)
        chg_1y = indicators.get("涨跌幅_60日", 0) * 4  # 近似年涨幅
        if pe_val > 80 or chg_1y > 200:
            L.append("\n### 5.3 逆向定价触发检查\n")
            L.append("当前估值或涨幅触发逆向定价条件，需特别关注价格是否透支未来增长：\n")
            L.append("| 触发项 | 阈值 | 当前数据 | 是否触发 |")
            L.append("|--------|------|----------|----------|")
            L.append(f"| PE-TTM | > 80 | {pe_val:.1f} | {'是' if pe_val > 80 else '否'} |")
            L.append(f"| 近似年涨幅 | > 200% | {chg_1y:.1f}% | {'是' if chg_1y > 200 else '否'} |")
            L.append("\n**建议**：高估值时需验证下一季度业绩能否支撑当前市值，否则面临估值压缩风险。")

    # ── 六、新闻动态 ──
    L.append("\n---\n## 六、新闻动态\n")
    if not news_df.empty:
        L.append("| 时间 | 标题 | 来源 |")
        L.append("|------|------|------|")
        for _, row in news_df.head(15).iterrows():
            L.append(f"| {row['发布时间']} | {row['新闻标题']} | {row['文章来源']} |")
    else:
        L.append("> 暂无近期新闻")

    # ── 七、行业板块 ──
    L.append("\n---\n## 七、行业板块排名\n")
    if not industry_df.empty:
        L.append("当日行业板块涨跌排名（前20）：\n")
        L.append("| 排名 | 板块 | 涨跌幅 | 换手率 |")
        L.append("|------|------|--------|--------|")
        for i, (_, row) in enumerate(industry_df.head(20).iterrows(), 1):
            chg = row['涨跌幅']
            L.append(f"| {i} | {row['板块']} | {fmt_pct(chg) if isinstance(chg,(int,float)) else chg} | {row.get('换手率','-')} |")
    else:
        L.append("> 暂无行业数据")

    # ── 八、扩展技术指标 ──
    if extended_indicators:
        L.append("\n---\n## 八、扩展技术指标\n")

        # RSI 背离
        rsi_div = extended_indicators.get('RSI背离', {})
        L.append("### 8.1 RSI 背离检测\n")
        L.append("RSI 背离是重要的趋势反转信号：")
        L.append("- **顶背离**：价格创新高但 RSI 未创新高，看跌信号")
        L.append("- **底背离**：价格创新低但 RSI 未创新低，看涨信号\n")
        L.append(f"- **检测结果**：{rsi_div.get('类型', '无背离')}")
        L.append(f"- **信号**：{rsi_div.get('信号', '无')}")
        L.append(f"- **可靠性**：{rsi_div.get('可靠性', '低')}")

        # MACD 柱状图
        macd_hist = extended_indicators.get('MACD柱状图', {})
        L.append("\n### 8.2 MACD 柱状图分析\n")
        L.append("MACD 柱状图反映多空动能的强弱变化：")
        L.append("- 红柱放大 → 多头增强；红柱缩小 → 多头减弱")
        L.append("- 绿柱放大 → 空头增强；绿柱缩小 → 空头减弱\n")
        L.append(f"- **连续红柱天数**：{macd_hist.get('连续红柱天数', 0)}")
        L.append(f"- **连续绿柱天数**：{macd_hist.get('连续绿柱天数', 0)}")
        L.append(f"- **趋势判断**：{macd_hist.get('趋势判断', '无')}")
        L.append(f"- **信号**：{macd_hist.get('信号', '无')}")

        # 成交量异动
        vol_anomaly = extended_indicators.get('成交量异动', {})
        L.append("\n### 8.3 成交量异动检测\n")
        L.append("成交量异动反映市场情绪和资金行为：")
        L.append("- 放量：可能有重大消息或主力行为")
        L.append("- 缩量：市场观望情绪浓厚\n")
        L.append(f"- **状态**：{vol_anomaly.get('状态', '正常')}")
        L.append(f"- **倍数**：{vol_anomaly.get('倍数', 0)}")
        L.append(f"- **信号**：{vol_anomaly.get('信号', '无')}")

        # K 线形态
        kline_patterns = extended_indicators.get('K线形态', [])
        L.append("\n### 8.4 K 线形态识别\n")
        if kline_patterns:
            L.append("| 形态 | 信号 | 可靠性 |")
            L.append("|------|------|--------|")
            for p in kline_patterns:
                L.append(f"| {p.get('形态', '')} | {p.get('信号', '')} | {p.get('可靠性', '')} |")
        else:
            L.append("近 5 个交易日未识别到典型 K 线形态。")

        # 筹码分布
        chip_dist = extended_indicators.get('筹码分布', {})
        L.append("\n### 8.5 筹码分布\n")
        L.append("筹码分布反映持仓成本结构：")
        L.append(f"- **平均成本**：{chip_dist.get('平均成本', 0):.2f} 元")
        L.append(f"- **获利盘比例**：{chip_dist.get('获利盘比例', 0) * 100:.1f}%")
        L.append(f"- **套牢盘比例**：{chip_dist.get('套牢盘比例', 0) * 100:.1f}%")
        L.append(f"- **筹码集中度**：{chip_dist.get('筹码集中度', '未知')}")

    # ── 九、估值分位数分析 ──
    if valuation_percentile:
        L.append("\n---\n## 九、估值分位数分析\n")
        L.append("估值分位数反映当前估值在近 5 年历史中的位置：")
        L.append("- 0%~20%：低估区间，可能存在投资机会")
        L.append("- 20%~40%：合理偏低")
        L.append("- 40%~60%：合理区间")
        L.append("- 60%~80%：合理偏高")
        L.append("- 80%~100%：高估区间，需注意风险\n")

        L.append("| 指标 | 当前值 | 分位数 | 估值区间 |")
        L.append("|------|--------|--------|----------|")
        for metric in ["PE", "PB", "股息率"]:
            info = valuation_percentile.get(metric, {})
            current = info.get('当前值', 0)
            percentile = info.get('分位数')
            zone = info.get('区间', '数据不足')
            pct_str = f"{percentile:.1f}%" if percentile is not None else "-"
            L.append(f"| {metric} | {current:.2f} | {pct_str} | {zone} |")

        summary = valuation_percentile.get('综合评价', '')
        if summary:
            L.append(f"\n**综合评价**：{summary}")

    # ── 十、行业对比分析 ──
    if industry_comparison:
        L.append("\n---\n## 十、行业对比分析\n")

        industry_code = industry_comparison.get('行业', '')
        L.append(f"所属行业板块：{industry_code}\n")

        # 估值对比
        valuation_comp = industry_comparison.get('估值对比', {})
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
        sentiment = industry_comparison.get('行业景气度', {})
        L.append("\n### 10.2 行业景气度\n")
        L.append(f"- **涨跌幅**：{sentiment.get('涨跌幅', 0):.2f}%")
        L.append(f"- **换手率**：{sentiment.get('换手率', 0):.2f}%")
        L.append(f"- **资金流向**：{sentiment.get('资金流入', '未知')}")
        L.append(f"- **景气度评估**：{sentiment.get('景气度', '中性')}")

        # 龙头溢价
        leader = industry_comparison.get('龙头溢价', {})
        L.append("\n### 10.3 龙头溢价分析\n")
        if leader.get('龙头公司'):
            L.append(f"- **龙头公司**：{leader.get('龙头公司', '')}")
            L.append(f"- **龙头 PE**：{leader.get('龙头PE', 0):.2f}")
            L.append(f"- **行业平均 PE**：{leader.get('行业平均PE', 0):.2f}")
            L.append(f"- **溢价率**：{leader.get('溢价率', 0):.2f}%")
            L.append(f"- **溢价合理性**：{leader.get('溢价合理性', '数据不足')}")
        else:
            L.append("> 暂无龙头溢价数据")

    # ── 十一、反证清单与跟踪因子 ──
    L.append("\n---\n## 十一、反证清单与跟踪因子\n")
    L.append("以下事实出现时，应重新评估当前结论：\n")

    # 根据当前技术状态生成反证清单
    if indicators.get("DIF", 0) > indicators.get("DEA", 0):
        L.append("1. MACD 出现死叉（DIF 下穿 DEA）")
    else:
        L.append("1. MACD 出现金叉（DIF 上穿 DEA）")

    ma20 = indicators.get("MA20", 0)
    ma60 = indicators.get("MA60", 0)
    if price > ma20:
        L.append(f"2. 股价跌破 20 日均线（当前 {ma20:.2f}）")
    else:
        L.append(f"2. 股价站上 20 日均线（当前 {ma20:.2f}）")

    if price > ma60:
        L.append(f"3. 股价跌破 60 日均线（当前 {ma60:.2f}）")
    else:
        L.append(f"3. 股价站上 60 日均线（当前 {ma60:.2f}）")

    if financial_health:
        profit_growth = financial_health.get("净利润同比", 0)
        if profit_growth > 0:
            L.append(f"4. 下一季度净利润同比转负（当前 {profit_growth:.1f}%）")
        else:
            L.append(f"4. 净利润同比继续下滑（当前 {profit_growth:.1f}%）")

    L.append("5. 主力资金连续 5 日以上净流出")
    L.append("6. 行业板块排名跌出前 30")

    # 关键因子跟踪
    L.append("\n**关键跟踪因子：**\n")
    L.append("| 因子 | 当前状态 | 信息源 | 更新频率 |")
    L.append("|------|----------|--------|----------|")
    L.append(f"| 均线趋势 | {'多头' if price > ma20 else '空头'} | K线数据 | 每日 |")
    L.append(f"| MACD信号 | {'金叉' if indicators.get('DIF',0) > indicators.get('DEA',0) else '死叉'} | K线数据 | 每日 |")
    L.append(f"| 主力资金 | {'流入' if fund_flow and safe_num(fund_flow.get('今日',{}).get('f62',0)) > 0 else '流出'} | 资金流向 | 每日 |")
    if financial_health:
        L.append(f"| 净利润增速 | {financial_health.get('净利润同比', '-')} | 财报 | 季度 |")
        L.append(f"| 资产负债率 | {financial_health.get('资产负债率', '-')} | 财报 | 季度 |")

    # ── 十二、加权信号评分 ──
    if weighted_score:
        L.append("\n---\n## 十二、加权信号评分\n")
        L.append(f"**综合评分：{weighted_score['score']:.2f}**（-10 到 +10）\n")
        L.append(f"**操作方向：{weighted_score['direction']}**")
        L.append(f"**置信度：{weighted_score['confidence']}**\n")

        L.append("**信号明细：**")
        for signal in weighted_score["signals"]:
            L.append(f"- {signal}")

        L.append(f"\n**多空统计：**")
        L.append(f"- 看多信号：{weighted_score['bullish_signals']} 个")
        L.append(f"- 看空信号：{weighted_score['bearish_signals']} 个")
        L.append(f"- 净信号数：{weighted_score['net_signals']}")

    # ── 十三、操作建议 ──
    if stop_loss and target and position:
        L.append("\n---\n## 十三、操作建议\n")
        L.append(f"**方向：{weighted_score['direction']}**")
        L.append(f"**仓位：{position['position_pct']}%**（{position['description']}）\n")

        L.append("**止损/目标位：**")
        L.append(f"- 止损价：{stop_loss['stop_loss']}（{stop_loss['description']}）")
        L.append(f"- 目标价：{target['target_price']}（{target['description']}）")
        L.append(f"- 风险收益比：1:{target['risk_reward_ratio']}")

    # ── 十四、支撑压力位 ──
    if support_resistance:
        L.append("\n---\n## 十四、支撑压力位\n")

        if support_resistance.get("resistance"):
            L.append("**压力位：**")
            L.append("| 价格 | 来源 |")
            L.append("|------|------|")
            for r in support_resistance["resistance"][:5]:
                L.append(f"| {r['price']} | {r['source']} |")

        if support_resistance.get("support"):
            L.append("\n**支撑位：**")
            L.append("| 价格 | 来源 |")
            L.append("|------|------|")
            for s in support_resistance["support"][:5]:
                L.append(f"| {s['price']} | {s['source']} |")

    # ── 十五、新闻情感分析 ──
    if sentiment_result:
        L.append("\n---\n## 十五、新闻情感分析\n")
        L.append(summarize_sentiment(sentiment_result))

    # ── 十六、风控提示 ──
    if risk_check and risk_check.get("warnings"):
        L.append("\n---\n## 十六、风控提示\n")
        for warning in risk_check["warnings"]:
            L.append(f"- [!] {warning}")

    # ── 风险提示 ──
    L.append("\n---\n## 风险提示\n")
    L.append("- 以上分析基于公开数据自动计算，请结合基本面和市场环境综合判断")
    L.append("- 技术指标存在滞后性，请结合自身风险承受能力做出投资决策")
    L.append("- 股市有风险，投资需谨慎")

    return "\n".join(L)


# ============================================================
# 主流程
# ============================================================

def analyze_stock(code, output_dir="."):
    print(f"\n{'='*60}")
    print(f"  分析股票: {code}")
    print(f"{'='*60}")

    name = get_stock_name(code)
    print(f"  股票名称: {name}")

    out_path = Path(output_dir) / "分析报告"
    out_path.mkdir(parents=True, exist_ok=True)
    print(f"  输出目录: {out_path}")

    print("\n[1/12] 获取 K 线数据...")
    df_hist = fetch_kline(code, days=500)
    print(f"  获取到 {len(df_hist)} 条 K 线数据")

    print("[2/12] 获取实时行情...")
    quote = fetch_realtime_quote(code)

    print("[3/12] 获取资金流向...")
    fund_flow = fetch_fund_flow(code)

    print("[4/12] 获取北向资金...")
    north_flow = fetch_north_flow()

    print("[5/12] 获取新闻和行业数据...")
    news_df = fetch_stock_news(code)
    industry_df = fetch_industry_boards()

    print("[6/12] 获取财务报表数据...")
    financial_data = fetch_financial_report(code)

    print("[7/12] 计算技术指标...")
    indicators = calculate_indicators(df_hist)

    # 计算扩展技术指标
    print("  计算扩展指标（RSI 背离、MACD 柱状图等）...")
    extended_indicators = calculate_extended_indicators(df_hist, indicators)

    print("[8/12] 计算加权信号评分...")
    weighted_score = calculate_weighted_score(indicators)

    print("[9/12] 计算动态止损/目标位...")
    price = indicators.get("最新价", 0)
    board_type = detect_board_type(code)
    stop_loss = calc_dynamic_stop_loss(
        current_price=price,
        atr=indicators.get("ATR14", 0),
        board_type=board_type
    )
    target = calc_target_price(
        current_price=price,
        stop_loss=stop_loss["stop_loss"]
    )

    print("[10/12] 计算支撑压力位...")
    support_resistance = calc_support_resistance(df_hist, price, indicators)

    print("[11/12] 计算仓位建议和风控检查...")
    position = calc_position_size(
        direction=weighted_score["direction"],
        score=weighted_score["score"],
        net_signals=weighted_score["net_signals"],
        has_bearish=weighted_score["bearish_signals"] > 0
    )
    risk_check = check_risk_rules(
        code=code,
        indicators=indicators,
        is_st="ST" in name,
        is_new_stock=False
    )

    print("[12/12] 分析新闻情感...")
    sentiment_result = analyze_sentiment(news_df.to_dict("records") if not news_df.empty else [])

    print("\n计算财务健康指标和投资评级...")
    financial_health = calculate_financial_health(quote, financial_data)
    rating = calculate_rating(indicators, financial_health, fund_flow)

    print("分析估值分位数...")
    valuation_percentile = analyze_valuation_percentile(code, quote, years=5)

    print("分析行业对比...")
    industry_comparison = analyze_industry_comparison(code)

    print("\n生成分析报告...")
    report = generate_report(
        code, name, df_hist, indicators, fund_flow, north_flow,
        quote, news_df, industry_df, financial_health, rating,
        extended_indicators, valuation_percentile, industry_comparison,
        weighted_score, stop_loss, target,
        support_resistance, position, risk_check, sentiment_result
    )
    today = datetime.date.today().strftime("%Y%m%d")
    report_file = out_path / f"{code}-{name}-分析报告-{today}.md"
    report_file.write_text(report, encoding="utf-8")
    print(f"  [OK] {report_file.name}")

    print(f"\n分析完成! 报告已保存至: {report_file}")
    return str(report_file)


# ============================================================
# 加权信号评分系统
# ============================================================

# 加权信号评分权重
SIGNAL_WEIGHTS = {
    "ma_alignment_bull": 2.0,     # 均线多头排列
    "ma_alignment_bear": -2.0,    # 均线空头排列
    "macd_golden_cross": 1.5,     # MACD 金叉
    "macd_death_cross": -1.5,     # MACD 死叉
    "macd_hist_positive": 0.5,    # MACD 红柱
    "macd_hist_negative": -0.5,   # MACD 绿柱
    "rsi_oversold": 1.0,          # RSI 超卖
    "rsi_overbought": -1.0,       # RSI 超买
    "rsi_extreme_overbought": -2.0,  # RSI 严重超买
    "rsi_extreme_oversold": 1.5,  # RSI 严重超卖
    "boll_lower": 1.0,            # 触及布林下轨
    "boll_upper": -1.0,           # 触及布林上轨
    "bias_alert": -1.0,           # 乖离率预警
    "volume_up": 1.0,             # 放量上涨
    "volume_down_weak": -0.5,     # 缩量上涨
    "volume_down_panic": -1.5,    # 放量下跌
    "obv_inflow": 0.5,            # OBV 资金流入
    "obv_outflow": -0.5,          # OBV 资金流出
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
    if ma5 > ma10 > ma20 > ma60:
        # 检查间距（< 1% 不认定为有效排列）
        gap_5_10 = abs(ma5 - ma10) / ma10 * 100 if ma10 > 0 else 0
        gap_10_20 = abs(ma10 - ma20) / ma20 * 100 if ma20 > 0 else 0
        if gap_5_10 > 1 and gap_10_20 > 1:
            score += SIGNAL_WEIGHTS["ma_alignment_bull"]
            signals.append("均线多头排列 +2.0")
            bullish_count += 1
    elif ma5 < ma10 < ma20 < ma60:
        gap_5_10 = abs(ma5 - ma10) / ma10 * 100 if ma10 > 0 else 0
        gap_10_20 = abs(ma10 - ma20) / ma20 * 100 if ma20 > 0 else 0
        if gap_5_10 > 1 and gap_10_20 > 1:
            score += SIGNAL_WEIGHTS["ma_alignment_bear"]
            signals.append("均线空头排列 -2.0")
            bearish_count += 1

    # 2. MACD 信号
    if dif > dea:
        score += SIGNAL_WEIGHTS["macd_golden_cross"]
        signals.append("MACD金叉 +1.5")
        bullish_count += 1
    else:
        score += SIGNAL_WEIGHTS["macd_death_cross"]
        signals.append("MACD死叉 -1.5")
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

    # 5. 乖离率检查
    if ma20 > 0 and price > 0:
        bias = (price - ma20) / ma20 * 100
        if abs(bias) > 5:
            score += SIGNAL_WEIGHTS["bias_alert"]
            signals.append(f"乖离率预警({bias:.1f}%) -1.0")
            bearish_count += 1

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
    # 获取股票 A 数据
    name_a = get_stock_name(code_a)
    quote_a = fetch_realtime_quote(code_a)
    df_a = fetch_kline(code_a, days=120)
    indicators_a = calculate_indicators(df_a)
    rating_a = calculate_rating(indicators_a, {}, {})

    stock_a = {
        "code": code_a,
        "name": name_a,
        "price": indicators_a.get("最新价", 0),
        "pe": quote_a.get("f9", 0),
        "pb": quote_a.get("f23", 0),
        "market_cap": safe_num(quote_a.get("f20", 0)),
        "change_pct": indicators_a.get("涨跌幅_今日", 0),
        "indicators": indicators_a,
        "rating": rating_a,
    }

    # 获取股票 B 数据
    name_b = get_stock_name(code_b)
    quote_b = fetch_realtime_quote(code_b)
    df_b = fetch_kline(code_b, days=120)
    indicators_b = calculate_indicators(df_b)
    rating_b = calculate_rating(indicators_b, {}, {})

    stock_b = {
        "code": code_b,
        "name": name_b,
        "price": indicators_b.get("最新价", 0),
        "pe": quote_b.get("f9", 0),
        "pb": quote_b.get("f23", 0),
        "market_cap": safe_num(quote_b.get("f20", 0)),
        "change_pct": indicators_b.get("涨跌幅_今日", 0),
        "indicators": indicators_b,
        "rating": rating_b,
    }

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
            name = get_stock_name(code)
            quote = fetch_realtime_quote(code)
            change_pct = safe_num(quote.get("f3", 0))
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
