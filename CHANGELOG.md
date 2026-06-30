# 更新日志

本文件记录 stock-analyzer-skill 的所有功能变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [v1.3.0] — 2026-06-30

### 新增
- **逐笔成交分析**：当日全部逐笔成交大单异动检测，大单占比、主力聚集识别、异常大单预警（`details/get` API）
- **板块资金全景**：全市场 100+ 行业板块资金流向排名，单次 `clist` 批量查询替代逐股查询
- **历史财务趋势**：近 5 年营收/利润/现金流 CAGR 与趋势分析（利润表 RPT_DMSK_FN_INCOME + 现金流量表 RPT_DMSK_FN_CASHFLOW）
- **财报期间标注**：基本面章节自动标注"基于 XXXX-XX-XX 财报"标签

### 修复
- **资金流向假数据**：`push2` 行情 API 的 f62 对所有股票返回 1，且 f66-f87 全部为 None。切换到 `push2his` 的 `fflow/daykline/get` 专项 API，获取真实逐日分层数据
- **主营业务构成百分比不闭合**：分母包含了 TYPE=1（重复项）和 TYPE=3（区域分类），导致百分比仅 33%。修正为仅对展示项目求和
- **每股收益始终显示 "-"**：`push2` 行情 API 的 f115 对所有股票返回 "-"。改为从 PE 反推（EPS = Price / PE）
- **北向资金 API 失效**：kline 端点 `ut=b2884a39...` 已失效。切换到 `fflow/kline/get` 端点，静默降级处理

### 改进
- **章节重新编号**：新增 3 个章节后全文 19 章顺序重排
- **API 请求优化**：移除 `fetch_realtime_quote` 中的资金流向字段合并（不同 ut 导致字段语义冲突）
- **数据源原则**：确立"实时快照用 push2，历史专项用 push2his，财务报表用 datacenter"的 API 选择规则

## [Unreleased] — 之前

### 修复

- **估值分析股息率字段**：`analyze_valuation_percentile` 中误用 f115（每股收益 EPS）作为股息率，修正为 f163（股息率 TTM）+ f168 备选（`valuation_analysis.py`）
- **反证监控净利润检查**：`check_condition_now` 从 `indicators` 获取净利润同比（永不返回），改为从 `fetch_realtime_quote().f41` 获取（`monitor.py`）
- **加权评分乖离率方向**：负乖离（超卖）不应被扣分。新增 `bias_alert_low: +1.0`（超卖反弹），与 `bias_alert_high: -1.0`（追高风险）区分（`analyzer.py`）
- **KDJ 集成到加权评分**：补充 KDJ 超买/超卖信号（4 档：K<10 +1.5 / K<20 +1.0 / K>80 -1.0 / K>90 -2.0），此前 k_val 虽被提取但未使用（`analyzer.py`）
- **港股 4 位代码 secid**：`get_secid` 对港股代码补齐到 5 位后才拼 secid，修复 4 位输入导致的 API 查询失败（`market_utils.py`）
- **美股 yfinance or fallback**：`fetch_us_realtime_quote` / `calculate_us_financial_health` 残留 `or` 运算符改为 `is not None` 判断（`us_stock.py`）
- **美股预热浪费**：美股模式跳过北向资金预热请求，节省 API 额度（`analyzer.py`）

### 改进

- **对比 RSI 评分**：改为以 50 为中性点（100 - 2 × |RSI-50|），不再偏向超买（`comparison.py`）
- **风控乖离率**：负乖离（超卖）不再作为「风控警告」展示（属于机会提示，非风险）（`risk_control.py`）
- **支撑压力位去重**：60 日与 20 日高低点比较从绝对阈值（0.01）改为相对阈值（1%），适配高价/低价股（`risk_control.py`）
- **年化涨幅精度**：60 日 → 年化指数从 4 修正为 4.2（252/60），更接近真实交易日数（`analyzer.py`）

### 待开发

- [ ] 增加多股票批量对比（3-5 只股票横向 PK）
- [ ] 增加自定义板块功能，支持用户自选股票组合分析
- [ ] 历史估值数据获取（当前为经验阈值判断）

## [1.2.1] - 2026-06-08

### 新增

