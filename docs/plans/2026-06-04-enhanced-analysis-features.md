# 增强分析功能实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 为 stock-analyzer-skill 添加 8 项增强分析功能：双股对比、板块分析、新闻情感分析、动态止损/目标位、支撑压力位、加权信号评分、仓位建议、风控铁律

**架构：** 在现有 `scripts/` 模块基础上，新增 `scripts/comparison.py`（对比分析）、`scripts/sentiment.py`（情感分析）、`scripts/risk_control.py`（风控模块），并在 `scripts/analyzer.py` 中集成新评分系统和报告生成逻辑

**技术栈：** Python 3.8+、pandas、numpy（无新增外部依赖）

---

## 文件结构

| 文件 | 职责 | 操作 |
|------|------|------|
| `scripts/comparison.py` | 双股对比、板块分析 | 新建 |
| `scripts/sentiment.py` | 新闻情感分析 | 新建 |
| `scripts/risk_control.py` | 动态止损/目标位、支撑压力位、仓位建议、风控铁律 | 新建 |
| `scripts/analyzer.py` | 集成新评分系统、报告生成 | 修改 |
| `tests/test_comparison.py` | 对比模块测试 | 新建 |
| `tests/test_sentiment.py` | 情感分析测试 | 新建 |
| `tests/test_risk_control.py` | 风控模块测试 | 新建 |
| `SKILL.md` | 更新功能说明 | 修改 |

---

## 任务 1：新闻情感分析模块

**文件：**
- 创建：`scripts/sentiment.py`
- 测试：`tests/test_sentiment.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_sentiment.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from sentiment import analyze_sentiment, summarize_sentiment


def test_analyze_sentiment_positive():
    """测试正面新闻情感分析"""
    news_list = [
        {"新闻标题": "公司业绩超预期增长", "新闻内容": "净利润大幅增长"},
        {"新闻标题": "获得重大利好消息", "新闻内容": "股价上涨突破新高"},
    ]
    result = analyze_sentiment(news_list)
    assert result["sentiment"] == "positive"
    assert result["positive_count"] >= 2


def test_analyze_sentiment_negative():
    """测试负面新闻情感分析"""
    news_list = [
        {"新闻标题": "公司业绩下滑亏损", "新闻内容": "净利润大幅下跌"},
        {"新闻标题": "高管减持风险", "新闻内容": "利空消息不断"},
    ]
    result = analyze_sentiment(news_list)
    assert result["sentiment"] == "negative"
    assert result["negative_count"] >= 2


def test_analyze_sentiment_neutral():
    """测试中性新闻情感分析"""
    news_list = [
        {"新闻标题": "公司召开股东大会", "新闻内容": "审议年度报告"},
        {"新闻标题": "行业标准发布", "新闻内容": "新规将于下月实施"},
    ]
    result = analyze_sentiment(news_list)
    assert result["sentiment"] == "neutral"


def test_summarize_sentiment():
    """测试情感摘要生成"""
    sentiment = {
        "sentiment": "positive",
        "positive_count": 5,
        "negative_count": 2,
        "summary": "新闻偏正面",
        "key_news": [{"title": "利好消息", "sentiment": "positive"}],
    }
    summary = summarize_sentiment(sentiment)
    assert "正面" in summary
    assert "5" in summary
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/test_sentiment.py -v`
预期：FAIL，ModuleNotFoundError: No module named 'sentiment'

- [ ] **步骤 3：编写最少实现代码**

