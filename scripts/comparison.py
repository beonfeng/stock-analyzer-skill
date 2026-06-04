#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对比分析模块
支持双股对比、板块分析
"""

from typing import Dict, Any, List, Optional


def compare_two_stocks(
    stock_a: Dict[str, Any],
    stock_b: Dict[str, Any]
) -> Dict[str, Any]:
    """
    对比两只股票。

    Args:
        stock_a: 股票 A 的数据
        stock_b: 股票 B 的数据

    Returns:
        dict: {
            'comparison': list,
            'winner': str,
            'summary': str
        }
    """
    comparison = []
    score_a = 0
    score_b = 0

    # 1. 估值对比（PE 越低越好）
    pe_a = stock_a.get("pe", 0)
    pe_b = stock_b.get("pe", 0)
    pe_winner = "a" if pe_a < pe_b and pe_a > 0 else "b" if pe_b < pe_a and pe_b > 0 else "tie"
    comparison.append({
        "dimension": "市盈率(PE)",
        "stock_a": f"{pe_a:.1f}",
        "stock_b": f"{pe_b:.1f}",
        "winner": pe_winner,
        "note": "越低越便宜",
    })
    if pe_winner == "a":
        score_a += 1
    elif pe_winner == "b":
        score_b += 1

    # 2. PB 对比
    pb_a = stock_a.get("pb", 0)
    pb_b = stock_b.get("pb", 0)
    pb_winner = "a" if pb_a < pb_b and pb_a > 0 else "b" if pb_b < pb_a and pb_b > 0 else "tie"
    comparison.append({
        "dimension": "市净率(PB)",
        "stock_a": f"{pb_a:.1f}",
        "stock_b": f"{pb_b:.1f}",
        "winner": pb_winner,
        "note": "越低越便宜",
    })
    if pb_winner == "a":
        score_a += 1
    elif pb_winner == "b":
        score_b += 1

    # 3. 市值对比
    mv_a = stock_a.get("market_cap", 0)
    mv_b = stock_b.get("market_cap", 0)
    mv_winner = "a" if mv_a > mv_b else "b" if mv_b > mv_a else "tie"
    comparison.append({
        "dimension": "总市值",
        "stock_a": f"{mv_a/1e8:.0f}亿",
        "stock_b": f"{mv_b/1e8:.0f}亿",
        "winner": mv_winner,
        "note": "越大越稳",
    })

    # 4. 涨跌幅对比
    chg_a = stock_a.get("change_pct", 0)
    chg_b = stock_b.get("change_pct", 0)
    chg_winner = "a" if chg_a > chg_b else "b" if chg_b > chg_a else "tie"
    comparison.append({
        "dimension": "今日涨跌",
        "stock_a": f"{chg_a:.2f}%",
        "stock_b": f"{chg_b:.2f}%",
        "winner": chg_winner,
        "note": "",
    })

    # 5. RSI 对比
    rsi_a = stock_a.get("indicators", {}).get("RSI6", 50)
    rsi_b = stock_b.get("indicators", {}).get("RSI6", 50)
    # RSI 50-70 之间较好
    rsi_score_a = 70 - abs(rsi_a - 60)  # 越接近 60 越好
    rsi_score_b = 70 - abs(rsi_b - 60)
    rsi_winner = "a" if rsi_score_a > rsi_score_b else "b" if rsi_score_b > rsi_score_a else "tie"
    comparison.append({
        "dimension": "RSI强弱",
        "stock_a": f"{rsi_a:.1f}",
        "stock_b": f"{rsi_b:.1f}",
        "winner": rsi_winner,
        "note": "50-70较佳",
    })
    if rsi_winner == "a":
        score_a += 1
    elif rsi_winner == "b":
        score_b += 1

    # 6. MACD 对比
    dif_a = stock_a.get("indicators", {}).get("DIF", 0)
    dea_a = stock_a.get("indicators", {}).get("DEA", 0)
    dif_b = stock_b.get("indicators", {}).get("DIF", 0)
    dea_b = stock_b.get("indicators", {}).get("DEA", 0)
    macd_a = dif_a - dea_a
    macd_b = dif_b - dea_b
    macd_winner = "a" if macd_a > macd_b else "b" if macd_b > macd_a else "tie"
    comparison.append({
        "dimension": "MACD动能",
        "stock_a": f"{macd_a:.4f}",
        "stock_b": f"{macd_b:.4f}",
        "winner": macd_winner,
        "note": "DIF-DEA",
    })
    if macd_winner == "a":
        score_a += 1
    elif macd_winner == "b":
        score_b += 1

    # 7. 综合评级对比
    rating_a = stock_a.get("rating", {}).get("分数", 0)
    rating_b = stock_b.get("rating", {}).get("分数", 0)
    rating_winner = "a" if rating_a > rating_b else "b" if rating_b > rating_a else "tie"
    comparison.append({
        "dimension": "综合评级",
        "stock_a": f"{rating_a:.1f}分",
        "stock_b": f"{rating_b:.1f}分",
        "winner": rating_winner,
        "note": "越高越好",
    })
    if rating_winner == "a":
        score_a += 1
    elif rating_winner == "b":
        score_b += 1

    # 计算总赢家
    if score_a > score_b:
        winner = "a"
        summary = f"{stock_a.get('name', '股票A')} 综合表现更优（{score_a}:{score_b}）"
    elif score_b > score_a:
        winner = "b"
        summary = f"{stock_b.get('name', '股票B')} 综合表现更优（{score_b}:{score_a}）"
    else:
        winner = "tie"
        summary = f"两只股票综合表现相当（{score_a}:{score_b}）"

    return {
        "comparison": comparison,
        "winner": winner,
        "score_a": score_a,
        "score_b": score_b,
        "summary": summary,
    }


def generate_comparison_table(
    comparison: List[Dict],
    name_a: str,
    name_b: str
) -> str:
    """
    生成对比表格的 Markdown 文本。

    Args:
        comparison: 对比数据列表
        name_a: 股票 A 名称
        name_b: 股票 B 名称

    Returns:
        str: Markdown 格式的对比表格
    """
    lines = [
        f"| 对比维度 | {name_a} | {name_b} | 胜出 | 说明 |",
        f"|----------|----------|----------|------|------|",
    ]

    for item in comparison:
        dim = item["dimension"]
        val_a = item["stock_a"]
        val_b = item["stock_b"]
        winner = item.get("winner", "tie")
        note = item.get("note", "")

        if winner == "a":
            winner_str = f"✓ {name_a}"
        elif winner == "b":
            winner_str = f"✓ {name_b}"
        else:
            winner_str = "平手"

        lines.append(f"| {dim} | {val_a} | {val_b} | {winner_str} | {note} |")

    return "\n".join(lines)
