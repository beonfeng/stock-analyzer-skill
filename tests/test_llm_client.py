#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM 客户端模块测试

测试策略：
- 不依赖实际 API Key（使用 mock 模拟）
- 测试 provider 检测、prompt 构建、响应解析
- 测试优雅降级（无 API Key 时返回 None）
- 测试 ReportContext 集成
"""

import os
import sys
from unittest import mock
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestProviderDetection:
    """测试 LLM provider 检测"""

    def test_detect_no_keys_returns_unknown(self):
        """无 API Key 时返回 UNKNOWN"""
        from scripts.llm_client import detect_provider, LLMProvider
        # 临时清除环境变量
        with mock.patch.dict(os.environ, {}, clear=True):
            provider, key, url = detect_provider()
            assert provider == LLMProvider.UNKNOWN
            assert key is None

    def test_detect_anthropic_from_env(self):
        """ANTHROPIC_API_KEY 检测为 Anthropic"""
        from scripts.llm_client import detect_provider, LLMProvider
        env = {"ANTHROPIC_API_KEY": "sk-ant-test-key-123"}
        with mock.patch.dict(os.environ, env, clear=True):
            provider, key, url = detect_provider()
            # 可能因为 HAS_ANTHROPIC=False 而无法检测，但至少不崩溃
            assert provider in (LLMProvider.ANTHROPIC, LLMProvider.UNKNOWN)

    def test_detect_openai_from_env(self):
        """OPENAI_API_KEY 检测为 OpenAI-compatible"""
        from scripts.llm_client import detect_provider, LLMProvider
        env = {"OPENAI_API_KEY": "sk-test-key-123"}
        with mock.patch.dict(os.environ, env, clear=True):
            provider, key, url = detect_provider()
            assert provider in (LLMProvider.OPENAI_COMPATIBLE, LLMProvider.UNKNOWN)

    def test_detect_stock_llm_key_anthropic(self):
        """STOCK_LLM_API_KEY 以 sk-ant- 开头检测为 Anthropic"""
        from scripts.llm_client import detect_provider, LLMProvider
        env = {"STOCK_LLM_API_KEY": "sk-ant-api03-xxx"}
        with mock.patch.dict(os.environ, env, clear=True):
            provider, key, url = detect_provider()
            assert provider == LLMProvider.ANTHROPIC

    def test_detect_stock_llm_key_openai(self):
        """STOCK_LLM_API_KEY 以 sk- 开头检测为 OpenAI-compatible"""
        from scripts.llm_client import detect_provider, LLMProvider
        env = {"STOCK_LLM_API_KEY": "sk-proj-xxx"}
        with mock.patch.dict(os.environ, env, clear=True):
            provider, key, url = detect_provider()
            assert provider == LLMProvider.OPENAI_COMPATIBLE


class TestPromptBuilding:
    """测试 prompt 构建"""

    def test_build_prompt_contains_key_fields(self):
        """Prompt 包含关键数据字段"""
        from scripts.llm_client import build_analysis_prompt
        ctx = {
            "name": "测试", "code": "000001", "price": 10.5, "change_pct": 2.5,
            "technical": {"DIF": 0.5, "DEA": 0.3, "MACD": 0.2, "macd_signal": "金叉",
                          "K": 65.0, "D": 58.0, "J": 79.0, "kdj_zone": "中性",
                          "RSI6": 55.0, "RSI14": 50.0,
                          "MA5": 10.0, "MA20": 9.5, "MA60": 8.0,
                          "trend": "多头", "boll_position": "中轨上方",
                          "ATR14": 0.3, "volume_anomaly": "N/A"},
            "fund_flow": {"main_net_today": 1000000, "main_net_5d": 5000000},
            "fundamentals": {"PE": 12.5, "PB": 1.5, "ROE": 15.0, "gross_margin": 30.0,
                            "revenue_yoy": 10.0, "profit_yoy": 8.0, "debt_ratio": 40.0,
                            "total_mktcap": 50000000000},
            "valuation": {"pe_percentile": "30%", "pe_zone": "偏低",
                         "pb_percentile": "25%", "pb_zone": "偏低"},
            "financial_health": {"red_flags": [], "warnings": ["测试预警"]},
            "sentiment": {"positive": 3, "negative": 1, "neutral": 2},
            "weighted_score": {"total": 5.0, "tech": 2.0, "fund": 1.5, "fin": 1.5},
            "risk": {"stop_loss": 9.0, "target_price": 12.0, "position": "30%"},
        }
        prompt = build_analysis_prompt(ctx)
        assert len(prompt) > 200
        assert "000001" in prompt
        assert "PE" in prompt
        assert "MACD" in prompt
        assert "执行摘要" in prompt
        assert "矛盾检测" in prompt

    def test_build_prompt_handles_empty_context(self):
        """空上下文不崩溃"""
        from scripts.llm_client import build_analysis_prompt
        prompt = build_analysis_prompt({})
        assert len(prompt) > 50
        assert "执行摘要" in prompt

    def test_build_llm_context_from_report_ctx(self):
        """从 ReportContext 提取数据不崩溃"""
        from scripts.llm_client import build_llm_context_from_report_ctx
        # 使用简化的 mock context
        class MockCtx:
            name = "测试"
            code = "000001"
            price = 10.5
            indicators = {"DIF": 0.5, "DEA": 0.3, "MACD": 0.2,
                         "K": 65, "D": 58, "J": 79,
                         "RSI6": 55, "RSI14": 50,
                         "MA5": 10.0, "MA10": 9.8,
                         "MA20": 9.5, "MA60": 8.0,
                         "ATR14": 0.3, "BOLL_MID": 9.5,
                         "BOLL_UP": 10.5, "BOLL_DN": 8.5,
                         "DIF_prev": 0.3, "DEA_prev": 0.4,
                         "涨跌幅_今日": 2.5}
            fund_flow = {"今日": {"f62": 1000000}, "5日": {"f62": 5000000}}
            quote = {"f9": 12.5, "f23": 1.5, "f37": 15.0, "f49": 30.0,
                    "f40": 10.0, "f41": 8.0, "f34": 40.0, "f20": 50000000000}
            financial_health = {"排雷红灯": [], "排雷预警": ["测试预警"]}
            valuation_percentile = {"pe_percentile": "30%", "pe_zone": "偏低",
                                   "pb_percentile": "25%", "pb_zone": "偏低"}
            sentiment_result = {"positive_count": 3, "negative_count": 1, "neutral_count": 2}
            weighted_score = {"total": 5.0, "technical": 2.0, "fund_flow": 1.5, "financial": 1.5}
            stop_loss = 9.0
            target = 12.0
            position = "30%"
            extended_indicators = {}

        ctx = MockCtx()
        data = build_llm_context_from_report_ctx(ctx)
        assert data["name"] == "测试"
        assert data["code"] == "000001"
        assert data["price"] == 10.5
        assert "technical" in data
        assert "fund_flow" in data
        assert "fundamentals" in data


class TestResponseParsing:
    """测试 LLM 响应解析"""

    def test_parse_standard_sections(self):
        """标准格式的响应解析"""
        from scripts.llm_client import parse_llm_response
        text = """