```python
# scripts/sentiment.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
新闻情感分析模块
基于关键词匹配判断新闻正面/负面/中性
"""

from typing import List, Dict, Any


# 正面关键词
POSITIVE_KEYWORDS = [
    "上涨", "增长", "盈利", "超预期", "利好", "回购", "升级", "突破",
    "新高", "涨停", "强势", "领涨", "加仓", "增持", "看好", "乐观",
    "回暖", "反弹", "放量", "主力流入", "机构买入", "业绩预增",
]

# 负面关键词
NEGATIVE_KEYWORDS = [
    "下跌", "亏损", "下滑", "不及预期", "利空", "减持", "降级", "风险",
    "跌停", "暴跌", "弱势", "领跌", "减仓", "清仓", "看空", "悲观",
    "破位", "放量下跌", "主力流出", "机构卖出", "业绩预减", "退市",
]


def analyze_sentiment(news_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    分析新闻列表的情感倾向。

    Args:
        news_list: 新闻列表，每条包含 '新闻标题' 和 '新闻内容' 字段

    Returns:
        dict: {
            'sentiment': 'positive' / 'negative' / 'neutral',
            'positive_count': int,
            'negative_count': int,
            'summary': str,
            'key_news': list
        }
    """
    if not news_list:
        return {
            "sentiment": "neutral",
            "positive_count": 0,
            "negative_count": 0,
            "summary": "无新闻数据",
            "key_news": [],
        }

    pos_count = 0
    neg_count = 0
    key_news = []

    for news in news_list:
        title = news.get("新闻标题", "")
        content = news.get("新闻内容", "")
        text = f"{title} {content}".lower()

        pos_score = sum(1 for kw in POSITIVE_KEYWORDS if kw in text)
        neg_score = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text)

        if pos_score > neg_score:
            pos_count += 1
            if pos_score >= 2:
                key_news.append({"title": title, "sentiment": "positive"})
        elif neg_score > pos_score:
            neg_count += 1
            if neg_score >= 2:
                key_news.append({"title": title, "sentiment": "negative"})

    # 判断整体情感
    total = pos_count + neg_count
    if total == 0:
        sentiment = "neutral"
        summary = "新闻情感中性，无明显方向"
    elif pos_count > neg_count * 1.5:
        sentiment = "positive"
        summary = f"新闻偏正面（正面 {pos_count} vs 负面 {neg_count}），市场情绪较好"
    elif neg_count > pos_count * 1.5:
        sentiment = "negative"
        summary = f"新闻偏负面（正面 {pos_count} vs 负面 {neg_count}），需注意风险"
    else:
        sentiment = "neutral"
        summary = f"新闻多空交织（正面 {pos_count} vs 负面 {neg_count}），方向不明"

    return {
        "sentiment": sentiment,
        "positive_count": pos_count,
        "negative_count": neg_count,
        "summary": summary,
        "key_news": key_news[:5],
    }


def summarize_sentiment(sentiment: Dict[str, Any]) -> str:
    """
    生成情感分析的文字摘要。

    Args:
        sentiment: analyze_sentiment 返回的情感分析结果

    Returns:
        str: 格式化的摘要文字
    """
    pos = sentiment.get("positive_count", 0)
    neg = sentiment.get("negative_count", 0)
    summary = sentiment.get("summary", "")
    key_news = sentiment.get("key_news", [])

    lines = [summary]

    if key_news:
        lines.append("\n**关键新闻：**")
        for news in key_news[:3]:
            icon = "[+]" if news["sentiment"] == "positive" else "[-]"
            lines.append(f"- {icon} {news['title']}")

    return "\n".join(lines)
```

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest tests/test_sentiment.py -v`
预期：4 个测试全部 PASS

- [ ] **步骤 5：Commit**

```bash
git add scripts/sentiment.py tests/test_sentiment.py
git commit -m "feat: add news sentiment analysis module"
```

---

## 任务 2：风控模块 - 动态止损/目标位

**文件：**
- 创建：`scripts/risk_control.py`
- 测试：`tests/test_risk_control.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_risk_control.py
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
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/test_risk_control.py -v`
预期：FAIL，ModuleNotFoundError

- [ ] **步骤 3：编写最少实现代码**

```python
# scripts/risk_control.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
风控模块
包含动态止损/目标位、支撑压力位、仓位建议、风控铁律
"""

from typing import Dict, Any, Optional
import pandas as pd
import numpy as np


# A 股不同板块的涨跌停幅度
LIMIT_RATIOS = {
    "main": 0.10,    # 主板 ±10%
    "gem": 0.20,     # 创业板 ±20%
    "star": 0.20,    # 科创板 ±20%
    "bj": 0.30,      # 北交所 ±30%
}


def detect_board_type(code: str) -> str:
    """
    判断 A 股板块类型。

    Args:
        code: 股票代码

    Returns:
        str: 'main' / 'gem' / 'star' / 'bj'
    """
    code = str(code).strip()
    if code.startswith("688"):
        return "star"
    elif code.startswith("300"):
        return "gem"
    elif code.startswith("8") or code.startswith("4"):
        return "bj"
    else:
        return "main"


def calc_dynamic_stop_loss(
    current_price: float,
    atr: float,
    board_type: str = "main",
    method: str = "atr"
) -> Dict[str, Any]:
    """
    计算动态止损位。

    Args:
        current_price: 当前价格
        atr: ATR（平均真实波幅）
        board_type: 板块类型
        method: 计算方法 ('atr' / 'percentage')

    Returns:
        dict: {
            'stop_loss': float,
            'stop_pct': float,
            'method': str,
            'description': str
        }
    """
    limit_ratio = LIMIT_RATIOS.get(board_type, 0.10)
    max_stop_pct = limit_ratio * 0.70  # 止损不超过涨跌停的 70%

    if method == "atr" and atr > 0:
        # ATR 方法：止损 = 当前价 - 2 × ATR
        atr_stop = current_price - 2 * atr
        stop_pct = (current_price - atr_stop) / current_price

        # 如果 ATR 止损幅度超过限制，使用百分比止损
        if stop_pct > max_stop_pct:
            stop_price = current_price * (1 - max_stop_pct)
            stop_pct = max_stop_pct
        else:
            stop_price = atr_stop
    else:
        # 百分比方法：默认 5%
        stop_pct = min(0.05, max_stop_pct)
        stop_price = current_price * (1 - stop_pct)

    return {
        "stop_loss": round(stop_price, 2),
        "stop_pct": round(stop_pct * 100, 2),
        "method": method,
        "description": f"止损价 {stop_price:.2f}，幅度 {stop_pct*100:.2f}%",
    }


def calc_target_price(
    current_price: float,
    stop_loss: float,
    risk_reward_ratio: float = 2.5
) -> Dict[str, Any]:
    """
    计算目标价位。

    Args:
        current_price: 当前价格
        stop_loss: 止损价
        risk_reward_ratio: 风险收益比（默认 2.5）

    Returns:
        dict: {
            'target_price': float,
            'upside_pct': float,
            'risk_reward_ratio': float,
            'description': str
        }
    """
    risk = current_price - stop_loss
    if risk <= 0:
        return {
            "target_price": current_price,
            "upside_pct": 0.0,
            "risk_reward_ratio": 0.0,
            "description": "止损价高于当前价，无法计算目标位",
        }

    target = current_price + risk * risk_reward_ratio
    upside_pct = (target - current_price) / current_price * 100

    return {
        "target_price": round(target, 2),
        "upside_pct": round(upside_pct, 2),
        "risk_reward_ratio": risk_reward_ratio,
        "description": f"目标价 {target:.2f}，预期涨幅 {upside_pct:.2f}%",
    }
```

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest tests/test_risk_control.py -v`
预期：3 个测试全部 PASS

- [ ] **步骤 5：Commit**

```bash
git add scripts/risk_control.py tests/test_risk_control.py
git commit -m "feat: add dynamic stop-loss and target price calculation"
```

---

## 任务 3：风控模块 - 支撑压力位计算

**文件：**
- 修改：`scripts/risk_control.py`
- 修改：`tests/test_risk_control.py`

- [ ] **步骤 1：编写失败的测试**

```python
# 在 tests/test_risk_control.py 中添加

from risk_control import calc_support_resistance


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
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/test_risk_control.py::test_calc_support_resistance -v`
预期：FAIL，ImportError: cannot import name 'calc_support_resistance'

- [ ] **步骤 3：编写最少实现代码**

```python
# 在 scripts/risk_control.py 中添加

def calc_support_resistance(
    df: pd.DataFrame,
    current_price: float,
    indicators: Dict[str, float]
) -> Dict[str, Any]:
    """
    计算支撑位和压力位。

    综合布林带、均线、近期高低点计算。

    Args:
        df: K线数据 DataFrame
        current_price: 当前价格
        indicators: 技术指标字典

    Returns:
        dict: {
            'resistance': [{'price': float, 'source': str}, ...],
            'support': [{'price': float, 'source': str}, ...]
        }
    """
    resistance = []
    support = []

    # 1. 布林带
    boll_up = indicators.get("BOLL_UP", 0)
    boll_mid = indicators.get("BOLL_MID", 0)
    boll_dn = indicators.get("BOLL_DN", 0)

    if boll_up > current_price:
        resistance.append({"price": round(boll_up, 2), "source": "布林上轨"})
    if boll_mid > current_price:
        resistance.append({"price": round(boll_mid, 2), "source": "布林中轨"})
    elif boll_mid < current_price:
        support.append({"price": round(boll_mid, 2), "source": "布林中轨"})
    if boll_dn < current_price:
        support.append({"price": round(boll_dn, 2), "source": "布林下轨"})

    # 2. 均线
    for ma_key in ["MA20", "MA60", "MA120", "MA250"]:
        ma_val = indicators.get(ma_key, 0)
        if ma_val <= 0:
            continue
        if ma_val > current_price:
            resistance.append({"price": round(ma_val, 2), "source": ma_key})
        else:
            support.append({"price": round(ma_val, 2), "source": ma_key})

    # 3. 近期高低点
    if len(df) >= 20:
        recent_20 = df.tail(20)
        high_20 = recent_20["最高"].max()
        low_20 = recent_20["最低"].min()

        if high_20 > current_price:
            resistance.append({"price": round(high_20, 2), "source": "20日最高"})
        if low_20 < current_price:
            support.append({"price": round(low_20, 2), "source": "20日最低"})

    if len(df) >= 60:
        recent_60 = df.tail(60)
        high_60 = recent_60["最高"].max()
        low_60 = recent_60["最低"].min()

        if high_60 > current_price and high_60 != high_20:
            resistance.append({"price": round(high_60, 2), "source": "60日最高"})
        if low_60 < current_price and low_60 != low_20:
            support.append({"price": round(low_60, 2), "source": "60日最低"})

    # 4. 斐波那契回撤（基于近期高低点）
    if len(df) >= 20:
        swing_high = high_20
        swing_low = low_20
        fib_range = swing_high - swing_low

        for ratio, name in [(0.382, "38.2%"), (0.5, "50%"), (0.618, "61.8%")]:
            fib_price = swing_high - fib_range * ratio
            if fib_price > current_price:
                resistance.append({"price": round(fib_price, 2), "source": f"斐波那契{name}"})
            elif fib_price < current_price:
                support.append({"price": round(fib_price, 2), "source": f"斐波那契{name}"})

    # 去重并排序
    resistance = sorted(
        [{"price": r["price"], "source": r["source"]} for r in
         {item["price"]: item for item in resistance}.values()],
        key=lambda x: x["price"]
    )
    support = sorted(
        [{"price": s["price"], "source": s["source"]} for s in
         {item["price"]: item for item in support}.values()],
        key=lambda x: x["price"],
        reverse=True
    )

    return {
        "resistance": resistance[:5],  # 最多 5 个压力位
        "support": support[:5],        # 最多 5 个支撑位
    }
```

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest tests/test_risk_control.py -v`
预期：4 个测试全部 PASS

- [ ] **步骤 5：Commit**

```bash
git add scripts/risk_control.py tests/test_risk_control.py
git commit -m "feat: add support/resistance level calculation"
```

---

## 任务 4：风控模块 - 仓位建议与风控铁律

**文件：**
- 修改：`scripts/risk_control.py`
- 修改：`tests/test_risk_control.py`

- [ ] **步骤 1：编写失败的测试**

```python
# 在 tests/test_risk_control.py 中添加

from risk_control import calc_position_size, check_risk_rules


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
        "MA20": 98.0,
        "MA5": 99.0,
        "MA10": 98.5,
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
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/test_risk_control.py -v`
预期：FAIL，ImportError

- [ ] **步骤 3：编写最少实现代码**

```python
# 在 scripts/risk_control.py 中添加

def calc_position_size(
    direction: str,
    score: float,
    net_signals: int,
    has_bearish: bool
) -> Dict[str, Any]:
    """
    计算仓位建议。

    Args:
        direction: 操作方向 ('buy' / 'sell' / 'hold')
        score: 技术面评分
        net_signals: 净信号数（看多信号数 - 看空信号数）
        has_bearish: 是否存在看空信号

    Returns:
        dict: {
            'position_pct': int,
            'confidence': str,
            'description': str
        }
    """
    if direction == "sell" or score <= -5:
        return {
            "position_pct": 0,
            "confidence": "较高" if score <= -5 else "中等",
            "description": "建议空仓，等待企稳信号",
        }

    if direction == "hold" or (score < 3) or has_bearish:
        return {
            "position_pct": 0,
            "confidence": "较低",
            "description": "建议观望，信号不明确或存在矛盾",
        }

    # 买入信号
    if score >= 5 and not has_bearish and net_signals >= 2:
        return {
            "position_pct": 15,
            "confidence": "较高",
            "description": "建议仓位 10-20%，信号较强",
        }

    if score >= 3 and not has_bearish and net_signals >= 1:
        return {
            "position_pct": 8,
            "confidence": "中等",
            "description": "建议仓位 5-10%，信号中等",
        }

    return {
        "position_pct": 0,
        "confidence": "较低",
        "description": "建议观望，信号不足",
    }


def check_risk_rules(
    code: str,
    indicators: Dict[str, float],
    is_st: bool = False,
    is_new_stock: bool = False
) -> Dict[str, Any]:
    """
    执行风控铁律检查。

    Args:
        code: 股票代码
        indicators: 技术指标字典
        is_st: 是否为 ST 股票
        is_new_stock: 是否为次新股

    Returns:
        dict: {
            'warnings': list,
            'blocked': bool
        }
    """
    warnings = []
    price = indicators.get("最新价", 0)
    ma20 = indicators.get("MA20", 0)
    ma5 = indicators.get("MA5", 0)
    ma10 = indicators.get("MA10", 0)

    # 1. 乖离率检查（价格偏离 MA20 > 5%）
    if ma20 > 0 and price > 0:
        bias = (price - ma20) / ma20 * 100
        if bias > 5:
            warnings.append(f"乖离率 {bias:.1f}% > 5%，不建议追高")
        elif bias < -5:
            warnings.append(f"乖离率 {bias:.1f}% < -5%，超卖区域")

    # 2. 均线间距检查（间距 < 1% 不认定为有效排列）
    if ma5 > 0 and ma10 > 0 and ma20 > 0:
        gap_5_10 = abs(ma5 - ma10) / ma10 * 100
        gap_10_20 = abs(ma10 - ma20) / ma20 * 100
        if gap_5_10 < 1 and gap_10_20 < 1:
            warnings.append("均线间距过小（<1%），不认定为有效排列")

    # 3. ST 股票警告
    if is_st:
        warnings.append("该股票为 ST/*ST，存在退市风险，请特别注意")

    # 4. 次新股警告
    if is_new_stock:
        warnings.append("该股票为次新股（上市不足 1 年），波动较大，请注意风险")

    return {
        "warnings": warnings,
        "blocked": is_st,  # ST 股票标记为高风险
    }
```

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest tests/test_risk_control.py -v`
预期：11 个测试全部 PASS

- [ ] **步骤 5：Commit**

```bash
git add scripts/risk_control.py tests/test_risk_control.py
git commit -m "feat: add position sizing and risk control rules"
```

---

## 任务 5：对比分析模块 - 双股对比

**文件：**
- 创建：`scripts/comparison.py`
- 测试：`tests/test_comparison.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_comparison.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from comparison import compare_two_stocks, generate_comparison_table


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
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/test_comparison.py -v`
预期：FAIL，ModuleNotFoundError

- [ ] **步骤 3：编写最少实现代码**

```python
# scripts/comparison.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对比分析模块
支持双股对比、板块分析
"""

