#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
新闻情感分析模块
基于关键词匹配判断新闻正面/负面/中性
"""

from typing import List, Dict, Any


# 正面关键词
POSITIVE_KEYWORDS = [
    "上涨", "增长", "盈利", "超预期", "利好", "回购", "升级", "突破",
    "新高", "涨停", "强势", "领涨", "加仓", "增持", "看好", "乐观",
    "回暖", "反弹", "放量", "主力流入", "机构买入", "业绩预增",
]

# 负面关键词
NEGATIVE_KEYWORDS = [
    "下跌", "亏损", "下滑", "不及预期", "利空", "减持", "降级", "风险",
    "跌停", "暴跌", "弱势", "领跌", "减仓", "清仓", "看空", "悲观",
    "破位", "放量下跌", "主力流出", "机构卖出", "业绩预减", "退市",
]


def analyze_sentiment(news_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    分析新闻列表的情感倾向。

    Args:
        news_list: 新闻列表，每条包含 '新闻标题' 和 '新闻内容' 字段

    Returns:
        dict: {
            'sentiment': 'positive' / 'negative' / 'neutral',
            'positive_count': int,
            'negative_count': int,
            'summary': str,
            'key_news': list
        }
    """
    if not news_list:
        return {
            "sentiment": "neutral",
            "positive_count": 0,
            "negative_count": 0,
            "summary": "无新闻数据",
            "key_news": [],
        }

    pos_count = 0
    neg_count = 0
    key_news = []

    for news in news_list:
        title = news.get("新闻标题", "")
        content = news.get("新闻内容", "")
        text = f"{title} {content}"

        pos_score = sum(1 for kw in POSITIVE_KEYWORDS if kw in text)
        neg_score = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text)

        if pos_score > neg_score:
            pos_count += 1
            if pos_score >= 2:
                key_news.append({"title": title, "sentiment": "positive"})
        elif neg_score > pos_score:
            neg_count += 1
            if neg_score >= 2:
                key_news.append({"title": title, "sentiment": "negative"})

    # 判断整体情感
    total = pos_count + neg_count
    if total == 0:
        sentiment = "neutral"
        summary = "新闻情感中性，无明显方向"
    elif pos_count > neg_count * 1.5:
        sentiment = "positive"
        summary = f"新闻偏正面（正面 {pos_count} vs 负面 {neg_count}），市场情绪较好"
    elif neg_count > pos_count * 1.5:
        sentiment = "negative"
        summary = f"新闻偏负面（正面 {pos_count} vs 负面 {neg_count}），需注意风险"
    else:
        sentiment = "neutral"
        summary = f"新闻多空交织（正面 {pos_count} vs 负面 {neg_count}），方向不明"

    return {
        "sentiment": sentiment,
        "positive_count": pos_count,
        "negative_count": neg_count,
        "summary": summary,
        "key_news": key_news[:5],
    }


def summarize_sentiment(sentiment: Dict[str, Any]) -> str:
    """
    生成情感分析的文字摘要。

    Args:
        sentiment: analyze_sentiment 返回的情感分析结果

    Returns:
        str: 格式化的摘要文字
    """
    pos = sentiment.get("positive_count", 0)
    neg = sentiment.get("negative_count", 0)
    summary = sentiment.get("summary", "")
    key_news = sentiment.get("key_news", [])

    lines = [summary, f"正面 {pos} 条，负面 {neg} 条"]

    if key_news:
        lines.append("\n**关键新闻：**")
        for news in key_news[:3]:
            icon = "[+]" if news["sentiment"] == "positive" else "[-]"
            lines.append(f"- {icon} {news['title']}")

    return "\n".join(lines)
