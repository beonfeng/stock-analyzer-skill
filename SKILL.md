---
name: stock-analyzer-skill
description: Use when the user asks to analyze a stock, industry, or sector — including trends, capital flow, financial reports, news, technical indicators, or historical performance. Triggers on keywords like "分析股票", "走势分析", "资金流向", "财报分析", "行业分析", "stock analysis".
---

# Stock Analyzer Skill — A 股综合分析 Skill

## Overview

基于东方财富 API 直连，对 A 股个股进行多维度综合分析，生成结构化 Markdown 报告。输出目录为 `分析报告/`，包含技术面、资金面、基本面、财务排雷、反证清单等分析。

## When to Use

- 用户要求分析某只股票的走势、技术指标、资金流向
- 用户要求分析某行业的板块轮动、行业排名
- 用户要求查看某只股票的财报、基本面数据
- 用户要求获取某只股票的新闻动态、舆情分析
- 用户要求做股票的综合诊断

**When NOT to Use:**
- 用户要求回测策略 → 使用 myhhub-stock 的 backtest 模块
- 用户要求实时盯盘 → 使用 leek-fund VSCode 扩展
- 用户要求自动交易 → 使用 northstar 平台

## 分析维度

| 维度 | 内容 | 数据源 |
|------|------|--------|
| 技术面 | KDJ/RSI/MACD/BOLL/均线/K线形态 | 东方财富 K线 API |
| 资金面 | 主力资金流向、北向资金 | 东方财富 fflow 资金流向 API |
| 基本面 | PE/PB/ROE/营收/净利润/资产负债率 | 东方财富实时行情 API |
| 财务排雷 | 净现比、销售回款率、应收/存货预警 | 东方财富财务报表 API |
| 资讯面 | 研报 + 公告 | 东方财富研报/公告 API |
| 行业面 | 所属行业排名、板块资金流向 | 东方财富行业板块 API |
| 反证清单 | 哪些事实会推翻当前结论 | 基于技术指标自动生成 |
| 投资评级 | 1-5星综合评分 | 技术+资金+财务综合计算 |
| 港股支持 | 港股数据获取和分析 | 东方财富港股 API |
| 美股支持 | 美股数据获取和分析（需 pip install yfinance） | yfinance |
| 北交所支持 | 北交所 8xxxxx 代码识别和分析 | 东方财富 API |
| 扩展技术指标 | RSI 背离、MACD 柱状图、成交量异动、K 线形态、筹码分布 | K线数据计算 |
| 估值分位数 | PE/PB/股息率 5 年分位数 | 历史数据计算 |
| 行业对比 | 估值排名、行业景气度、龙头溢价 | 行业板块 API |
| **逐笔成交分析** | 当日全部逐笔成交，大单异动检测、主力聚集识别 | 东方财富逐笔成交 API |
| **板块资金全景** | 全市场 100+ 行业板块资金流向排名 | clist 批量查询 API |
| **历史财务趋势** | 近 5 年营收/利润/现金流 CAGR 与趋势分析 | 财务报表 API |
| **加权信号评分** | 多维度加权评分（-10到+10） | 技术指标综合计算 |
| **动态止损/目标位** | 基于 ATR 和风险收益比 | K线数据计算 |
| **支撑压力位** | 布林带+均线+高低点+斐波那契 | K线数据计算 |
| **仓位建议** | 根据评分和信号强度 | 评分系统计算 |
| **风控铁律** | 乖离率、均线间距、ST/次新股检查 | 多维度综合判断 |
| **新闻情感分析** | 关键词匹配判断正面/负面/中性 | 新闻数据计算 |

## 工作流程

```
输入: 股票代码 (如 000001, 600519)
  ↓
1. 获取股票基本信息 → 确定股票名称、所属行业
  ↓
2. 并行获取数据:
   ├── K线历史数据 (330个交易日)
   ├── 实时行情 + 财务指标
   ├── 资金流向 (今日/3日/5日/10日，含超大单/大单/中单/小单分层)
   ├── 逐笔成交明细 (当日全部逐笔，大单异动检测)
   ├── 北向资金
   ├── 个股新闻
   ├── 行业板块数据
   ├── 板块资金全景 (全市场100+板块排名)
   ├── 财务报表数据
   └── 历史财务数据 (近5年利润表+现金流量表)
  ↓
3. 计算技术指标 + 财务健康指标 + 投资评级
  ↓
4. 计算加权信号评分 + 动态止损/目标位 + 支撑压力位
  ↓
5. 计算仓位建议 + 风控检查 + 新闻情感分析
  ↓
6. 生成综合分析报告 (单文件，19章):
   └── 分析报告/
       └── 股票代码-股票名称-分析报告-YYYYMMDD.md
```

## 报告结构

