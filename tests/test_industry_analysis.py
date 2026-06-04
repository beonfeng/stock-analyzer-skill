#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
industry_analysis 模块的单元测试

测试覆盖：
- 获取股票所属行业
- 获取同行业股票列表
- 估值对比分析
- 资金流向对比
- 行业景气度分析
- 龙头溢价分析
- 主函数完整流程
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import patch, MagicMock

from scripts.industry_analysis import (
    _safe_float,
    _get_market_id,
    _find_industry_from_board,
    _evaluate_sentiment,
    _evaluate_premium_reasonableness,
    get_stock_industry,
    fetch_industry_peers,
    analyze_valuation_comparison,
    analyze_fund_flow_comparison,
    analyze_industry_sentiment,
    analyze_leader_premium,
    analyze_industry_comparison,
)


# ============================================================
# 辅助函数测试
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

    def test_dash_returns_default(self):
        """测试 '-' 返回默认值"""
        assert _safe_float("-") == 0

    def test_empty_string_returns_default(self):
        """测试空字符串返回默认值"""
        assert _safe_float("") == 0

    def test_invalid_string_returns_default(self):
        """测试无效字符串返回默认值"""
        assert _safe_float("abc") == 0


class TestGetMarketId:
    """_get_market_id 辅助函数测试"""

    @patch('scripts.industry_analysis.get_market_info')
    def test_valid_code(self, mock_market):
        """测试有效代码"""
        mock_market.return_value = ('SH', 1, 100)
        assert _get_market_id('600519') == 1

    @patch('scripts.industry_analysis.get_market_info')
    def test_invalid_code(self, mock_market):
        """测试无效代码"""
        mock_market.side_effect = ValueError("无法识别")
        assert _get_market_id('INVALID') == 0


# ============================================================
# 景气度评估测试
# ============================================================

class TestEvaluateSentiment:
    """_evaluate_sentiment 辅助函数测试"""

    def test_high_sentiment(self):
        """测试高景气度"""
        result = _evaluate_sentiment(3.0, 5.0, 1000000, 80, 20)
        assert result == '高景气'

    def test_low_sentiment(self):
        """测试低景气度"""
        result = _evaluate_sentiment(-3.0, 1.0, -1000000, 20, 80)
        assert result == '低景气'

    def test_neutral_sentiment(self):
        """测试中性景气度"""
        result = _evaluate_sentiment(0.5, 2.0, 0, 50, 50)
        assert result == '中性'


# ============================================================
# 溢价合理性评估测试
# ============================================================

class TestEvaluatePremiumReasonableness:
    """_evaluate_premium_reasonableness 辅助函数测试"""

    def test_high_roe_support(self):
        """测试高 ROE 支撑"""
        result = _evaluate_premium_reasonableness(30, 25, 30, 20)
        assert '合理' in result
        assert 'ROE' in result

    def test_undervalued(self):
        """测试低估"""
        result = _evaluate_premium_reasonableness(-10, 10, 15, 20)
        assert '低估' in result

    def test_small_premium(self):
        """测试小幅溢价"""
        result = _evaluate_premium_reasonableness(15, 10, 20, 18)
        assert '合理' in result

    def test_medium_premium(self):
        """测试中等溢价"""
        result = _evaluate_premium_reasonableness(40, 10, 30, 20)
        assert '偏高' in result

    def test_large_premium(self):
        """测试大幅溢价"""
        result = _evaluate_premium_reasonableness(80, 10, 40, 20)
        assert '较高' in result

    def test_excessive_premium(self):
        """测试溢价过高"""
        result = _evaluate_premium_reasonableness(150, 10, 60, 20)
        assert '过高' in result


# ============================================================
# 获取股票行业测试
# ============================================================

