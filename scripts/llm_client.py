#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM 客户端模块 — 多 Provider AI 增强报告解读

当用户设置 --llm 标志且配置了 API Key 时，使用 LLM 生成：
- 执行摘要（自然语言综述）
- 指标矛盾检测（如 MACD 看多但 RSI 超买）
- 白话技术信号解读（面向非专业投资者）
- 重点关注跟踪因子

支持 Provider:
- Anthropic (ANTHROPIC_API_KEY 环境变量)
- OpenAI-compatible (OPENAI_API_KEY + OPENAI_BASE_URL 环境变量)
- 自定义 (STOCK_LLM_API_KEY + STOCK_LLM_BASE_URL 环境变量)

所有依赖均为可选，未安装时自动降级为规则输出。
"""

import os
import json
import re
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ============================================================
# 安全导入 — 所有 LLM 依赖均可选
# ============================================================

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# ============================================================
# Provider 类型
# ============================================================

class LLMProvider(Enum):
    ANTHROPIC = "anthropic"
    OPENAI_COMPATIBLE = "openai_compatible"
    UNKNOWN = "unknown"


# ============================================================
# Provider 检测
# ============================================================

def detect_provider() -> Tuple[LLMProvider, Optional[str], Optional[str]]:
    """
    检测可用的 LLM provider 和凭证。

    检测顺序：
    1. STOCK_LLM_API_KEY 环境变量 → 根据 key 前缀推断 provider
    2. ANTHROPIC_API_KEY 环境变量 → Anthropic
    3. OPENAI_API_KEY 环境变量 → OpenAI-compatible

    Returns:
        (provider, api_key, base_url)
        provider=UNKNOWN 表示未检测到可用 provider
    """
    # 显式指定
    explicit_key = os.environ.get("STOCK_LLM_API_KEY", "")
    if explicit_key:
        base_url = os.environ.get("STOCK_LLM_BASE_URL", "")
        if explicit_key.startswith("sk-ant-"):
            return LLMProvider.ANTHROPIC, explicit_key, base_url
        elif explicit_key.startswith("sk-"):
            return LLMProvider.OPENAI_COMPATIBLE, explicit_key, base_url or "https://api.openai.com/v1"
        else:
            # 未知前缀，尝试作为 OpenAI-compatible
            return LLMProvider.OPENAI_COMPATIBLE, explicit_key, base_url or "https://api.openai.com/v1"

    # Anthropic
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if anthropic_key and HAS_ANTHROPIC:
        return LLMProvider.ANTHROPIC, anthropic_key, ""

    # OpenAI
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if openai_key and HAS_REQUESTS:
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        return LLMProvider.OPENAI_COMPATIBLE, openai_key, base_url

    return LLMProvider.UNKNOWN, None, None


# ============================================================
# Prompt 构建
# ============================================================

def build_analysis_prompt(ctx_data: Dict[str, Any]) -> str:
    """
    从 ReportContext 提取的数据构建 LLM 分析 prompt。

    发送结构化数据而非原始 markdown，节省 token 并提高准确性。
    """
    # 构建精简的结构化数据摘要
    lines = []
    lines.append("你是一位专业的A股投资分析师。请基于以下结构化数据，生成一份简明的分析解读。")
    lines.append("")

    # 基本信息
    stock_name = ctx_data.get("name", "未知")
    stock_code = ctx_data.get("code", "未知")
    price = ctx_data.get("price", 0)
    change_pct = ctx_data.get("change_pct", 0)
    lines.append(f"## 股票: {stock_name}({stock_code}) 最新价: {price:.2f} 涨跌幅: {change_pct:+.2f}%")
    lines.append("")

    # 技术面
    tech = ctx_data.get("technical", {})
    if tech:
        lines.append("## 技术面数据")
        lines.append(f"- MACD: DIF={tech.get('DIF', 0):.4f}, DEA={tech.get('DEA', 0):.4f}, "
                     f"MACD柱={tech.get('MACD', 0):.4f}, 信号={tech.get('macd_signal', 'N/A')}")
        lines.append(f"- KDJ: K={tech.get('K', 0):.1f}, D={tech.get('D', 0):.1f}, J={tech.get('J', 0):.1f}, "
                     f"状态={tech.get('kdj_zone', 'N/A')}")
        rsi6 = tech.get('RSI6', 50)
        rsi14 = tech.get('RSI14', 50)
        lines.append(f"- RSI: RSI6={rsi6:.1f}, RSI14={rsi14:.1f}")
        lines.append(f"- 均线: MA5={tech.get('MA5', 0):.2f}, MA20={tech.get('MA20', 0):.2f}, "
                     f"MA60={tech.get('MA60', 0):.2f}")
        lines.append(f"- 趋势: {tech.get('trend', 'N/A')}")
        boll_pos = tech.get('boll_position', 'N/A')
        lines.append(f"- 布林带位置: {boll_pos}")
        lines.append(f"- ATR14: {tech.get('ATR14', 0):.2f}")
        vol_anomaly = tech.get('volume_anomaly', 'N/A')
        if vol_anomaly != 'N/A':
            lines.append(f"- 成交量异动: {vol_anomaly}")
        lines.append("")

    # 资金面
    fund = ctx_data.get("fund_flow", {})
    if fund:
        lines.append("## 资金面数据")
        main_today = fund.get("main_net_today", 0) / 1e8
        main_5d = fund.get("main_net_5d", 0) / 1e8
        lines.append(f"- 主力资金今日: {main_today:+.2f}亿, 5日: {main_5d:+.2f}亿")
        lines.append("")

    # 基本面
    funda = ctx_data.get("fundamentals", {})
    if funda:
        lines.append("## 基本面数据")
        lines.append(f"- PE: {funda.get('PE', 0):.1f}, PB: {funda.get('PB', 0):.2f}")
        lines.append(f"- ROE: {funda.get('ROE', 0):.2f}%, 毛利率: {funda.get('gross_margin', 0):.2f}%")
        lines.append(f"- 营收同比: {funda.get('revenue_yoy', 0):.2f}%, 净利润同比: {funda.get('profit_yoy', 0):.2f}%")
        lines.append(f"- 资产负债率: {funda.get('debt_ratio', 0):.2f}%")
        lines.append(f"- 总市值: {funda.get('total_mktcap', 0)/1e8:.0f}亿")
        if funda.get('dividend_yield', 0) > 0:
            lines.append(f"- 股息率: {funda.get('dividend_yield', 0):.2f}%")
        lines.append("")

    # 估值分位数
    val = ctx_data.get("valuation", {})
    if val:
        lines.append("## 估值分位数（近5年）")
        lines.append(f"- PE 分位数: {val.get('pe_percentile', 'N/A')}, 区域: {val.get('pe_zone', 'N/A')}")
        lines.append(f"- PB 分位数: {val.get('pb_percentile', 'N/A')}, 区域: {val.get('pb_zone', 'N/A')}")
        lines.append("")

    # 财务健康
    health = ctx_data.get("financial_health", {})
    if health:
        lines.append("## 财务健康")
        red = health.get("red_flags", [])
        warnings = health.get("warnings", [])
        if red:
            lines.append(f"- 红灯信号({len(red)}项): {', '.join(red[:5])}")
        if warnings:
            lines.append(f"- 预警信号({len(warnings)}项): {', '.join(warnings[:5])}")
        if not red and not warnings:
            lines.append("- 未发现明显财务风险")
        lines.append("")

    # 情绪面
    sentiment = ctx_data.get("sentiment", {})
    if sentiment:
        pos = sentiment.get("positive", 0)
        neg = sentiment.get("negative", 0)
        neu = sentiment.get("neutral", 0)
        lines.append(f"## 新闻情绪: 正面{pos}条 负面{neg}条 中性{neu}条")
        lines.append("")

    # 评分
    score = ctx_data.get("weighted_score", {})
    if score:
        lines.append(f"## 综合评分: {score.get('total', 0):.1f}/10 (技术:{score.get('tech', 0):.1f} "
                     f"资金:{score.get('fund', 0):.1f} 财务:{score.get('fin', 0):.1f})")
        lines.append("")

    # 风控
    risk = ctx_data.get("risk", {})
    if risk:
        lines.append("## 风控数据")
        lines.append(f"- 动态止损: {risk.get('stop_loss', 0):.2f}")
        lines.append(f"- 目标价: {risk.get('target_price', 0):.2f}")
        lines.append(f"- 建议仓位: {risk.get('position', 'N/A')}")
        lines.append("")

    # 输出要求
    lines.append("---")
    lines.append("请按以下格式输出（使用中文，简洁专业）：")
    lines.append("")
    lines.append("## 执行摘要")
    lines.append("用1-2段话概括当前该股票的综合状况，涵盖技术面、资金面、基本面和估值的最关键信息。")
    lines.append("")
    lines.append("## 矛盾检测")
    lines.append("列出指标之间的矛盾信号（如：MACD金叉但RSI超买、主力流出但股价上涨等）。如无明显矛盾，写「未检测到显著矛盾」。")
    lines.append("")
    lines.append("## 技术信号白话解读")
    lines.append("用通俗易懂的语言解释当前技术指标的含义，面向非专业投资者。避免使用专业术语堆砌。")
    lines.append("")
    lines.append("## 重点关注因子")
    lines.append("列出2-4个未来最需要跟踪的关键因素（如：能否突破某均线、资金能否连续3日流入、PE分位数变化等），每个一行。")

    return "\n".join(lines)


# ============================================================
# LLM 调用
# ============================================================

def call_llm(
    provider: LLMProvider,
    prompt: str,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    timeout: int = 30,
) -> Optional[str]:
    """
    调用 LLM 并返回文本结果。

    Args:
        provider: LLM provider 类型
        prompt: 分析 prompt
        api_key: API key（可选，默认从环境变量读取）
        base_url: API base URL（OpenAI-compatible 需要）
        model: 模型名称（可选，使用默认值）
        timeout: 超时秒数

    Returns:
        LLM 响应文本，失败返回 None
    """
    if provider == LLMProvider.ANTHROPIC:
        return _call_anthropic(prompt, api_key, model, timeout)
    elif provider == LLMProvider.OPENAI_COMPATIBLE:
        return _call_openai_compatible(prompt, api_key, base_url, model, timeout)
    else:
        return None


def _call_anthropic(
    prompt: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    timeout: int = 30,
) -> Optional[str]:
    """通过 Anthropic SDK 调用 Claude。"""
    if not HAS_ANTHROPIC:
        return None

    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return None

    model_name = model or os.environ.get("STOCK_LLM_MODEL", "claude-sonnet-4-6")

    try:
        client = anthropic.Anthropic(api_key=key, timeout=float(timeout))
        message = client.messages.create(
            model=model_name,
            max_tokens=1024,
            system="你是一位专业的A股投资分析师。请基于提供的数据生成简洁、准确的分析解读。所有内容仅供参考，不构成投资建议。",
            messages=[{"role": "user", "content": prompt}],
        )
        # 提取文本内容
        for block in message.content:
            if hasattr(block, "text"):
                return block.text
        return None
    except Exception as e:
        print(f"  [AI] Anthropic API 调用失败: {e}")
        return None


def _call_openai_compatible(
    prompt: str,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    timeout: int = 30,
) -> Optional[str]:
    """通过 requests 调用 OpenAI-compatible API。"""
    if not HAS_REQUESTS:
        return None

    key = api_key or os.environ.get("OPENAI_API_KEY", "")
    if not key:
        return None

    url_base = base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    # 确保 URL 不以 / 结尾
    url_base = url_base.rstrip("/")
    url = f"{url_base}/chat/completions"

    model_name = model or os.environ.get("STOCK_LLM_MODEL", "gpt-4o-mini")

    try:
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model_name,
                "messages": [
                    {"role": "system", "content": "你是一位专业的A股投资分析师。请基于提供的数据生成简洁、准确的分析解读。所有内容仅供参考，不构成投资建议。请用中文回复。"},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 1024,
                "temperature": 0.3,
            },
            timeout=timeout,
        )
        if resp.status_code == 200:
            data = resp.json()
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
        else:
            print(f"  [AI] API 返回非 200: {resp.status_code}")
            return None
    except Exception as e:
        print(f"  [AI] OpenAI-compatible API 调用失败: {e}")
        return None

    return None


# ============================================================
# 响应解析
# ============================================================

def parse_llm_response(text: str) -> Dict[str, Any]:
    """
    解析 LLM 返回的文本为结构化数据。

    使用启发式标题匹配，不依赖完美格式。
    对 LLM 输出的格式变化具有鲁棒性。

    Returns:
        dict: {
            'executive_summary': str,
            'contradictions': List[str],
            'signal_explanation': str,
            'key_factors': List[str],
        }
    """
    result = {
        "executive_summary": "",
        "contradictions": [],
        "signal_explanation": "",
        "key_factors": [],
    }

    if not text or not text.strip():
        return result

    # 按 ## 标题分段
    sections = _split_by_sections(text)

    for title, content in sections:
        title_lower = title.lower().strip()

        if "执行摘要" in title_lower or "概要" in title_lower or "summary" in title_lower:
            result["executive_summary"] = content.strip()

        elif "矛盾" in title_lower:
            # 提取矛盾列表（- 或 * 或 数字 开头）
            result["contradictions"] = _extract_list_items(content)

        elif "白话" in title_lower or "技术信号" in title_lower or "解读" in title_lower:
            result["signal_explanation"] = content.strip()

        elif "跟踪" in title_lower or "关注" in title_lower or "因子" in title_lower:
            result["key_factors"] = _extract_list_items(content)

    # 如果标题解析失败，尝试从全文提取
    if not any(result.values()):
        # 把整个响应作为执行摘要
        result["executive_summary"] = text.strip()[:500]

    return result


def _split_by_sections(text: str) -> List[Tuple[str, str]]:
    """按 Markdown ## 标题分割文本。返回 [(title, content), ...]"""
    sections = []
    current_title = ""
    current_content = []

    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("## "):
            if current_title or current_content:
                sections.append((current_title, "\n".join(current_content)))
            current_title = line[3:].strip()
            current_content = []
        else:
            if line:
                current_content.append(line)

    if current_title or current_content:
        sections.append((current_title, "\n".join(current_content)))

    return sections


