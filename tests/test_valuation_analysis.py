#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
valuation_analysis 模块的单元测试

测试覆盖：
- 分位数计算（正常情况、空列表、边界值、无效值）
- 估值区间判断（各种分位数、异常输入）
- 历史数据获取（成功、失败情况）
- 主函数（完整流程）
- 辅助函数（经验判断、综合评价）
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
import numpy as np
from unittest.mock import patch

from scripts.valuation_analysis import (
    calculate_percentile,
    get_valuation_zone,
    fetch_historical_valuation,
    analyze_valuation_percentile,
    _estimate_zone_from_value,
    _generate_summary,
    _safe_float,
)


# ============================================================
# _safe_float 辅助函数测试
# ============================================================

class TestSafeFloat:
    """_safe_float 辅助函数测试"""

    def test_normal_number(self):
        """测试正常数字"""
        assert _safe_float(3.14) == 3.14

    def test_string_number(self):
        """测试字符串数字"""
        assert _safe_float("2.5") == 2.5

    def test_none_returns_default(self):
        """测试 None 返回默认值"""
        assert _safe_float(None) == 0
        assert _safe_float(None, default=0) == 0

    def test_dash_returns_default(self):
        """测试 '-' 返回默认值"""
        assert _safe_float("-") == 0

    def test_empty_string_returns_default(self):
        """测试空字符串返回默认值"""
        assert _safe_float("") == 0

    def test_invalid_string_returns_default(self):
        """测试无效字符串返回默认值"""
        assert _safe_float("abc") == 0


# ============================================================
# 分位数计算测试
# ============================================================