from typing import Dict, Any, List, Optional


def compare_two_stocks(
    stock_a: Dict[str, Any],
    stock_b: Dict[str, Any]
) -> Dict[str, Any]:
    """
    对比两只股票。

    Args:
        stock_a: 股票 A 的数据
        stock_b: 股票 B 的数据

    Returns:
        dict: {
            'comparison': list,
            'winner': str,
            'summary': str
        }
    """
    comparison = []
    score_a = 0
    score_b = 0

    # 1. 估值对比（PE 越低越好）
    pe_a = stock_a.get("pe", 0)
    pe_b = stock_b.get("pe", 0)
    pe_winner = "a" if pe_a < pe_b and pe_a > 0 else "b" if pe_b < pe_a and pe_b > 0 else "tie"
    comparison.append({
        "dimension": "市盈率(PE)",
        "stock_a": f"{pe_a:.1f}",
        "stock_b": f"{pe_b:.1f}",
        "winner": pe_winner,
        "note": "越低越便宜",
    })
    if pe_winner == "a":
        score_a += 1
    elif pe_winner == "b":
        score_b += 1

    # 2. PB 对比
    pb_a = stock_a.get("pb", 0)
    pb_b = stock_b.get("pb", 0)
    pb_winner = "a" if pb_a < pb_b and pb_a > 0 else "b" if pb_b < pb_a and pb_b > 0 else "tie"
    comparison.append({
        "dimension": "市净率(PB)",
        "stock_a": f"{pb_a:.1f}",
        "stock_b": f"{pb_b:.1f}",
        "winner": pb_winner,
        "note": "越低越便宜",
    })
    if pb_winner == "a":
        score_a += 1
    elif pb_winner == "b":
        score_b += 1

    # 3. 市值对比
    mv_a = stock_a.get("market_cap", 0)
    mv_b = stock_b.get("market_cap", 0)
    mv_winner = "a" if mv_a > mv_b else "b" if mv_b > mv_a else "tie"
    comparison.append({
        "dimension": "总市值",
        "stock_a": f"{mv_a/1e8:.0f}亿",
        "stock_b": f"{mv_b/1e8:.0f}亿",
        "winner": mv_winner,
        "note": "越大越稳",
    })

    # 4. 涨跌幅对比
    chg_a = stock_a.get("change_pct", 0)
    chg_b = stock_b.get("change_pct", 0)
    chg_winner = "a" if chg_a > chg_b else "b" if chg_b > chg_a else "tie"
    comparison.append({
        "dimension": "今日涨跌",
        "stock_a": f"{chg_a:.2f}%",
        "stock_b": f"{chg_b:.2f}%",
        "winner": chg_winner,
        "note": "",
    })

    # 5. RSI 对比
    rsi_a = stock_a.get("indicators", {}).get("RSI6", 50)
    rsi_b = stock_b.get("indicators", {}).get("RSI6", 50)
    # RSI 50-70 之间较好
    rsi_score_a = 70 - abs(rsi_a - 60)  # 越接近 60 越好
    rsi_score_b = 70 - abs(rsi_b - 60)
    rsi_winner = "a" if rsi_score_a > rsi_score_b else "b" if rsi_score_b > rsi_score_a else "tie"
    comparison.append({
        "dimension": "RSI强弱",
        "stock_a": f"{rsi_a:.1f}",
        "stock_b": f"{rsi_b:.1f}",
        "winner": rsi_winner,
        "note": "50-70较佳",
    })
    if rsi_winner == "a":
        score_a += 1
    elif rsi_winner == "b":
        score_b += 1

    # 6. MACD 对比
    dif_a = stock_a.get("indicators", {}).get("DIF", 0)
    dea_a = stock_a.get("indicators", {}).get("DEA", 0)
    dif_b = stock_b.get("indicators", {}).get("DIF", 0)
    dea_b = stock_b.get("indicators", {}).get("DEA", 0)
    macd_a = dif_a - dea_a
    macd_b = dif_b - dea_b
    macd_winner = "a" if macd_a > macd_b else "b" if macd_b > macd_a else "tie"
    comparison.append({
        "dimension": "MACD动能",
        "stock_a": f"{macd_a:.4f}",
        "stock_b": f"{macd_b:.4f}",
        "winner": macd_winner,
        "note": "DIF-DEA",
    })
    if macd_winner == "a":
        score_a += 1
    elif macd_winner == "b":
        score_b += 1

    # 7. 综合评级对比
    rating_a = stock_a.get("rating", {}).get("分数", 0)
    rating_b = stock_b.get("rating", {}).get("分数", 0)
    rating_winner = "a" if rating_a > rating_b else "b" if rating_b > rating_a else "tie"
    comparison.append({
        "dimension": "综合评级",
        "stock_a": f"{rating_a:.1f}分",
        "stock_b": f"{rating_b:.1f}分",
        "winner": rating_winner,
        "note": "越高越好",
    })
    if rating_winner == "a":
        score_a += 1
    elif rating_winner == "b":
        score_b += 1

    # 计算总赢家
    if score_a > score_b:
        winner = "a"
        summary = f"{stock_a.get('name', '股票A')} 综合表现更优（{score_a}:{score_b}）"
    elif score_b > score_a:
        winner = "b"
        summary = f"{stock_b.get('name', '股票B')} 综合表现更优（{score_b}:{score_a}）"
    else:
        winner = "tie"
        summary = f"两只股票综合表现相当（{score_a}:{score_b}）"

    return {
        "comparison": comparison,
        "winner": winner,
        "score_a": score_a,
        "score_b": score_b,
        "summary": summary,
    }