def _extract_list_items(text: str) -> List[str]:
    """从文本中提取列表项（- 或 * 或 数字 开头）。"""
    items = []
    for line in text.split("\n"):
        line = line.strip()
        # 匹配 "- item", "* item", "1. item", "- 1. item" 等格式
        match = re.match(r'^[-*]\s+(.+)$', line) or re.match(r'^\d+[.)]\s*(.+)$', line)
        if match:
            item = match.group(1).strip()
            if item and len(item) > 2:
                items.append(item)
        elif line and not line.startswith("#") and len(line) > 5:
            # 如果没有列表标记但内容有意义，也收录
            # 仅在明确没有列表项的段落中才使用这种方式
            pass

    # 如果没有提取到列表项，检查是否是「未检测到显著矛盾」之类的表述
    if not items:
        if "未检测到" in text or "无明显" in text or "无显著" in text:
            return []

    return items[:10]  # 最多 10 项


# ============================================================
# 辅助 — 构建 LLM 上下文数据
# ============================================================

def build_llm_context_from_report_ctx(ctx) -> Dict[str, Any]:
    """
    从 ReportContext 提取 LLM 所需的结构化数据。

    Args:
        ctx: ReportContext 实例

    Returns:
        dict: JSON-serializable 数据
    """
    data = {
        "name": ctx.name,
        "code": ctx.code,
        "price": ctx.price,
        "change_pct": ctx.indicators.get("change_pct", 0) if ctx.indicators else 0,
    }

    # 技术面
    ind = ctx.indicators or {}
    dif = ind.get("DIF", 0)
    dea = ind.get("DEA", 0)
    dif_p = ind.get("DIF_prev")
    dea_p = ind.get("DEA_prev")
    if dif_p is not None and dea_p is not None and dif_p <= dea_p and dif > dea:
        macd_signal = "金叉（真实上穿）"
    elif dif_p is not None and dea_p is not None and dif_p >= dea_p and dif < dea:
        macd_signal = "死叉（真实下穿）"
    else:
        macd_signal = "多头区域" if dif > dea else "空头区域"

    k_val = ind.get("K", 50)
    kdj_zone = "超买" if k_val > 80 else "超卖" if k_val < 20 else "中性"

    # 趋势判断
    ma5 = ind.get("MA5", 0)
    ma20 = ind.get("MA20", 0)
    ma60 = ind.get("MA60", 0)
    price = ctx.price or 0
    if price > ma5 > ma20 > ma60:
        trend = "多头排列（强势）"
    elif price < ma5 < ma20 < ma60:
        trend = "空头排列（弱势）"
    elif price > ma20:
        trend = "中期趋势向上"
    elif price < ma20:
        trend = "中期趋势向下"
    else:
        trend = "横盘震荡"

    # 布林带位置
    boll_mid = ind.get("BOLL_MID", 0)
    boll_up = ind.get("BOLL_UP", 0)
    boll_dn = ind.get("BOLL_DN", 0)
    if boll_up > 0 and boll_dn > 0:
        if price >= boll_up * 0.98:
            boll_pos = "触及上轨（可能超买）"
        elif price <= boll_dn * 1.02:
            boll_pos = "触及下轨（可能超卖）"
        elif price > boll_mid:
            boll_pos = "中轨上方"
        else:
            boll_pos = "中轨下方"
    else:
        boll_pos = "N/A"

    data["technical"] = {
        "DIF": dif, "DEA": dea, "MACD": ind.get("MACD", 0),
        "macd_signal": macd_signal,
        "K": k_val, "D": ind.get("D", 50), "J": ind.get("J", 50),
        "kdj_zone": kdj_zone,
        "RSI6": ind.get("RSI6", 50), "RSI14": ind.get("RSI14", 50),
        "MA5": ma5, "MA10": ind.get("MA10", 0),
        "MA20": ma20, "MA60": ma60,
        "trend": trend,
        "boll_position": boll_pos,
        "ATR14": ind.get("ATR14", 0),
        "volume_anomaly": _serialize_volume_anomaly(ctx),
    }

    # 资金面
    ff = ctx.fund_flow or {}
    today_ff = ff.get("今日", {}) if isinstance(ff, dict) else {}
    data["fund_flow"] = {
        "main_net_today": today_ff.get("f62", 0) if isinstance(today_ff, dict) else 0,
        "main_net_5d": safe_num_from_dict(ff, "5日", "f62") if isinstance(ff, dict) else 0,
    }

    # 基本面
    quote = ctx.quote or {}
    data["fundamentals"] = {
        "PE": safe_num_from_dict(quote, "f9"),
        "PB": safe_num_from_dict(quote, "f23"),
        "ROE": safe_num_from_dict(quote, "f37"),
        "gross_margin": safe_num_from_dict(quote, "f49"),
        "revenue_yoy": safe_num_from_dict(quote, "f40"),
        "profit_yoy": safe_num_from_dict(quote, "f41"),
        "debt_ratio": safe_num_from_dict(quote, "f34"),
        "total_mktcap": safe_num_from_dict(quote, "f20"),
        "dividend_yield": safe_num_from_dict(quote, "f92"),
    }

    # 估值分位数
    vp = ctx.valuation_percentile or {}
    data["valuation"] = {
        "pe_percentile": vp.get("pe_percentile", "N/A") if isinstance(vp, dict) else "N/A",
        "pe_zone": vp.get("pe_zone", "N/A") if isinstance(vp, dict) else "N/A",
        "pb_percentile": vp.get("pb_percentile", "N/A") if isinstance(vp, dict) else "N/A",
        "pb_zone": vp.get("pb_zone", "N/A") if isinstance(vp, dict) else "N/A",
    }

    # 财务健康
    fh = ctx.financial_health or {}
    data["financial_health"] = {
        "red_flags": fh.get("排雷红灯", []) if isinstance(fh, dict) else [],
        "warnings": fh.get("排雷预警", []) if isinstance(fh, dict) else [],
    }

    # 情绪
    sent = ctx.sentiment_result or {}
    data["sentiment"] = {
        "positive": sent.get("positive_count", 0) if isinstance(sent, dict) else 0,
        "negative": sent.get("negative_count", 0) if isinstance(sent, dict) else 0,
        "neutral": sent.get("neutral_count", 0) if isinstance(sent, dict) else 0,
    }

    # 评分
    ws = ctx.weighted_score or {}
    data["weighted_score"] = {
        "total": ws.get("total", 0) if isinstance(ws, dict) else 0,
        "tech": ws.get("technical", 0) if isinstance(ws, dict) else 0,
        "fund": ws.get("fund_flow", 0) if isinstance(ws, dict) else 0,
        "fin": ws.get("financial", 0) if isinstance(ws, dict) else 0,
    }

    # 风控
    risk_data = {}
    if ctx.stop_loss is not None:
        risk_data["stop_loss"] = safe_num(ctx.stop_loss) if not isinstance(ctx.stop_loss, dict) else 0
    if ctx.target is not None:
        risk_data["target_price"] = safe_num(ctx.target) if not isinstance(ctx.target, dict) else 0
    if ctx.position is not None:
        risk_data["position"] = str(ctx.position) if not isinstance(ctx.position, dict) else "N/A"
    data["risk"] = risk_data

    return data