class TestGetStockIndustry:
    """测试 get_stock_industry 函数"""

    @patch('scripts.industry_analysis._http_get_safe')
    @patch('scripts.industry_analysis.get_market_info')
    @patch('scripts.industry_analysis.get_secid')
    def test_success_from_stock_api(self, mock_secid, mock_market, mock_http):
        """测试从个股接口成功获取行业"""
        mock_market.return_value = ('SH', 1, 100)
        mock_secid.return_value = '1.600519'
        mock_http.return_value = {
            "data": {
                "f127": "BK0477"
            }
        }

        result = get_stock_industry('600519')
        assert result == 'BK0477'

    @patch('scripts.industry_analysis._http_get_safe')
    @patch('scripts.industry_analysis.get_market_info')
    @patch('scripts.industry_analysis.get_secid')
    def test_empty_api_response(self, mock_secid, mock_market, mock_http):
        """测试 API 返回空数据"""
        mock_market.return_value = ('SH', 1, 100)
        mock_secid.return_value = '1.600519'
        mock_http.return_value = {"data": {}}

        # 当 f127 为空时，会调用 _find_industry_from_board
        with patch('scripts.industry_analysis._find_industry_from_board', return_value=''):
            result = get_stock_industry('600519')
            assert result == ''

    @patch('scripts.industry_analysis.get_market_info')
    def test_invalid_code(self, mock_market):
        """测试无效代码"""
        mock_market.side_effect = ValueError("无法识别")
        result = get_stock_industry('INVALID')
        assert result == ''


# ============================================================
# 获取同行业股票列表测试
# ============================================================

class TestFetchIndustryPeers:
    """测试 fetch_industry_peers 函数"""

    @patch('scripts.industry_analysis.get_stock_industry')
    @patch('scripts.industry_analysis._http_get_safe')
    def test_success(self, mock_http, mock_industry):
        """测试成功获取同行业股票"""
        mock_industry.return_value = 'BK0477'
        mock_http.return_value = {
            "data": {
                "diff": [
                    {
                        "f12": "600519",
                        "f14": "贵州茅台",
                        "f9": 30.5,
                        "f23": 8.2,
                        "f37": 25.3,
                        "f20": 2000000000000,
                    },
                    {
                        "f12": "000858",
                        "f14": "五粮液",
                        "f9": 20.1,
                        "f23": 5.1,
                        "f37": 22.1,
                        "f20": 800000000000,
                    },
                ]
            }
        }

        result = fetch_industry_peers('600519')
        assert len(result) == 2
        assert result[0]['代码'] == '600519'
        assert result[0]['名称'] == '贵州茅台'
        assert result[0]['PE'] == 30.5
        assert result[1]['代码'] == '000858'

    @patch('scripts.industry_analysis.get_stock_industry')
    def test_no_industry_found(self, mock_industry):
        """测试未找到行业"""
        mock_industry.return_value = ''
        result = fetch_industry_peers('600519')
        assert result == []

    @patch('scripts.industry_analysis.get_stock_industry')
    @patch('scripts.industry_analysis._http_get_safe')
    def test_empty_api_response(self, mock_http, mock_industry):
        """测试 API 返回空数据"""
        mock_industry.return_value = 'BK0477'
        mock_http.return_value = {"data": {"diff": []}}
        result = fetch_industry_peers('600519')
        assert result == []


# ============================================================
# 估值对比分析测试
# ============================================================

class TestAnalyzeValuationComparison:
    """测试 analyze_valuation_comparison 函数"""

    def test_normal_comparison(self):
        """测试正常估值对比"""
        peers = [
            {'代码': '600519', '名称': '贵州茅台', 'PE': 30.0, 'PB': 8.0, 'ROE': 25.0, '总市值': 2000},
            {'代码': '000858', '名称': '五粮液', 'PE': 20.0, 'PB': 5.0, 'ROE': 22.0, '总市值': 800},
            {'代码': '002304', '名称': '洋河股份', 'PE': 15.0, 'PB': 3.0, 'ROE': 18.0, '总市值': 500},
        ]

        result = analyze_valuation_comparison('600519', peers)
        assert result['PE排名'] == 3  # PE 最高，排名最后
        assert result['PB排名'] == 3  # PB 最高
        assert result['ROE排名'] == 1  # ROE 最高
        assert len(result['估值排名']) == 3

    def test_empty_peers(self):
        """测试空列表"""
        result = analyze_valuation_comparison('600519', [])
        assert result['PE排名'] == 0
        assert result['PB排名'] == 0
        assert result['ROE排名'] == 0
        assert result['估值排名'] == []

    def test_all_negative_pe(self):
        """测试所有股票 PE 为负"""
        peers = [
            {'代码': '600519', '名称': '股票A', 'PE': -10.0, 'PB': 2.0, 'ROE': -5.0, '总市值': 100},
            {'代码': '000858', '名称': '股票B', 'PE': -20.0, 'PB': 1.0, 'ROE': -10.0, '总市值': 50},
        ]

        result = analyze_valuation_comparison('600519', peers)
        assert result['PE排名'] == 0  # 无有效 PE 数据
        assert result['估值排名'] == []

    def test_best_valuation(self):
        """测试估值最优的股票"""
        peers = [
            {'代码': '600519', '名称': '贵州茅台', 'PE': 10.0, 'PB': 2.0, 'ROE': 30.0, '总市值': 2000},
            {'代码': '000858', '名称': '五粮液', 'PE': 20.0, 'PB': 5.0, 'ROE': 20.0, '总市值': 800},
        ]

        result = analyze_valuation_comparison('600519', peers)
        assert result['PE排名'] == 1
        assert result['PB排名'] == 1
        assert result['ROE排名'] == 1