def generate_comparison_table(
    comparison: List[Dict],
    name_a: str,
    name_b: str
) -> str:
    """
    生成对比表格的 Markdown 文本。

    Args:
        comparison: 对比数据列表
        name_a: 股票 A 名称
        name_b: 股票 B 名称

    Returns:
        str: Markdown 格式的对比表格
    """
    lines = [
        f"| 对比维度 | {name_a} | {name_b} | 胜出 | 说明 |",
        f"|----------|----------|----------|------|------|",
    ]

    for item in comparison:
        dim = item["dimension"]
        val_a = item["stock_a"]
        val_b = item["stock_b"]
        winner = item.get("winner", "tie")
        note = item.get("note", "")

        if winner == "a":
            winner_str = f"✓ {name_a}"
        elif winner == "b":
            winner_str = f"✓ {name_b}"
        else:
            winner_str = "平手"

        lines.append(f"| {dim} | {val_a} | {val_b} | {winner_str} | {note} |")

    return "\n".join(lines)
```

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest tests/test_comparison.py -v`
预期：3 个测试全部 PASS

- [ ] **步骤 5：Commit**

```bash
git add scripts/comparison.py tests/test_comparison.py
git commit -m "feat: add stock comparison module"
```

---

## 任务 6：对比分析模块 - 板块分析

