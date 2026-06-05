# 📊 Stock Analyzer Skill

> **一句话：输入股票代码或名称，AI 自动生成 16 维度专业分析报告。**

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-yellow.svg)](https://www.python.org/)
[![Tests 240+](https://img.shields.io/badge/tests-240+-green.svg)](tests/)

直连东方财富 API，零浏览器依赖，2 个 Python 包即可运行。适用于 **Claude Code**、**Cursor**、**OpenClaw** 等 AI Agent，也可作为独立 CLI 工具使用。

---

## ✨ 为什么选择这个工具？

| 痛点 | 本方案 |
|------|--------|
| 手动看盘费时费力 | 输入代码，12 步数据流水线自动完成 |
| 单一维度分析容易误判 | 16 个维度交叉验证，减少盲区 |
| 只告诉你买什么 | **反证清单**告诉你什么情况会打脸 |
| 止损全靠感觉 | ATR 动态止损，自动适配 10%/20%/30% 涨跌停板 |
| 依赖 Selenium 或浏览器 | 直连 API，`http.client` 绕过系统代理 |

---

## 🔍 16 维度分析全景

```
┌─────────────────────────────────────────────────────────────┐
│                    📋 综合评级 ★★★★★                        │
├──────────────┬──────────────┬──────────────┬────────────────┤
│  📈 技术面    │  💰 资金面    │  📊 基本面    │  🛡️ 风控面     │
│              │              │              │                │
│ • 均线系统    │ • 主力资金    │ • PE/PB/EPS  │ • 财务排雷     │
│ • MACD       │ • 北向资金    │ • ROE/毛利率  │ • 动态止损     │
│ • KDJ        │ • 行业板块    │ • 营收增速    │ • 支撑压力位   │
│ • RSI        │ • 资金热力图  │ • 负债率      │ • 仓位建议     │
│ • 布林带      │              │ • 估值百分位  │ • 乖离率检查   │
│ • ATR        │              │ • 行业对比    │ • 风控铁律     │
├──────────────┴──────────────┴──────────────┴────────────────┤
│  🧠 智能层：加权评分（18 信号，-10 ~ +10）→ 买/卖/持有判定     │
│  📰 舆情层：新闻情感分析（正面/负面/中性）                      │
│  ⚖️ 反证层：列出推翻当前结论的关键条件                         │
└─────────────────────────────────────────────────────────────┘
```

### 三大模式

| 模式 | 说明 | 命令示例 |
|------|------|----------|
| 📊 **单股分析** | 16 章节完整报告 | `美的集团` |
| ⚖️ **双股对比** | 7 维度横向 PK | `compare 贵州茅台 五粮液` |
| 🏭 **板块分析** | 10 大板块 × 5 只龙头 | `sector 白酒` |

---

## 🚀 快速开始

### Claude Code（推荐）

```text
/stock-analyzer-skill 000333
/stock-analyzer-skill 美的集团
```

### 命令行

```bash
# 单股分析（支持代码或中文名称）
python stock_analyzer.py 000333
python stock_analyzer.py 美的集团

# 批量分析
python stock_analyzer.py 美的集团 贵州茅台 宁德时代

# 双股对比
python stock_analyzer.py compare 贵州茅台 五粮液

# 板块分析（白酒/新能源/半导体/银行/医药/消费/科技/地产/军工/汽车）
python stock_analyzer.py sector 白酒

# 指定输出目录
python stock_analyzer.py -o ./reports 600519
```

---

## 📄 报告示例

报告自动生成到 `分析报告/` 目录，Markdown 格式，可直接在 GitHub/Typora/VS Code 中阅读。

### 单股分析

| 股票 | 评级 | 亮点 |
|------|------|------|
| [宁德时代（300750）](examples/300750-宁德时代-分析报告-20260605.md) | ★★★★ | 创业板权重，技术面偏多 |
| [贵州茅台（600519）](examples/600519-贵州茅台-分析报告-20260605.md) | ★★★★★ | 估值百分位分析，行业龙头溢价 |

### 双股对比 & 板块分析

- [茅台 vs 五粮液](examples/compare-茅台vs五粮液.md) — PE/PB/RSI/MACD 等 7 维度 PK
- [白酒板块](examples/sector-白酒板块.md) — 5 只龙头股汇总分析

---

## 🏗️ 安装

```bash
git clone https://github.com/beonfeng/stock-analyzer-skill.git
cd stock-analyzer-skill
pip install -r requirements.txt
```

**仅 2 个外部依赖：** `pandas` + `numpy`，其余全部使用 Python 内置模块。

> 💡 为什么不用 `requests`？项目刻意使用 `http.client` 直连 HTTPS，绕过系统代理配置，在公司网络环境下更稳定。

---

## 📁 项目结构

```text
stock-analyzer-skill/
├── stock_analyzer.py          # 入口文件（CLI 分发）
├── scripts/                   # 核心模块
│   ├── analyzer.py            # 主引擎：API 调用 + 指标计算 + 报告生成
│   ├── technical_indicators.py # 扩展指标：RSI 背离、MACD 柱量、K 线形态
│   ├── valuation_analysis.py  # 估值百分位：PE/PB/股息率 5 年分位
│   ├── industry_analysis.py   # 行业对比：估值排名、资金流向、龙头溢价
│   ├── risk_control.py        # 风控：动态止损、支撑压力、仓位计算
│   ├── comparison.py          # 双股对比 + 板块分析
│   ├── sentiment.py           # 新闻情感分析
│   ├── market_utils.py        # 市场识别（沪/深/港）
│   └── utils.py               # HTTP 客户端（直连、重试、代理绕过）
├── tests/                     # 240+ 测试用例
├── templates/                 # 报告模板（16 章节）
├── examples/                  # 示例报告
└── references/                # 技术指标 & 财务指标参考文档
```

---

## 📚 文档

| 文档 | 内容 |
|------|------|
| [技术指标说明](references/technical-indicators.md) | MA/MACD/KDJ/RSI/布林带/ATR 计算逻辑 |
| [财务排雷规则](references/financial-metrics.md) | 红黄绿灯预警体系 |
| [数据源说明](references/data-sources.md) | 东方财富 API 端点 & 参数 |
| [报告模板](templates/report-template.md) | 16 章节完整模板 |
| [更新日志](CHANGELOG.md) | 版本历史 |

---

## 🤝 贡献

欢迎提交 Issue 和 PR！

- 🐛 **Bug 修复** — 直接提 PR
- ✨ **新功能** — 先开 Issue 讨论方案
- 📝 **文档改进** — 随时欢迎
- 🧪 **测试补充** — 目前 240+，目标 300+

提交的功能点会记录在 [CHANGELOG.md](CHANGELOG.md) 中。

---

## ☕ 赞赏支持

如果这个 Skill 对你有帮助，欢迎 [请我喝杯咖啡](sponsor/sponsor.md)。

---

## ⚠️ 免责声明

本项目仅用于**公开资料研究、投研学习和 AI Agent 工作流演示**。
所有分析结果均基于公开数据自动计算，**不构成投资建议**。
市场有风险，投资需谨慎。

---

## License

[MIT License](LICENSE)
