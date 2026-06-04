# Stock Analyzer Skill：基于东方财富 API 的 A 股自动分析 Skill

> 面向 Claude Code、Cursor、OpenClaw 等 AI Agent 的 A 股自动分析 Skill。
> 关键词：Stock Analysis、A 股投研、自动分析、东方财富 API、技术分析、财务排雷。

## 为什么需要它

当你让 AI 分析股票时，它往往需要你手动提供数据，或者只能分析已有文件。

`stock-analyzer-skill` 的目标不同：**自动从东方财富 API 获取实时数据，一键生成完整的分析报告。**

它会自动完成：

1. 获取 K 线历史数据（最多 500 个交易日）。
2. 获取实时行情和财务指标。
3. 获取资金流向（主力、超大单、大单、中单、小单）。
4. 计算技术指标（均线、MACD、KDJ、RSI、布林带、ATR）。
5. 计算财务健康指标和排雷评分。
6. 计算加权信号评分和操作建议。
7. 生成综合分析报告（Markdown 格式）。

## 核心能力

| 能力 | 解决的问题 |
|---|---|
| 自动数据采集 | 绕过系统代理直连东方财富 API，自动获取 K 线、行情、资金流向 |
| 技术分析 | 均线、MACD、KDJ、RSI、布林带、ATR 等指标自动计算 |
| 财务排雷 | 自动检查资产负债率、市盈率、净利润增速等风险指标 |
| 资金分析 | 主力资金流向、北向资金、行业板块排名 |
| 综合评级 | 1-5 星自动评级，基于趋势、超买超卖、资金面、财务健康 |
| 批量分析 | 支持同时分析多只股票 |
| 港股支持 | 支持港股数据获取和分析 |
| 扩展技术指标 | RSI 背离、MACD 柱状图、成交量异动、K 线形态、筹码分布 |
| 估值分位数 | 当前估值在近 5 年历史中的百分位 |
| 行业对比 | 同行业估值排名、行业景气度、龙头溢价分析 |
| 加权信号评分 | 18 种技术信号加权评分（-10 到 +10），三级制判定 |
| 动态止损/目标位 | 基于 ATR 和风险收益比自动计算 |
| 支撑压力位 | 布林带+均线+高低点+斐波那契回撤 |
| 仓位建议 | 根据评分和信号强度动态计算（最高 20%） |
| 风控铁律 | 乖离率、均线间距、ST/次新股检查 |
| 新闻情感分析 | 关键词匹配判断正面/负面/中性 |
| 双股对比 | 7 维度横向对比（PE/PB/市值/涨跌/RSI/MACD/评级） |
| 板块分析 | 10 个板块代表性股票映射和趋势分析 |

## 适合谁

- 想用 AI Agent 做快速个股筛选的个人投资者。
- 正在学习技术分析、财务分析的投研学习者。
- 想给 Claude Code/Cursor 增加金融研究能力的 AI 工具玩家。
- 需要批量分析多只股票的投资者。

## 快速开始

### 方式一：使用 slash command（推荐）

在 Claude Code 中直接使用：

```text
/stock-analyzer-skill 000333
```

或批量分析：

```text
/stock-analyzer-skill 000333 600519 300750
```

### 方式二：直接运行脚本

```bash
python ~/.claude/skills/stock-analyzer/stock_analyzer.py 000333
```

或批量：

```bash
python ~/.claude/skills/stock-analyzer/stock_analyzer.py 000333 600519 300750
```

### 方式三：手动读取 Skill

如果你的 Agent 暂不支持技能目录，也可以直接让它读取 `SKILL.md`：

```text
请读取 ~/.claude/skills/stock-analyzer/SKILL.md，并按其中流程分析某只股票。
```

## 推荐提示词

```text
用 stock-analyzer-skill 分析美的集团 000333，看看现在能不能买。
```

```text
帮我分析贵州茅台 600519、宁德时代 300750、比亚迪 002594 这三只股票，对比一下哪个更值得投资。
```

```text
分析一下白酒板块整体走势。
```

## 输出示例

报告自动保存到 `股票代码-股票名称/股票代码-股票名称-分析报告-日期.md`：

```text
000333-美的集团/
└── 000333-美的集团-分析报告-20260604.md
```

### 报告模板

完整的报告模板请查看：[templates/report-template.md](templates/report-template.md)

### 分析示例

- [000333-美的集团](examples/000333-美的集团.md)
- [600519-贵州茅台](examples/600519-贵州茅台.md)
- [300750-宁德时代](examples/300750-宁德时代.md)

### 报告章节