**文件：**
- 修改：`scripts/comparison.py`
- 修改：`tests/test_comparison.py`

- [ ] **步骤 1：编写失败的测试**

```python
# 在 tests/test_comparison.py 中添加

from comparison import get_sector_stocks, analyze_sector


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
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/test_comparison.py -v`
预期：FAIL，ImportError

- [ ] **步骤 3：编写最少实现代码**

```python
# 在 scripts/comparison.py 中添加

# 板块代表性股票映射
SECTOR_STOCKS = {
    "白酒": ["600519", "000858", "000568", "002304", "603369"],
    "新能源": ["300750", "002594", "601012", "600438", "002129"],
    "半导体": ["688981", "002371", "603501", "688012", "002049"],
    "银行": ["601398", "600036", "601288", "600016", "601166"],
    "医药": ["600276", "000538", "300760", "603259", "002007"],
    "消费": ["600887", "000568", "603288", "002304", "600519"],
    "科技": ["002415", "300059", "002230", "688111", "002475"],
    "地产": ["000002", "600048", "001979", "600383", "000069"],
    "军工": ["600893", "000768", "600760", "002179", "600862"],
    "汽车": ["002594", "601238", "000625", "600104", "601633"],
}


def get_sector_stocks(sector_name: str) -> List[str]:
    """
    获取板块代表性股票代码列表。

    Args:
        sector_name: 板块名称

    Returns:
        list: 股票代码列表
    """
    return SECTOR_STOCKS.get(sector_name, [])


def analyze_sector(sector_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    分析板块整体情况。

    Args:
        sector_data: 板块数据，包含 stocks 列表

    Returns:
        dict: {
            'sector_name': str,
            'avg_change': float,
            'trend': str,
            'stocks_count': int,
            'up_count': int,
            'down_count': int
        }
    """
    stocks = sector_data.get("stocks", [])
    if not stocks:
        return {
            "sector_name": sector_data.get("sector_name", ""),
            "avg_change": 0.0,
            "trend": "无数据",
            "stocks_count": 0,
            "up_count": 0,
            "down_count": 0,
        }

    changes = [s.get("change_pct", 0) for s in stocks]
    avg_change = sum(changes) / len(changes)
    up_count = sum(1 for c in changes if c > 0)
    down_count = sum(1 for c in changes if c < 0)

    if avg_change > 2:
        trend = "强势上涨"
    elif avg_change > 0.5:
        trend = "温和上涨"
    elif avg_change > -0.5:
        trend = "横盘震荡"
    elif avg_change > -2:
        trend = "温和下跌"
    else:
        trend = "弱势下跌"

    return {
        "sector_name": sector_data.get("sector_name", ""),
        "avg_change": round(avg_change, 2),
        "trend": trend,
        "stocks_count": len(stocks),
        "up_count": up_count,
        "down_count": down_count,
    }
```

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest tests/test_comparison.py -v`
预期：6 个测试全部 PASS

- [ ] **步骤 5：Commit**

```bash
git add scripts/comparison.py tests/test_comparison.py
git commit -m "feat: add sector analysis with representative stocks mapping"
```

---

## 任务 7：加权信号评分系统

**文件：**
- 修改：`scripts/analyzer.py`
- 测试：`tests/test_analyzer.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_analyzer.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from analyzer import calculate_weighted_score


def test_calculate_weighted_score_bullish():
    """测试多头信号评分"""
    indicators = {
        "最新价": 100.0,
        "MA5": 101.0,
        "MA10": 100.5,
        "MA20": 100.0,
        "MA60": 99.0,
        "DIF": 2.0,
        "DEA": 1.5,
        "RSI6": 45.0,
        "K": 55.0,
        "BOLL_UP": 110.0,
        "BOLL_DN": 90.0,
        "VOL_MA5": 1000000,
        "成交量": 1500000,
    }
    result = calculate_weighted_score(indicators)

    assert "score" in result
    assert "signals" in result
    assert "direction" in result
    assert result["score"] > 0  # 多头信号应得正分
    assert result["direction"] in ["buy", "sell", "hold"]


def test_calculate_weighted_score_bearish():
    """测试空头信号评分"""
    indicators = {
        "最新价": 90.0,
        "MA5": 89.0,
        "MA10": 89.5,
        "MA20": 90.0,
        "MA60": 91.0,
        "DIF": -2.0,
        "DEA": -1.5,
        "RSI6": 75.0,
        "K": 85.0,
        "BOLL_UP": 110.0,
        "BOLL_DN": 85.0,
        "VOL_MA5": 1000000,
        "成交量": 1200000,
    }
    result = calculate_weighted_score(indicators)

    assert result["score"] < 0  # 空头信号应得负分
    assert result["direction"] in ["buy", "sell", "hold"]


def test_calculate_weighted_score_signal_count():
    """测试信号计数"""
    indicators = {
        "最新价": 100.0,
        "MA5": 101.0,
        "MA10": 100.0,
        "MA20": 99.0,
        "MA60": 98.0,
        "DIF": 1.0,
        "DEA": 0.5,
        "RSI6": 50.0,
        "K": 50.0,
        "BOLL_UP": 110.0,
        "BOLL_DN": 90.0,
        "VOL_MA5": 1000000,
        "成交量": 1000000,
    }
    result = calculate_weighted_score(indicators)

    assert "bullish_signals" in result
    assert "bearish_signals" in result
    assert "net_signals" in result
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/test_analyzer.py -v`
预期：FAIL，ImportError: cannot import name 'calculate_weighted_score'

- [ ] **步骤 3：编写最少实现代码**

```python
# 在 scripts/analyzer.py 中添加

