#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
technical_indicators 模块的单元测试

测试覆盖：
- RSI 背离检测（顶背离、底背离、无背离）
- MACD 柱状图分析（红柱、绿柱、斜率）
- 成交量异动检测（放量、缩量、天量、地量）
- K 线形态识别（十字星、锤子线、倒锤子线、吞没、乌云盖顶）
- 筹码分布计算（平均成本、获利盘、套牢盘、集中度）
- 综合扩展指标函数
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
import numpy as np
import pandas as pd

from scripts.technical_indicators import (
    detect_rsi_divergence,
    analyze_macd_histogram,
    detect_volume_anomaly,
    identify_candlestick_patterns,
    calculate_chip_distribution,
    calculate_extended_indicators,
)


# ============================================================
# RSI 背离检测测试
# ============================================================

class TestDetectRsiDivergence:
    """测试 detect_rsi_divergence 函数"""

    def test_top_divergence(self):
        """价格创新高但 RSI 未创新高 → 顶背离"""
        # 价格：先涨到高点，回落，再创新高
        close = pd.Series([
            10, 11, 12, 13, 14, 15, 14, 13, 14, 15,
            16, 15, 14, 13, 14, 15, 16, 17, 16, 15,
            16, 17, 18, 17, 16, 17, 18, 19, 18, 17,
        ])
        # RSI：第一个高点时 RSI 较高，第二个价格新高时 RSI 较低
        rsi = pd.Series([
            40, 45, 50, 55, 60, 70, 65, 55, 60, 70,
            75, 65, 55, 50, 55, 60, 65, 72, 68, 60,
            65, 70, 73, 68, 62, 66, 70, 68, 64, 60,
        ])
        result = detect_rsi_divergence(close, rsi, lookback=10)
        assert result['类型'] == '顶背离'
        assert '看跌' in result['信号'] or '卖' in result['信号']
        assert result['可靠性'] in ('高', '中', '低')

    def test_bottom_divergence(self):
        """价格创新低但 RSI 未创新低 → 底背离"""
        # 价格：先跌到低点，反弹，再创新低
        close = pd.Series([
            20, 19, 18, 17, 16, 15, 16, 17, 16, 15,
            14, 15, 16, 17, 16, 15, 14, 13, 14, 15,
            14, 13, 12, 13, 14, 13, 12, 11, 12, 13,
        ])
        # RSI：第一个低点时 RSI 较低，第二个价格新低时 RSI 较高
        rsi = pd.Series([
            50, 45, 40, 35, 25, 20, 30, 40, 35, 28,
            22, 30, 40, 45, 38, 30, 25, 18, 28, 38,
            30, 25, 20, 30, 35, 28, 24, 22, 30, 35,
        ])
        result = detect_rsi_divergence(close, rsi, lookback=10)
        assert result['类型'] == '底背离'
        assert '看涨' in result['信号'] or '买' in result['信号']
        assert result['可靠性'] in ('高', '中', '低')

    def test_no_divergence(self):
        """价格和 RSI 同步运动 → 无背离"""
        # 价格和 RSI 单调递增
        close = pd.Series(range(1, 31))  # 1, 2, 3, ..., 30
        rsi = pd.Series([30 + i for i in range(30)])  # 30, 31, 32, ..., 59
        result = detect_rsi_divergence(close, rsi, lookback=10)
        assert result['类型'] == '无背离'

    def test_returns_dict_keys(self):
        """返回字典包含所有必需键"""
        close = pd.Series(range(1, 31))
        rsi = pd.Series([50.0] * 30)
        result = detect_rsi_divergence(close, rsi, lookback=10)
        assert '类型' in result
        assert '信号' in result
        assert '可靠性' in result

    def test_short_data_returns_no_divergence(self):
        """数据不足时返回无背离"""
        close = pd.Series([10, 11, 12])
        rsi = pd.Series([50, 55, 60])
        result = detect_rsi_divergence(close, rsi, lookback=20)
        assert result['类型'] == '无背离'


# ============================================================
# MACD 柱状图分析测试
# ============================================================

