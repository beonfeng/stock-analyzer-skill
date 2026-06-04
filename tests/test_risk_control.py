import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from risk_control import calc_dynamic_stop_loss, calc_target_price, calc_support_resistance, calc_position_size, check_risk_rules


def test_calc_dynamic_stop_loss_main_board():
    """测试主板股票止损位计算"""
    # 主板涨跌停 ±10%，止损应不超过 7%
    result = calc_dynamic_stop_loss(
        current_price=100.0,
        atr=3.0,
        board_type="main"
    )
    assert result["stop_loss"] > 0
    assert result["stop_loss"] < 100.0
    # 止损幅度不超过 7%（主板涨跌停 10% 的 70%）
    assert (100.0 - result["stop_loss"]) / 100.0 <= 0.07


def test_calc_dynamic_stop_loss_gem():
    """测试创业板止损位计算"""
    result = calc_dynamic_stop_loss(
        current_price=100.0,
        atr=5.0,
        board_type="gem"
    )
    # 创业板涨跌停 ±20%，止损幅度不超过 14%
    assert (100.0 - result["stop_loss"]) / 100.0 <= 0.14


def test_calc_target_price():
    """测试目标位计算"""
    result = calc_target_price(
        current_price=100.0,
        stop_loss=95.0,
        risk_reward_ratio=2.5
    )
    # 目标价 = 当前价 + (当前价 - 止损价) × 风险收益比
    expected = 100.0 + (100.0 - 95.0) * 2.5
    assert abs(result["target_price"] - expected) < 0.01
    assert result["risk_reward_ratio"] == 2.5


def test_calc_support_resistance():
    """测试支撑压力位计算"""
    # 构造模拟数据
    import pandas as pd
    df = pd.DataFrame({
        "收盘": [100, 102, 101, 103, 105, 104, 106, 108, 107, 109,
                 110, 108, 106, 104, 102, 100, 98, 96, 94, 92],
        "最高": [101, 103, 102, 104, 106, 105, 107, 109, 108, 110,
                 111, 109, 107, 105, 103, 101, 99, 97, 95, 93],
        "最低": [99, 101, 100, 102, 104, 103, 105, 107, 106, 108,
                 109, 107, 105, 103, 101, 99, 97, 95, 93, 91],
    })
    indicators = {
        "BOLL_UP": 115.0,
        "BOLL_MID": 105.0,
        "BOLL_DN": 95.0,
        "MA20": 105.0,
        "MA60": 100.0,
    }

    result = calc_support_resistance(df, 108.0, indicators)

    assert "resistance" in result
    assert "support" in result
    assert len(result["resistance"]) >= 1
    assert len(result["support"]) >= 1
    # 压力位应高于当前价
    for r in result["resistance"]:
        assert r["price"] > 108.0
    # 支撑位应低于当前价
    for s in result["support"]:
        assert s["price"] < 108.0


def test_calc_position_size_buy_high_confidence():
    """测试高置信度买入的仓位建议"""
    result = calc_position_size(
        direction="buy",
        score=6.0,
        net_signals=3,
        has_bearish=False
    )
    assert result["position_pct"] >= 10
    assert result["position_pct"] <= 20
    assert result["confidence"] == "较高"


def test_calc_position_size_sell():
    """测试卖出信号的仓位建议"""
    result = calc_position_size(
        direction="sell",
        score=-5.0,
        net_signals=-3,
        has_bearish=True
    )
    assert result["position_pct"] == 0
    assert "空仓" in result["description"]


def test_calc_position_size_hold():
    """测试观望信号的仓位建议"""
    result = calc_position_size(
        direction="hold",
        score=1.0,
        net_signals=0,
        has_bearish=False
    )
    assert result["position_pct"] == 0
    assert "观望" in result["description"]


def test_check_risk_rules_normal():
    """测试正常情况下的风控检查"""
    indicators = {
        "最新价": 100.0,
        "MA20": 97.0,
        "MA5": 100.5,
        "MA10": 99.0,
    }
    result = check_risk_rules(
        code="600519",
        indicators=indicators,
        is_st=False,
        is_new_stock=False
    )
    assert len(result["warnings"]) == 0


def test_check_risk_rules_high_bias():
    """测试乖离率过高的风控警告"""
    indicators = {
        "最新价": 120.0,  # 偏离 MA20 超过 5%
        "MA20": 100.0,
        "MA5": 115.0,
        "MA10": 110.0,
    }
    result = check_risk_rules(
        code="600519",
        indicators=indicators,
        is_st=False,
        is_new_stock=False
    )
    assert any("乖离率" in w for w in result["warnings"])


def test_check_risk_rules_st_stock():
    """测试 ST 股票的风控警告"""
    indicators = {"最新价": 10.0, "MA20": 9.5, "MA5": 9.8, "MA10": 9.6}
    result = check_risk_rules(
        code="000001",
        indicators=indicators,
        is_st=True,
        is_new_stock=False
    )
    assert any("ST" in w for w in result["warnings"])


def test_check_risk_rules_new_stock():
    """测试次新股的风控警告"""
    indicators = {"最新价": 50.0, "MA20": 48.0, "MA5": 49.0, "MA10": 48.5}
    result = check_risk_rules(
        code="301001",
        indicators=indicators,
        is_st=False,
        is_new_stock=True
    )
    assert any("次新股" in w for w in result["warnings"])