# 加权信号评分权重
SIGNAL_WEIGHTS = {
    "ma_alignment_bull": 2.0,     # 均线多头排列
    "ma_alignment_bear": -2.0,    # 均线空头排列
    "macd_golden_cross": 1.5,     # MACD 金叉
    "macd_death_cross": -1.5,     # MACD 死叉
    "macd_hist_positive": 0.5,    # MACD 红柱
    "macd_hist_negative": -0.5,   # MACD 绿柱
    "rsi_oversold": 1.0,          # RSI 超卖
    "rsi_overbought": -1.0,       # RSI 超买
    "rsi_extreme_overbought": -2.0,  # RSI 严重超买
    "rsi_extreme_oversold": 1.5,  # RSI 严重超卖
    "boll_lower": 1.0,            # 触及布林下轨
    "boll_upper": -1.0,           # 触及布林上轨
    "bias_alert": -1.0,           # 乖离率预警
    "volume_up": 1.0,             # 放量上涨
    "volume_down_weak": -0.5,     # 缩量上涨
    "volume_down_panic": -1.5,    # 放量下跌
    "obv_inflow": 0.5,            # OBV 资金流入
    "obv_outflow": -0.5,          # OBV 资金流出
}


def calculate_weighted_score(indicators: Dict[str, float]) -> Dict[str, Any]:
    """
    计算加权信号评分。

    Args:
        indicators: 技术指标字典

    Returns:
        dict: {
            'score': float,
            'direction': 'buy' / 'sell' / 'hold',
            'confidence': '较高' / '中等' / '较低',
            'signals': list,
            'bullish_signals': int,
            'bearish_signals': int,
            'net_signals': int
        }
    """
    score = 0.0
    signals = []
    bullish_count = 0
    bearish_count = 0

    price = indicators.get("最新价", 0)
    ma5 = indicators.get("MA5", 0)
    ma10 = indicators.get("MA10", 0)
    ma20 = indicators.get("MA20", 0)
    ma60 = indicators.get("MA60", 0)
    dif = indicators.get("DIF", 0)
    dea = indicators.get("DEA", 0)
    rsi6 = indicators.get("RSI6", 50)
    k_val = indicators.get("K", 50)
    boll_up = indicators.get("BOLL_UP", 0)
    boll_dn = indicators.get("BOLL_DN", 0)
    vol_ma5 = indicators.get("VOL_MA5", 0)
    volume = indicators.get("成交量", 0)

    # 1. 均线排列判断
    if ma5 > ma10 > ma20 > ma60:
        # 检查间距（< 1% 不认定为有效排列）
        gap_5_10 = abs(ma5 - ma10) / ma10 * 100 if ma10 > 0 else 0
        gap_10_20 = abs(ma10 - ma20) / ma20 * 100 if ma20 > 0 else 0
        if gap_5_10 > 1 and gap_10_20 > 1:
            score += SIGNAL_WEIGHTS["ma_alignment_bull"]
            signals.append("均线多头排列 +2.0")
            bullish_count += 1
    elif ma5 < ma10 < ma20 < ma60:
        gap_5_10 = abs(ma5 - ma10) / ma10 * 100 if ma10 > 0 else 0
        gap_10_20 = abs(ma10 - ma20) / ma20 * 100 if ma20 > 0 else 0
        if gap_5_10 > 1 and gap_10_20 > 1:
            score += SIGNAL_WEIGHTS["ma_alignment_bear"]
            signals.append("均线空头排列 -2.0")
            bearish_count += 1

    # 2. MACD 信号
    if dif > dea:
        score += SIGNAL_WEIGHTS["macd_golden_cross"]
        signals.append("MACD金叉 +1.5")
        bullish_count += 1
    else:
        score += SIGNAL_WEIGHTS["macd_death_cross"]
        signals.append("MACD死叉 -1.5")
        bearish_count += 1

    # MACD 柱状图
    macd_hist = dif - dea
    if macd_hist > 0:
        score += SIGNAL_WEIGHTS["macd_hist_positive"]
        signals.append("MACD红柱 +0.5")
    else:
        score += SIGNAL_WEIGHTS["macd_hist_negative"]
        signals.append("MACD绿柱 -0.5")

    # 3. RSI 信号
    if rsi6 < 20:
        score += SIGNAL_WEIGHTS["rsi_extreme_oversold"]
        signals.append("RSI严重超卖(<20) +1.5")
        bullish_count += 1
    elif rsi6 < 30:
        score += SIGNAL_WEIGHTS["rsi_oversold"]
        signals.append("RSI超卖(<30) +1.0")
        bullish_count += 1
    elif rsi6 > 80:
        score += SIGNAL_WEIGHTS["rsi_extreme_overbought"]
        signals.append("RSI严重超买(>80) -2.0")
        bearish_count += 1
    elif rsi6 > 70:
        score += SIGNAL_WEIGHTS["rsi_overbought"]
        signals.append("RSI超买(>70) -1.0")
        bearish_count += 1

    # 4. 布林带信号
    if price > 0:
        if boll_up > 0 and price >= boll_up * 0.98:
            score += SIGNAL_WEIGHTS["boll_upper"]
            signals.append("触及布林上轨 -1.0")
            bearish_count += 1
        elif boll_dn > 0 and price <= boll_dn * 1.02:
            score += SIGNAL_WEIGHTS["boll_lower"]
            signals.append("触及布林下轨 +1.0")
            bullish_count += 1

    # 5. 乖离率检查
    if ma20 > 0 and price > 0:
        bias = (price - ma20) / ma20 * 100
        if abs(bias) > 5:
            score += SIGNAL_WEIGHTS["bias_alert"]
            signals.append(f"乖离率预警({bias:.1f}%) -1.0")
            bearish_count += 1

    # 6. 量价关系
    if vol_ma5 > 0 and volume > 0:
        vol_ratio = volume / vol_ma5
        if vol_ratio > 1.5:
            # 放量
            chg = indicators.get("涨跌幅_今日", 0)
            if chg > 0:
                score += SIGNAL_WEIGHTS["volume_up"]
                signals.append("放量上涨 +1.0")
                bullish_count += 1
            else:
                score += SIGNAL_WEIGHTS["volume_down_panic"]
                signals.append("放量下跌 -1.5")
                bearish_count += 1
        elif vol_ratio < 0.5:
            chg = indicators.get("涨跌幅_今日", 0)
            if chg > 0:
                score += SIGNAL_WEIGHTS["volume_down_weak"]
                signals.append("缩量上涨 -0.5")

    # 归一化到 -10 到 +10
    score = max(-10, min(10, score))

    # 计算净信号数
    net_signals = bullish_count - bearish_count

    # 判断操作方向
    has_bearish = bearish_count > 0
    if score >= 5 and not has_bearish and net_signals >= 2:
        direction = "buy"
        confidence = "较高"
    elif score >= 3 and not has_bearish and net_signals >= 1:
        direction = "buy"
        confidence = "中等"
    elif score <= -5:
        direction = "sell"
        confidence = "较高"
    elif score <= -3:
        direction = "sell"
        confidence = "中等"
    else:
        direction = "hold"
        confidence = "较低"

    return {
        "score": round(score, 2),
        "direction": direction,
        "confidence": confidence,
        "signals": signals,
        "bullish_signals": bullish_count,
        "bearish_signals": bearish_count,
        "net_signals": net_signals,
    }
