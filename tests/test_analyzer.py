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


def test_safe_display():
    """测试 safe_display 函数 - 数据缺失显示 '-' 而非 0"""
    from scripts.utils import safe_display

    # None/空值 → "-"
    assert safe_display(None) == "-"
    assert safe_display("-") == "-"
    assert safe_display("") == "-"
    assert safe_display("N/A") == "-"
    assert safe_display("--") == "-"
    assert safe_display("nan") == "-"
    assert safe_display("NaN") == "-"
    assert safe_display("null") == "-"

    # 0 → "-"（数据缺失）
    assert safe_display(0) == "-"
    assert safe_display(0.0) == "-"
    assert safe_display("0") == "-"

    # 正常数值 → 格式化显示
    assert safe_display(15.34) == "15.34"
    assert safe_display(100) == "100.00"
    assert safe_display(-5.2) == "-5.20"

    # 负值也是有效数据
    assert safe_display(-0.5) == "-0.50"

    # 非数值字符串 → "-"
    assert safe_display("abc") == "-"
    assert safe_display("暂无") == "-"

    # 自定义格式
    assert safe_display(15.34, ".1f") == "15.3"
    assert safe_display(100, ".0f") == "100"

    # show_zero=True 时 0 显示为数值而非 "-"
    assert safe_display(0, show_zero=True) == "0.00"
    assert safe_display(0.0, show_zero=True) == "0.00"
    assert safe_display("0", show_zero=True) == "0.00"  # 字符串 "0" 是合法零值