# ============================================================
# 资金流向对比测试
# ============================================================

class TestAnalyzeFundFlowComparison:
    """测试 analyze_fund_flow_comparison 函数"""

    @patch('scripts.industry_analysis._get_market_id')
    @patch('scripts.industry_analysis._http_get_safe')
    def test_normal_comparison(self, mock_http, mock_market_id):
        """测试正常资金流向对比"""
        mock_market_id.return_value = 1

        # 模拟两只股票的资金流向
        mock_http.side_effect = [
            {"data": {"f62": 1000000, "f164": 5000000}},  # 股票A
            {"data": {"f62": -500000, "f164": 2000000}},   # 股票B
        ]

        peers = [
            {'代码': '600519', '名称': '贵州茅台', 'PE': 30.0, 'PB': 8.0, 'ROE': 25.0, '总市值': 2000},
            {'代码': '000858', '名称': '五粮液', 'PE': 20.0, 'PB': 5.0, 'ROE': 22.0, '总市值': 800},
        ]

        result = analyze_fund_flow_comparison('600519', peers)
        assert len(result['今日排名']) == 2
        assert len(result['5日排名']) == 2
        assert result['今日排名'][0]['代码'] == '600519'  # 今日净流入最多
        assert result['5日排名'][0]['代码'] == '600519'   # 5日净流入最多

    def test_empty_peers(self):
        """测试空列表"""
        result = analyze_fund_flow_comparison('600519', [])
        assert result['今日排名'] == []
        assert result['5日排名'] == []


# ============================================================
# 行业景气度分析测试
# ============================================================

class TestAnalyzeIndustrySentiment:
    """测试 analyze_industry_sentiment 函数"""

    @patch('scripts.industry_analysis._http_get_safe')
    def test_high_sentiment(self, mock_http):
        """测试高景气度行业"""
        mock_http.return_value = {
            "data": {
                "diff": [
                    {
                        "f12": "BK0477",
                        "f3": 3.5,
                        "f8": 4.2,
                        "f62": 500000000,
                        "f104": 45,
                        "f105": 5,
                    }
                ]
            }
        }

        result = analyze_industry_sentiment('BK0477')
        assert result['涨跌幅'] == 3.5
        assert result['换手率'] == 4.2
        assert result['资金流入'] == '流入'
        assert result['景气度'] == '高景气'

    @patch('scripts.industry_analysis._http_get_safe')
    def test_low_sentiment(self, mock_http):
        """测试低景气度行业"""
        mock_http.return_value = {
            "data": {
                "diff": [
                    {
                        "f12": "BK0477",
                        "f3": -3.0,
                        "f8": 0.8,
                        "f62": -300000000,
                        "f104": 5,
                        "f105": 45,
                    }
                ]
            }
        }

        result = analyze_industry_sentiment('BK0477')
        assert result['涨跌幅'] == -3.0
        assert result['资金流入'] == '流出'
        assert result['景气度'] == '低景气'

    @patch('scripts.industry_analysis._http_get_safe')
    def test_empty_api_response(self, mock_http):
        """测试 API 返回空数据"""
        mock_http.return_value = {"data": {"diff": []}}
        result = analyze_industry_sentiment('BK0477')
        assert result['景气度'] == '中性'

    def test_empty_industry_code(self):
        """测试空行业代码"""
        result = analyze_industry_sentiment('')
        assert result['景气度'] == '中性'


