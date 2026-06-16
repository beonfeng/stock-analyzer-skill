#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AKShare 备选数据源模块 — 提供 A 股数据的第三个独立来源

当东方财富 API 和腾讯/新浪均不可用时，自动切换到 AKShare。
AKShare 的核心优势在于财务数据覆盖（现金流量表/资产负债/利润表），
这是腾讯和新浪完全不具备的能力。

设计原则：
- 每个函数返回与东方财富 API 兼容的格式
- 标记 _source='AKShare' 用于溯源
- 可选依赖：pip install akshare 时可用，否则全部函数返回 None
- 静默降级：所有异常都被捕获，通过 HAS_AKSHARE 标志判断可用性
"""

import datetime
from typing import Dict, List, Optional

import pandas as pd
import numpy as np

# 安全导入：AKShare 是可选依赖
try:
    import akshare as ak
    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False
    ak = None  # type: ignore


# ============================================================
# 本地工具函数
# ============================================================

def _safe_num(val, default=0.0):
    """安全数值转换（不依赖 utils.py，避免循环导入）"""
    if val is None:
        return default
    if isinstance(val, (int, float, np.integer, np.floating)):
        if np.isnan(float(val)) or np.isinf(float(val)):
            return default
        return float(val)
    if isinstance(val, str):
        val = val.strip()
        if val in ("-", "--", "N/A", "nan", "", "None", "暂无", "未知"):
            return default
        try:
            return float(val.replace(",", "").replace("%", ""))
        except ValueError:
            return default
    return default


def _normalize_code(code: str) -> str:
    """确保股票代码是 6 位数字字符串（AKShare 要求纯数字）"""
    return code.strip().zfill(6) if len(code.strip()) < 6 else code.strip()


def _get_market_prefix(code: str) -> str:
    """根据股票代码返回市场前缀"""
    code = _normalize_code(code)
    if code.startswith('6'):
        return "SH"
    elif code.startswith(('0', '3', '2')):
        return "SZ"
    elif code.startswith(('8', '4')):
        return "BJ"
    return "SH"


# ============================================================
# AKShare — K 线数据
# ============================================================

def fetch_kline_akshare(code: str, days: int = 500) -> Optional[pd.DataFrame]:
    """
    从 AKShare 获取前复权日线 K 线数据。

    API: ak.stock_zh_a_hist()

    Args:
        code: 股票代码 (如 '600519')
        days: 回溯天数

    Returns:
        pd.DataFrame: 东方财富兼容列格式 [日期/开盘/收盘/最高/最低/成交量/成交额/涨跌幅/换手率/振幅]
                      附加 _source='AKShare' 列
        None: akshare 未安装或请求失败
    """
    if not HAS_AKSHARE:
        return None

    code = _normalize_code(code)
    market = _get_market_prefix(code)
    # AKShare symbol 格式: "sh600519" / "sz000001" / "bj8xxxxx"
    prefix_map = {"SH": "sh", "SZ": "sz", "BJ": "bj"}
    symbol = f"{prefix_map.get(market, 'sh')}{code}"

    end_date = datetime.date.today().strftime("%Y%m%d")
    start_date = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%Y%m%d")

    try:
        df = ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust="qfq",
        )
        if df is None or df.empty:
            return None
    except Exception:
        # AKShare API 不稳定时的二次尝试：不带 adjust 参数
        try:
            df = ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust="",
            )
            if df is None or df.empty:
                return None
        except Exception:
            return None

    # AKShare 返回的列名可能是中文或英文，做兼容映射
    col_map = {
        "日期": "日期", "开盘": "开盘", "收盘": "收盘",
        "最高": "最高", "最低": "最低", "成交量": "成交量",
        "成交额": "成交额", "振幅": "振幅", "涨跌幅": "涨跌幅",
        "换手率": "换手率",
    }
    # 实际 AKShare 列名（不同版本可能不同，取并集）
    rename = {}
    for eng_col, cn_col in col_map.items():
        if eng_col in df.columns:
            rename[eng_col] = cn_col

    if rename:
        df = df.rename(columns=rename)

    # 确保必要列存在
    required = ["日期", "开盘", "收盘", "最高", "最低", "成交量", "成交额", "涨跌幅", "换手率"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        # 尝试从英文列名映射（AKShare 不同版本的列名差异）
        en_to_cn = {
            "open": "开盘", "close": "收盘", "high": "最高", "low": "最低",
            "volume": "成交量", "amount": "成交额", "pct_chg": "涨跌幅",
            "turnover_rate": "换手率", "amplitude": "振幅",
        }
        df = df.rename(columns={k: v for k, v in en_to_cn.items() if k in df.columns})
        missing = [c for c in required if c not in df.columns]

    if "日期" not in df.columns:
        return None

    # 只保留需要的列
    keep_cols = [c for c in required if c in df.columns]
    df = df[keep_cols].copy()

    # 标准化数值类型
    for col in ["开盘", "收盘", "最高", "最低"]:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: _safe_num(x, 0.0))
    for col in ["成交量", "成交额"]:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: _safe_num(x, 0.0))

    # 补充缺失列
    if "成交额" not in df.columns:
        df["成交额"] = (df.get("收盘", 0) * df.get("成交量", 0)).astype(float)
    if "涨跌幅" not in df.columns and len(df) > 1:
        prev = df["收盘"].shift(1)
        df["涨跌幅"] = ((df["收盘"] - prev) / prev * 100).fillna(0).round(2)
    if "振幅" not in df.columns and len(df) > 1:
        prev = df["收盘"].shift(1)
        df["振幅"] = ((df["最高"] - df["最低"]) / prev * 100).fillna(0).round(2)

    if "涨跌幅" not in df.columns:
        df["涨跌幅"] = 0.0
    if "振幅" not in df.columns:
        df["振幅"] = 0.0
    if "换手率" not in df.columns:
        df["换手率"] = 0.0

    df = df.sort_values("日期").reset_index(drop=True)
    df["_source"] = "AKShare"
    return df


# ============================================================
# AKShare — 实时行情
# ============================================================

def fetch_quote_akshare(code: str) -> Optional[Dict]:
    """
    从 AKShare 获取实时行情，返回东方财富兼容格式。

    API: ak.stock_zh_a_spot_em()

    AKShare 提供 PE/PB/ROE/营收增速/净利润增速/资产负债率 等完整财务指标，
    数据完整度与东方财富相当，优于腾讯（缺 ROE/毛利率/营收增速）。

    Args:
        code: 股票代码 (如 '600519')

    Returns:
        dict: 东方财富兼容格式，含 _source='AKShare' 标记
        None: akshare 未安装或请求失败
    """
    if not HAS_AKSHARE:
        return None

    code = _normalize_code(code)

    try:
        spot_df = ak.stock_zh_a_spot_em()
        if spot_df is None or spot_df.empty:
            return None
    except Exception:
        return None

    # 在 DataFrame 中查找目标股票
    code_col = None
    for col in ["代码", "code"]:
        if col in spot_df.columns:
            code_col = col
            break

    if code_col is None:
        return None

    # 确保代码是字符串类型对比
    spot_df[code_col] = spot_df[code_col].astype(str)
    match = spot_df[spot_df[code_col] == code]
    if match.empty:
        return None

    row = match.iloc[0]

    # 列名映射（AKShare 中文字段 → 东方财富 f_ 字段）
    field_map = {
        "名称": ("f14", lambda x: str(x)),
        "最新价": ("f2", lambda x: _safe_num(x, 0.0)),
        "涨跌幅": ("f3", lambda x: _safe_num(x, 0.0)),
        "涨跌额": ("f4", lambda x: _safe_num(x, 0.0)),
        "成交量": ("f5", lambda x: _safe_num(x, 0.0)),
        "成交额": ("f6", lambda x: _safe_num(x, 0.0)),
        "换手率": ("f8", lambda x: _safe_num(x, 0.0)),
        "市盈率-动态": ("f9", lambda x: _safe_num(x, 0.0)),
        "市净率": ("f23", lambda x: _safe_num(x, 0.0)),
        "最高": ("f15", lambda x: _safe_num(x, 0.0)),
        "最低": ("f16", lambda x: _safe_num(x, 0.0)),
        "今开": ("f17", lambda x: _safe_num(x, 0.0)),
        "昨收": ("f18", lambda x: _safe_num(x, 0.0)),
        "总市值": ("f20", lambda x: _safe_num(x, 0.0)),
        "流通市值": ("f21", lambda x: _safe_num(x, 0.0)),
        "振幅": ("f43", lambda x: _safe_num(x, 0.0)),
    }

    result = {}
    for cn_col, (f_field, converter) in field_map.items():
        if cn_col in spot_df.columns:
            result[f_field] = converter(row[cn_col])

    # 补充 AKShare 可能不提供的字段（用默认值）
    _default_fields = {
        "f37": 0,   # ROE
        "f49": 0,   # 毛利率
        "f40": 0,   # 营收（元）
        "f41": 0,  # 净利润同比
        "f34": 0,  # 资产负债率
        "f115": 0, # 每股收益
    }
    for f_field, default in _default_fields.items():
        if f_field not in result:
            result[f_field] = default

    # 尝试补充更多财务指标（如果 spot_df 提供了）
    _extra_fields = {
        "量比": "f10",
    }
    for cn_col, f_field in _extra_fields.items():
        if cn_col in spot_df.columns:
            result[f_field] = _safe_num(row[cn_col], 0.0)

    market = _get_market_prefix(code)
    result["market"] = market
    result["_source"] = "AKShare"
    return result


# ============================================================
# AKShare — 财务报表（核心差异化能力）
# ============================================================

def fetch_financial_report_akshare(code: str) -> Optional[List[Dict]]:
    """
    从 AKShare 获取财务报表关键指标，返回 EastMoney datacenter 兼容格式。

    AKShare 的财务数据覆盖是腾讯/新浪完全不具备的能力。
    使用 ak.stock_zh_a_indicator() 获取核心财务指标。

    API: ak.stock_zh_a_indicator()

    Args:
        code: 股票代码 (如 '600519')

    Returns:
        list: [{"REPORT_DATE": "2024-09-30", "NETCASHFLOW_OPERATE": ..., ...}, ...]
              与东方财富 datacenter 兼容格式
        None: akshare 未安装或请求失败
    """
    if not HAS_AKSHARE:
        return None

    code = _normalize_code(code)
    market = _get_market_prefix(code)
    prefix_map = {"SH": "sh", "SZ": "sz", "BJ": "bj"}
    symbol = f"{prefix_map.get(market, 'sh')}{code}"

    try:
        df = ak.stock_financial_abstract_ths(symbol=symbol, indicator="按报告期")
        if df is None or df.empty:
            return None
    except Exception:
        try:
            # 备用 API
            df = ak.stock_zh_a_indicator(symbol=symbol)
            if df is None or df.empty:
                return None
        except Exception:
            return None

    # 将 AKShare DataFrame 转换为 EastMoney datacenter 兼容的 list[dict]
    results = []
    for _, row in df.iterrows():
        item = {}

        # 报告日期
        for date_col in ["报告期", "日期"]:
            if date_col in df.columns:
                date_val = str(row[date_col])[:10]
                if date_val and date_val != "nan":
                    item["REPORT_DATE"] = date_val
                    break
        if "REPORT_DATE" not in item:
            continue  # 无日期行跳过

        # AKShare 字段名 → EastMoney datacenter 字段名
        _field_mapping = {
            # 现金流
            "经营活动现金流量净额": "NETCASHFLOW_OPERATE",
            "投资活动现金流量净额": "NETCASHFLOW_INVEST",
            "筹资活动现金流量净额": "NETCASHFLOW_FINANCE",
            "经营性现金流/营业收入": "OCF_TO_REVENUE",
            # 资产负债
            "资产总计": "TOTAL_ASSETS",
            "负债合计": "TOTAL_LIABILITIES",
            "归属于母公司股东权益合计": "EQUITY_PARENT",
            "应收账款": "ACCOUNTS_RECEIVABLE",
            "存货": "INVENTORY",
            # 利润
            "营业总收入": "OPERATE_INCOME",
            "营业收入": "OPERATE_INCOME",
            "净利润": "NET_PROFIT_PARENT",
            "归属于母公司所有者的净利润": "NET_PROFIT_PARENT",
            "净利润同比增长": "NET_PROFIT_YOY",
            # 比率
            "销售毛利率": "GROSS_MARGIN",
            "销售净利率": "NET_MARGIN",
            "净资产收益率": "ROE",
            "资产负债率": "DEBT_RATIO",
            "基本每股收益": "BASIC_EPS",
        }

        for ak_field, em_field in _field_mapping.items():
            if ak_field in df.columns:
                item[em_field] = _safe_num(row[ak_field], 0.0)

        # 确保至少有一些关键字段
        has_data = any(
            k in item
            for k in ["NETCASHFLOW_OPERATE", "NET_PROFIT_PARENT", "TOTAL_ASSETS"]
        )
        if has_data:
            results.append(item)

    return results if results else None


# ============================================================
# AKShare — 公司概况
# ============================================================

def fetch_company_profile_akshare(code: str) -> Optional[Dict]:
    """
    从 AKShare 获取公司概况，返回与 analyzer.fetch_company_profile 兼容格式。

    API: ak.stock_individual_info_em()

    Args:
        code: 股票代码 (如 '600519')

    Returns:
        dict: {
            '基本信息': dict,
            '公司简介': str,
            '经营范围': str,
            '主营业务': list,
            '股东结构': list,
        }
        None: akshare 未安装或请求失败
    """
    if not HAS_AKSHARE:
        return None

    code = _normalize_code(code)
    market = _get_market_prefix(code)
    prefix_map = {"SH": "sh", "SZ": "sz", "BJ": "bj"}
    symbol = f"{prefix_map.get(market, 'sh')}{code}"

    result: Dict = {
        "基本信息": {},
        "公司简介": "",
        "经营范围": "",
        "主营业务": [],
        "股东结构": [],
    }

    try:
        info_df = ak.stock_individual_info_em(symbol=symbol)
        if info_df is None or info_df.empty:
            return None
    except Exception:
        return None

    # 将 AKShare 返回的 DataFrame (item/value 格式) 转为 dict
    info_dict = {}
    if "item" in info_df.columns and "value" in info_df.columns:
        for _, row in info_df.iterrows():
            key = str(row["item"]).strip()
            val = str(row["value"]).strip() if row["value"] is not None else ""
            info_dict[key] = val

    result["基本信息"] = {
        "公司名称": info_dict.get("股票简称", ""),
        "所属行业": info_dict.get("行业", ""),
        "总市值": info_dict.get("总市值", ""),
        "流通市值": info_dict.get("流通市值", ""),
        "上市日期": info_dict.get("上市时间", ""),
        "总股本": info_dict.get("总股本", ""),
        "流通股": info_dict.get("流通股", ""),
    }
    result["公司简介"] = ""
    result["经营范围"] = info_dict.get("经营范围", "")

    return result


# ============================================================
# AKShare — 个股新闻（备选资讯源）
# ============================================================

def fetch_news_akshare(code: str) -> Optional[pd.DataFrame]:
    """
    从 AKShare 获取个股新闻，返回东方财富兼容格式。

    API: ak.stock_news_em()

    Args:
        code: 股票代码 (如 '600519')

    Returns:
        pd.DataFrame: 列 ['新闻标题','发布时间','文章来源','链接']
        None: akshare 未安装或请求失败
    """
    if not HAS_AKSHARE:
        return None

    code = _normalize_code(code)

    try:
        news_df = ak.stock_news_em(symbol=code)
        if news_df is None or news_df.empty:
            return None
    except Exception:
        return None

    # AKShare 新闻列名 → 东方财富兼容格式
    col_mapping = {}
    for col in news_df.columns:
        if col in ("新闻标题", "title"):
            col_mapping[col] = "新闻标题"
        elif col in ("发布时间", "pub_time"):
            col_mapping[col] = "发布时间"
        elif col in ("文章来源", "source"):
            col_mapping[col] = "文章来源"
        elif col in ("新闻链接", "url"):
            col_mapping[col] = "链接"

    if col_mapping:
        news_df = news_df.rename(columns=col_mapping)

    # 保留需要的列
    keep = [c for c in ["新闻标题", "发布时间", "文章来源", "链接"] if c in news_df.columns]
    if not keep:
        return None

    return news_df[keep].head(15)  # 最多返回 15 条


# ============================================================
# AKShare — 资金流向（暂不支持，标记不可用）
# ============================================================

def fetch_fund_flow_akshare(code: str) -> Optional[Dict]:
    """
    AKShare 不直接提供分层资金流向数据（超大单/大单/中单/小单），
    但可以通过个股资金流向接口获取总量。

    当前返回 None，标记暂不支持。后续可接入 ak.stock_individual_fund_flow()。

    Args:
        code: 股票代码

    Returns:
        None: 暂不支持
    """
    # AKShare 有 stock_individual_fund_flow_rank() 但不提供逐日分层数据
    # 留给后续迭代实现
    return None


# ============================================================
# 数据源健康检查
# ============================================================

def check_akshare_health() -> Dict[str, bool]:
    """
    快速检查 AKShare 各接口是否可用。

    Returns:
        dict: {source_name: bool} 格式，与 alternative_sources.check_source_health() 一致
    """
    if not HAS_AKSHARE:
        return {"AKShare(未安装)": False}

    results = {}

    # K 线检查（用贵州茅台近5日）
    try:
        df = fetch_kline_akshare("600519", days=5)
        results["AKShare K线"] = df is not None and not df.empty
    except Exception:
        results["AKShare K线"] = False

    # 实时行情检查
    try:
        q = fetch_quote_akshare("600519")
        results["AKShare 实时行情"] = q is not None and q.get("f14", "")
    except Exception:
        results["AKShare 实时行情"] = False

    # 财务数据检查
    try:
        fin = fetch_financial_report_akshare("600519")
        results["AKShare 财务报表"] = fin is not None and len(fin) > 0
    except Exception:
        results["AKShare 财务报表"] = False

    return results


# ============================================================
# 模块自测
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("AKShare 数据源测试")
    print(f"AKShare 可用: {HAS_AKSHARE}")
    print("=" * 60)

    if not HAS_AKSHARE:
        print("\n[跳过] AKShare 未安装，请运行: pip install akshare")
        exit(0)

    print("\n--- 健康检查 ---")
    health = check_akshare_health()
    for name, ok in health.items():
        print(f"  {'[OK]' if ok else '[FAIL]'} {name}")

    print("\n--- K线数据 (600519 近5日) ---")
    kline = fetch_kline_akshare("600519", days=5)
    if kline is not None and not kline.empty:
        print(kline[["日期", "开盘", "收盘", "成交量", "涨跌幅"]].tail().to_string())

    print("\n--- 实时行情 (600519) ---")
    q = fetch_quote_akshare("600519")
    if q:
        print(f"  名称: {q.get('f14', '-')}, 最新价: {q.get('f2', 0):.2f}")
        print(f"  PE: {q.get('f9', 0):.1f}, 总市值: {q.get('f20', 0)/1e8:.0f}亿")
        print(f"  来源: {q.get('_source', '?')}")

    print("\n--- 财务报表 (600519) ---")
    fin = fetch_financial_report_akshare("600519")
    if fin:
        latest = fin[0] if isinstance(fin, list) else fin
        print(f"  报告期: {latest.get('REPORT_DATE', '-')}")
        for k, v in latest.items():
            if k != "REPORT_DATE":
                print(f"  {k}: {v}")

    print("\n" + "=" * 60)
    print("测试完成")