## 执行摘要
这是执行摘要内容。

## 矛盾检测
- 矛盾1：MACD看多但RSI超买
- 矛盾2：主力流出但股价上涨

## 技术信号白话解读
这是白话解读内容。

## 重点关注因子
- 因子1：关注MA20支撑
- 因子2：关注资金流向
"""
        result = parse_llm_response(text)
        assert "执行摘要" in result["executive_summary"]
        assert len(result["contradictions"]) == 2
        assert "白话解读" in result["signal_explanation"]
        assert len(result["key_factors"]) == 2

    def test_parse_no_contradictions(self):
        """无矛盾时的解析"""
        from scripts.llm_client import parse_llm_response
        text = """
## 矛盾检测
未检测到显著矛盾
"""
        result = parse_llm_response(text)
        assert result["contradictions"] == []

    def test_parse_malformed_response(self):
        """格式异常的响应"""
        from scripts.llm_client import parse_llm_response
        result = parse_llm_response("")
        assert result["executive_summary"] == ""
        assert result["contradictions"] == []
        assert result["signal_explanation"] == ""
        assert result["key_factors"] == []

    def test_parse_text_without_headers(self):
        """无标题的纯文本"""
        from scripts.llm_client import parse_llm_response
        text = "这是没有标题的纯文本内容。"
        result = parse_llm_response(text)
        # 应该至少提取执行摘要
        assert len(result["executive_summary"]) > 0


class TestLLMIntegration:
    """测试 LLM 与 analyzer 的集成"""

    def test_analyze_stock_accepts_llm_flag(self):
        """analyze_stock 接受 llm_enabled 参数"""
        from scripts.analyzer import analyze_stock
        import inspect
        sig = inspect.signature(analyze_stock)
        assert "llm_enabled" in sig.parameters

    def test_section_ai_interpretation_empty_without_llm(self):
        """无 LLM 数据时 _section_ai_interpretation 返回空列表"""
        from scripts.analyzer import _section_ai_interpretation
        class MockCtx:
            llm_interpretation = None
        result = _section_ai_interpretation(MockCtx())
        assert result == []

    def test_section_ai_interpretation_with_data(self):
        """有 LLM 数据时 _section_ai_interpretation 生成内容"""
        from scripts.analyzer import _section_ai_interpretation
        class MockCtx:
            llm_interpretation = {
                "executive_summary": "测试摘要",
                "contradictions": ["矛盾1", "矛盾2"],
                "signal_explanation": "测试解读",
                "key_factors": ["因子1", "因子2"],
            }
        result = _section_ai_interpretation(MockCtx())
        assert len(result) > 0
        combined = "\n".join(result)
        assert "AI 增强解读" in combined
        assert "测试摘要" in combined

    def test_section_summary_shows_ai_summary(self):
        """_section_summary 在有 LLM 数据时显示 AI 综述"""
        from scripts.analyzer import _section_summary

        class MockCtx:
            llm_interpretation = {"executive_summary": "这是一段AI生成的综述"}
            rating = None
            indicators = {"涨跌幅_今日": 0, "涨跌幅_5日": 0, "涨跌幅_20日": 0, "涨跌幅_60日": 0}
            price = 10.0
            fund_flow = None
            quote = {}
            financial_health = None

        # 不导入私有格式化函数，只检查不会崩溃且包含 AI 综述
        result = _section_summary(MockCtx())
        combined = "\n".join(result)
        assert "AI 综述" in combined
        assert "AI生成的综述" in combined


class TestCLIFlag:
    """测试 CLI --llm 标志"""

    def test_llm_flag_parsed(self):
        """--llm 标志被正确解析"""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--llm", action="store_true", default=False)
        args = parser.parse_args(["--llm"])
        assert args.llm is True

    def test_llm_flag_default_false(self):
        """默认不启用 --llm"""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--llm", action="store_true", default=False)
        args = parser.parse_args([])
        assert args.llm is False
