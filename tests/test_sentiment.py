import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from sentiment import analyze_sentiment, summarize_sentiment


def test_analyze_sentiment_positive():
    """测试正面新闻情感分析"""
    news_list = [
        {"新闻标题": "公司业绩超预期增长", "新闻内容": "净利润大幅增长"},
        {"新闻标题": "获得重大利好消息", "新闻内容": "股价上涨突破新高"},
    ]
    result = analyze_sentiment(news_list)
    assert result["sentiment"] == "positive"
    assert result["positive_count"] >= 2


def test_analyze_sentiment_negative():
    """测试负面新闻情感分析"""
    news_list = [
        {"新闻标题": "公司业绩下滑亏损", "新闻内容": "净利润大幅下跌"},
        {"新闻标题": "高管减持风险", "新闻内容": "利空消息不断"},
    ]
    result = analyze_sentiment(news_list)
    assert result["sentiment"] == "negative"
    assert result["negative_count"] >= 2


def test_analyze_sentiment_neutral():
    """测试中性新闻情感分析"""
    news_list = [
        {"新闻标题": "公司召开股东大会", "新闻内容": "审议年度报告"},
        {"新闻标题": "行业标准发布", "新闻内容": "新规将于下月实施"},
    ]
    result = analyze_sentiment(news_list)
    assert result["sentiment"] == "neutral"


def test_summarize_sentiment():
    """测试情感摘要生成"""
    sentiment = {
        "sentiment": "positive",
        "positive_count": 5,
        "negative_count": 2,
        "summary": "新闻偏正面",
        "key_news": [{"title": "利好消息", "sentiment": "positive"}],
    }
    summary = summarize_sentiment(sentiment)
    assert "正面" in summary
    assert "5" in summary