```markdown
# 股票名称（代码）股票分析报告

## 公司概况
- 基本信息、主营业务构成、股权结构

## 公司分析
- 最大机会、最大风险、核心洞察

## 总结
- 综合评级：★☆☆☆☆ ~ ★★★★★（1-5星）
- 最新价、涨跌幅、资金流向、财务排雷结论

## 一、行情概览
- 当日行情数据、区间涨跌幅统计

## 二、技术分析
- 均线系统（MA5/10/20/60/120/250）
- MACD / KDJ / RSI / 布林带

## 三、资金分析
- 今日/3日/5日/10日资金流向
- 超大单/大单/中单/小单完整分层（来自 fflow 专项 API）

## 四、逐笔成交分析 [NEW]
- 当日全部逐笔成交大单异动检测
- 大单占比、主力聚集识别、异常大单预警

## 五、基本面分析
- 估值指标（PE/PB/总市值/流通市值/每股收益）
- 盈利与成长（ROE/毛利率/净利润同比/资产负债率）
- 标注财报报告期

## 六、财务排雷
- 核心指标、排雷结论（红灯/黄灯/通过）

## 七、历史财务趋势 [NEW]
- 近5年营收/利润/现金流 CAGR 与趋势分析
- 净利率走势、现金流质量评估

## 八、新闻动态
- 近期研报+公告列表

## 九、行业板块排名
- 当日行业板块涨跌排名（前20）

## 十、板块资金全景 [NEW]
- 全市场100+板块资金流向排名（TOP 10 流入/流出）
- 所属行业定位与资金排名

## 十一、扩展技术指标
- RSI 背离 / MACD 柱状图 / 成交量异动 / K 线形态 / 筹码分布

## 十二、估值分位数分析
- PE/PB/股息率 5 年分位数

## 十三、行业对比分析
- 同行业估值排名 / 行业景气度 / 龙头溢价

## 十四、反证清单与跟踪因子
- 哪些事实出现会推翻当前结论 / 关键跟踪因子表

## 十五、加权信号评分
- 综合评分（-10 到 +10）/ 操作方向和置信度

## 十六、操作建议
- 方向和仓位建议 / 止损/目标位 / 风险收益比

## 十七、支撑压力位
- 压力位（布林带、均线、高低点、斐波那契）/ 支撑位

## 十八、新闻情感分析
- 新闻正面/负面/中性判断 / 关键新闻提取

## 十九、风控提示
- 乖离率预警 / 均线间距检查 / ST/次新股警告

## 风险提示
```

## 使用方式

### 1. 分析股票（默认）

```bash
# 分析单只股票
python stock_analyzer.py 000001

# 分析多只股票
python stock_analyzer.py 000001 600519 000858
```

脚本自动在当前工作目录下创建 `分析报告/` 文件夹，内含综合分析报告。

### 2. 双股对比

```bash
python stock_analyzer.py compare 600519 000858
```

### 3. 板块分析

```bash
python stock_analyzer.py sector 白酒
```

支持的板块：白酒、新能源、半导体、银行、医药、消费、科技、地产、军工、汽车

### 4. 指定输出目录

```bash
python stock_analyzer.py -o ./reports 600519
python stock_analyzer.py -o ./reports compare 600519 000858
```

### 5. AI 增强分析

脚本生成基础数据报告后，Claude 读取报告文件，结合市场环境给出综合研判：
- 趋势判断（多头/空头/震荡）
- 关键支撑位/压力位
- 资金面信号解读
- 风险提示

### 6. 报告内容

分析报告自动包含 19 个章节：
- 逐笔成交分析（四章）
- 历史财务趋势（七章）
- 板块资金全景（十章）
- 加权信号评分（十五章）
- 操作建议（十六章）
- 支撑压力位（十七章）
- 新闻情感分析（十八章）
- 风控提示（十九章）

## 依赖安装

```bash
pip install -r requirements.txt
```

**依赖说明：**
- `pandas` — 数据处理
- `numpy` — 数值计算
- `http.client` / `ssl` — 直连 HTTPS（Python 内置，绕过系统代理）

如遇网络不稳定，脚本会自动重试（最多 8 次）。

## 目录结构