class TestAnalyzeMacdHistogram:
    """测试 analyze_macd_histogram 函数"""

    def test_consecutive_red_bars(self):
        """连续红柱（DIF > DEA）"""
        # 最近 5 天 DIF > DEA
        dif = pd.Series([1.0, 1.5, 2.0, 2.5, 3.0])
        dea = pd.Series([0.5, 0.8, 1.0, 1.2, 1.5])
        result = analyze_macd_histogram(dif, dea)
        assert result['连续红柱天数'] >= 5
        assert result['连续绿柱天数'] == 0

    def test_consecutive_green_bars(self):
        """连续绿柱（DIF < DEA）"""
        dif = pd.Series([3.0, 2.5, 2.0, 1.5, 1.0])
        dea = pd.Series([3.5, 3.2, 2.8, 2.5, 2.0])
        result = analyze_macd_histogram(dif, dea)
        assert result['连续绿柱天数'] >= 5
        assert result['连续红柱天数'] == 0

    def test_histogram_slope_positive(self):
        """柱状图斜率为正（红柱放大）"""
        dif = pd.Series([0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0])
        dea = pd.Series([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        result = analyze_macd_histogram(dif, dea)
        assert result['柱状图斜率'] > 0

    def test_histogram_slope_negative(self):
        """柱状图斜率为负（红柱缩小或绿柱放大）"""
        dif = pd.Series([4.0, 3.5, 3.0, 2.5, 2.0, 1.5, 1.0, 0.5])
        dea = pd.Series([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        result = analyze_macd_histogram(dif, dea)
        assert result['柱状图斜率'] < 0

    def test_returns_dict_keys(self):
        """返回字典包含所有必需键"""
        dif = pd.Series([1.0, 1.5, 2.0])
        dea = pd.Series([0.5, 0.8, 1.0])
        result = analyze_macd_histogram(dif, dea)
        assert '连续红柱天数' in result
        assert '连续绿柱天数' in result
        assert '柱状图斜率' in result
        assert '趋势判断' in result
        assert '信号' in result

    def test_mixed_bars(self):
        """混合红绿柱"""
        # 最近几天 DIF 和 DEA 交替
        dif = pd.Series([1.0, 0.5, 1.0, 0.5, 1.0, 0.5, 1.0, 0.5, 1.0, 0.5])
        dea = pd.Series([0.5, 1.0, 0.5, 1.0, 0.5, 1.0, 0.5, 1.0, 0.5, 1.0])
        result = analyze_macd_histogram(dif, dea)
        # 最后一天 DIF < DEA → 绿柱
        assert result['连续绿柱天数'] >= 1


# ============================================================
# 成交量异动检测测试
# ============================================================

class TestDetectVolumeAnomaly:
    """测试 detect_volume_anomaly 函数"""

    def test_normal_volume(self):
        """正常成交量"""
        result = detect_volume_anomaly(volume=1000, ma5=1000, ma20=1000)
        assert result['状态'] == '正常'

    def test_high_volume(self):
        """放量：当日成交量 > 5 日均量 × 1.5"""
        result = detect_volume_anomaly(volume=1600, ma5=1000, ma20=1000)
        assert result['状态'] == '放量'
        assert result['倍数'] == pytest.approx(1.6)

    def test_low_volume(self):
        """缩量：当日成交量 < 5 日均量 × 0.5"""
        result = detect_volume_anomaly(volume=400, ma5=1000, ma20=1000)
        assert result['状态'] == '缩量'
        assert result['倍数'] == pytest.approx(0.4)

    def test_returns_dict_keys(self):
        """返回字典包含所有必需键"""
        result = detect_volume_anomaly(volume=1000, ma5=1000, ma20=1000)
        assert '状态' in result
        assert '倍数' in result
        assert '信号' in result

    def test_high_volume_signal(self):
        """放量应有对应的信号描述"""
        result = detect_volume_anomaly(volume=1600, ma5=1000, ma20=1000)
        assert isinstance(result['信号'], str)
        assert len(result['信号']) > 0

    def test_takes_priority_extreme_high(self):
        """天量优先于放量（天量也是放量的一种）"""
        result = detect_volume_anomaly(volume=2500, ma5=1000, ma20=1000)
        assert result['状态'] == '天量'

    def test_takes_priority_extreme_low(self):
        """地量优先于缩量"""
        result = detect_volume_anomaly(volume=200, ma5=1000, ma20=1000)
        assert result['状态'] == '地量'


# ============================================================
# K 线形态识别测试
# ============================================================

class TestIdentifyCandlestickPatterns:
    """测试 identify_candlestick_patterns 函数"""

    def _make_df(self, opens, closes, highs, lows):
        """辅助方法：构造 K 线 DataFrame"""
        return pd.DataFrame({
            '开盘': opens,
            '收盘': closes,
            '最高': highs,
            '最低': lows,
        })

    def test_doji(self):
        """十字星：开盘价 ≈ 收盘价，上下影线较长"""
        df = self._make_df(
            opens=[10.0, 10.0, 10.0, 10.0, 10.1],
            closes=[10.0, 10.0, 10.0, 10.0, 10.12],
            highs=[10.0, 10.0, 10.0, 10.0, 10.5],
            lows=[10.0, 10.0, 10.0, 10.0, 9.6],
        )
        patterns = identify_candlestick_patterns(df, lookback=1)
        pattern_names = [p['形态'] for p in patterns]
        assert '十字星' in pattern_names

    def test_hammer(self):
        """锤子线：下影线 > 实体 2 倍，上影线很短"""
        df = self._make_df(
            opens=[10.0, 10.0, 10.0, 10.0, 10.5],
            closes=[10.0, 10.0, 10.0, 10.0, 10.6],
            highs=[10.0, 10.0, 10.0, 10.0, 10.65],
            lows=[10.0, 10.0, 10.0, 10.0, 9.8],
        )
        patterns = identify_candlestick_patterns(df, lookback=1)
        pattern_names = [p['形态'] for p in patterns]
        assert '锤子线' in pattern_names

    def test_inverted_hammer(self):
        """倒锤子线：上影线 > 实体 2 倍，下影线很短"""
        df = self._make_df(
            opens=[10.0, 10.0, 10.0, 10.0, 10.0],
            closes=[10.0, 10.0, 10.0, 10.0, 10.1],
            highs=[10.0, 10.0, 10.0, 10.0, 10.8],
            lows=[10.0, 10.0, 10.0, 10.0, 9.98],
        )
        patterns = identify_candlestick_patterns(df, lookback=1)
        pattern_names = [p['形态'] for p in patterns]
        assert '倒锤子线' in pattern_names

    def test_engulfing_bullish(self):
        """看涨吞没：阳线实体完全包含前一日阴线实体"""
        df = self._make_df(
            opens=[10.0, 10.0, 10.0, 10.5, 9.8],
            closes=[10.0, 10.0, 10.0, 10.0, 10.6],
            highs=[10.0, 10.0, 10.0, 10.6, 10.7],
            lows=[10.0, 10.0, 10.0, 9.9, 9.7],
        )
        patterns = identify_candlestick_patterns(df, lookback=1)
        pattern_names = [p['形态'] for p in patterns]
        assert '看涨吞没' in pattern_names

    def test_engulfing_bearish(self):
        """看跌吞没：阴线实体完全包含前一日阳线实体"""
        df = self._make_df(
            opens=[10.0, 10.0, 10.0, 10.0, 10.5],
            closes=[10.0, 10.0, 10.0, 10.4, 9.8],
            highs=[10.0, 10.0, 10.0, 10.5, 10.6],
            lows=[10.0, 10.0, 10.0, 9.9, 9.7],
        )
        patterns = identify_candlestick_patterns(df, lookback=1)
        pattern_names = [p['形态'] for p in patterns]
        assert '看跌吞没' in pattern_names

    def test_dark_cloud_cover(self):
        """乌云盖顶：阳线后出现高开低走阴线"""
        df = self._make_df(
            opens=[10.0, 10.0, 10.0, 10.0, 10.8],
            closes=[10.0, 10.0, 10.0, 10.4, 10.1],
            highs=[10.0, 10.0, 10.0, 10.5, 10.9],
            lows=[10.0, 10.0, 10.0, 9.9, 10.0],
        )
        patterns = identify_candlestick_patterns(df, lookback=1)
        pattern_names = [p['形态'] for p in patterns]
        assert '乌云盖顶' in pattern_names

    def test_returns_list(self):
        """返回值是列表"""
        df = self._make_df(
            opens=[10.0] * 10,
            closes=[10.1] * 10,
            highs=[10.2] * 10,
            lows=[9.9] * 10,
        )
        patterns = identify_candlestick_patterns(df, lookback=5)
        assert isinstance(patterns, list)

    def test_each_pattern_has_required_keys(self):
        """每个形态字典包含必需键"""
        df = self._make_df(
            opens=[10.0] * 5,
            closes=[10.1] * 5,
            highs=[10.2] * 5,
            lows=[9.9] * 5,
        )
        patterns = identify_candlestick_patterns(df, lookback=5)
        for p in patterns:
            assert '形态' in p
            assert '信号' in p
            assert '可靠性' in p

    def test_no_patterns_in_normal_candles(self):
        """普通阳线无特殊形态"""
        # 连续普通阳线，无特殊形态
        df = self._make_df(
            opens=[10.0 + i * 0.1 for i in range(10)],
            closes=[10.1 + i * 0.1 for i in range(10)],
            highs=[10.15 + i * 0.1 for i in range(10)],
            lows=[9.95 + i * 0.1 for i in range(10)],
        )
        patterns = identify_candlestick_patterns(df, lookback=5)
        # 普通阳线不应该有十字星、锤子线等形态
        pattern_names = [p['形态'] for p in patterns]
        assert '十字星' not in pattern_names
        assert '锤子线' not in pattern_names


# ============================================================
# 筹码分布计算测试
# ============================================================

class TestCalculateChipDistribution:
    """测试 calculate_chip_distribution 函数"""

    def test_basic_calculation(self):
        """基本筹码分布计算"""
        df = pd.DataFrame({
            '收盘': [10.0, 10.5, 11.0, 10.8, 11.2],
            '成交量': [1000, 1200, 800, 1500, 900],
        })
        result = calculate_chip_distribution(df, current_price=11.0)
        assert '平均成本' in result
        assert '获利盘比例' in result
        assert '套牢盘比例' in result
        assert '筹码集中度' in result

    def test_average_cost(self):
        """平均成本应为成交量加权平均"""
        df = pd.DataFrame({
            '收盘': [10.0, 20.0],
            '成交量': [1000, 1000],
        })
        result = calculate_chip_distribution(df, current_price=15.0)
        # 加权平均 = (10*1000 + 20*1000) / (1000+1000) = 15.0
        assert result['平均成本'] == pytest.approx(15.0)

    def test_profit_ratio_all_profit(self):
        """当前价格高于所有成本 → 获利盘比例 100%"""
        df = pd.DataFrame({
            '收盘': [10.0, 11.0, 12.0],
            '成交量': [1000, 1000, 1000],
        })
        result = calculate_chip_distribution(df, current_price=15.0)
        assert result['获利盘比例'] == pytest.approx(1.0)

    def test_profit_ratio_all_loss(self):
        """当前价格低于所有成本 → 获利盘比例 0%"""
        df = pd.DataFrame({
            '收盘': [10.0, 11.0, 12.0],
            '成交量': [1000, 1000, 1000],
        })
        result = calculate_chip_distribution(df, current_price=8.0)
        assert result['获利盘比例'] == pytest.approx(0.0)

    def test_loss_ratio(self):
        """套牢盘比例 = 1 - 获利盘比例"""
        df = pd.DataFrame({
            '收盘': [10.0, 12.0],
            '成交量': [1000, 1000],
        })
        result = calculate_chip_distribution(df, current_price=11.0)
        # 获利盘：10.0 的 1000 股获利，12.0 的 1000 股套牢
        assert result['获利盘比例'] == pytest.approx(0.5)
        assert result['套牢盘比例'] == pytest.approx(0.5)

    def test_chip_concentration_types(self):
        """筹码集中度应为字符串描述"""
        df = pd.DataFrame({
            '收盘': [10.0, 10.1, 10.2, 10.1, 10.0],
            '成交量': [1000, 1000, 1000, 1000, 1000],
        })
        result = calculate_chip_distribution(df, current_price=10.1)
        assert isinstance(result['筹码集中度'], str)
        assert result['筹码集中度'] in ('高度集中', '较为集中', '较为分散', '非常分散')

    def test_high_concentration(self):
        """价格波动小 → 筹码集中"""
        # 价格波动非常小
        df = pd.DataFrame({
            '收盘': [10.00, 10.01, 10.02, 10.01, 10.00],
            '成交量': [1000, 1000, 1000, 1000, 1000],
        })
        result = calculate_chip_distribution(df, current_price=10.01)
        # 价格波动极小，应为高度集中
        assert result['筹码集中度'] == '高度集中'

    def test_low_concentration(self):
        """价格波动大 → 筹码分散"""
        df = pd.DataFrame({
            '收盘': [5.0, 10.0, 15.0, 8.0, 20.0],
            '成交量': [1000, 1000, 1000, 1000, 1000],
        })
        result = calculate_chip_distribution(df, current_price=12.0)
        # 价格波动大
        assert result['筹码集中度'] in ('较为分散', '非常分散')

    def test_returns_dict_keys(self):
        """返回字典包含所有必需键"""
        df = pd.DataFrame({
            '收盘': [10.0, 11.0],
            '成交量': [1000, 1000],
        })
        result = calculate_chip_distribution(df, current_price=10.5)
        required_keys = ['平均成本', '获利盘比例', '套牢盘比例', '筹码集中度']
        for key in required_keys:
            assert key in result


# ============================================================
# 综合扩展指标测试
# ============================================================

class TestCalculateExtendedIndicators:
    """测试 calculate_extended_indicators 函数"""

    def _make_df(self, n=60):
        """构造测试用 DataFrame"""
        np.random.seed(42)
        base = 10.0
        close = base + np.cumsum(np.random.randn(n) * 0.1)
        high = close + np.abs(np.random.randn(n) * 0.2)
        low = close - np.abs(np.random.randn(n) * 0.2)
        opens = close + np.random.randn(n) * 0.05
        volume = np.random.randint(1000, 10000, n).astype(float)
        return pd.DataFrame({
            '开盘': opens,
            '收盘': close,
            '最高': high,
            '最低': low,
            '成交量': volume,
        })

    def test_returns_dict(self):
        """返回字典类型"""
        df = self._make_df(60)
        indicators = {
            'RSI6': 50.0,
            'DIF': 0.5,
            'DEA': 0.3,
        }
        result = calculate_extended_indicators(df, indicators)
        assert isinstance(result, dict)

    def test_contains_rsi_divergence(self):
        """结果包含 RSI 背离信息"""
        df = self._make_df(60)
        # 构造 RSI 序列
        close = df['收盘']
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(6).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(6).mean()
        rs = gain / loss
        rsi = 100 - 100 / (1 + rs)

        indicators = {
            'RSI6': rsi.iloc[-1],
            'DIF': 0.5,
            'DEA': 0.3,
        }
        result = calculate_extended_indicators(df, indicators)
        assert 'RSI背离' in result

    def test_contains_macd_histogram(self):
        """结果包含 MACD 柱状图信息"""
        df = self._make_df(60)
        indicators = {'RSI6': 50.0, 'DIF': 0.5, 'DEA': 0.3}
        result = calculate_extended_indicators(df, indicators)
        assert 'MACD柱状图' in result

    def test_contains_volume_anomaly(self):
        """结果包含成交量异动信息"""
        df = self._make_df(60)
        indicators = {'RSI6': 50.0, 'DIF': 0.5, 'DEA': 0.3}
        result = calculate_extended_indicators(df, indicators)
        assert '成交量异动' in result

    def test_contains_candlestick_patterns(self):
        """结果包含 K 线形态信息"""
        df = self._make_df(60)
        indicators = {'RSI6': 50.0, 'DIF': 0.5, 'DEA': 0.3}
        result = calculate_extended_indicators(df, indicators)
        assert 'K线形态' in result

    def test_contains_chip_distribution(self):
        """结果包含筹码分布信息"""
        df = self._make_df(60)
        indicators = {'RSI6': 50.0, 'DIF': 0.5, 'DEA': 0.3}
        result = calculate_extended_indicators(df, indicators)
        assert '筹码分布' in result


class TestEdgeCases:
    """边界条件测试"""

    def test_empty_series(self):
        """测试空 Series 输入"""
        empty = pd.Series(dtype=float)
        result = detect_rsi_divergence(empty, empty, lookback=20)
        assert result['类型'] == '无背离'

    def test_nan_values(self):
        """测试包含 NaN 的数据"""
        data = pd.Series([1, 2, np.nan, 4, 5])
        # 测试不会崩溃

    def test_zero_volume(self):
        """测试零成交量"""
        df = pd.DataFrame({
            '收盘': [10.0, 11.0, 12.0],
            '成交量': [0, 0, 0]
        })
        result = calculate_chip_distribution(df, 11.0)
        assert result['平均成本'] == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