1. **总结** — 结论先行，综合评级和关键指标
2. **一、行情概览** — 当日价格、涨跌幅、成交量
3. **二、技术分析** — 均线、MACD、KDJ、RSI、布林带
4. **三、资金分析** — 主力资金流向、北向资金
5. **四、基本面分析** — 估值指标、盈利与成长
6. **五、财务排雷** — 风险指标检查和排雷结论
7. **六、新闻动态** — 近期新闻
8. **七、行业板块排名** — 当日行业涨跌排名
9. **八、反证清单与跟踪因子** — 需要跟踪的关键指标
10. **九、估值分位数分析** — PE/PB/股息率 5 年分位数及估值区间
11. **十、行业对比分析** — 同行业估值排名、行业景气度、龙头溢价
12. **十一、扩展技术指标** — RSI 背离、MACD 柱状图、成交量异动、K 线形态、筹码分布
13. **十二、加权信号评分** — 18 种技术信号加权评分和多空统计
14. **十三、操作建议** — 方向、仓位、止损/目标位、风险收益比
15. **十四、支撑压力位** — 布林带+均线+高低点+斐波那契
16. **十五、新闻情感分析** — 正面/负面/中性判断
17. **十六、风控提示** — 乖离率、均线间距、ST/次新股警告
18. **风险提示** — 免责声明

## 目录结构

```text
stock-analyzer-skill/
├── README.md                    # 本文件
├── CHANGELOG.md                 # 更新日志
├── SKILL.md                     # Skill 定义文件
├── stock_analyzer.py            # 入口文件
├── scripts/                     # 核心脚本模块
│   ├── __init__.py
│   ├── analyzer.py              # 核心分析逻辑
│   ├── sentiment.py             # 新闻情感分析
│   ├── risk_control.py          # 风控模块（止损/目标位/支撑压力位/仓位/风控铁律）
│   ├── comparison.py            # 对比分析（双股对比/板块分析）
│   ├── market_utils.py          # 市场判断、价格转换
│   ├── technical_indicators.py  # 技术指标计算
│   ├── valuation_analysis.py    # 估值分位数分析
│   ├── industry_analysis.py     # 行业对比分析
│   └── utils.py                 # 共享工具函数
├── tests/                       # 单元测试（240+ 测试用例）
│   ├── test_analyzer.py
│   ├── test_comparison.py
│   ├── test_risk_control.py
│   ├── test_sentiment.py
│   ├── test_market_utils.py
│   ├── test_technical_indicators.py
│   ├── test_valuation_analysis.py
│   └── test_industry_analysis.py
├── templates/
│   └── report-template.md       # 完整报告模板
├── references/
│   ├── technical-indicators.md  # 技术指标说明
│   ├── financial-metrics.md     # 财务指标说明
│   └── data-sources.md          # 数据源说明
├── examples/
│   ├── 000333-美的集团.md       # 美的集团分析示例
│   ├── 600519-贵州茅台.md       # 贵州茅台分析示例
│   └── 300750-宁德时代.md       # 宁德时代分析示例
└── docs/
    └── api-reference.md         # API 参考文档
```

## 技术指标说明

| 指标 | 说明 | 信号 |
|---|---|---|
| MA5/10/20/60/120/250 | 移动平均线 | 价格在上方=多头，下方=空头 |
| MACD | 指数平滑异同移动平均线 | DIF上穿DEA=金叉（看涨），下穿=死叉（看跌） |
| KDJ | 随机指标 | K>80=超买，K<20=超卖 |
| RSI | 相对强弱指数 | >80=超买，<20=超卖 |
| BOLL | 布林带 | 触及上轨=可能回调，触及下轨=可能反弹 |
| ATR | 平均真实波幅 | 越大说明近期波动越剧烈 |

## 财务排雷规则

| 指标 | 绿灯 | 黄灯 | 红灯 |
|---|---|---|---|
| 资产负债率 | <60% | 60-70% | >70% |
| 市盈率 | 0-30 | 30-80 | <0 或 >80 |
| 净利润同比 | >10% | 0-10% | <0 |

## 数据源

本 Skill 直连东方财富 API，绕过系统代理，自动重试：

- **K 线数据**：`push2his.eastmoney.com`
- **实时行情**：`push2.eastmoney.com` / `82.push2.eastmoney.com`
- **资金流向**：`push2.eastmoney.com`
- **北向资金**：`push2his.eastmoney.com`
- **新闻数据**：`np-listapi.eastmoney.com`
- **行业数据**：`82.push2.eastmoney.com`
- **财务报表**：`datacenter.eastmoney.com`

## 局限性

- 支持 A 股和港股，不支持美股
- 技术指标存在滞后性
- 财务排雷基于简化模型，不能替代专业分析

## 贡献

欢迎提交 Issue：

- 新功能建议
- Bug 报告
- 技术指标改进建议
- 数据源补充

也欢迎提交 PR。提交的功能点会记录在 [CHANGELOG.md](CHANGELOG.md) 中。

## ☕ 赞赏支持

如果这个 Skill 帮你少踩坑、更高效，欢迎 [请我喝杯咖啡](sponsor/sponsor.md)。

你的支持会用于持续维护分析模板、补充行业因子、增加 A 股案例、开发 AkShare 取数脚本。

## 免责声明

本项目仅用于公开资料研究、投研学习和 AI Agent 工作流演示。
所有分析结果均基于公开数据自动计算，不构成投资建议。
市场有风险，投资需谨慎，请自行判断并承担风险。

## License

MIT License. See [`LICENSE`](LICENSE).