```text
stock-analyzer-skill/
├── README.md                    # 项目说明
├── SKILL.md                     # Skill 定义文件（本文件）
├── LICENSE                      # MIT 开源协议
├── .gitignore                   # Git 忽略文件
├── .github/
│   └── FUNDING.yml              # GitHub Sponsors 配置
├── stock_analyzer.py            # 入口文件（简洁）
├── scripts/                     # 核心脚本模块
│   ├── __init__.py
│   ├── analyzer.py              # 核心分析逻辑
│   ├── market_utils.py          # 市场判断、价格转换
│   ├── technical_indicators.py  # 技术指标计算
│   ├── valuation_analysis.py    # 估值分位数分析
│   ├── industry_analysis.py     # 行业对比分析
│   ├── sentiment.py             # 新闻情感分析
│   ├── risk_control.py          # 风控模块（止损/目标位/支撑压力/仓位/风控铁律）
│   ├── comparison.py            # 对比分析（双股对比/板块分析）
│   └── utils.py                 # 共享工具函数
├── tests/                       # 单元测试
│   ├── test_market_utils.py
│   ├── test_technical_indicators.py
│   ├── test_valuation_analysis.py
│   ├── test_industry_analysis.py
│   ├── test_analyzer.py
│   ├── test_comparison.py
│   ├── test_risk_control.py
│   └── test_sentiment.py
├── templates/
│   └── report-template.md       # 完整报告模板
├── references/
│   ├── technical-indicators.md  # 技术指标说明
│   ├── financial-metrics.md     # 财务指标说明
│   └── data-sources.md          # 数据源说明
├── docs/
│   ├── api-reference.md         # API 参考文档
│   ├── plans/                   # 开发计划
│   └── specs/                   # 设计文档
└── 分析报告/                     # 报告输出目录（gitignore）
    ├── <code>-<name>-分析报告-YYYYMMDD.md
    ├── 对比-<nameA>vs<nameB>-YYYYMMDD.md
    └── 板块-<name>-YYYYMMDD.md
```

## 技术指标说明

详见 `references/technical-indicators.md`

| 指标 | 说明 | 信号 |
|---|---|---|
| MA5/10/20/60/120/250 | 移动平均线 | 价格在上方=多头，下方=空头 |
| MACD | 指数平滑异同移动平均线 | DIF上穿DEA=金叉（看涨），下穿=死叉（看跌） |
| KDJ | 随机指标 | K>80=超买，K<20=超卖 |
| RSI | 相对强弱指数 | >80=超买，<20=超卖 |
| BOLL | 布林带 | 触及上轨=可能回调，触及下轨=可能反弹 |
| ATR | 平均真实波幅 | 越大说明近期波动越剧烈 |

## 财务排雷规则

详见 `references/financial-metrics.md`

| 指标 | 绿灯 | 黄灯 | 红灯 |
|---|---|---|---|
| 资产负债率 | <60% | 60-70% | >70% |
| 市盈率 | 0-30 | 30-80 | <0 或 >80 |
| 净利润同比 | >10% | 0-10% | <0 |

## 数据源

详见 `references/data-sources.md`

本 Skill 直连东方财富 API，绕过系统代理，自动重试：

- **K 线数据**：`push2his.eastmoney.com`
- **实时行情**：`push2.eastmoney.com`
- **资金流向（分层）**：`push2his.eastmoney.com`（fflow/daykline/get，含超大单/大单/中单/小单）
- **逐笔成交**：`push2.eastmoney.com`（details/get）
- **北向资金**：`push2his.eastmoney.com`（fflow/kline/get）
- **板块资金全景**：`push2.eastmoney.com`（clist/get，m:90+t:2）
- **资讯数据**：`reportapi.eastmoney.com`（研报）+ `np-anotice-stock.eastmoney.com`（公告）
- **行业数据**：`push2.eastmoney.com`
- **财务报表**：`datacenter.eastmoney.com`（利润表 RPT_DMSK_FN_INCOME + 现金流量表 RPT_DMSK_FN_CASHFLOW）

## Common Mistakes

| 错误 | 正确做法 |
|------|----------|
| 股票代码带交易所前缀 | 脚本接受纯数字代码，自动识别交易所 |
| 分析非交易日数据 | 脚本自动获取最近交易日数据 |
| 忽略复权处理 | 默认使用前复权 (qfq) 数据 |
| 行业名称不精确 | 使用东方财富返回的标准行业名称 |

## 局限性

- 支持 A 股（含北交所 8xxxxx、深交所 ETF 基金）、港股和美股（通过 yfinance）
- 美股需要额外安装 `pip install yfinance`
- 技术指标存在滞后性
- 财务排雷基于简化模型，不能替代专业分析
- 估值分位数使用全市场经验阈值，需结合行业特性判断

## 更新日志

详见 [CHANGELOG.md](CHANGELOG.md)

| 版本 | 日期 | 更新内容 |
|---|---|---|
| v1.3.0 | 2026-06-30 | 新增强：逐笔成交分析、板块资金全景、历史财务趋势（3章）。Bug修复：资金流向假数据(改用fflow API)、订单分层缺失、主营百分比不闭合(33%→100%)、EPS缺失、北向资金API修复。财报期间标注。报告扩展至19章 |
| v1.2.0 | 2026-06-08 | 全面代码审计修复（29 Bug + 24 优化）、北交所支持、美股价格修复、generate_report 重构、情感分析加权 |
| v1.1.1 | 2026-06-05 | 支持深交所 ETF 基金代码（159xxx）、名称模糊匹配、修复变量未定义问题 |
| v1.1.0 | 2026-06-04 | 新增加权评分、止损目标位、支撑压力位、仓位建议、风控铁律、情感分析、双股对比、板块分析 |
| v1.0.0 | 2026-06-04 | 初始版本，支持 K 线、行情、资金流向、北向资金、新闻、行业、财务报表 |