class TestCalculatePercentile:
    """测试 calculate_percentile 函数"""

    # === 正常情况 ===

    def test_basic_percentile_middle(self):
        """测试当前值在历史序列中间位置"""
        result = calculate_percentile(50, [10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
        # 有 4 个值小于 50，5 个值等于 50（仅 1 个），共 10 个
        # (4 + 0.5) / 10 * 100 = 45.0
        assert result == 45.0

    def test_basic_percentile_low(self):
        """测试当前值为最小值"""
        result = calculate_percentile(10, [10, 20, 30, 40, 50])
        # 0 个小于，1 个等于，共 5 个
        # (0 + 0.5) / 5 * 100 = 10.0
        assert result == 10.0

    def test_basic_percentile_high(self):
        """测试当前值为最大值"""
        result = calculate_percentile(50, [10, 20, 30, 40, 50])
        # 4 个小于，1 个等于，共 5 个
        # (4 + 0.5) / 5 * 100 = 90.0
        assert result == 90.0

    def test_percentile_below_all(self):
        """测试当前值小于所有历史值"""
        result = calculate_percentile(5, [10, 20, 30, 40, 50])
        # 0 个小于，0 个等于，共 5 个
        # (0 + 0) / 5 * 100 = 0.0
        assert result == 0.0

    def test_percentile_above_all(self):
        """测试当前值大于所有历史值"""
        result = calculate_percentile(100, [10, 20, 30, 40, 50])
        # 5 个小于，0 个等于，共 5 个
        # (5 + 0) / 5 * 100 = 100.0
        assert result == 100.0

    def test_percentile_with_duplicates(self):
        """测试历史值中包含重复值"""
        result = calculate_percentile(30, [10, 20, 30, 30, 30, 40, 50])
        # 2 个小于，3 个等于，共 7 个
        # (2 + 1.5) / 7 * 100 = 50.0
        assert result == pytest.approx(50.0)

    def test_percentile_with_numpy_array(self):
        """测试输入为 numpy 数组"""
        arr = np.array([10, 20, 30, 40, 50])
        result = calculate_percentile(30, arr)
        assert result == pytest.approx(50.0)

    # === 空列表和无效值 ===

    def test_empty_list_raises(self):
        """测试空列表应抛出 ValueError"""
        with pytest.raises(ValueError, match="不能为空"):
            calculate_percentile(50, [])

    def test_non_list_raises(self):
        """测试非列表输入应抛出 TypeError"""
        with pytest.raises(TypeError, match="必须是列表"):
            calculate_percentile(50, "not a list")

    def test_non_numeric_current_raises(self):
        """测试非数值 current_value 应抛出 TypeError"""
        with pytest.raises(TypeError, match="无法转换"):
            calculate_percentile("abc", [10, 20, 30])

    def test_nan_current_raises(self):
        """测试 NaN current_value 应抛出 ValueError"""
        with pytest.raises(ValueError, match="不是有效数值"):
            calculate_percentile(float('nan'), [10, 20, 30])

    def test_inf_current_raises(self):
        """测试 Inf current_value 应抛出 ValueError"""
        with pytest.raises(ValueError, match="不是有效数值"):
            calculate_percentile(float('inf'), [10, 20, 30])

    def test_historical_with_nan_filtered(self):
        """测试历史值中包含 NaN 应被过滤"""
        result = calculate_percentile(30, [10, float('nan'), 20, 30, 40, float('nan'), 50])
        # 有效值: [10, 20, 30, 40, 50]，共 5 个
        # 2 个小于 30，1 个等于 30
        # (2 + 0.5) / 5 * 100 = 50.0
        assert result == 50.0

    def test_historical_with_inf_filtered(self):
        """测试历史值中包含 Inf 应被过滤"""
        result = calculate_percentile(30, [10, 20, 30, 40, float('inf')])
        # 有效值: [10, 20, 30, 40]，共 4 个
        # 2 个小于 30，1 个等于 30
        # (2 + 0.5) / 4 * 100 = 62.5
        assert result == 62.5

    def test_all_nan_raises(self):
        """测试历史值全为 NaN 应抛出 ValueError"""
        with pytest.raises(ValueError, match="没有有效数值"):
            calculate_percentile(30, [float('nan'), float('nan')])

    # === 边界值 ===

    def test_result_clamped_to_0(self):
        """测试结果不低于 0"""
        result = calculate_percentile(-999, [10, 20, 30])
        assert result >= 0

    def test_result_clamped_to_100(self):
        """测试结果不超过 100"""
        result = calculate_percentile(999, [10, 20, 30])
        assert result <= 100

    def test_single_value_list(self):
        """测试历史值列表只有一个元素"""
        result = calculate_percentile(50, [50])
        # 0 个小于，1 个等于，共 1 个
        # (0 + 0.5) / 1 * 100 = 50.0
        assert result == 50.0

    def test_float_precision(self):
        """测试浮点精度"""
        result = calculate_percentile(1.5, [1.0, 1.5, 2.0])
        # 1 个小于，1 个等于，共 3 个
        # (1 + 0.5) / 3 * 100 = 50.0
        assert result == pytest.approx(50.0)


# ============================================================
# 估值区间判断测试
# ============================================================

class TestGetValuationZone:
    """测试 get_valuation_zone 函数"""

    # === 各种分位数 ===

    def test_undervalued_low(self):
        """0% 属于低估"""
        assert get_valuation_zone(0) == "低估"

    def test_undervalued_high(self):
        """19% 属于低估"""
        assert get_valuation_zone(19) == "低估"

    def test_reasonable_low_low(self):
        """20% 属于合理偏低"""
        assert get_valuation_zone(20) == "合理偏低"

    def test_reasonable_low_high(self):
        """39% 属于合理偏低"""
        assert get_valuation_zone(39) == "合理偏低"

    def test_reasonable_mid_low(self):
        """40% 属于合理"""
        assert get_valuation_zone(40) == "合理"

    def test_reasonable_mid_high(self):
        """59% 属于合理"""
        assert get_valuation_zone(59) == "合理"

    def test_reasonable_high_low(self):
        """60% 属于合理偏高"""
        assert get_valuation_zone(60) == "合理偏高"

    def test_reasonable_high_high(self):
        """79% 属于合理偏高"""
        assert get_valuation_zone(79) == "合理偏高"

    def test_overvalued_low(self):
        """80% 属于高估"""
        assert get_valuation_zone(80) == "高估"

    def test_overvalued_high(self):
        """100% 属于高估"""
        assert get_valuation_zone(100) == "高估"

    # === 边界值 ===

    def test_exact_boundaries(self):
        """测试所有精确边界值"""
        assert get_valuation_zone(0) == "低估"
        assert get_valuation_zone(20) == "合理偏低"
        assert get_valuation_zone(40) == "合理"
        assert get_valuation_zone(60) == "合理偏高"
        assert get_valuation_zone(80) == "高估"
        assert get_valuation_zone(100) == "高估"

    def test_float_percentile(self):
        """测试浮点百分位"""
        assert get_valuation_zone(50.5) == "合理"
        assert get_valuation_zone(79.9) == "合理偏高"

    # === 异常输入 ===

    def test_negative_raises(self):
        """测试负数应抛出 ValueError"""
        with pytest.raises(ValueError, match="0~100"):
            get_valuation_zone(-1)

    def test_above_100_raises(self):
        """测试超过 100 应抛出 ValueError"""
        with pytest.raises(ValueError, match="0~100"):
            get_valuation_zone(101)

    def test_non_numeric_raises(self):
        """测试非数值应抛出 TypeError"""
        with pytest.raises(TypeError, match="数值类型"):
            get_valuation_zone("high")

    def test_none_raises(self):
        """测试 None 应抛出 TypeError"""
        with pytest.raises(TypeError, match="数值类型"):
            get_valuation_zone(None)


# ============================================================
# 经验判断辅助函数测试
# ============================================================

class TestEstimateZoneFromValue:
    """测试 _estimate_zone_from_value 函数"""

    # === PE 经验判断 ===

    def test_pe_negative(self):
        """PE 为负 → 亏损"""
        assert _estimate_zone_from_value("PE", -10) == "亏损"

    def test_pe_low(self):
        """PE < 15 → 低估（通用阈值）"""
        assert _estimate_zone_from_value("PE", 10) == "低估（全市场通用）"

    def test_pe_reasonable(self):
        """15 <= PE < 25 → 合理（通用阈值）"""
        assert _estimate_zone_from_value("PE", 20) == "合理（全市场通用）"

    def test_pe_reasonable_high(self):
        """25 <= PE < 40 → 合理偏高（通用阈值）"""
        assert _estimate_zone_from_value("PE", 30) == "合理偏高（全市场通用）"

    def test_pe_overvalued(self):
        """PE >= 40 → 高估（通用阈值）"""
        assert _estimate_zone_from_value("PE", 50) == "高估（全市场通用）"

    # === PB 经验判断 ===

    def test_pb_negative(self):
        """PB 为负 → 净资产为负"""
        assert _estimate_zone_from_value("PB", -1) == "净资产为负"

    def test_pb_below_1(self):
        """PB < 1 → 破净（通用阈值）"""
        assert _estimate_zone_from_value("PB", 0.8) == "破净（全市场通用）"

    def test_pb_low(self):
        """1 <= PB < 2 → 低估（通用阈值）"""
        assert _estimate_zone_from_value("PB", 1.5) == "低估（全市场通用）"

    def test_pb_reasonable(self):
        """2 <= PB < 4 → 合理（通用阈值）"""
        assert _estimate_zone_from_value("PB", 3) == "合理（全市场通用）"

    def test_pb_reasonable_high(self):
        """4 <= PB < 8 → 合理偏高（通用阈值）"""
        assert _estimate_zone_from_value("PB", 6) == "合理偏高（全市场通用）"

    def test_pb_overvalued(self):
        """PB >= 8 → 高估（通用阈值）"""
        assert _estimate_zone_from_value("PB", 10) == "高估（全市场通用）"

    # === 股息率经验判断 ===

    def test_dividend_zero(self):
        """股息率为 0 → 无分红"""
        assert _estimate_zone_from_value("股息率", 0) == "无分红"

    def test_dividend_negative(self):
        """股息率为负 → 无分红"""
        assert _estimate_zone_from_value("股息率", -1) == "无分红"

    def test_dividend_low(self):
        """股息率 < 1% → 偏低"""
        assert _estimate_zone_from_value("股息率", 0.5) == "偏低"

    def test_dividend_reasonable(self):
        """1% <= 股息率 < 3% → 合理"""
        assert _estimate_zone_from_value("股息率", 2) == "合理"

    def test_dividend_high(self):
        """3% <= 股息率 < 5% → 较高"""
        assert _estimate_zone_from_value("股息率", 4) == "较高"

    def test_dividend_very_high(self):
        """股息率 >= 5% → 高股息"""
        assert _estimate_zone_from_value("股息率", 6) == "高股息"

    # === 特殊情况 ===

    def test_zero_value_pe(self):
        """PE 为 0 → 数据缺失"""
        assert _estimate_zone_from_value("PE", 0) == "数据缺失"

    def test_unknown_metric(self):
        """未知指标 → 数据不足"""
        assert _estimate_zone_from_value("未知指标", 50) == "数据不足"

    # === 行业差异化阈值 ===

    def test_bank_pb_1_is_reasonable(self):
        """银行 PB=1.0 合理（通用阈值会说破净）"""
        assert "合理" in _estimate_zone_from_value("PB", 1.0, "银行行业")

    def test_bank_pe_7_is_reasonable(self):
        """银行 PE=7 合理（通用阈值会说低估）"""
        assert "合理" in _estimate_zone_from_value("PE", 7, "银行行业")

    def test_liquor_pe_30_is_reasonable(self):
        """白酒 PE=30 合理（通用阈值会说合理偏高）"""
        assert "合理" in _estimate_zone_from_value("PE", 30, "白酒行业")

    def test_liquor_pb_7_is_reasonable(self):
        """白酒 PB=7 合理（通用阈值会说高估）"""
        assert "合理" in _estimate_zone_from_value("PB", 7, "白酒行业")

    def test_appliance_pb_28_is_reasonable(self):
        """家电 PB=2.8 合理（美的集团典型案例）"""
        result = _estimate_zone_from_value("PB", 2.79, "家电行业")
        assert "合理" in result

    def test_appliance_pe_15_is_reasonable(self):
        """家电 PE=15 合理"""
        result = _estimate_zone_from_value("PE", 14.64, "家电行业")
        assert "合理" in result

    def test_semiconductor_pe_45_is_reasonable(self):
        """半导体 PE=45 合理（通用阈值会说高估）"""
        assert "合理" in _estimate_zone_from_value("PE", 45, "半导体行业")

    def test_unknown_industry_falls_back(self):
        """未知行业回退到通用阈值"""
        assert _estimate_zone_from_value("PE", 10, "未知行业XYZ") == "低估（全市场通用）"
        assert _estimate_zone_from_value("PB", 1.5, "未知行业XYZ") == "低估（全市场通用）"


# ============================================================
# 综合评价测试
# ============================================================

class TestGenerateSummary:
    """测试 _generate_summary 函数"""

    def test_all_undervalued(self):
        """多项指标低估 → 投资机会"""
        result = {
            'PE': {'当前值': 10, '分位数': 15, '区间': '低估'},
            'PB': {'当前值': 0.8, '分位数': 10, '区间': '低估'},
            '股息率': {'当前值': 3.0, '分位数': 85, '区间': '高估'},
        }
        summary = _generate_summary(result)
        assert "低估" in summary
        assert "投资机会" in summary

    def test_all_overvalued(self):
        """多项指标高估 → 估值风险"""
        result = {
            'PE': {'当前值': 80, '分位数': 90, '区间': '高估'},
            'PB': {'当前值': 15, '分位数': 95, '区间': '高估'},
            '股息率': {'当前值': 0.1, '分位数': 5, '区间': '低估'},
        }
        summary = _generate_summary(result)
        assert "高估" in summary
        assert "估值风险" in summary

    def test_all_reasonable(self):
        """多项指标合理 → 合理区间"""
        result = {
            'PE': {'当前值': 20, '分位数': 50, '区间': '合理'},
            'PB': {'当前值': 3, '分位数': 50, '区间': '合理'},
            '股息率': {'当前值': 2.0, '分位数': 50, '区间': '合理'},
        }
        summary = _generate_summary(result)
        assert "合理" in summary

    def test_mixed_zones(self):
        """指标分化 → 综合判断"""
        result = {
            'PE': {'当前值': 10, '分位数': 15, '区间': '低估'},
            'PB': {'当前值': 15, '分位数': 95, '区间': '高估'},
            '股息率': {'当前值': 2.0, '分位数': 50, '区间': '合理'},
        }
        summary = _generate_summary(result)
        assert "分化" in summary

    def test_missing_data(self):
        """数据不足"""
        result = {
            'PE': {'当前值': 0, '分位数': None, '区间': '数据不足'},
            'PB': {'当前值': 0, '分位数': None, '区间': '数据不足'},
            '股息率': {'当前值': 0, '分位数': None, '区间': '数据不足'},
        }
        summary = _generate_summary(result)
        assert "数据不足" in summary

    def test_loss_situation(self):
        """亏损情况"""
        result = {
            'PE': {'当前值': -10, '分位数': None, '区间': '亏损'},
            'PB': {'当前值': 2, '分位数': 50, '区间': '合理'},
            '股息率': {'当前值': 0, '分位数': None, '区间': '无分红'},
        }
        summary = _generate_summary(result)
        assert "亏损" in summary

    def test_summary_contains_details(self):
        """综合评价应包含各指标详情"""
        result = {
            'PE': {'当前值': 15.5, '分位数': 30, '区间': '合理偏低'},
            'PB': {'当前值': 2.1, '分位数': 45, '区间': '合理'},
            '股息率': {'当前值': 1.5, '分位数': 60, '区间': '合理偏高'},
        }
        summary = _generate_summary(result)
        # 应包含各指标的当前值
        assert "15.50" in summary
        assert "2.10" in summary
        assert "1.50" in summary


# ============================================================
# 历史数据获取测试（mock）
# ============================================================

class TestFetchHistoricalValuation:
    """测试 fetch_historical_valuation 函数"""

    @patch('scripts.valuation_analysis._http_get_safe')
    @patch('scripts.valuation_analysis.get_market_info')
    @patch('scripts.valuation_analysis.get_secid')
    def test_returns_dict_structure(self, mock_secid, mock_market, mock_http):
        """测试返回字典结构正确"""
        mock_market.return_value = ('SH', 1, 100)
        mock_secid.return_value = '1.600519'
        mock_http.return_value = {"data": {"klines": []}}

        result = fetch_historical_valuation('600519')
        assert 'PE' in result
        assert 'PB' in result
        assert '股息率' in result
        assert isinstance(result['PE'], list)
        assert isinstance(result['PB'], list)
        assert isinstance(result['股息率'], list)

    @patch('scripts.valuation_analysis._http_get_safe')
    @patch('scripts.valuation_analysis.get_market_info')
    @patch('scripts.valuation_analysis.get_secid')
    def test_empty_api_response(self, mock_secid, mock_market, mock_http):
        """测试 API 返回空数据"""
        mock_market.return_value = ('SH', 1, 100)
        mock_secid.return_value = '1.600519'
        mock_http.return_value = {"data": {"klines": []}}

        result = fetch_historical_valuation('600519')
        assert result['PE'] == []
        assert result['PB'] == []
        assert result['股息率'] == []

    @patch('scripts.valuation_analysis._http_get_safe')
    @patch('scripts.valuation_analysis.get_market_info')
    @patch('scripts.valuation_analysis.get_secid')
    def test_none_api_response(self, mock_secid, mock_market, mock_http):
        """测试 API 返回 None"""
        mock_market.return_value = ('SH', 1, 100)
        mock_secid.return_value = '1.600519'
        mock_http.return_value = None

        result = fetch_historical_valuation('600519')
        assert result['PE'] == []
        assert result['PB'] == []
        assert result['股息率'] == []

    @patch('scripts.valuation_analysis._http_get_safe')
    @patch('scripts.valuation_analysis.get_market_info')
    def test_invalid_code_returns_empty(self, mock_market, mock_http):
        """测试无效代码返回空字典"""
        mock_market.side_effect = ValueError("无法识别")

        result = fetch_historical_valuation('INVALID')
        assert result['PE'] == []
        assert result['PB'] == []
        assert result['股息率'] == []

    @patch('scripts.valuation_analysis._http_get_safe')
    @patch('scripts.valuation_analysis.get_market_info')
    @patch('scripts.valuation_analysis.get_secid')
    def test_with_kline_data(self, mock_secid, mock_market, mock_http):
        """测试有 K 线数据的情况（API 限制下 PE/PB 仍为空）"""
        mock_market.return_value = ('SH', 1, 100)
        mock_secid.return_value = '1.600519'
        mock_http.return_value = {
            "data": {
                "klines": [
                    "2024-01-01,100,105,110,95,1000000,105000000,5,5,5,1.5,10500000000",
                    "2024-01-02,105,108,112,103,1200000,129600000,4,2.86,3,1.8,10800000000",
                ]
            }
        }

        result = fetch_historical_valuation('600519', years=5)
        # 由于 API 限制，PE/PB/股息率历史数据为空
        assert isinstance(result['PE'], list)
        assert isinstance(result['PB'], list)
        assert isinstance(result['股息率'], list)


# ============================================================
# 主函数测试（mock）
# ============================================================

class TestAnalyzeValuationPercentile:
    """测试 analyze_valuation_percentile 主函数"""

    @patch('scripts.valuation_analysis.fetch_historical_valuation')
    def test_with_empty_history(self, mock_fetch):
        """测试无历史数据时使用经验判断"""
        mock_fetch.return_value = {'PE': [], 'PB': [], '股息率': []}

        current_quote = {
            'f9': 25.0,   # PE
            'f23': 3.0,   # PB
            'f115': 2.0,  # 股息率（可能的字段）
        }

        result = analyze_valuation_percentile('600519', current_quote)

        # 验证返回结构
        assert 'PE' in result
        assert 'PB' in result
        assert '股息率' in result
        assert '综合评价' in result

        # 验证 PE
        assert result['PE']['当前值'] == 25.0
        assert result['PE']['分位数'] is None  # 无历史数据
        assert '合理' in result['PE']['区间']

        # 验证 PB
        assert result['PB']['当前值'] == 3.0
        assert result['PB']['分位数'] is None
        assert '合理' in result['PB']['区间']

        # 验证综合评价
        assert isinstance(result['综合评价'], str)
        assert len(result['综合评价']) > 0

    @patch('scripts.valuation_analysis.fetch_historical_valuation')
    def test_with_history_data(self, mock_fetch):
        """测试有历史数据时计算分位数"""
        mock_fetch.return_value = {
            'PE': [10, 15, 20, 25, 30, 35, 40, 45, 50],
            'PB': [1, 2, 3, 4, 5, 6, 7, 8, 9],
            '股息率': [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5],
        }

        current_quote = {
            'f9': 25.0,   # PE
            'f23': 5.0,   # PB
            'f115': 2.5,  # 股息率
        }

        result = analyze_valuation_percentile('600519', current_quote)

        # PE 25 在 [10,15,20,25,30,35,40,45,50] 中：
        # 3 个小于，1 个等于，共 9 个
        # (3 + 0.5) / 9 * 100 = 38.89
        assert result['PE']['分位数'] is not None
        assert result['PE']['分位数'] == pytest.approx(38.89, abs=0.01)

        # PB 5 在 [1,2,3,4,5,6,7,8,9] 中：
        # 4 个小于，1 个等于，共 9 个
        # (4 + 0.5) / 9 * 100 = 50.0
        assert result['PB']['分位数'] is not None
        assert result['PB']['分位数'] == pytest.approx(50.0, abs=0.01)

    @patch('scripts.valuation_analysis.fetch_historical_valuation')
    def test_with_none_quote_values(self, mock_fetch):
        """测试行情数据中包含 None 值"""
        mock_fetch.return_value = {'PE': [], 'PB': [], '股息率': []}

        current_quote = {
            'f9': None,
            'f23': '-',
            'f115': None,
        }

        result = analyze_valuation_percentile('600519', current_quote)

        # None 和 '-' 应被安全转换为 0
        assert result['PE']['当前值'] == 0
        assert result['PB']['当前值'] == 0

    @patch('scripts.valuation_analysis.fetch_historical_valuation')
    def test_with_missing_quote_keys(self, mock_fetch):
        """测试行情数据中缺少关键字段"""
        mock_fetch.return_value = {'PE': [], 'PB': [], '股息率': []}

        current_quote = {}

        result = analyze_valuation_percentile('600519', current_quote)

        # 缺少字段应使用默认值 0
        assert result['PE']['当前值'] == 0
        assert result['PB']['当前值'] == 0
        assert result['股息率']['当前值'] == 0

    @patch('scripts.valuation_analysis.fetch_historical_valuation')
    def test_returns_complete_structure(self, mock_fetch):
        """测试返回结构完整性"""
        mock_fetch.return_value = {'PE': [], 'PB': [], '股息率': []}

        current_quote = {'f9': 20, 'f23': 2, 'f115': 1.5}
        result = analyze_valuation_percentile('600519', current_quote)

        # 检查所有必需的键
        for metric in ['PE', 'PB', '股息率']:
            assert metric in result
            assert '当前值' in result[metric]
            assert '分位数' in result[metric]
            assert '区间' in result[metric]
        assert '综合评价' in result

    @patch('scripts.valuation_analysis.fetch_historical_valuation')
    def test_negative_pe_shows_loss(self, mock_fetch):
        """测试 PE 为负时显示亏损"""
        mock_fetch.return_value = {'PE': [], 'PB': [], '股息率': []}

        current_quote = {'f9': -15, 'f23': 2, 'f115': 0}
        result = analyze_valuation_percentile('600519', current_quote)

        assert '亏损' in result['PE']['区间']

    @patch('scripts.valuation_analysis.fetch_historical_valuation')
    def test_high_valuation(self, mock_fetch):
        """测试高估值情况"""
        mock_fetch.return_value = {'PE': [], 'PB': [], '股息率': []}

        current_quote = {'f9': 100, 'f23': 20, 'f115': 0.1}
        result = analyze_valuation_percentile('600519', current_quote)

        assert '高估' in result['PE']['区间']
        assert '高估' in result['PB']['区间']

    @patch('scripts.valuation_analysis.fetch_historical_valuation')
    def test_dividend_from_f163(self, mock_fetch):
        """测试股息率从 f163 字段获取（f115 为 None 时回退）"""
        mock_fetch.return_value = {'PE': [], 'PB': [], '股息率': []}

        current_quote = {'f9': 20, 'f23': 2, 'f115': None, 'f163': 3.5}
        result = analyze_valuation_percentile('600519', current_quote)

        # f115 为 None 时，应回退到 f163
        assert result['股息率']['当前值'] == 3.5

    @patch('scripts.valuation_analysis.fetch_historical_valuation')
    def test_dividend_f163_primary_source(self, mock_fetch):
        """测试 f163 是股息率的主数据源（f115 是每股收益，不应误用）"""
        mock_fetch.return_value = {'PE': [], 'PB': [], '股息率': []}

        current_quote = {'f9': 20, 'f23': 2, 'f163': 3.5}
        result = analyze_valuation_percentile('600519', current_quote)

        # f163 是股息率的主字段
        assert result['股息率']['当前值'] == 3.5


# ============================================================
# 集成测试
# ============================================================

class TestIntegration:
    """集成测试：组合使用多个函数"""

    def test_percentile_to_zone_consistency(self):
        """分位数计算和区间判断的一致性"""
        # 构造历史数据
        historical = list(range(1, 101))  # 1~100

        test_cases = [
            (10, "低估"),       # 低值
            (30, "合理偏低"),   # 中低值
            (50, "合理"),       # 中间值
            (70, "合理偏高"),   # 中高值
            (90, "高估"),       # 高值
        ]

        for value, expected_zone_keyword in test_cases:
            percentile = calculate_percentile(value, historical)
            zone = get_valuation_zone(percentile)
            assert expected_zone_keyword in zone, \
                f"值 {value} 的分位数 {percentile}% 应属于 {expected_zone_keyword}，实际为 {zone}"

    def test_full_pipeline_with_mock(self):
        """完整流程测试（带 mock）"""
        with patch('scripts.valuation_analysis.fetch_historical_valuation') as mock_fetch:
            mock_fetch.return_value = {
                'PE': [10, 15, 20, 25, 30, 35, 40, 45, 50, 55],
                'PB': [1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5, 5.5],
                '股息率': [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0],
            }

            current_quote = {
                'f9': 20,    # PE
                'f23': 2.5,  # PB
                'f163': 2.0, # 股息率
            }

            result = analyze_valuation_percentile('600519', current_quote)

            # 验证所有指标都有有效结果
            for metric in ['PE', 'PB', '股息率']:
                assert result[metric]['当前值'] > 0
                assert result[metric]['分位数'] is not None
                assert 0 <= result[metric]['分位数'] <= 100
                assert result[metric]['区间'] != ""
                assert result[metric]['区间'] != "数据不足"

            # 综合评价不为空
            assert len(result['综合评价']) > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
