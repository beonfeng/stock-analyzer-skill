# Stock Analyzer Skill — 项目文档

## 项目概述

基于东方财富 API 直连的 A 股多维度综合分析工具，生成结构化 Markdown 报告。可作为 Claude Code Skill 使用，也可独立 CLI 运行。

- **语言**: Python 3.8+
- **核心依赖**: pandas + numpy（A 股/港股/北交所）；yfinance（美股，可选）
- **数据源**: 东方财富 API（直连 HTTPS，绕过系统代理）+ yfinance（美股）
- **市场支持**: A 股（沪/深）、北交所、港股、美股

## 架构

```
stock_analyzer.py (入口/CLI 分发)
  ├── cmd_analyze()   → scripts/analyzer.py → analyze_stock()
  ├── cmd_compare()   → scripts/comparison.py
  ├── cmd_sector()    → scripts/comparison.py
  └── cmd_monitor()   → scripts/monitor.py
```

### 模块职责

| 文件 | 职责 |
|------|------|
| `stock_analyzer.py` | CLI 入口，argparse 子命令分发，报告格式化 |
| `scripts/analyzer.py` | 主引擎：16 步分析流水线，`ReportContext` + 24 个 `_section_*` 函数生成 19 章报告 |
| `scripts/utils.py` | HTTP 客户端（`http.client` 直连），重试机制，请求限速 |
| `scripts/technical_indicators.py` | MACD/KDJ/RSI/BOLL/ATR/均线/K 线形态/成交量异动 |
| `scripts/valuation_analysis.py` | PE/PB/股息率 5 年分位数 |
| `scripts/industry_analysis.py` | 同行业估值排名、景气度、龙头溢价 |
| `scripts/risk_control.py` | 动态止损位、支撑压力位、仓位建议、风控铁律 |
| `scripts/comparison.py` | 双股对比（7 维度）、板块分析（10 板块 × 5 龙头） |
| `scripts/sentiment.py` | 新闻关键词情感分析（正面/负面/中性） |
| `scripts/monitor.py` | 反证清单监控：解析已生成报告，追踪触发条件 |
| `scripts/market_utils.py` | 市场类型识别（沪/深/北交所/港/美）、价格除数、交易日判断 |
| `scripts/us_stock.py` | 美股数据通过 yfinance 获取 |
| `scripts/exporter.py` | Markdown → HTML / PDF 导出 |

### 报告输出

所有报告统一输出到 `分析报告/` 目录（gitignore），命名规范：
- 单股: `<code>-<name>-分析报告-YYYYMMDD.md`
- 对比: `对比-<nameA>vs<nameB>-YYYYMMDD.md`
- 板块: `板块-<name>-YYYYMMDD.md`
- 监控: `监控报告-YYYYMMDD.md`

## 常用命令

```bash
# 运行测试（241+ cases）
python -m pytest tests/ -q

# 运行主程序
python stock_analyzer.py 600519           # 单股分析
python stock_analyzer.py compare A B       # 双股对比
python stock_analyzer.py sector 白酒        # 板块分析
python stock_analyzer.py monitor           # 反证监控
python stock_analyzer.py -o ./out 600519   # 指定父目录
python stock_analyzer.py 600519 --format html  # 导出 HTML
```

## 代码约定

- **HTTP 请求**: 使用 `scripts/utils.py` 中的 `safe_fetch()` 统一发起，自动处理重试（最多 8 次）、代理绕过、请求限速（每分钟 ≤12 次）
- **API 端点**: 所有东方财富 API URL 定义在对应脚本文件顶部
- **中文编码**: Windows 控制台 GBK 兼容，使用 ASCII 安全 emoji 替换（`use_emoji=False`）
- **交易日处理**: 非交易日自动使用最近交易日数据，并在报告中标注
- **前复权**: K 线数据默认使用前复权（`fqt=1`）
- **报告生成**: `generate_report` 使用 `ReportContext` 打包参数，24 个 `_section_*` 函数各负责一个章节（19章报告）
- **资金流向**: 使用 `push2his` 的 `fflow/daykline/get` 专项 API 获取完整订单分层数据（超大单/大单/中单/小单），`push2` 行情 API 的 f62/f66-f87 字段不可靠
- **API 选择原则**: 实时快照数据用 `push2`，历史专项数据用 `push2his`，财务报表用 `datacenter`。不要往行情接口追加财务/资金流向字段
- **情感分析**: 使用加权关键词字典（`POSITIVE_WEIGHTS`/`NEGATIVE_WEIGHTS`），长词优先匹配
- **安全数值**: 使用 `safe_num()` 统一转换 API 返回值，处理 `"-"`、`"N/A"`、`"--"`、`"nan"` 等异常值
- **数据显示**: 使用 `safe_display()` 显示数值，缺失数据返回 `-` 而非 `0`，避免歧义（PE=0 可能是数据缺失也可能是零收益）

## 项目文件规范

- 输出报告放入 `分析报告/`，不放入项目根目录
- `templates/` 存放报告模板，`references/` 存放参考资料
- `docs/plans/` 和 `docs/specs/` 存放设计文档
- 配置文件在 `.claude/` 目录下（gitignore）