- **safe_display 函数**：数据显示缺失时返回 `-` 而非 `0`，避免歧义（PE=0 可能是数据缺失也可能是零收益）
  - 估值指标表（PE/PB/每股收益等）使用 `safe_display`
  - 财务排雷指标表使用 `safe_display`
  - 新增 18 个单元测试验证 `safe_display` 行为

### 修复

- **北向资金代码**：使用正确的北向资金专用 secid（`1.000016` / `0.399005`），原代码使用的是指数代码
- **PE 为 0 时显示**：`_section_summary` 中 PE=0 时显示 `-` 而非 `0.00`
- **北交所代码处理**：`fetch_company_profile` 对北交所股票生成正确的 secucode（`BJ` 后缀）
- **每股收益显示**：`f115` 为 0 或缺失时显示 `-`
- **年化涨幅计算**：数据不足时（<60天）不触发逆向定价检查，避免误判
- **反证清单正则**：支持阿拉伯数字标题（如 `## 11. 反证清单`）
- **变量名错误**：`calculate_financial_health` 中 `revenue_growth` → `revenue`（`f40` 是营业收入绝对值不是增长率）
- **market_cap 安全转换**：`comparison.py` 中添加 `safe_num` 包装，防止 TypeError
- **空日期防御**：主营构成按日期分组时过滤空字符串 key
- **O(n) 搜索优化**：`fetch_realtime_quote` 方法2 从 O(n) 遍历改为 O(1) 字典索引

### 改进

- 测试用例从 240 增加到 241
- **EMA 计算说明**：`technical_indicators.py` 添加注释说明 MACD 序列计算与 analyzer.py 中单值计算的区别（序列用于柱状图分析，非重复逻辑）

## [1.2.0] - 2026-06-08

### 新增

- **资讯数据源**：原新闻 API（np-listapi.eastmoney.com）已下线（404），替换为研报 API（reportapi.eastmoney.com）+ 公告 API（np-anotice-stock.eastmoney.com），报告中标注 `[研报]`/`[公告]` 来源
- **北交所支持**：识别 8 开头的北交所代码（如 830799），正确处理价格除数
- **美股修复**：修复美股价格除数错误（1000→1），AAPL 等价格不再被错误除以 1000
- **情感分析加权**：关键词改为权重字典（涨停=3、利好=2 等），长词优先匹配，返回匹配关键词详情

### 修复

- **全面代码审计修复**（29 Bug + 24 优化）：
  - CRITICAL: 可变默认参数 `default={}` 跨调用数据污染（utils.py）
  - CRITICAL: `get_stock_name` 返回值元组拆包优先级（analyzer.py）
  - CRITICAL: `analyze_stock` 空 DataFrame 未防护导致 IndexError（analyzer.py）
  - CRITICAL: `_section_trade_suggestion` 未检查 `weighted_score` 导致 TypeError（analyzer.py）
  - CRITICAL: filter 参数注入风险（analyzer.py）
  - HIGH: XSS 标题/表格内容未转义（exporter.py）
  - HIGH: K 线数据 `float()` 未用 `safe_num()` 导致 ValueError（analyzer.py）
  - HIGH: 涨跌幅计算除零风险（analyzer.py）
  - HIGH: `ReportContext.__init__` 不校验必填字段（analyzer.py）
  - HIGH: `us_stock.py` 运算符优先级、None 值传播、浮点真值检查
  - HIGH: 连接对象泄漏、缓存参数浅拷贝污染（utils.py）
  - MEDIUM: 对比分析市值/涨跌幅维度未计入总分（comparison.py）
  - MEDIUM: 港股代码支持扩展为 4-5 位（market_utils.py）
  - MEDIUM: 北交所 4 开头代码支持（market_utils.py）
  - MEDIUM: `fetch_stock_news` 日期切片 None 防护（analyzer.py）
  - MEDIUM: `f115`/`f104`/`f105` 字段缺失（analyzer.py）
  - MEDIUM: 移除未使用的导入（analyzer.py）
  - 以及 24 项 LOW 级别优化
