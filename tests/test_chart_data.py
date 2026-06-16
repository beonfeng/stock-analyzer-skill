#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图表数据提取与模板测试

测试策略：
- 测试数据提取函数的返回格式和 JSON 可序列化
- 测试图表模板生成的 HTML 包含关键元素
- 测试空数据/缺失数据的优雅处理
"""

import json
import sys
from pathlib import Path

import pytest
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestChartDataExtraction:
    """测试 chart_data.py 数据提取"""

    def _make_test_df(self, days=120):
        """生成测试 K 线数据"""
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=days, freq="B")
        price = 100 + np.cumsum(np.random.randn(days) * 2)
        return pd.DataFrame({
            "日期": dates.strftime("%Y-%m-%d"),
            "开盘": price + np.random.randn(days) * 0.5,
            "收盘": price,
            "最高": price + np.abs(np.random.randn(days) * 1),
            "最低": price - np.abs(np.random.randn(days) * 1),
            "成交量": np.random.randint(100000, 50000000, days),
            "成交额": np.random.randint(10000000, 500000000, days),
        })

    def test_extract_kline_data_format(self):
        """K 线数据提取返回正确格式"""
        from scripts.chart_data import extract_kline_chart_data
        df = self._make_test_df(120)
        data = extract_kline_chart_data(df)

        assert "dates" in data
        assert "close" in data
        assert "volume" in data
        assert len(data["dates"]) == 120
        assert len(data["close"]) == 120
        assert data["latest_price"] > 0

    def test_extract_kline_json_serializable(self):
        """K 线数据可 JSON 序列化"""
        from scripts.chart_data import extract_kline_chart_data
        df = self._make_test_df(50)
        data = extract_kline_chart_data(df)
        json_str = json.dumps(data, default=str)
        assert len(json_str) > 100
        parsed = json.loads(json_str)
        assert parsed["latest_price"] is not None

    def test_extract_kline_empty(self):
        """空 DataFrame 不崩溃"""
        from scripts.chart_data import extract_kline_chart_data
        data = extract_kline_chart_data(pd.DataFrame())
        assert data["dates"] == []
        assert data["close"] == []

    def test_extract_kline_none(self):
        """None 输入不崩溃"""
        from scripts.chart_data import extract_kline_chart_data
        data = extract_kline_chart_data(None)
        assert data["dates"] == []

    def test_extract_valuation_data(self):
        """估值数据提取"""
        from scripts.chart_data import extract_valuation_chart_data
        data = extract_valuation_chart_data(
            {"f9": 25.5, "f23": 3.2, "f92": 1.5},
            {"pe_percentile": "45%", "pe_zone": "合理", "pb_percentile": "30%", "pb_zone": "偏低"},
        )
        assert data["pe_current"] == 25.5
        assert data["pb_current"] == 3.2
        assert data["pe_percentile"] == 45.0

    def test_extract_valuation_none(self):
        """None 估值数据不崩溃"""
        from scripts.chart_data import extract_valuation_chart_data
        data = extract_valuation_chart_data(None, None)
        assert data["pe_current"] == 0
        assert data["pe_percentile"] is None

    def test_extract_fund_flow_data(self):
        """资金流数据提取"""
        from scripts.chart_data import extract_fund_flow_chart_data
        df = self._make_test_df(20)
        data = extract_fund_flow_chart_data(
            {"今日": {"f62": 50000000}, "5日": {"f62": 120000000}},
            df,
        )
        assert data["main_today"] == 5000.0  # 转为万元
        assert data["main_5d"] == 12000.0

    def test_extract_all_chart_data(self):
        """统一提取接口"""
        from scripts.chart_data import extract_all_chart_data
        df = self._make_test_df(120)
        data = extract_all_chart_data(df)
        assert "kline" in data
        assert "valuation" in data
        assert "fund_flow" in data


class TestChartTemplates:
    """测试 charts_template.py 模板生成"""

    def _make_chart_data(self):
        from scripts.chart_data import extract_all_chart_data
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=120, freq="B")
        price = 100 + np.cumsum(np.random.randn(120) * 2)
        df = pd.DataFrame({
            "日期": dates.strftime("%Y-%m-%d"),
            "开盘": price + np.random.randn(120) * 0.5,
            "收盘": price,
            "最高": price + np.abs(np.random.randn(120) * 1),
            "最低": price - np.abs(np.random.randn(120) * 1),
            "成交量": np.random.randint(100000, 50000000, 120),
            "成交额": np.random.randint(10000000, 500000000, 120),
        })
        return extract_all_chart_data(df)

    def test_kline_chart_html_contains_elements(self):
        """K 线图表 HTML 包含关键元素"""
        from scripts.charts_template import build_kline_chart_html
        data = {"dates": ["2024-01-01", "2024-01-02"], "close": [100.0, 101.0],
                "volume": [10000, 12000], "ma5": [None, 100.5],
                "ma10": [None, None], "ma20": [None, None], "ma60": [None, None],
                "boll_up": [None, None], "boll_mid": [None, None], "boll_dn": [None, None],
                "macd_dif": [None, None], "macd_dea": [None, None], "macd_hist": [None, None],
                "name": "测试", "code": "000001", "latest_price": 101.0}
        html = build_kline_chart_html(data)
        assert "<canvas" in html
        assert 'chart-kline' in html
        assert 'application/json' in html

    def test_valuation_chart_html_contains_elements(self):
        """估值图表 HTML 包含关键元素"""
        from scripts.charts_template import build_valuation_chart_html
        data = {"pe_current": 25.5, "pe_percentile": 45.0, "pe_zone": "合理",
                "pb_current": 3.2, "pb_percentile": 30.0, "pb_zone": "偏低",
                "pe_history": [], "pb_history": []}
        html = build_valuation_chart_html(data)
        assert "估值" in html
        assert 'chart-valuation' in html
        assert "25.5" in html

    def test_fund_flow_chart_html_contains_elements(self):
        """资金流图表 HTML 包含关键元素"""
        from scripts.charts_template import build_fund_flow_chart_html
        data = {"main_today": 5000, "main_5d": 12000, "dates": []}
        html = build_fund_flow_chart_html(data)
        assert "主力资金" in html
        assert 'chart-fundflow' in html

    def test_build_all_charts_html(self):
        """统一图表生成"""
        from scripts.charts_template import build_all_charts_html
        chart_data = self._make_chart_data()
        html = build_all_charts_html(chart_data)
        assert len(html) > 500
        assert "<canvas" in html
        assert "<script" in html
        # 验证 HTML 完整性：script 标签闭合
        assert html.count("</script>") >= 1

    def test_chart_renderer_js_present(self):
        """渲染 JS 被包含"""
        from scripts.charts_template import _CHART_RENDERER_JS
        assert "renderKlineChart" in _CHART_RENDERER_JS
        assert "renderValuationChart" in _CHART_RENDERER_JS
        assert "renderFundFlowChart" in _CHART_RENDERER_JS


class TestExporterIntegration:
    """测试 exporter.py 与图表的集成"""

    def test_md_to_html_accepts_chart_data(self):
        """md_to_html 接受 chart_data 参数"""
        from scripts.exporter import md_to_html
        html = md_to_html("# Test\nHello", "测试", chart_data={})
        assert "Test" in html

    def test_md_to_html_injects_charts(self):
        """md_to_html 在有 chart_data 时注入图表"""
        from scripts.exporter import md_to_html
        from scripts.chart_data import extract_all_chart_data
        import pandas as pd
        import numpy as np

        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=120, freq="B")
        price = 100 + np.cumsum(np.random.randn(120) * 2)
        df = pd.DataFrame({
            "日期": dates.strftime("%Y-%m-%d"),
            "开盘": price + np.random.randn(120) * 0.5,
            "收盘": price,
            "最高": price + np.abs(np.random.randn(120) * 1),
            "最低": price - np.abs(np.random.randn(120) * 1),
            "成交量": np.random.randint(100000, 50000000, 120),
            "成交额": np.random.randint(10000000, 500000000, 120),
        })
        chart_data = extract_all_chart_data(df)
        html = md_to_html("# Test\nHello", "测试", chart_data=chart_data)
        assert "<canvas" in html
        assert "chart-kline" in html

    def test_md_to_html_no_chart_without_data(self):
        """无 chart_data 时不注入图表"""
        from scripts.exporter import md_to_html
        html = md_to_html("# Test", "测试")
        assert "<canvas" not in html