# ============================================================
# 龙头溢价分析测试
# ============================================================

class TestAnalyzeLeaderPremium:
    """测试 analyze_leader_premium 函数"""

    def test_normal_premium(self):
        """测试正常龙头溢价"""
        peers = [
            {'代码': '600519', '名称': '贵州茅台', 'PE': 30.0, 'PB': 8.0, 'ROE': 25.0, '总市值': 2000},
            {'代码': '000858', '名称': '五粮液', 'PE': 20.0, 'PB': 5.0, 'ROE': 22.0, '总市值': 800},
            {'代码': '002304', '名称': '洋河股份', 'PE': 15.0, 'PB': 3.0, 'ROE': 18.0, '总市值': 500},
        ]

        result = analyze_leader_premium('600519', peers)
        assert result['龙头公司'] == '贵州茅台'
        assert result['龙头PE'] == 30.0
        assert result['行业平均PE'] == 21.67  # (30+20+15)/3
        assert result['溢价率'] > 0

    def test_empty_peers(self):
        """测试空列表"""
        result = analyze_leader_premium('600519', [])
        assert result['龙头公司'] == ''
        assert result['龙头PE'] == 0.0

    def test_leader_is_undervalued(self):
        """测试龙头估值低于行业平均"""
        peers = [
            {'代码': '600519', '名称': '贵州茅台', 'PE': 15.0, 'PB': 3.0, 'ROE': 10.0, '总市值': 2000},
            {'代码': '000858', '名称': '五粮液', 'PE': 25.0, 'PB': 5.0, 'ROE': 18.0, '总市值': 800},
        ]

        result = analyze_leader_premium('600519', peers)
        assert result['龙头公司'] == '贵州茅台'
        assert result['溢价率'] < 0  # 低于平均
        assert '低估' in result['溢价合理性']

    def test_high_roe_supports_premium(self):
        """测试高 ROE 支撑溢价"""
        peers = [
            {'代码': '600519', '名称': '贵州茅台', 'PE': 40.0, 'PB': 10.0, 'ROE': 25.0, '总市值': 2000},
            {'代码': '000858', '名称': '五粮液', 'PE': 20.0, 'PB': 5.0, 'ROE': 15.0, '总市值': 800},
        ]

        result = analyze_leader_premium('600519', peers)
        assert '合理' in result['溢价合理性']
        assert 'ROE' in result['溢价合理性']

    def test_excessive_premium(self):
        """测试溢价过高"""
        peers = [
            {'代码': '600519', '名称': '贵州茅台', 'PE': 100.0, 'PB': 20.0, 'ROE': 5.0, '总市值': 2000},
            {'代码': '000858', '名称': '五粮液', 'PE': 10.0, 'PB': 2.0, 'ROE': 15.0, '总市值': 800},
            {'代码': '002304', '名称': '洋河股份', 'PE': 10.0, 'PB': 2.0, 'ROE': 12.0, '总市值': 500},
            {'代码': '600809', '名称': '山西汾酒', 'PE': 10.0, 'PB': 2.0, 'ROE': 18.0, '总市值': 400},
            {'代码': '000568', '名称': '泸州老窖', 'PE': 10.0, 'PB': 2.0, 'ROE': 16.0, '总市值': 300},
        ]

        result = analyze_leader_premium('600519', peers)
        # 平均 PE = (100 + 10 + 10 + 10 + 10) / 5 = 28
        # 溢价率 = (100 - 28) / 28 * 100 = 257%
        # 由于 ROE=5 < 15，不触发高 ROE 检查，应返回 '过高'
        assert '过高' in result['溢价合理性']


# ============================================================
# 主函数测试
# ============================================================

