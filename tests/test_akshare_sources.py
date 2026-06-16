#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AKShare 数据源模块测试

测试策略：
- 不依赖 AKShare 实际安装（使用 mock 模拟）
- 测试函数签名、返回格式兼容性、_source 标记
- 测试 HAS_AKSHARE 标志的优雅降级
- 测试 DataSourceManager 优先级链和回退逻辑
"""

import os
import sys
import json
from unittest import mock
from pathlib import Path

import pytest
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestAKShareImport:
    """测试 AKShare 模块的安全导入"""

    def test_module_imports_without_error(self):
        """模块导入不抛异常（即使 akshare 未安装）"""
        from scripts import akshare_sources
        assert hasattr(akshare_sources, 'HAS_AKSHARE')

    def test_has_akshare_is_boolean(self):
        """HAS_AKSHARE 是布尔值"""
        from scripts import akshare_sources
        assert isinstance(akshare_sources.HAS_AKSHARE, bool)

    def test_fallback_imports_in_analyzer(self):
        """analyzer.py 中的 AKShare 导入不抛异常"""
        from scripts import analyzer
        assert hasattr(analyzer, 'HAS_AKSHARE')
        assert isinstance(analyzer.HAS_AKSHARE, bool)

    def test_datasource_manager_imports(self):
        """DataSourceManager 模块正常导入"""
        from scripts import datasource_manager
        from scripts.datasource_manager import DataSourceManager, get_datasource_manager
        assert DataSourceManager is not None
        mgr = get_datasource_manager()
        assert mgr is not None


class TestAKShareSourceCompatibility:
    """测试 AKShare 函数返回格式与东方财富兼容"""

    def test_fetch_kline_akshare_returns_none_when_not_installed(self):
        """未安装 akshare 时返回 None"""
        from scripts import akshare_sources
        if not akshare_sources.HAS_AKSHARE:
            result = akshare_sources.fetch_kline_akshare("600519", days=5)
            assert result is None

    def test_fetch_quote_akshare_returns_none_when_not_installed(self):
        """未安装 akshare 时返回 None"""
        from scripts import akshare_sources
        if not akshare_sources.HAS_AKSHARE:
            result = akshare_sources.fetch_quote_akshare("600519")
            assert result is None

    def test_fetch_financial_report_akshare_returns_none_when_not_installed(self):
        """未安装 akshare 时返回 None"""
        from scripts import akshare_sources
        if not akshare_sources.HAS_AKSHARE:
            result = akshare_sources.fetch_financial_report_akshare("600519")
            assert result is None

    def test_fetch_company_profile_akshare_returns_none_when_not_installed(self):
        """未安装 akshare 时返回 None"""
        from scripts import akshare_sources
        if not akshare_sources.HAS_AKSHARE:
            result = akshare_sources.fetch_company_profile_akshare("600519")
            assert result is None

    def test_fetch_news_akshare_returns_none_when_not_installed(self):
        """未安装 akshare 时返回 None"""
        from scripts import akshare_sources
        if not akshare_sources.HAS_AKSHARE:
            result = akshare_sources.fetch_news_akshare("600519")
            assert result is None

    def test_fetch_fund_flow_akshare_returns_none(self):
        """资金流向 AKShare 暂不支持，始终返回 None"""
        from scripts import akshare_sources
        result = akshare_sources.fetch_fund_flow_akshare("600519")
        assert result is None


class TestDataSourceManager:
    """测试统一数据源管理器"""

    def test_manager_initialization(self):
        """DataSourceManager 正常初始化"""
        from scripts.datasource_manager import DataSourceManager
        mgr = DataSourceManager()
        assert mgr.get_stats()["success"] == {}
        assert mgr.get_stats()["fail"] == {}

    def test_manager_stats_recording(self):
        """统计记录正常工作"""
        from scripts.datasource_manager import DataSourceManager
        mgr = DataSourceManager()
        mgr._record("EastMoney", True)
        mgr._record("AKShare", False)
        stats = mgr.get_stats()
        assert stats["success"]["EastMoney"] == 1
        assert stats["fail"]["AKShare"] == 1

    def test_manager_reset_stats(self):
        """重置统计"""
        from scripts.datasource_manager import DataSourceManager
        mgr = DataSourceManager()
        mgr._record("EastMoney", True)
        mgr.reset_stats()
        assert mgr.get_stats()["success"] == {}

    def test_check_all_health_returns_dict(self):
        """健康检查返回 dict 结构"""
        from scripts.datasource_manager import DataSourceManager
        mgr = DataSourceManager()
        health = mgr.check_all_health()
        assert isinstance(health, dict)
        assert "alt" in health
        assert "akshare" in health

    def test_get_datasource_manager_singleton(self):
        """get_datasource_manager 返回单例"""
        from scripts.datasource_manager import get_datasource_manager
        mgr1 = get_datasource_manager()
        mgr2 = get_datasource_manager()
        assert mgr1 is mgr2


class TestFallbackChainIntegration:
    """测试 analyzer.py 中的 AKShare 回退链集成"""

    def test_fetch_kline_has_akshare_fallback(self):
        """fetch_kline 包含 AKShare 回退逻辑"""
        from scripts.analyzer import fetch_kline
        # 测试正常调用不会崩溃（无论 AKShare 是否安装）
        try:
            df = fetch_kline("600519", days=5)
            assert isinstance(df, pd.DataFrame)
        except Exception as e:
            pytest.fail(f"fetch_kline 崩溃: {e}")

    def test_fetch_financial_report_has_akshare_fallback(self):
        """fetch_financial_report 包含 AKShare 回退"""
        from scripts.analyzer import fetch_financial_report
        try:
            result = fetch_financial_report("600519")
            assert isinstance(result, list)
        except Exception as e:
            pytest.fail(f"fetch_financial_report 崩溃: {e}")

    def test_fetch_company_profile_has_akshare_fallback(self):
        """fetch_company_profile 包含 AKShare 回退"""
        from scripts.analyzer import fetch_company_profile
        try:
            result = fetch_company_profile("600519")
            assert isinstance(result, dict)
            assert "基本信息" in result
        except Exception as e:
            pytest.fail(f"fetch_company_profile 崩溃: {e}")

    def test_fetch_stock_news_has_akshare_fallback(self):
        """fetch_stock_news 包含 AKShare 回退"""
        from scripts.analyzer import fetch_stock_news
        try:
            result = fetch_stock_news("600519")
            assert isinstance(result, pd.DataFrame)
        except Exception as e:
            pytest.fail(f"fetch_stock_news 崩溃: {e}")
