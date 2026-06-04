import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from comparison import compare_two_stocks, generate_comparison_table, get_sector_stocks, analyze_sector


def test_compare_two_stocks():
    """测试双股对比分析"""
    stock_a = {
        "code": "600519",
        "name": "贵州茅台",
        "price": 1800.0,
        "pe": 35.0,
        "pb": 10.0,
        "market_cap": 23000e8,
        "change_pct": 1.5,
        "indicators": {"RSI6": 55.0, "DIF": 5.0, "DEA": 3.0},
        "rating": {"星级": 4, "分数": 4.2},
    }
    stock_b = {
        "code": "000858",
        "name": "五粮液",
        "price": 150.0,
        "pe": 25.0,
        "pb": 6.0,
        "market_cap": 6000e8,
        "change_pct": 0.8,
        "indicators": {"RSI6": 48.0, "DIF": 2.0, "DEA": 1.5},
        "rating": {"星级": 3, "分数": 3.5},
    }

    result = compare_two_stocks(stock_a, stock_b)

    assert "comparison" in result
    assert "winner" in result
    assert len(result["comparison"]) >= 5  # 至少 5 个对比维度


def test_generate_comparison_table():
    """测试对比表格生成"""
    comparison = [
        {"dimension": "估值", "stock_a": "35.0", "stock_b": "25.0", "winner": "b"},
        {"dimension": "技术面", "stock_a": "55.0", "stock_b": "48.0", "winner": "a"},
    ]
    table = generate_comparison_table(comparison, "茅台", "五粮液")
    assert "茅台" in table
    assert "五粮液" in table
    assert "估值" in table


def test_get_sector_stocks():
    """测试获取板块代表性股票"""
    stocks = get_sector_stocks("白酒")
    assert len(stocks) >= 3
    assert "600519" in stocks  # 贵州茅台


def test_get_sector_stocks_unknown():
    """测试未知板块"""
    stocks = get_sector_stocks("未知板块")
    assert len(stocks) == 0


def test_analyze_sector():
    """测试板块分析"""
    # 模拟板块分析结果
    sector_data = {
        "sector_name": "白酒",
        "stocks": [
            {"code": "600519", "name": "贵州茅台", "change_pct": 1.5},
            {"code": "000858", "name": "五粮液", "change_pct": 0.8},
        ],
    }
    result = analyze_sector(sector_data)
    assert "avg_change" in result
    assert "trend" in result
