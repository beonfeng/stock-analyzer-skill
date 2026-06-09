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

from .market_utils import get_market_info, convert_price, is_hk_stock, is_us_stock, get_secid
from .utils import _http_get, _http_get_safe, safe_num, is_trading_day, print_request_stats, reset_request_stats
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
# 模块级状态
# ============================================================

_last_analysis_time = 0  # 上次分析完成时间戳，用于连续调用冷却保护


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
    # 港股 API 不稳定，需要更多重试（最坏情况：12次重试 × 4秒间隔 ≈ 48秒）
    # 港股 kline 接口经常返回空数据或超时，多次重试可显著提高成功率
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

    # 方法1（优先）：直接查询单只股票 — O(1) 请求，适用于所有市场
    params2 = {
        "secid": get_secid(code, market_id),
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        "fields": "f43,f44,f45,f46,f47,f48,f50,f51,f52,f55,f57,f58,f60,f62,f71,f92,f105,f116,f117,f162,f167,f168,f169,f170,f171,f173,f177,f183,f184,f185,f186,f187,f188,f189,f190,f191,f192,f193",
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
            if abs(pe) < 0.01 and pe != 0:
                print(f"  [警告] PE 值异常小 ({pe})，f162 原始值={pe_raw}，可能不需要除以100")

        # PB：f167 API 返回基点值，需除以 100
        pb_raw = data.get("f167", "-")
        if pb_raw != "-" and pb_raw is not None:
            pb = direct("f167") / 100
            if abs(pb) < 0.01 and pb != 0:
                print(f"  [警告] PB 值异常小 ({pb})，f167 原始值={pb_raw}，可能不需要除以100")
        else:
            pb = 0

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
            "market": market_code,  # 市场类型
        }
    # 方法2（备选）：从列表中遍历查找 — O(n) 性能较差，仅 A 股可用
    # 注意：此方法会请求约 5000 只股票的列表再逐个匹配，单股分析建议优先使用方法1
    if market_code in ('SH', 'SZ'):
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

    return {"market": market_code}


def fetch_fund_flow(code):
    """获取个股资金流向（单次请求获取所有周期）"""
    _, market_id, _ = get_market_info(code)
    params = {
        "secid": get_secid(code, market_id),
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "fields": "f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f124,f267,f164,f174",
    }
    j = _http_get_safe("push2.eastmoney.com", "/api/qt/stock/get", params)
    if not j or not j.get("data"):
        return {}
    data = j["data"]
    # 今日的详细数据（含超大单/大单/中单/小单拆分）
    today_data = {
        "f62": data.get("f62", 0),   # 今日主力净流入
        "f184": data.get("f184", 0), # 今日主力净流入占比
        "f66": data.get("f66", 0), "f69": data.get("f69", 0),   # 超大单
        "f72": data.get("f72", 0), "f75": data.get("f75", 0),   # 大单
        "f78": data.get("f78", 0), "f81": data.get("f81", 0),   # 中单
        "f84": data.get("f84", 0), "f87": data.get("f87", 0),   # 小单
    }
    # 多周期仅返回主力净流入（API 仅提供汇总值）
    result = {
        "今日": today_data,
        "3日": {"f62": data.get("f267", 0)},
        "5日": {"f62": data.get("f164", 0)},
        "10日": {"f62": data.get("f174", 0)},
    }
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
        except Exception as e:
            print(f"  [警告] 北向资金({symbol})获取失败: {e}")
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
    except Exception as e:
        print(f"  [警告] 新闻数据获取失败: {e}")
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
    except Exception as e:
        print(f"  [警告] 财务报表获取失败: {e}")
        return []


