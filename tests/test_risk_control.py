import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from risk_control import calc_dynamic_stop_loss, calc_target_price


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