def _serialize_volume_anomaly(ctx) -> str:
    """序列化成交量异动信息"""
    ext = ctx.extended_indicators or {}
    if not isinstance(ext, dict):
        return "N/A"
    vol_anomaly = ext.get("volume_anomaly", {})
    if not isinstance(vol_anomaly, dict) or not vol_anomaly:
        return "N/A"
    desc = vol_anomaly.get("description", "")
    return str(desc) if desc else "N/A"


def safe_num_from_dict(d, key, sub_key=None):
    """从嵌套字典中安全提取数值"""
    try:
        if sub_key:
            inner = d.get(key, {})
            if isinstance(inner, dict):
                val = inner.get(sub_key, 0)
            else:
                return 0
        else:
            val = d.get(key, 0)
        if val is None:
            return 0
        if isinstance(val, (int, float)):
            return float(val)
        return 0
    except Exception:
        return 0


def safe_num(val):
    """安全数值转换"""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val.replace(",", ""))
        except ValueError:
            return 0.0
    return 0.0


# ============================================================
# 模块自测
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("LLM 客户端测试")
    print("=" * 60)

    # Provider 检测
    provider, key, url = detect_provider()
    print(f"\nProvider: {provider.value}")
    print(f"Has Anthropic SDK: {HAS_ANTHROPIC}")
    print(f"Has Requests: {HAS_REQUESTS}")
    if key:
        print(f"API Key: {key[:12]}...")
    if url:
        print(f"Base URL: {url}")

    # Prompt 构建测试
    print("\n--- Prompt 构建测试 ---")
    test_ctx = {
        "name": "贵州茅台", "code": "600519",
        "price": 1680.50, "change_pct": 1.25,
        "technical": {
            "DIF": 12.5, "DEA": 10.3, "MACD": 2.2,
            "macd_signal": "金叉（真实上穿）",
            "K": 65.0, "D": 58.0, "J": 79.0,
            "kdj_zone": "中性",
            "RSI6": 62.0, "RSI14": 55.0,
            "MA5": 1650.0, "MA20": 1620.0, "MA60": 1550.0,
            "trend": "多头排列（强势）",
            "boll_position": "中轨上方",
            "ATR14": 25.5,
        },
        "fund_flow": {"main_net_today": 50000000, "main_net_5d": 120000000},
        "fundamentals": {
            "PE": 28.5, "PB": 9.8, "ROE": 25.3,
            "gross_margin": 78.5, "revenue_yoy": 15.2,
            "profit_yoy": 18.6, "debt_ratio": 19.5,
            "total_mktcap": 2100000000000,
        },
        "valuation": {
            "pe_percentile": "45%", "pe_zone": "合理",
            "pb_percentile": "52%", "pb_zone": "合理",
        },
        "financial_health": {
            "red_flags": [], "warnings": ["应收账款增速高于营收增速"],
        },
        "sentiment": {"positive": 3, "negative": 1, "neutral": 2},
        "weighted_score": {"total": 6.5, "tech": 2.0, "fund": 1.5, "fin": 3.0},
        "risk": {"stop_loss": 1550.0, "target_price": 1850.0, "position": "30%"},
    }
    prompt = build_analysis_prompt(test_ctx)
    print(f"Prompt 长度: {len(prompt)} 字符")
    print(prompt[:500] + "...")

    # 响应解析测试
    print("\n--- 响应解析测试 ---")
    mock_response = """
## 执行摘要
贵州茅台当前处于多头排列强势格局，MACD金叉信号明确，主力资金持续流入。
基本面稳健，ROE高达25%以上。

## 矛盾检测
- MACD金叉但KDJ的J值接近80，短期可能有回调压力
- 主力资金持续流入但散户资金呈现流出态势

## 技术信号白话解读
当前茅台处于"均线多头排列"状态，相当于短期、中期、长期投资者都处于盈利状态。
MACD刚刚出现金叉，就像汽车刚挂上D档准备加速。

## 重点关注因子
- 能否站稳MA20均线（当前1620元）不跌破
- 主力资金能否连续3日净流入
- PE是否继续维持在30倍以下
- 关注下季度财报ROE是否保持25%以上
"""
    parsed = parse_llm_response(mock_response)
    print(f"执行摘要: {parsed['executive_summary'][:80]}...")
    print(f"矛盾检测: {parsed['contradictions']}")
    print(f"白话解读: {parsed['signal_explanation'][:80]}...")
    print(f"跟踪因子: {parsed['key_factors']}")

    print("\n" + "=" * 60)
    print("测试完成")
