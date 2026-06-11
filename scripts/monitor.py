#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
反证清单监控模块 — 检查历史分析报告中的反证条件是否已生效

功能：
- 扫描分析报告目录，解析反证清单
- 获取实时行情数据，逐一检查反证条件
- 生成监控报告，标注已触发的条件
"""

import re
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from .analyzer import (
    fetch_kline,
    fetch_realtime_quote,
    fetch_fund_flow,
    calculate_indicators,
    get_stock_name,
    safe_num,
)


def parse_report_filename(filepath: Path) -> Optional[Dict[str, str]]:
    """
    从文件名解析股票代码、名称、日期。

    文件名格式: {code}-{name}-分析报告-{YYYYMMDD}.md
    例: 002594-比亚迪-分析报告-20260605.md
    例: AAPL-苹果-分析报告-20260606.md
    """
    # 支持 A 股/港股（6 位数字）和美股（字母 ticker）
    pattern = r"^([A-Za-z0-9.]+)-(.+)-分析报告-(\d{8})\.md$"
    m = re.match(pattern, filepath.name)
    if not m:
        return None
    return {
        "code": m.group(1),
        "name": m.group(2),
        "date": m.group(3),
        "path": str(filepath),
    }


def parse_counter_evidence(content: str) -> List[Dict[str, Any]]:
    """
    从报告内容中解析反证清单。

    返回条件列表，每个条件包含:
      - index: 序号
      - text: 原始文本
      - type: 条件类型 (macd_cross / price_ma / profit_growth / fund_flow / sector_rank)
      - direction: 方向 (bullish / bearish)，表示该条件触发意味着什么
      - params: 附带参数（如均线值）
    """
    # 定位反证清单章节（标题可能带有后缀如"与跟踪因子"）
    # 支持中文数字（一、二、三...）和阿拉伯数字（1、2、3...）
    header_pattern = r"##\s*(?:[一二三四五六七八九十百]+|\d+)\s*[、.]\s*反证清单.*"
    match = re.search(header_pattern, content)
    if not match:
        return []

    # 提取到下一个 ## 标题为止（兼容无分隔线的报告）
    start = match.end()
    next_section = re.search(r"\n##\s", content[start:])
    end = start + next_section.start() if next_section else len(content)
    section = content[start:end]

    conditions = []

    # 解析编号列表: "1. MACD 出现死叉（DIF 下穿 DEA）"
    lines = section.split("\n")
    for line in lines:
        line = line.strip()
        m = re.match(r"^(\d+)\.\s*(.+)$", line)
        if not m:
            continue

        index = int(m.group(1))
        text = m.group(2)
        condition = {"index": index, "text": text, "type": "unknown", "direction": "unknown", "params": {}}

        # MACD 交叉
        if "MACD" in text and ("死叉" in text or "金叉" in text):
            negated = any(neg in text for neg in ["未出现", "未形成", "暂无", "尚未", "避免", "预警"])
            if negated:
                condition["type"] = "macd_cross_negated"  # 标记为非触发条件
            else:
                condition["type"] = "macd_cross"
                if "死叉" in text:
                    condition["direction"] = "bearish"  # 当前看多，死叉出现=反证
                else:
                    condition["direction"] = "bullish"  # 当前看空，金叉出现=反证

        # 股价与均线关系
        elif "20 日均线" in text or "20日均线" in text:
            condition["type"] = "price_ma20"
            ma_match = re.search(r"当前\s*([\d.]+)", text)
            if ma_match:
                condition["params"]["ma_value"] = float(ma_match.group(1))
            if "跌破" in text:
                condition["direction"] = "bearish"  # 当前价格在MA20之上，跌破=反证
            else:
                condition["direction"] = "bullish"  # 当前价格在MA20之下，站上=反证

        elif "60 日均线" in text or "60日均线" in text:
            condition["type"] = "price_ma60"
            ma_match = re.search(r"当前\s*([\d.]+)", text)
            if ma_match:
                condition["params"]["ma_value"] = float(ma_match.group(1))
            if "跌破" in text:
                condition["direction"] = "bearish"
            else:
                condition["direction"] = "bullish"

        # 净利润增速
        elif "净利润" in text:
            condition["type"] = "profit_growth"
            growth_match = re.search(r"当前\s*([-\d.]+)%", text)
            if growth_match:
                condition["params"]["prev_growth"] = float(growth_match.group(1))
            if "转负" in text:
                condition["direction"] = "bearish"  # 当前增长为正，转负=反证
            else:
                condition["direction"] = "bullish"  # 当前下滑，继续下滑=反证（看空信号强化）

        # 主力资金连续流出
        elif "主力资金" in text and "流出" in text:
            condition["type"] = "fund_flow_streak"
            condition["direction"] = "bearish"

        # 行业板块排名
        elif "行业板块" in text or "板块排名" in text:
            condition["type"] = "sector_rank"
            condition["direction"] = "bearish"

        conditions.append(condition)

    return conditions


def check_condition_now(condition: Dict[str, Any], indicators: Dict, fund_flow: Dict, quote: Dict = None) -> Dict[str, Any]:
    """
    检查单个反证条件当前是否已触发。

    返回:
      - triggered: bool
      - current_value: 当前值
      - detail: 视情况而定的详情
    """
    ctype = condition["type"]
    result = {"triggered": False, "current_value": None, "detail": ""}

    if ctype == "macd_cross":
        dif = indicators.get("DIF", 0)
        dea = indicators.get("DEA", 0)
        is_golden = dif > dea
        result["current_value"] = f"DIF={dif:.4f}, DEA={dea:.4f}"
        if condition["direction"] == "bearish":
            # 反证条件是"出现死叉"，检查是否已死叉
            result["triggered"] = not is_golden
            result["detail"] = f"{'死叉' if not is_golden else '仍为金叉'}"
        else:
            # 反证条件是"出现金叉"，检查是否已金叉
            result["triggered"] = is_golden
            result["detail"] = f"{'金叉' if is_golden else '仍为死叉'}"

    elif ctype in ("price_ma20", "price_ma60"):
        price = indicators.get("最新价", 0)
        ma_key = "MA20" if ctype == "price_ma20" else "MA60"
        ma_value = indicators.get(ma_key, 0)
        if ma_value == 0:
            result["triggered"] = False
            result["current_value"] = f"价格={price:.2f}, {ma_key}=N/A"
            result["detail"] = "均线数据不可用，无法判断"
            return result
        result["current_value"] = f"价格={price:.2f}, {ma_key}={ma_value:.2f}"

        if condition["direction"] == "bearish":
            # 反证条件是"跌破均线"，检查价格是否在均线之下
            result["triggered"] = price < ma_value
            result["detail"] = f"{'已跌破' if price < ma_value else '未跌破'}"
        else:
            # 反证条件是"站上均线"，检查价格是否在均线之上
            result["triggered"] = price > ma_value
            result["detail"] = f"{'已站上' if price > ma_value else '未站上'}"

    elif ctype == "profit_growth":
        # 从实时行情获取净利润同比（quote.f41 字段）
        raw_f41 = quote.get("f41") if quote else None
        if raw_f41 is not None and str(raw_f41).strip() not in ("", "-", "N/A", "--"):
            profit_growth = safe_num(raw_f41)
            result["current_value"] = f"净利润同比={profit_growth:.1f}%"
            if condition["direction"] == "bearish":
                result["triggered"] = profit_growth < 0
                result["detail"] = f"{'已转负' if profit_growth < 0 else '仍为正增长'}"
            else:
                prev_growth = condition["params"].get("prev_growth", 0)
                result["triggered"] = profit_growth < prev_growth
                result["detail"] = f"{'继续下滑' if profit_growth < prev_growth else '有所改善'}"
        else:
            result["current_value"] = "需季报更新后检查"
            result["detail"] = "需要最新财报数据，当前跳过"

    elif ctype == "fund_flow_streak":
        # 检查 5 日资金流向
        flow_5d = safe_num(fund_flow.get("5日", {}).get("f62", 0))
        flow_3d = safe_num(fund_flow.get("3日", {}).get("f62", 0))
        flow_today = safe_num(fund_flow.get("今日", {}).get("f62", 0))
        result["current_value"] = f"今日={flow_today/1e8:.2f}亿, 3日={flow_3d/1e8:.2f}亿, 5日={flow_5d/1e8:.2f}亿"

        # 5日累计净流出为负 → 连续流出
        if flow_5d < 0:
            result["triggered"] = True
            result["detail"] = f"5日累计净流出 {flow_5d/1e8:.2f} 亿"
        else:
            result["triggered"] = False
            result["detail"] = f"5日累计净流入 {flow_5d/1e8:.2f} 亿"

    elif ctype == "sector_rank":
        # 尝试从行情数据获取所属行业信息
        # 由于板块排名需要实时查询，此处标记为需要手动确认
        result["triggered"] = False
        result["current_value"] = "需板块数据"
        result["detail"] = "建议查看行业板块排名是否仍在前30名"

    return result


def scan_reports(report_dir: str, codes: Optional[List[str]] = None, days: Optional[int] = None) -> List[Dict[str, str]]:
    """
    扫描报告目录，返回匹配的分析报告列表。

    Args:
        report_dir: 报告目录路径
        codes: 可选的股票代码过滤列表
        days: 只扫描最近 N 天的报告（按文件名日期）

    Returns:
        报告信息列表
    """
    report_path = Path(report_dir)
    if not report_path.exists():
        return []

    reports = []
    cutoff_date = None
    if days:
        cutoff_date = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%Y%m%d")

    for f in sorted(report_path.glob("*-分析报告-*.md"), reverse=True):
        info = parse_report_filename(f)
        if not info:
            continue

        # 按代码过滤
        if codes and info["code"] not in codes:
            continue

        # 按日期过滤
        if cutoff_date and info["date"] < cutoff_date:
            continue

        reports.append(info)

    return reports


def monitor_reports(report_dir: str, codes: Optional[List[str]] = None, days: Optional[int] = None) -> Dict[str, Any]:
    """
    核心监控函数：扫描报告、检查反证条件。

    Args:
        report_dir: 报告目录
        codes: 可选的股票代码过滤
        days: 只检查最近 N 天的报告

    Returns:
        {
            "scan_time": str,
            "reports_scanned": int,
            "results": [
                {
                    "code": str,
                    "name": str,
                    "report_date": str,
                    "report_path": str,
                    "conditions": [
                        {
                            "index": int,
                            "text": str,
                            "type": str,
                            "direction": str,
                            "triggered": bool,
                            "current_value": str,
                            "detail": str,
                        }
                    ],
                    "triggered_count": int,
                }
            ],
            "total_triggered": int,
        }
    """
    reports = scan_reports(report_dir, codes, days)

    if not reports:
        return {
            "scan_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "reports_scanned": 0,
            "results": [],
            "total_triggered": 0,
            "message": "未找到匹配的分析报告",
        }

    results = []
    total_triggered = 0
    # 按报告日期排序（最新优先），再按代码去重
    reports.sort(key=lambda r: r["date"], reverse=True)
    seen_codes = {}
    for r in reports:
        if r["code"] not in seen_codes:
            seen_codes[r["code"]] = r

    for code, report_info in seen_codes.items():
        filepath = Path(report_info["path"])
        try:
            content = filepath.read_text(encoding="utf-8")
        except Exception as e:
            results.append({
                "code": code,
                "name": report_info["name"],
                "report_date": report_info["date"],
                "report_path": report_info["path"],
                "conditions": [],
                "triggered_count": 0,
                "error": f"读取报告失败: {e}",
            })
            continue

        # 解析反证清单
        conditions = parse_counter_evidence(content)
        if not conditions:
            results.append({
                "code": code,
                "name": report_info["name"],
                "report_date": report_info["date"],
                "report_path": report_info["path"],
                "conditions": [],
                "triggered_count": 0,
                "note": "报告中未找到反证清单",
            })
            continue

        # 获取实时数据
        try:
            quote = fetch_realtime_quote(code)
            df = fetch_kline(code, days=120)
            indicators = calculate_indicators(df)
            fund_flow = fetch_fund_flow(code)
        except Exception as e:
            results.append({
                "code": code,
                "name": report_info["name"],
                "report_date": report_info["date"],
                "report_path": report_info["path"],
                "conditions": [],
                "triggered_count": 0,
                "error": f"获取数据失败: {e}",
            })
            continue

        # 逐一检查条件
        checked = []
        triggered_count = 0
        for cond in conditions:
            check = check_condition_now(cond, indicators, fund_flow, quote)
            checked.append({
                **cond,
                "triggered": check["triggered"],
                "current_value": check["current_value"],
                "detail": check["detail"],
            })
            if check["triggered"]:
                triggered_count += 1

        total_triggered += triggered_count
        results.append({
            "code": code,
            "name": report_info["name"],
            "report_date": report_info["date"],
            "report_path": report_info["path"],
            "conditions": checked,
            "triggered_count": triggered_count,
        })

    return {
        "scan_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "reports_scanned": len(results),
        "results": results,
        "total_triggered": total_triggered,
    }


def format_monitor_report(data: Dict[str, Any], use_emoji: bool = True) -> str:
    """
    将监控结果格式化为可读的 Markdown 报告。

    Args:
        data: monitor_reports() 返回的数据
        use_emoji: 是否使用 emoji（False 时使用 ASCII 兼容字符）
    """
    # 字符映射
    if use_emoji:
        OK = "✅"
        WARN = "⚠️"
        ALERT = "🚨"
        FAIL = "❌"
        SQUARE = "⬜"
    else:
        OK = "[OK]"
        WARN = "[!]"
        ALERT = "[!!]"
        FAIL = "[X]"
        SQUARE = "[--]"

    L = []
    L.append("# 反证清单监控报告\n")
    L.append(f"> 扫描时间: {data['scan_time']}")
    L.append(f"> 扫描报告数: {data['reports_scanned']}")
    L.append(f"> 触发条件总数: {data['total_triggered']}\n")

    if data.get("message"):
        L.append(f"**{data['message']}**\n")
        return "\n".join(L)

    L.append("---\n")

    for stock in data["results"]:
        code = stock["code"]
        name = stock["name"]
        date = stock["report_date"]
        triggered = stock["triggered_count"]

        # 标题带状态标记
        if stock.get("error"):
            status = f"{FAIL} 数据获取失败"
        elif triggered > 0:
            status = f"{ALERT} {triggered} 项已触发"
        elif stock.get("note"):
            status = f"{WARN} 无反证清单"
        else:
            status = f"{OK} 全部未触发"

        L.append(f"## {name}（{code}）— {status}\n")
        L.append(f"- 报告日期: {date}")
        L.append(f"- 报告路径: `{stock['report_path']}`\n")

        if stock.get("error"):
            L.append(f"> {WARN} {stock['error']}\n")
            continue

        if stock.get("note"):
            L.append(f"> {stock['note']}\n")
            continue

        if not stock["conditions"]:
            continue

        # 条件明细表格
        L.append("| # | 反证条件 | 当前状态 | 是否触发 |")
        L.append("|---|----------|----------|----------|")

        for cond in stock["conditions"]:
            idx = cond["index"]
            text = cond["text"]
            detail = cond.get("detail", "")
            triggered_mark = f"{ALERT} **已触发**" if cond.get("triggered") else f"{SQUARE} 未触发"
            L.append(f"| {idx} | {text} | {detail} | {triggered_mark} |")

        L.append("")

    # 汇总
    L.append("---\n")
    L.append("## 汇总\n")

    triggered_stocks = [s for s in data["results"] if s["triggered_count"] > 0]
    if triggered_stocks:
        L.append(f"**{WARN} {len(triggered_stocks)} 只股票有反证条件已触发：**\n")
        for s in triggered_stocks:
            L.append(f"- **{s['name']}（{s['code']}）**：{s['triggered_count']} 项触发")
        L.append(f"\n> 建议重新评估这些股票的分析结论。")
    else:
        L.append(f"**{OK} 所有股票的反证条件均未触发，当前分析结论仍然有效。**")

    L.append("")
    return "\n".join(L)
