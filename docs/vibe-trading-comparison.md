# Vibe-Trading vs Stock Analyzer Skill — 对比分析

> 分析日期：2026-06-16 | 基于 Vibe-Trading v0.1.9 (10.8k Stars) vs Stock Analyzer current

## 一、核心定位差异

| | Vibe-Trading | Stock Analyzer Skill |
|---|---|---|
| **定位** | AI 量化交易工作台（策略→回测→交易） | A 股综合分析报告生成器 |
| **用户** | 量化爱好者/散户交易者 | Claude Code 用户（AI 辅助分析） |
| **核心价值** | 自然语言→策略代码→回测→导出 | 一键获取多维度数据→结构化报告 |
| **技术门槛** | Docker/PyPI 一条命令 | Python 脚本 |

## 二、Web 界面

| 维度 | Vibe-Trading | Stock Analyzer Skill |
|------|-------------|---------------------|
| **有无** | ✅ React + FastAPI SSE | ❌ 纯 CLI + Markdown |
| **部署** | Docker → `localhost:8899` | 本地 Python |
| **交互** | 聊天式 + 仪表盘（Alpha Zoo/相关性热力图/回测图表） | 命令行参数 |
| **实时流** | SSE 实时推送 | 控制台 print |

## 三、核心架构

| 维度 | Vibe-Trading | Stock Analyzer Skill |
|------|-------------|---------------------|
| **执行引擎** | ReAct Agent + DAG 编排 Swarm | 线性 13 步分析流水线 |
| **LLM 集成** | 14+ 提供商 | 无 |
| **工具数量** | 35+ MCP + 77 金融技能 | ~20 函数 |
| **数据源** | 7 个自动降级 | 3 个顺序回退 |
| **多 Agent** | 29 预置专家团队 | 无 |

## 四、功能矩阵

| 功能 | Vibe-Trading | Stock Analyzer |
|------|:--:|:--:|
| 单股/双股/行业分析 | ✅ | ✅ |
| 技术指标 | ✅ | ✅ |
| 资金流向/财务排雷 | ✅ | ✅ |
| 策略回测 | ✅ 7引擎 | ❌ |
| 因子库 | ✅ 452个 | ❌ |
| 多Agent协作 | ✅ | ❌ |
| LLM驱动分析 | ✅ | ❌ |
| 策略导出 | ✅ Pine/TDX/MQL5 | ❌ |
| 相关性热力图 | ✅ ECharts | ❌ |
| 实盘交易 | ✅ Connector-First | ❌ |
| MCP插件 | ✅ | ❌ |
| 估值分位数 | 不确定 | ✅ PE/PB/股息率5年 |
| 动态止损 | 不确定 | ✅ ATR动态 |
| 新闻情感分析 | ✅ LLM驱动 | ✅ 关键词词典 |
| 监控反证清单 | ❌ | ✅ |

## 五、可采用的优化点

### P0 — 高价值可执行
1. ✅ LLM 增强报告解读 — 自然语言总结、矛盾识别、指标解释
2. ✅ 数据源扩展 + 自动降级 — AKShare 接入、DataLoader 协议
3. ✅ 交互式图表 — K线图、分位数图、资金流向图嵌入 HTML

### P1 — 中等价值
4. 策略回测 MVP — A股简易回测（Sharpe/回撤/胜率）
5. 数据源扩展完善 — Tushare/mootdx 可选
6. 前端相关性矩阵 — ECharts 多维热力图

### P2 — 长期演进
7. 监控系统 Web 化 — 定时任务 + 推送通知
8. MCP 工具化 — 封装为 MCP Server
9. 因子库轻量版 — Alpha101 前20个 A 股适配