def fetch_company_profile(code):
    """
    获取公司概况：基本资料 + 主营业务构成。

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
    result = {
        '基本信息': {},
        '公司简介': '',
        '经营范围': '',
        '主营业务': [],
        '股东结构': [],
    }

    try:
        market_code, _, _ = get_market_info(code)
        # 港股接口不同，暂不支持
        if market_code == 'HK':
            return result
    except ValueError:
        return result

    secucode = f"{code}.{'SH' if market_code == 'SH' else 'SZ'}"

    # 1. 获取公司基本资料
    try:
        params1 = {
            'code': f"{'SH' if market_code == 'SH' else 'SZ'}{code}",
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
                latest_date = max(by_date.keys())
                latest_items = by_date[latest_date]
                total_income = sum(it.get('MAIN_BUSINESS_INCOME', 0) for it in latest_items)

                for it in sorted(latest_items, key=lambda x: x.get('MAIN_BUSINESS_INCOME', 0), reverse=True):
                    name = it.get('ITEM_NAME', '')
                    income = it.get('MAIN_BUSINESS_INCOME', 0)
                    ratio = (income / total_income * 100) if total_income > 0 else 0
                    gross = it.get('GROSS_RPOFIT_RATIO', 0)
                    result['主营业务'].append({
                        '名称': name,
                        '收入': income / 1e8,  # 转为亿元
                        '占比': ratio,
                        '毛利率': gross,
                        '报告期': latest_date,
                    })
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
                latest3 = max(by_date3.keys())
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
        return name, quote if quote else {"market": ""}
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

    # KDJ
    low_min = low.rolling(9).min()
    high_max = high.rolling(9).max()
    rsv = (close - low_min) / (high_max - low_min).replace(0, 1e-10) * 100  # 避免除零
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
        loss_safe = loss.replace(0, 1e-10)  # 避免除零
        rs = gain / loss_safe
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

    # 原始成交量（供量价分析使用）
    indicators["成交量"] = volume.iloc[-1]

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
                 'price', 'now']
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def _section_title(ctx):
    """标题"""
    L = []
    L.append(f"# {ctx.name}（{ctx.code}）股票分析报告")
    L.append(f"\n> 生成时间：{ctx.now}")
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
    if overseas and (overseas[0].get('占比', 100) or 100) < 5:
        opportunities.append(f"**海外市场**：境外收入占比仅 {(overseas[0].get('占比', 0) or 0):.1f}%，海外市场拓展潜力大")

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
        top1 = holders[0].get('占流通股比', 0)
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

    # 估值判断
    if pe > 0:
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
    macd_signal = "MACD金叉（看涨）" if dif > dea else "MACD死叉（看跌）"
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
    pe = safe_num(ctx.quote.get("f9", 0)) if ctx.quote else 0
    pb = safe_num(ctx.quote.get("f23", 0)) if ctx.quote else 0
    mv = ctx.quote.get("f20", 0) if ctx.quote else 0
    if pe or pb:
        pe_str = f"{pe:.2f}" if pe else "-"
        pb_str = f"{pb:.2f}" if pb else "-"
        L.append(f"**基本面**：市盈率(动) {pe_str}，市净率 {pb_str}，总市值 {fmt_num(mv) if isinstance(mv,(int,float)) else mv}。")

    # 财务排雷一句话
    if ctx.financial_health:
        red_flags = ctx.financial_health.get("排雷红灯", [])
        warnings = ctx.financial_health.get("排雷预警", [])
        if red_flags:
            L.append(f"**财务排雷**：发现 {len(red_flags)} 项红灯信号，需重点关注。")
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
    dif_signal = "短期趋势强于长期" if dif_val > 0 else "短期趋势弱于长期"
    dea_signal = "中期趋势向上" if dea_val > 0 else "中期趋势向下"
    macd_signal = "金叉（看涨）" if dif_val > dea_val else "死叉（看跌）"
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
            L.append(f"### {period}资金流向\n")
            L.append("| 项目 | 净流入 | 占比 | 说明 |")
            L.append("|------|--------|------|------|")
            for fk, pk, label in field_labels:
                val = safe_num(data.get(fk, 0))
                pct = data.get(pk, "-")
                desc = "资金看好" if val > 0 else "资金撤离" if val < 0 else "持平"
                L.append(f"| {label} | {fmt_num(val)} | {pct} | {desc} |")
            L.append("")
    else:
        L.append("> 暂无资金流向数据（网络不稳定，部分接口可能获取失败）\n")

    return L


def _section_fundamentals(ctx):
    """基本面分析"""
    L = []
    L.append("---\n## 四、基本面分析\n")

    if ctx.quote:
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
            v = ctx.quote.get(key, "-")
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
            v = ctx.quote.get(key, "-")
            if isinstance(v, (int, float)):
                # 如果值超过1000，可能是原始数值而非百分比，显示为金额
                if abs(v) > 1000:
                    v = fmt_num(v)
                else:
                    v = f"{v:.2f}%"
            L.append(f"| {label} | {v} | {desc} |")
    else:
        L.append("> 暂无基本面数据\n")

    return L


def _section_financial_screen(ctx):
    """财务排雷"""
    L = []
    if not ctx.financial_health:
        return L

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
        v = ctx.financial_health.get(key, "-")
        if isinstance(v, (int, float)):
            if fmt == "amount":
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
    if len(ctx.df) >= 250:
        chg_1y = ((ctx.df["收盘"].iloc[-1] / ctx.df["收盘"].iloc[-250]) - 1) * 100
    elif len(ctx.df) >= 60:
        chg_60 = ctx.indicators.get("涨跌幅_60日", 0)
        chg_1y = ((1 + chg_60 / 100) ** 4 - 1) * 100  # 复合增长率
    else:
        chg_1y = ctx.indicators.get("涨跌幅_60日", 0) * 4  # 数据不足时简单线性近似
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
    L.append("\n---\n## 六、新闻动态\n")
    if not ctx.news_df.empty:
        L.append("| 时间 | 标题 | 来源 |")
        L.append("|------|------|------|")
        for _, row in ctx.news_df.head(15).iterrows():
            L.append(f"| {row['发布时间']} | {row['新闻标题']} | {row['文章来源']} |")
    else:
        L.append("> 暂无近期新闻")

    return L


def _section_industry_board(ctx):
    """行业板块"""
    L = []
    L.append("\n---\n## 七、行业板块排名\n")
    if not ctx.industry_df.empty:
        L.append("当日行业板块涨跌排名（前20）：\n")
        L.append("| 排名 | 板块 | 涨跌幅 | 换手率 |")
        L.append("|------|------|--------|--------|")
        for i, (_, row) in enumerate(ctx.industry_df.head(20).iterrows(), 1):
            chg = row['涨跌幅']
            L.append(f"| {i} | {row['板块']} | {fmt_pct(chg) if isinstance(chg,(int,float)) else chg} | {row.get('换手率','-')} |")
    else:
        L.append("> 暂无行业数据")

    return L


def _section_extended_indicators(ctx):
    """扩展技术指标"""
    L = []
    if not ctx.extended_indicators:
        return L

    L.append("\n---\n## 八、扩展技术指标\n")

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

    L.append("\n---\n## 十、行业对比分析\n")

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
    L.append(f"- **涨跌幅**：{sentiment.get('涨跌幅', 0):.2f}%")
    L.append(f"- **换手率**：{sentiment.get('换手率', 0):.2f}%")
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
    L.append("\n---\n## 十一、反证清单与跟踪因子\n")
    L.append("以下事实出现时，应重新评估当前结论：\n")

    # 根据当前技术状态生成反证清单
    if ctx.indicators.get("DIF", 0) > ctx.indicators.get("DEA", 0):
        L.append("1. MACD 出现死叉（DIF 下穿 DEA）")
    else:
        L.append("1. MACD 出现金叉（DIF 上穿 DEA）")

    ma20 = ctx.indicators.get("MA20", 0)
    ma60 = ctx.indicators.get("MA60", 0)
    if ctx.price > ma20:
        L.append(f"2. 股价跌破 20 日均线（当前 {ma20:.2f}）")
    else:
        L.append(f"2. 股价站上 20 日均线（当前 {ma20:.2f}）")

    if ctx.price > ma60:
        L.append(f"3. 股价跌破 60 日均线（当前 {ma60:.2f}）")
    else:
        L.append(f"3. 股价站上 60 日均线（当前 {ma60:.2f}）")

    if ctx.financial_health:
        profit_growth = ctx.financial_health.get("净利润同比", 0)
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
    L.append(f"| 均线趋势 | {'多头' if ctx.price > ma20 else '空头'} | K线数据 | 每日 |")
    L.append(f"| MACD信号 | {'金叉' if ctx.indicators.get('DIF',0) > ctx.indicators.get('DEA',0) else '死叉'} | K线数据 | 每日 |")
    L.append(f"| 主力资金 | {'流入' if ctx.fund_flow and safe_num(ctx.fund_flow.get('今日',{}).get('f62',0)) > 0 else '流出'} | 资金流向 | 每日 |")
    if ctx.financial_health:
        L.append(f"| 净利润增速 | {ctx.financial_health.get('净利润同比', '-')} | 财报 | 季度 |")
        L.append(f"| 资产负债率 | {ctx.financial_health.get('资产负债率', '-')} | 财报 | 季度 |")

    return L


def _section_weighted_score(ctx):
    """加权信号评分"""
    L = []
    if not ctx.weighted_score:
        return L

    L.append("\n---\n## 十二、加权信号评分\n")
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
    if not (ctx.stop_loss and ctx.target and ctx.position):
        return L

    L.append("\n---\n## 十三、操作建议\n")
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

    L.append("\n---\n## 十四、支撑压力位\n")

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

    L.append("\n---\n## 十五、新闻情感分析\n")
    L.append(summarize_sentiment(ctx.sentiment_result))

    return L


def _section_risk_control(ctx):
    """风控提示"""
    L = []
    if not (ctx.risk_check and ctx.risk_check.get("warnings")):
        return L

    L.append("\n---\n## 十六、风控提示\n")
    for warning in ctx.risk_check["warnings"]:
        L.append(f"- [!] {warning}")

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
                    sentiment_result=None, company_profile=None):
    """生成单个综合分析报告"""
    ctx = ReportContext(
        code=code, name=name, df=df, indicators=indicators,
        fund_flow=fund_flow, north_flow=north_flow, quote=quote,
        news_df=news_df, industry_df=industry_df,
        financial_health=financial_health or {}, rating=rating,
        extended_indicators=extended_indicators,
        valuation_percentile=valuation_percentile,
        industry_comparison=industry_comparison,
        weighted_score=weighted_score, stop_loss=stop_loss,
        target=target, support_resistance=support_resistance,
        position=position, risk_check=risk_check,
        sentiment_result=sentiment_result,
        company_profile=company_profile,
        price=indicators.get("最新价", 0),
        now=datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    )

    L = []
    for section_fn in [
        _section_title, _section_company_profile, _section_company_analysis,
        _section_summary, _section_market_overview, _section_technical_analysis,
        _section_fund_flow, _section_fundamentals, _section_financial_screen,
        _section_news, _section_industry_board, _section_extended_indicators,
        _section_valuation_percentile, _section_industry_comparison,
        _section_counter_evidence, _section_weighted_score,
        _section_trade_suggestion, _section_support_resistance,
        _section_sentiment, _section_risk_control, _section_disclaimer
    ]:
        L.extend(section_fn(ctx))

    return "\n".join(L)


# ============================================================
# 主流程
# ============================================================

def analyze_stock(code, output_dir="."):
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

    # 预估请求数
    estimated_requests = 13 if us_mode else 26
    print(f"  [预估] 本次分析预计发送约 {estimated_requests} 次 API 请求（含行业对比数据）")
    print(f"  [限制] 每分钟 ≤12 次，会话上限 60 次，超过自动冷却")
    print()

    print("[1/13] 获取 K 线数据...")
    df_hist = fetch_kline(code, days=500)
    print(f"  获取到 {len(df_hist)} 条 K 线数据")

    print("[2/13] 获取实时行情... [复用已有数据，无额外请求]")

    if us_mode:
        # 美股：跳过东方财富专属数据
        print("[3/13] 资金流向... [N/A 美股不适用]")
        fund_flow = {}

        print("[4/13] 北向资金... [N/A 美股不适用]")
        north_flow = {}

        print("[5/13] 新闻和行业数据... [N/A 美股不适用]")
        news_df = pd.DataFrame()
        industry_df = pd.DataFrame()

        print("[6/13] 财务报表... [使用东方财富行情数据]")
        financial_data = {}
    else:
        print("[3/13] 获取资金流向...")
        fund_flow = fetch_fund_flow(code)

        print("[4/13] 获取北向资金...")
        north_flow = fetch_north_flow()

        print("[5/13] 获取新闻和行业数据...")
        news_df = fetch_stock_news(code)
        industry_df = fetch_industry_boards()

        print("[6/13] 获取财务报表数据...")
        financial_data = fetch_financial_report(code)

    print("[7/13] 获取公司概况...")
    company_profile = fetch_company_profile(code)

    print("[8/13] 计算技术指标...")
    indicators = calculate_indicators(df_hist)

    # 计算扩展技术指标
    print("  计算扩展指标（RSI 背离、MACD 柱状图等）...")
    extended_indicators = calculate_extended_indicators(df_hist, indicators)

    print("[9/13] 计算加权信号评分...")
    weighted_score = calculate_weighted_score(indicators)

    print("[10/13] 计算动态止损/目标位...")
    price = indicators.get("最新价", 0)
    # 美股使用 main 板型（无涨跌幅限制，但计算逻辑兼容）
    board_type = "main" if us_mode else detect_board_type(code)
    stop_loss = calc_dynamic_stop_loss(
        current_price=price,
        atr=indicators.get("ATR14", 0),
        board_type=board_type
    )
    target = calc_target_price(
        current_price=price,
        stop_loss=stop_loss["stop_loss"]
    )

    print("[11/13] 计算支撑压力位...")
    support_resistance = calc_support_resistance(df_hist, price, indicators)

    print("[12/13] 计算仓位建议和风控检查...")
    position = calc_position_size(
        direction=weighted_score["direction"],
        score=weighted_score["score"],
        net_signals=weighted_score["net_signals"],
        has_bearish=weighted_score["bearish_signals"] > 0
    )
    # 根据股票名称判断是否为 ST 股票
    is_st = "ST" in name.upper() if name else False
    risk_check = check_risk_rules(
        code=code,
        indicators=indicators,
        is_st=is_st,
        is_new_stock=False
    )

    if us_mode:
        print("[13/13] 新闻情感... [N/A 美股不适用]")
        sentiment_result = {"score": 0, "label": "N/A", "positive": 0, "negative": 0, "neutral": 0}

        print("\n计算财务健康指标和投资评级...")
        financial_health = calculate_financial_health(quote, financial_data)
        rating = calculate_rating(indicators, financial_health, fund_flow)

        print("估值分位... [N/A 美股无历史分位数据]")
        valuation_percentile = None

        print("行业对比... [N/A 美股不适用]")
        industry_comparison = None
    else:
        print("[13/13] 分析新闻情感...")
        sentiment_result = analyze_sentiment(news_df.to_dict("records") if not news_df.empty else [])

        print("\n计算财务健康指标和投资评级...")
        financial_health = calculate_financial_health(quote, financial_data)
        rating = calculate_rating(indicators, financial_health, fund_flow)

        print("分析估值分位数...")
        valuation_percentile = analyze_valuation_percentile(code, quote, years=5, kline_data=df_hist)

        print("分析行业对比...")
        industry_comparison = analyze_industry_comparison(code)

    print("\n生成分析报告...")
    report = generate_report(
        code, name, df_hist, indicators, fund_flow, north_flow,
        quote, news_df, industry_df, financial_health, rating,
        extended_indicators, valuation_percentile, industry_comparison,
        weighted_score, stop_loss, target,
        support_resistance, position, risk_check, sentiment_result,
        company_profile
    )
    today = datetime.date.today().strftime("%Y%m%d")
    report_file = (out_path / f"{code}-{name}-分析报告-{today}.md").resolve()
    report_file.write_text(report, encoding="utf-8")
    print(f"  [OK] {report_file.name}")

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
    "macd_golden_cross": 1.5,     # MACD 金叉 — 趋势转折确认信号
    "macd_death_cross": -1.5,     # MACD 死叉 — 趋势转折确认信号
    "macd_hist_positive": 0.5,    # MACD 红柱 — 多头动能辅助确认
    "macd_hist_negative": -0.5,   # MACD 绿柱 — 空头动能辅助确认
    "rsi_oversold": 1.0,          # RSI 超卖（<30）— 超卖反弹机会
    "rsi_overbought": -1.0,       # RSI 超买（>70）— 超买回调风险
    "rsi_extreme_overbought": -2.0,  # RSI 严重超买（>80）— 高度危险信号，加重权重
    "rsi_extreme_oversold": 1.5,  # RSI 严重超卖（<20）— 强反弹信号，加重权重
    "boll_lower": 1.0,            # 触及布林下轨 — 短期超卖支撑
    "boll_upper": -1.0,           # 触及布林上轨 — 短期超买压力
    "bias_alert": -1.0,           # 乖离率预警（>5%）— 均值回归风险
    "volume_up": 1.0,             # 放量上涨 — 量价配合看多
    "volume_down_weak": -0.5,     # 缩量上涨 — 上涨动能不足
    "volume_down_panic": -1.5,    # 放量下跌 — 恐慌性抛售信号
    "obv_inflow": 0.5,            # OBV 资金流入 — 资金面辅助确认
    "obv_outflow": -0.5,          # OBV 资金流出 — 资金面辅助确认
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
    reset_request_stats()

    # 获取股票 A 数据（复用 quote，避免重复请求）
    name_a, quote_a = get_stock_name(code_a, return_quote=True)
    df_a = fetch_kline(code_a, days=120)
    indicators_a = calculate_indicators(df_a)
    rating_a = calculate_rating(indicators_a, {}, {})

    stock_a = {
        "code": code_a,
        "name": name_a,
        "price": indicators_a.get("最新价", 0),
        "pe": quote_a.get("f9", 0) if quote_a else 0,
        "pb": quote_a.get("f23", 0) if quote_a else 0,
        "market_cap": safe_num(quote_a.get("f20", 0)) if quote_a else 0,
        "change_pct": indicators_a.get("涨跌幅_今日", 0),
        "indicators": indicators_a,
        "rating": rating_a,
    }

    # 获取股票 B 数据（复用 quote，避免重复请求）
    name_b, quote_b = get_stock_name(code_b, return_quote=True)
    df_b = fetch_kline(code_b, days=120)
    indicators_b = calculate_indicators(df_b)
    rating_b = calculate_rating(indicators_b, {}, {})

    stock_b = {
        "code": code_b,
        "name": name_b,
        "price": indicators_b.get("最新价", 0),
        "pe": quote_b.get("f9", 0) if quote_b else 0,
        "pb": quote_b.get("f23", 0) if quote_b else 0,
        "market_cap": safe_num(quote_b.get("f20", 0)) if quote_b else 0,
        "change_pct": indicators_b.get("涨跌幅_今日", 0),
        "indicators": indicators_b,
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