- **行业板块数据获取失败**：`82.push2.eastmoney.com` 不稳定（频繁 RemoteDisconnected），切换为 `push2.eastmoney.com`
- **严重**：`generate_enhanced_comparison_report` 中 PE/PB/市值格式化前未做 `safe_num` 转换，API 返回异常值时崩溃
- **严重**：`cmd_compare` 始终传空 `financial_data` 给 `calculate_financial_health`，财务报表数据从未使用
- `cmd_sector` 中 `fund_flow` 为 None 时 `.get()` 崩溃
- `us_stock.py` 中 `or` 模式导致 PE=0 等合法 falsy 值被错误 fallback
- `us_stock.py` 与 `market_utils.py` 重复定义 `is_us_stock`
- `valuation_analysis.py` 中 `fetch_historical_valuation` 是死代码（API 不返回历史估值）
- `valuation_analysis.py` 浮点数 `==` 比较改为容差比较
- `industry_analysis.py` PE≤0 股票排名返回 0 时添加说明标记
- `technical_indicators.py` `np.polyfit` 全 NaN 崩溃防护
- `technical_indicators.py` `rolling().mean()` 数据不足时 NaN 传播
- `risk_control.py` 浮点数 `!=` 比较改为 `abs` 差值比较
- `risk_control.py` 支撑/压力位去重时合并 source 信息（多指标共振）
- `comparison.py` PE≤0 假设说明 + `safe_num` 转换
- `monitor.py` 正则匹配中文数字修复（支持"二十"以上）
- `monitor.py` 章节提取从 `---` 分隔线改为 `##` 标题
- `utils.py` 裸 `except:` 改为 `except Exception:`
- `utils.py` falsy 值不被缓存（改为 `result is not None`）
- `utils.py` 冷却后 `_session_start_time` 未重置导致统计不准
- `exporter.py` HTML title 未转义、`md_to_html` 空值检查

### 改进

- **generate_report 重构**：794 行巨型函数拆分为 `ReportContext` 类 + 21 个 `_section_*` 子函数
- `analyzer.py` 所有 `except: pass` 改为 `print(警告信息)`，不再静默吞掉异常
- `SIGNAL_WEIGHTS` 添加详细注释说明每个权重的选择依据
- 年化涨幅计算：优先用 250 日数据，不足时用复合增长率公式 `(1+r)^4-1`
- `safe_num` 支持 `"N/A"`、`"--"`、`"nan"` 等常见异常值
- User-Agent 版本更新至 Chrome 136/137、Firefox 139
- 缓存淘汰从 O(n) 线性扫描改为 O(1) FIFO
- K 线形态识别互斥形态改用 `elif`，提取 magic number 为模块常量
- PDF 降级为 HTML 时打印警告信息
- `sys.argv` 修改改为 `parse_args` 参数传递
- 行业对比资金流向获取添加进度提示
- 估值分位数阈值添加行业特性说明

### 改进

- **技术指标说明完善**：为 MACD、RSI、KDJ、布林带等指标添加详细的数值含义、区间说明和信号解释

- **技术指标说明完善**：为 MACD、RSI、KDJ、布林带等指标添加详细的数值含义、区间说明和信号解释
  - MACD：添加 DIF/DEA/MACD柱的含义说明，红柱/绿柱的多空判断
  - RSI：添加 6 个区间说明（超买/强势/中性偏多/中性偏空/弱势/超卖）
  - KDJ：添加 K/D/J 三个值的含义说明和区域判断
  - 布林带：添加上轨/中轨/下轨的含义说明，带宽的含义说明
  - 资金流向：添加各类资金的定义说明，净流入/净流出的含义说明
  - ATR：添加 ATR 的用途说明（计算止损位）

### 新增

- **反证清单监控**：新增 `monitor` 子命令，自动扫描历史分析报告，检查反证清单中的条件是否已触发
  - 支持按股票代码过滤（`python stock_analyzer.py monitor 000333 600519`）
  - 支持按时间范围过滤（`--days 3` 只检查最近 3 天的报告）
  - 自动去重，每只股票只检查最新报告
  - 实时获取行情数据，逐一校验 MACD 交叉、均线突破、资金流向等条件
  - 生成 Markdown 监控报告，标注已触发的反证条件
  - 财务类条件（净利润增速、板块排名）需季报更新后检查，当前标记为跳过
- **报告导出 HTML/PDF**：`analyze`/`compare`/`sector` 子命令新增 `--format` 参数
  - `--format html`：生成带 CSS 样式的 HTML 报告，浏览器可直接打印为 PDF
  - `--format pdf`：优先使用 weasyprint 生成 PDF，不可用时自动降级为 HTML
  - HTML 报告内嵌专业样式：表格、引用块、打印优化
