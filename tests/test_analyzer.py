# tests/test_analyzer.py
import sys
from pathlib import Path

# 添加项目根目录到 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.analyzer import calculate_weighted_score, compare_stocks_wrapper, analyze_sector_wrapper


def test_calculate_weighted_score_bullish():
    """测试多头信号评分"""
    indicators = {
        "最新价": 100.0,
        "MA5": 101.0,
        "MA10": 100.5,
        "MA20": 100.0,
        "MA60": 99.0,
        "DIF": 2.0,
        "DEA": 1.5,
        "RSI6": 45.0,
        "K": 55.0,
        "BOLL_UP": 110.0,
        "BOLL_DN": 90.0,
        "VOL_MA5": 1000000,
        "成交量": 1500000,
    }
    result = calculate_weighted_score(indicators)

    assert "score" in result
    assert "signals" in result
    assert "direction" in result
    assert result["score"] > 0  # 多头信号应得正分
    assert result["direction"] in ["buy", "sell", "hold"]


def test_calculate_weighted_score_bearish():
    """测试空头信号评分"""
    indicators = {
        "最新价": 90.0,
        "MA5": 89.0,
        "MA10": 89.5,
        "MA20": 90.0,
        "MA60": 91.0,
        "DIF": -2.0,
        "DEA": -1.5,
        "RSI6": 75.0,
        "K": 85.0,
        "BOLL_UP": 110.0,
        "BOLL_DN": 85.0,
        "VOL_MA5": 1000000,
        "成交量": 1200000,
    }
    result = calculate_weighted_score(indicators)

    assert result["score"] < 0  # 空头信号应得负分
    assert result["direction"] in ["buy", "sell", "hold"]


def test_calculate_weighted_score_signal_count():
    """测试信号计数"""
    indicators = {
        "最新价": 100.0,
        "MA5": 101.0,
        "MA10": 100.0,
        "MA20": 99.0,
        "MA60": 98.0,
        "DIF": 1.0,
        "DEA": 0.5,
        "RSI6": 50.0,
        "K": 50.0,
        "BOLL_UP": 110.0,
        "BOLL_DN": 90.0,
        "VOL_MA5": 1000000,
        "成交量": 1000000,
    }
    result = calculate_weighted_score(indicators)

    assert "bullish_signals" in result
    assert "bearish_signals" in result
    assert "net_signals" in result


def test_compare_stocks_wrapper():
    """测试双股对比便捷函数"""
    # 这个测试需要实际 API 调用，标记为集成测试
    # result = compare_stocks_wrapper("600519", "000858")
    # assert "comparison" in result
    pass  # 跳过，需要网络


def test_analyze_sector_wrapper():
    """测试板块分析便捷函数"""
    # result = analyze_sector_wrapper("白酒")
    # assert "sector_name" in result
    pass  # 跳过，需要网络