class TestAnalyzeIndustryComparison:
    """测试 analyze_industry_comparison 主函数"""

    @patch('scripts.industry_analysis.get_stock_industry')
    @patch('scripts.industry_analysis.fetch_industry_peers')
    @patch('scripts.industry_analysis.analyze_valuation_comparison')
    @patch('scripts.industry_analysis.analyze_fund_flow_comparison')
    @patch('scripts.industry_analysis.analyze_industry_sentiment')
    @patch('scripts.industry_analysis.analyze_leader_premium')
    def test_complete_flow(self, mock_leader, mock_sentiment,
                           mock_flow, mock_valuation, mock_peers, mock_industry):
        """测试完整流程"""
        mock_industry.return_value = 'BK0477'
        mock_peers.return_value = [
            {'代码': '600519', '名称': '贵州茅台', 'PE': 30.0, 'PB': 8.0, 'ROE': 25.0, '总市值': 2000},
        ]
        mock_valuation.return_value = {'PE排名': 1, 'PB排名': 1, 'ROE排名': 1, '估值排名': []}
        mock_flow.return_value = {'今日排名': [], '5日排名': []}
        mock_sentiment.return_value = {'涨跌幅': 1.0, '换手率': 2.0, '资金流入': '流入', '景气度': '中性'}
        mock_leader.return_value = {'龙头公司': '贵州茅台', '龙头PE': 30.0, '行业平均PE': 25.0, '溢价率': 20.0, '溢价合理性': '合理'}

        result = analyze_industry_comparison('600519')

        assert result['行业'] == 'BK0477'
        assert '估值对比' in result
        assert '资金流向' in result
        assert '行业景气度' in result
        assert '龙头溢价' in result

    @patch('scripts.industry_analysis.get_stock_industry')
    @patch('scripts.industry_analysis.fetch_industry_peers')
    def test_no_industry_found(self, mock_peers, mock_industry):
        """测试未找到行业"""
        mock_industry.return_value = ''
        mock_peers.return_value = []

        result = analyze_industry_comparison('600519')
        assert result['行业'] == ''
        assert result['估值对比']['PE排名'] == 0
        assert result['资金流向']['今日排名'] == []
        assert result['行业景气度']['景气度'] == '中性'
        assert result['龙头溢价']['龙头公司'] == ''


# ============================================================
# 集成测试
# ============================================================

class TestIntegration:
    """集成测试"""

    @patch('scripts.industry_analysis._http_get_safe')
    @patch('scripts.industry_analysis.get_market_info')
    @patch('scripts.industry_analysis.get_secid')
    def test_fetch_peers_with_real_structure(self, mock_secid, mock_market, mock_http):
        """测试获取同行业股票的完整流程"""
        mock_market.return_value = ('SH', 1, 100)
        mock_secid.return_value = '1.600519'

        # 模拟获取行业 - 使用 return_value 而非 side_effect
        mock_http.return_value = {
            "data": {
                "diff": [
                    {"f12": "600519", "f14": "贵州茅台", "f9": 30.5, "f23": 8.2, "f37": 25.3, "f20": 2000000000000},
                    {"f12": "000858", "f14": "五粮液", "f9": 20.1, "f23": 5.1, "f37": 22.1, "f20": 800000000000},
                ]
            }
        }

        # 测试 fetch_industry_peers（跳过 get_stock_industry 的调用）
        with patch('scripts.industry_analysis.get_stock_industry', return_value='BK0477'):
            peers = fetch_industry_peers('600519')
            assert len(peers) == 2
            assert peers[0]['代码'] == '600519'

    def test_valuation_ranking_consistency(self):
        """测试估值排名一致性"""
        peers = [
            {'代码': 'A', '名称': '股票A', 'PE': 10.0, 'PB': 1.0, 'ROE': 30.0, '总市值': 100},
            {'代码': 'B', '名称': '股票B', 'PE': 20.0, 'PB': 2.0, 'ROE': 20.0, '总市值': 200},
            {'代码': 'C', '名称': '股票C', 'PE': 30.0, 'PB': 3.0, 'ROE': 10.0, '总市值': 300},
        ]

        result = analyze_valuation_comparison('A', peers)
        assert result['PE排名'] == 1  # PE 最低
        assert result['PB排名'] == 1  # PB 最低
        assert result['ROE排名'] == 1  # ROE 最高
        assert result['估值排名'][0]['代码'] == 'A'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