- **美股分析支持**：通过东方财富 API 支持美股 ticker（如 AAPL、TSLA、NVDA）
  - 输入包含字母的代码自动识别为美股（如 `python stock_analyzer.py AAPL`）
  - K 线、实时行情、财务指标均通过东方财富 API 获取，无需额外依赖
  - 技术指标、加权评分、止损/目标位等核心功能正常工作
  - 资金流向、北向资金、行业板块等 A 股专属维度标记为 N/A

---

## [1.1.1] - 2026-06-05

### 新增

- **ETF 基金支持**：支持深交所 ETF 基金代码（159xxx 系列）
- **名称输入优化**：支持股票中文名称模糊匹配（如输入"神州数码"自动识别为 000034）

### 修复

- 修复 `market_utils.py` 不支持 `1` 开头的 6 位代码问题
- 修复 `stock_analyzer.py` 中 `safe_num`、`compare_two_stocks`、`datetime` 未定义问题

### 变更

- 清理根目录冗余报告文件，统一存放至 `分析报告/` 目录
- 添加 `.claude/` 目录到 `.gitignore`
- 更新示例报告至 20260605

---

## [1.1.0] - 2026-06-04

### 新增

- **加权信号评分系统**：18 种技术信号加权评分（-10 到 +10），三级制判定（买入/卖出/观望）
- **动态止损/目标位**：基于 ATR 和风险收益比（1:2.5）自动计算
- **支撑压力位**：综合布林带、均线、近期高低点、斐波那契回撤
- **仓位建议**：根据评分和信号强度动态计算（最高 20%）
- **风控铁律**：乖离率检查、均线间距检查、ST 股票警告、次新股警告
- **新闻情感分析**：基于关键词匹配判断正面/负面/中性
- **双股对比分析**：7 维度横向对比（PE/PB/市值/涨跌/RSI/MACD/评级）
- **板块分析**：10 个板块代表性股票映射和趋势分析（白酒/新能源/半导体/银行/医药/消费/科技/地产/军工/汽车）
- **报告新增章节**：十二至十六章（加权信号评分、操作建议、支撑压力位、新闻情感分析、风控提示）

### 新增文件

- `scripts/sentiment.py` — 新闻情感分析模块
- `scripts/risk_control.py` — 风控模块（止损/目标位/支撑压力位/仓位/风控铁律）
- `scripts/comparison.py` — 对比分析模块（双股对比/板块分析）
- `tests/test_sentiment.py` — 4 个测试用例
- `tests/test_risk_control.py` — 11 个测试用例
- `tests/test_comparison.py` — 5 个测试用例
- `tests/test_analyzer.py` — 5 个测试用例

### 变更

- `scripts/analyzer.py` — 集成新模块、新增加权评分函数和便捷函数
- `SKILL.md` — 更新功能说明、报告结构、目录结构

### 测试

- 测试用例总数：240+
- 覆盖模块：analyzer, comparison, risk_control, sentiment, market_utils, technical_indicators, valuation_analysis, industry_analysis

---

## [1.0.0] - 2026-06-04

### 新增

- **初始版本**
- K 线历史数据获取（最多 500 个交易日）
- 实时行情和财务指标获取
- 资金流向分析（主力、超大单、大单、中单、小单）
- 北向资金数据
- 技术指标计算（均线、MACD、KDJ、RSI、布林带、ATR）
- 财务健康指标和排雷评分
- 综合评级（1-5 星）
- 港股支持
- 扩展技术指标（RSI 背离、MACD 柱状图、成交量异动、K 线形态、筹码分布）
- 估值分位数分析（PE/PB/股息率 5 年分位数）
- 行业对比分析（估值排名、行业景气度、龙头溢价）
- 反证清单与跟踪因子
- 批量分析功能

### 数据源

- 直连东方财富 API，绕过系统代理
- 自动重试机制（最多 8 次）

---

## GitHub 贡献记录

> 本章节记录 GitHub 用户提交的功能点和改进。

### 功能请求

（等待社区贡献）

### Bug 修复

（等待社区贡献）

### 改进建议

（等待社区贡献）
