#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
新闻情感分析模块
基于关键词匹配判断新闻正面/负面/中性
"""

from typing import List, Dict, Any


# 正面关键词权重（权重越高，影响越大）
POSITIVE_WEIGHTS = {
    "涨停": 3, "利好": 2, "大涨": 2, "放量": 1, "突破": 1.5,
    "回暖": 1, "增长": 1, "上涨": 1, "强势": 1.5, "新高": 2,
    "盈利": 1.5, "超预期": 2, "回购": 1.5, "升级": 1.5, "领涨": 1.5,
    "加仓": 1, "增持": 1.5, "看好": 1, "乐观": 1, "反弹": 1,
    "主力流入": 2, "机构买入": 2, "业绩预增": 2,
}

# 负面关键词权重
NEGATIVE_WEIGHTS = {
    "跌停": 3, "利空": 2, "大跌": 2, "下跌": 1, "暴跌": 2,
    "破位": 1.5, "下行": 1, "弱势": 1.5, "新低": 2, "暴雷": 3,
    "亏损": 2, "下滑": 1.5, "不及预期": 2, "减持": 1.5, "降级": 1.5,
    "风险": 1, "领跌": 1.5, "减仓": 1, "清仓": 1.5, "看空": 1,
    "悲观": 1, "放量下跌": 2, "主力流出": 2, "机构卖出": 2,
    "业绩预减": 2, "退市": 3,
}

# 按长度降序排列（长词优先匹配，避免子串误匹配）
POSITIVE_KEYWORDS = sorted(POSITIVE_WEIGHTS.keys(), key=len, reverse=True)
NEGATIVE_KEYWORDS = sorted(NEGATIVE_WEIGHTS.keys(), key=len, reverse=True)


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
    all_matched_pos = set()
    all_matched_neg = set()

    for news in news_list:
        title = news.get("新闻标题", "")
        content = news.get("新闻内容", "")
        text = f"{title} {content}"

        # 加权计数 + 已匹配关键词集合避免重复计数
        pos_score = 0
        neg_score = 0
        matched_pos = set()
        matched_neg = set()

        for kw in POSITIVE_KEYWORDS:
            if kw in text:
                pos_score += POSITIVE_WEIGHTS[kw]
                matched_pos.add(kw)
        for kw in NEGATIVE_KEYWORDS:
            if kw in text:
                neg_score += NEGATIVE_WEIGHTS[kw]
                matched_neg.add(kw)

        all_matched_pos.update(matched_pos)
        all_matched_neg.update(matched_neg)

        if pos_score > neg_score:
            pos_count += 1
            if pos_score >= 2:
                key_news.append({"title": title, "sentiment": "positive", "keywords": list(matched_pos)})
        elif neg_score > pos_score:
            neg_count += 1
            if neg_score >= 2:
                key_news.append({"title": title, "sentiment": "negative", "keywords": list(matched_neg)})

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
        "matched_keywords": {
            "positive": sorted(all_matched_pos),
            "negative": sorted(all_matched_neg),
        },
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