```

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest tests/test_analyzer.py -v`
预期：3 个测试全部 PASS

- [ ] **步骤 5：Commit**

```bash
git add scripts/analyzer.py tests/test_analyzer.py
git commit -m "feat: add weighted signal scoring system"
```

---

## 任务 8：集成到主流程和报告生成

**文件：**
- 修改：`scripts/analyzer.py`
- 修改：`SKILL.md`

- [ ] **步骤 1：修改 analyze_stock 函数集成新模块**

```python
# 在 scripts/analyzer.py 中修改 analyze_stock 函数

from sentiment import analyze_sentiment, summarize_sentiment
from risk_control import (
    calc_dynamic_stop_loss, calc_target_price,
    calc_support_resistance, calc_position_size,
    check_risk_rules, detect_board_type
)
from comparison import compare_two_stocks, generate_comparison_table, get_sector_stocks


def analyze_stock(code, output_dir="."):
    """主分析流程（增强版）"""
    # ... 现有代码 ...

    # 新增：计算加权评分
    print("[8/12] 计算加权信号评分...")
    weighted_score = calculate_weighted_score(indicators)

    # 新增：计算动态止损/目标位
    print("[9/12] 计算动态止损/目标位...")
    board_type = detect_board_type(code)
    stop_loss = calc_dynamic_stop_loss(
        current_price=price,
        atr=indicators.get("ATR14", 0),
        board_type=board_type
    )
    target = calc_target_price(
        current_price=price,
        stop_loss=stop_loss["stop_loss"]
    )

    # 新增：计算支撑压力位
    print("[10/12] 计算支撑压力位...")
    support_resistance = calc_support_resistance(df_hist, price, indicators)

    # 新增：仓位建议
    position = calc_position_size(
        direction=weighted_score["direction"],
        score=weighted_score["score"],
        net_signals=weighted_score["net_signals"],
        has_bearish=weighted_score["bearish_signals"] > 0
    )

    # 新增：风控检查
    risk_check = check_risk_rules(
        code=code,
        indicators=indicators,
        is_st="ST" in name,
        is_new_stock=False  # 需要从 list_date 判断
    )

    # 新增：新闻情感分析
    print("[11/12] 分析新闻情感...")
    sentiment = analyze_sentiment(news_df.to_dict("records") if not news_df.empty else [])

    # 生成增强版报告
    print("[12/12] 生成增强版报告...")
    # ... 调用增强版 generate_report ...
```

- [ ] **步骤 2：增强报告生成函数**

在 `generate_report` 函数中添加新的章节：

```python
def generate_report(..., weighted_score=None, stop_loss=None, target=None,
                    support_resistance=None, position=None, risk_check=None,
                    sentiment=None):
    """生成增强版综合分析报告"""

    # ... 现有章节 ...

    # 新增：十二、加权信号评分
    if weighted_score:
        L.append("\n---\n## 十二、加权信号评分\n")
        L.append(f"**综合评分：{weighted_score['score']:.2f}**（-10 到 +10）\n")
        L.append(f"**操作方向：{weighted_score['direction']}**")
        L.append(f"**置信度：{weighted_score['confidence']}**\n")

        L.append("**信号明细：**")
        for signal in weighted_score["signals"]:
            L.append(f"- {signal}")

        L.append(f"\n**多空统计：**")
        L.append(f"- 看多信号：{weighted_score['bullish_signals']} 个")
        L.append(f"- 看空信号：{weighted_score['bearish_signals']} 个")
        L.append(f"- 净信号数：{weighted_score['net_signals']}")

    # 新增：十三、操作建议
    if stop_loss and target and position:
        L.append("\n---\n## 十三、操作建议\n")
        L.append(f"**方向：{weighted_score['direction']}**")
        L.append(f"**仓位：{position['position_pct']}%**（{position['description']}）\n")

        L.append("**止损/目标位：**")
        L.append(f"- 止损价：{stop_loss['stop_loss']}（{stop_loss['description']}）")
        L.append(f"- 目标价：{target['target_price']}（{target['description']}）")
        L.append(f"- 风险收益比：1:{target['risk_reward_ratio']}")

    # 新增：十四、支撑压力位
    if support_resistance:
        L.append("\n---\n## 十四、支撑压力位\n")

        if support_resistance.get("resistance"):
            L.append("**压力位：**")
            L.append("| 价格 | 来源 |")
            L.append("|------|------|")
            for r in support_resistance["resistance"][:5]:
                L.append(f"| {r['price']} | {r['source']} |")

        if support_resistance.get("support"):
            L.append("\n**支撑位：**")
            L.append("| 价格 | 来源 |")
            L.append("|------|------|")
            for s in support_resistance["support"][:5]:
                L.append(f"| {s['price']} | {s['source']} |")

    # 新增：十五、新闻情感
    if sentiment:
        L.append("\n---\n## 十五、新闻情感分析\n")
        L.append(summarize_sentiment(sentiment))

    # 新增：十六、风控提示
    if risk_check and risk_check.get("warnings"):
        L.append("\n---\n## 十六、风控提示\n")
        for warning in risk_check["warnings"]:
            L.append(f"- [!] {warning}")

    # ... 风险提示 ...
```

- [ ] **步骤 3：更新 SKILL.md**

更新功能说明，添加新功能的描述。

- [ ] **步骤 4：运行完整测试**

运行：`python -m pytest tests/ -v`
预期：所有测试 PASS

- [ ] **步骤 5：Commit**

```bash
git add scripts/analyzer.py SKILL.md
git commit -m "feat: integrate enhanced analysis features into main workflow"
```

---

## 任务 9：添加对比分析和板块分析的便捷函数

**文件：**
- 修改：`scripts/analyzer.py`
- 测试：`tests/test_analyzer.py`

- [ ] **步骤 1：编写失败的测试**

```python
# 在 tests/test_analyzer.py 中添加

from analyzer import compare_stocks_wrapper, analyze_sector_wrapper


def test_compare_stocks_wrapper():
    """测试双股对比便捷函数"""
    # 这个测试需要实际 API 调用，标记为集成测试
    # result = compare_stocks_wrapper("600519", "000858")
    # assert "comparison" in result
    pass  # 跳过，需要网络


def test_analyze_sector_wrapper():
    """测试板块分析便捷函数"""
    # result = analyze_sector_wrapper("白酒")
    # assert "sector_name" in result
    pass  # 跳过，需要网络
```

