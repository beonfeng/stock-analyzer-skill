# Stock Analyzer Skill

> 基于东方财富 API 的 A 股自动分析 Skill，适用于 Claude Code、Cursor、OpenClaw 等 AI Agent。

## 功能特性

- 🔄 **自动数据采集** — 直连东方财富 API，自动获取 K 线、行情、资金流向
- 📊 **技术分析** — 均线、MACD、KDJ、RSI、布林带、ATR 等指标自动计算
- 💰 **资金分析** — 主力资金流向、北向资金、行业板块排名
- ⚠️ **财务排雷** — 自动检查资产负债率、市盈率、净利润增速等风险指标
- ⭐ **综合评级** — 1-5 星自动评级，基于趋势、超买超卖、资金面、财务健康
- 📈 **加权评分** — 18 种技术信号加权评分（-10 到 +10），三级制判定
- 🎯 **操作建议** — 动态止损/目标位、支撑压力位、仓位建议
- 🛡️ **风控铁律** — 乖离率、均线间距、ST/次新股检查
- 📰 **情感分析** — 新闻正面/负面/中性判断
- 🔄 **双股对比** — 7 维度横向对比
- 📊 **板块分析** — 10 个板块代表性股票映射
- 🇭🇰 **港股支持** — 支持港股数据获取和分析

## 快速开始

### Claude Code（推荐）

```text
/stock-analyzer-skill 000333
```

### 命令行

```bash
python stock_analyzer.py 000333
```

### 批量分析

```bash
python stock_analyzer.py 000333 600519 300750
```

## 输出示例

报告自动保存到 `股票代码-股票名称/股票代码-股票名称-分析报告-日期.md`：

```text
000333-美的集团/
└── 000333-美的集团-分析报告-20260604.md
```

### 单股分析

- [600519-贵州茅台](examples/600519-贵州茅台.md) — 完整 16 章节报告
- [002594-比亚迪](examples/002594-比亚迪-完整报告.md) — 完整版（含所有新增功能）
- [000333-美的集团](examples/000333-美的集团.md)
- [300750-宁德时代](examples/300750-宁德时代.md)

### 双股对比

- [茅台 vs 五粮液](examples/compare-茅台vs五粮液.md) — 7 维度横向对比

### 板块分析

- [白酒板块](examples/sector-白酒板块.md) — 5 只代表性股票汇总分析

**报告模板：** [templates/report-template.md](templates/report-template.md)

## 安装

### 1. 克隆仓库

```bash
git clone https://github.com/beonfeng/stock-analyzer-skill.git
cd stock-analyzer-skill
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

**依赖说明：**
- `pandas` — 数据处理
- `numpy` — 数值计算
- Python 内置模块：`http.client`、`ssl`、`json`、`datetime` 等

## 文档

- [技术指标说明](references/technical-indicators.md)
- [财务排雷规则](references/financial-metrics.md)
- [数据源说明](references/data-sources.md)
- [更新日志](CHANGELOG.md)

## 项目结构

```text
stock-analyzer-skill/
├── stock_analyzer.py        # 入口文件
├── scripts/                 # 核心模块
│   ├── analyzer.py          # 分析逻辑
│   ├── sentiment.py         # 情感分析
│   ├── risk_control.py      # 风控模块
│   └── comparison.py        # 对比分析
├── tests/                   # 测试（240+）
├── templates/               # 报告模板
├── examples/                # 分析示例
└── references/              # 参考文档
```

## 局限性

- 支持 A 股和港股，不支持美股
- 技术指标存在滞后性
- 财务排雷基于简化模型，不能替代专业分析

## 贡献

欢迎提交 Issue 和 PR。提交的功能点会记录在 [CHANGELOG.md](CHANGELOG.md) 中。

## 赞赏支持

如果这个 Skill 对你有帮助，欢迎 [请我喝杯咖啡](sponsor/sponsor.md)。

## 免责声明

本项目仅用于公开资料研究、投研学习和 AI Agent 工作流演示。
所有分析结果均基于公开数据自动计算，不构成投资建议。
市场有风险，投资需谨慎。

## License

MIT License. See [`LICENSE`](LICENSE).