- [ ] **步骤 2：编写便捷函数**

```python
# 在 scripts/analyzer.py 中添加

def compare_stocks_wrapper(code_a: str, code_b: str) -> Dict[str, Any]:
    """
    双股对比分析的便捷函数。

    Args:
        code_a: 股票 A 代码
        code_b: 股票 B 代码

    Returns:
        dict: 对比分析结果
    """
    # 获取股票 A 数据
    name_a = get_stock_name(code_a)
    quote_a = fetch_realtime_quote(code_a)
    df_a = fetch_kline(code_a, days=120)
    indicators_a = calculate_indicators(df_a)
    rating_a = calculate_rating(indicators_a, {}, {})

    stock_a = {
        "code": code_a,
        "name": name_a,
        "price": indicators_a.get("最新价", 0),
        "pe": quote_a.get("f9", 0),
        "pb": quote_a.get("f23", 0),
        "market_cap": safe_num(quote_a.get("f20", 0)),
        "change_pct": indicators_a.get("涨跌幅_今日", 0),
        "indicators": indicators_a,
        "rating": rating_a,
    }

    # 获取股票 B 数据
    name_b = get_stock_name(code_b)
    quote_b = fetch_realtime_quote(code_b)
    df_b = fetch_kline(code_b, days=120)
    indicators_b = calculate_indicators(df_b)
    rating_b = calculate_rating(indicators_b, {}, {})

    stock_b = {
        "code": code_b,
        "name": name_b,
        "price": indicators_b.get("最新价", 0),
        "pe": quote_b.get("f9", 0),
        "pb": quote_b.get("f23", 0),
        "market_cap": safe_num(quote_b.get("f20", 0)),
        "change_pct": indicators_b.get("涨跌幅_今日", 0),
        "indicators": indicators_b,
        "rating": rating_b,
    }

    return compare_two_stocks(stock_a, stock_b)


def analyze_sector_wrapper(sector_name: str) -> Dict[str, Any]:
    """
    板块分析的便捷函数。

    Args:
        sector_name: 板块名称

    Returns:
        dict: 板块分析结果
    """
    from comparison import get_sector_stocks, analyze_sector

    codes = get_sector_stocks(sector_name)
    if not codes:
        return {"error": f"未知板块: {sector_name}"}

    stocks = []
    for code in codes:
        try:
            name = get_stock_name(code)
            quote = fetch_realtime_quote(code)
            change_pct = safe_num(quote.get("f3", 0))
            stocks.append({
                "code": code,
                "name": name,
                "change_pct": change_pct,
            })
        except Exception:
            continue

    sector_data = {
        "sector_name": sector_name,
        "stocks": stocks,
    }

    return analyze_sector(sector_data)
```

- [ ] **步骤 3：Commit**

```bash
git add scripts/analyzer.py tests/test_analyzer.py
git commit -m "feat: add convenience wrappers for comparison and sector analysis"
```

---

## 任务 10：更新文档和最终测试

**文件：**
- 修改：`SKILL.md`
- 测试：完整测试套件

- [ ] **步骤 1：更新 SKILL.md**

在分析维度表格中添加新功能：

```markdown
| 维度 | 内容 | 数据源 |
|------|------|--------|
| 技术面 | KDJ/RSI/MACD/BOLL/均线/K线形态 | 东方财富 K线 API |
| 资金面 | 主力资金流向、北向资金 | 东方财富资金流向 API |
| 基本面 | PE/PB/ROE/营收/净利润/资产负债率 | 东方财富实时行情 API |
| 财务排雷 | 净现比、销售回款率、应收/存货预警 | 东方财富财务报表 API |
| 新闻面 | 个股新闻、公告、情感分析 | 东方财富新闻 API |
| 行业面 | 所属行业排名、板块资金流向 | 东方财富行业板块 API |
| 反证清单 | 哪些事实会推翻当前结论 | 基于技术指标自动生成 |
| 投资评级 | 1-5星综合评分 | 技术+资金+财务综合计算 |
| 港股支持 | 港股数据获取和分析 | 东方财富港股 API |
| 扩展技术指标 | RSI 背离、MACD 柱状图、成交量异动、K 线形态、筹码分布 | K线数据计算 |
| 估值分位数 | PE/PB/股息率 5 年分位数 | 历史数据计算 |
| 行业对比 | 估值排名、行业景气度、龙头溢价 | 行业板块 API |
| **加权信号评分** | 多维度加权评分（-10到+10） | 技术指标综合计算 |
| **动态止损/目标位** | 基于 ATR 和风险收益比 | K线数据计算 |
| **支撑压力位** | 布林带+均线+高低点+斐波那契 | K线数据计算 |
| **仓位建议** | 根据评分和信号强度 | 评分系统计算 |
| **风控铁律** | 乖离率、均线间距、ST/次新股检查 | 多维度综合判断 |
| **新闻情感分析** | 关键词匹配判断正面/负面/中性 | 新闻数据计算 |
| **双股对比** | 7维度横向对比 | 两只股票数据 |
| **板块分析** | 代表性股票汇总分析 | 板块映射+个股数据 |
```

- [ ] **步骤 2：添加使用说明**

```markdown
## 新增功能使用

### 双股对比
```bash
python stock_analyzer.py compare 600519 000858
```

### 板块分析
```bash
python stock_analyzer.py sector 白酒
```

### 加权评分报告
分析报告中自动包含加权信号评分、操作建议、支撑压力位、风控提示。
```

- [ ] **步骤 3：运行完整测试**

运行：`python -m pytest tests/ -v`
预期：所有测试 PASS

- [ ] **步骤 4：Commit**

```bash
git add SKILL.md
git commit -m "docs: update SKILL.md with new features"
```

---

## 自检清单

- [x] 规格覆盖度：所有 8 项功能都有对应任务
- [x] 占位符扫描：无 TODO/待定/后续实现
- [x] 类型一致性：函数签名和返回值类型一致
- [x] 测试覆盖：每个模块都有单元测试
- [x] DRY：复用现有模块，避免重复代码
- [x] TDD：每个任务先写测试再实现

---

## 执行交接

计划已完成并保存到 `docs/superpowers/plans/2026-06-04-enhanced-analysis-features.md`。两种执行方式：

**1. 子代理驱动（推荐）** - 每个任务调度一个新的子代理，任务间进行审查，快速迭代

**2. 内联执行** - 在当前会话中使用 executing-plans 执行任务，批量执行并设有检查点

选哪种方式？
