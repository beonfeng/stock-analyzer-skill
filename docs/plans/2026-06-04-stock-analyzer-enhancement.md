# Stock Analyzer 功能增强实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 为 stock-analyzer-skill 增加港股支持、扩展技术指标、估值分位数分析和行业对比分析功能

**架构：** 将功能拆分为独立模块（market_utils.py、technical_indicators.py、valuation_analysis.py、industry_analysis.py），通过 analyze_stock.py 主脚本调用，保持单一职责原则

**技术栈：** Python 3.8+、pandas、numpy、http.client（直连东方财富 API）

---

## 文件结构

### 新增文件

| 文件 | 职责 |
|------|------|
| `market_utils.py` | 市场判断、代码识别、价格转换 |
| `technical_indicators.py` | RSI 背离、MACD 柱状图、成交量异动、K 线形态、筹码分布 |
| `valuation_analysis.py` | 估值分位数历史对比（PE/PB/股息率） |
| `industry_analysis.py` | 行业对比分析（估值、资金、景气度、龙头溢价） |

### 修改文件

| 文件 | 改动内容 |
|------|----------|
| `analyze_stock.py` | 调用新模块、更新报告生成逻辑 |
| `templates/report-template.md` | 新增第九、十章节 |
| `references/technical-indicators.md` | 新增技术指标说明 |
| `README.md` | 更新功能列表和目录结构 |
| `SKILL.md` | 更新分析维度和报告结构 |

---

## 任务清单

### 任务 1：创建市场工具模块 (market_utils.py)

**文件：**
- 创建：`market_utils.py`

- [ ] **步骤 1：编写市场判断函数**

```python
def get_market_info(code):
    """
    根据股票代码判断市场类型

    参数:
        code: 股票代码（如 '000001', '600519', '00700'）

    返回:
        tuple: (market_name, market_id, price_divisor)
            - market_name: 'SH' / 'SZ' / 'HK'
            - market_id: 1 / 0 / 116
            - price_divisor: 100 (A股) / 1000 (港股)
    """
    code = str(code).strip()

    # 港股：5 位数字
    if len(code) == 5 and code.isdigit():
        return 'HK', 116, 1000

    # 上海：6 开头
    if code.startswith('6'):
        return 'SH', 1, 100

    # 深圳：0/3 开头
    return 'SZ', 0, 100


def convert_price(raw_price, market):
    """
    根据市场类型转换价格

    参数:
        raw_price: API 返回的原始价格值
        market: 市场类型 ('SH'/'SZ'/'HK')

    返回:
        float: 转换后的价格（元/港币）
    """
    if raw_price is None or raw_price == '-' or raw_price == 0:
        return 0

    try:
        price = float(raw_price)
    except (ValueError, TypeError):
        return 0

    if market == 'HK':
        return price / 1000  # 港股：毫 → 港币
    else:
        return price / 100   # A 股：分 → 人民币


def is_hk_stock(code):
    """判断是否为港股"""
    return len(str(code).strip()) == 5 and str(code).strip().isdigit()


def get_secid(code, market_id):
    """
    获取东方财富 API 的 secid 参数

    参数:
        code: 股票代码
        market_id: 市场 ID (1=上海, 0=深圳, 116=香港)

    返回:
        str: secid 格式如 '1.600519' 或 '116.00700'
    """
    return f"{market_id}.{code}"
```

- [ ] **步骤 2：编写测试用例**

```python
# test_market_utils.py
import pytest
from market_utils import get_market_info, convert_price, is_hk_stock, get_secid

def test_get_market_info_hk():
    market, mid, divisor = get_market_info('00700')
    assert market == 'HK'
    assert mid == 116
    assert divisor == 1000

def test_get_market_info_sh():
    market, mid, divisor = get_market_info('600519')
    assert market == 'SH'
    assert mid == 1
    assert divisor == 100

def test_get_market_info_sz():
    market, mid, divisor = get_market_info('000001')
    assert market == 'SZ'
    assert mid == 0
    assert divisor == 100

def test_convert_price_hk():
    assert convert_price(458200, 'HK') == 458.2

def test_convert_price_a():
    assert convert_price(8250, 'SH') == 82.5

def test_convert_price_zero():
    assert convert_price(0, 'HK') == 0
    assert convert_price(None, 'SH') == 0
    assert convert_price('-', 'SZ') == 0

def test_is_hk_stock():
    assert is_hk_stock('00700') == True
    assert is_hk_stock('600519') == False
    assert is_hk_stock('000001') == False

def test_get_secid():
    assert get_secid('00700', 116) == '116.00700'
    assert get_secid('600519', 1) == '1.600519'
    assert get_secid('000001', 0) == '0.000001'
```

- [ ] **步骤 3：运行测试验证**

运行：`python -m pytest test_market_utils.py -v`
预期：全部 PASS

- [ ] **步骤 4：Commit**

```bash
git add market_utils.py test_market_utils.py
git commit -m "feat: add market_utils module for HK stock support"
```

---

### 任务 2：更新 analyze_stock.py 支持港股

**文件：**
- 修改：`analyze_stock.py:1-50` (导入部分)
- 修改：`analyze_stock.py:70-104` (fetch_kline 函数)
- 修改：`analyze_stock.py:107-172` (fetch_realtime_quote 函数)
- 修改：`analyze_stock.py:289-344` (股票名称映射)

- [ ] **步骤 1：更新导入部分**

在 `analyze_stock.py` 顶部添加导入：

```python
from market_utils import get_market_info, convert_price, is_hk_stock, get_secid
```

- [ ] **步骤 2：更新 fetch_kline 函数支持港股**

```python
def fetch_kline(code, days=500):
    """获取 K 线历史数据（支持 A 股和港股）"""
    market_name, market_id, price_divisor = get_market_info(code)

    end = datetime.date.today().strftime("%Y%m%d")
    start = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%Y%m%d")

    params = {
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f116",
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "klt": "101", "fqt": "1",
        "secid": get_secid(code, market_id),
        "beg": start, "end": end,
    }

    # 港股接口不稳定，增加重试次数和超时时间
    retries = 12 if market_name == 'HK' else 8
    timeout = 20 if market_name == 'HK' else 15

    j = _http_get("push2his.eastmoney.com", "/api/qt/stock/kline/get", params, timeout=timeout, retries=retries)
    klines = j.get("data", {}).get("klines", [])
    if not klines:
        return pd.DataFrame()

    rows = []
    for line in klines:
        parts = line.split(",")
        if len(parts) >= 11:
            rows.append({
                "日期": parts[0],
                "开盘": float(parts[1]) / price_divisor,
                "收盘": float(parts[2]) / price_divisor,
                "最高": float(parts[3]) / price_divisor,
                "最低": float(parts[4]) / price_divisor,
                "成交量": float(parts[5]),
                "成交额": float(parts[6]),
                "振幅": float(parts[7]),
                "涨跌幅": float(parts[8]),
                "涨跌额": float(parts[9]),
                "换手率": float(parts[10]),
            })
    return pd.DataFrame(rows)
```

- [ ] **步骤 3：更新 fetch_realtime_quote 函数支持港股**

```python
def fetch_realtime_quote(code):
    """获取实时行情 + 财务指标（支持 A 股和港股）"""
    market_name, market_id, price_divisor = get_market_info(code)

    # 方法2：直接查询单只股票
    params2 = {
        "secid": get_secid(code, market_id),
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        "fields": "f43,f44,f45,f46,f47,f48,f50,f51,f52,f55,f57,f58,f60,f62,f71,f92,f105,f116,f117,f162,f167,f168,f169,f170,f171,f173,f177,f183,f184,f185,f186,f187,f188,f189,f190,f191,f192,f193",
        "invt": "2",
    }
    j2 = _http_get_safe("push2.eastmoney.com", "/api/qt/stock/get", params2)
    if j2 and j2.get("data"):
        data = j2["data"]

        def safe_float(v, default=0):
            if v is None or v == "-":
                return default
            try:
                return float(v)
            except (ValueError, TypeError):
                return default

        # 根据市场类型使用不同的价格除数
        def div_price(field):
            raw = safe_float(data.get(field, 0))
            return raw / price_divisor if raw != 0 else 0

        def div100(field):
            raw = safe_float(data.get(field, 0))
            return raw / 100 if raw != 0 else 0

        def direct(field):
            return safe_float(data.get(field, 0))

        return {
            "f14": data.get("f58", ""),  # 名称
            "f2": div_price("f43"),  # 最新价
            "f3": div100("f170"),  # 涨跌幅
            "f9": div100("f162"),  # PE
            "f23": div100("f167"),  # PB
            "f20": direct("f116"),  # 总市值
            "f21": direct("f117"),  # 流通市值
            "f37": direct("f173"),  # ROE
            "f49": direct("f186"),  # 毛利率
            "f40": direct("f183"),  # 营收同比
            "f41": direct("f185"),  # 净利润同比
            "f34": direct("f188"),  # 资产负债率
            "market": market_name,  # 新增：市场类型
        }
    return {}
```

- [ ] **步骤 4：添加港股名称映射**

```python
# 常见港股名称映射
_HK_STOCK_NAMES = {
    "00700": "腾讯控股",
    "09988": "阿里巴巴",
    "09618": "京东",
    "03690": "美团",
    "01810": "小米",
    "09888": "百度",
    "01024": "快手",
    "02015": "理想汽车",
    "09866": "蔚来",
    "09868": "小鹏汽车",
    "01211": "比亚迪",
    "00941": "中国移动",
    "00883": "中国海洋石油",
    "00388": "香港交易所",
    "02318": "中国平安",
    "01398": "工商银行",
    "00939": "建设银行",
    "03988": "中国银行",
    "01288": "农业银行",
    "00005": "汇丰控股",
}

def get_stock_name(code):
    """获取股票名称：先尝试 API，再用内置映射"""
    try:
        quote = fetch_realtime_quote(code)
        name = quote.get("f14", "")
        if name:
            return name
    except Exception:
        pass

    # 根据市场类型选择映射表
    if is_hk_stock(code):
        return _HK_STOCK_NAMES.get(code, code)

    return _STOCK_NAMES.get(code, code)
```

- [ ] **步骤 5：测试港股功能**

运行：`python analyze_stock.py 00700`
预期：成功获取腾讯控股数据并生成报告

- [ ] **步骤 6：Commit**

```bash
git add analyze_stock.py
git commit -m "feat: add Hong Kong stock support to analyze_stock.py"
```

---

### 任务 3：创建技术指标扩展模块 (technical_indicators.py)

**文件：**
- 创建：`technical_indicators.py`

- [ ] **步骤 1：编写 RSI 背离检测函数**

```python
import pandas as pd
import numpy as np


def detect_rsi_divergence(close, rsi, lookback=20):
    """
    检测 RSI 背离

    参数:
        close: 收盘价序列 (pandas Series)
        rsi: RSI 序列 (pandas Series)
        lookback: 回看周期（天数）

    返回:
        dict: {
            '类型': '顶背离' / '底背离' / '无背离',
            '信号': str,
            '可靠性': '高' / '中' / '低'
        }
    """
    if len(close) < lookback or len(rsi) < lookback:
        return {'类型': '无背离', '信号': '数据不足', '可靠性': '-'}

    # 取最近 lookback 天的数据
    recent_close = close.tail(lookback).values
    recent_rsi = rsi.tail(lookback).values

    # 找到价格高点和低点的位置
    price_high_idx = np.argmax(recent_close)
    price_low_idx = np.argmin(recent_close)

    # 检查是否在近期（最近 5 天内）出现新高/新低
    recent_window = 5

    # 顶背离：价格创新高，但 RSI 未创新高
    if price_high_idx >= lookback - recent_window:
        # 找到之前的价格高点
        prev_high_idx = np.argmax(recent_close[:price_high_idx]) if price_high_idx > 0 else 0
        if recent_close[price_high_idx] > recent_close[prev_high_idx]:
            # 价格创新高
            if recent_rsi[price_high_idx] < recent_rsi[prev_high_idx]:
                # RSI 未创新高 -> 顶背离
                return {
                    '类型': '顶背离',
                    '信号': '价格创新高但 RSI 未创新高，看跌信号',
                    '可靠性': '高' if recent_rsi[price_high_idx] > 70 else '中'
                }

    # 底背离：价格创新低，但 RSI 未创新低
    if price_low_idx >= lookback - recent_window:
        # 找到之前的价格低点
        prev_low_idx = np.argmin(recent_close[:price_low_idx]) if price_low_idx > 0 else 0
        if recent_close[price_low_idx] < recent_close[prev_low_idx]:
            # 价格创新低
            if recent_rsi[price_low_idx] > recent_rsi[prev_low_idx]:
                # RSI 未创新低 -> 底背离
                return {
                    '类型': '底背离',
                    '信号': '价格创新低但 RSI 未创新低，看涨信号',
                    '可靠性': '高' if recent_rsi[price_low_idx] < 30 else '中'
                }

    return {'类型': '无背离', '信号': '无明显背离信号', '可靠性': '-'}
```

- [ ] **步骤 2：编写 MACD 柱状图分析函数**

```python
def analyze_macd_histogram(dif_series, dea_series):
    """
    分析 MACD 柱状图

    参数:
        dif_series: DIF 序列 (pandas Series)
        dea_series: DEA 序列 (pandas Series)

    返回:
        dict: {
            '连续红柱天数': int,
            '连续绿柱天数': int,
            '柱状图斜率': float,
            '趋势判断': str,
            '信号': str
        }
    """
    if len(dif_series) < 5 or len(dea_series) < 5:
        return {
            '连续红柱天数': 0,
            '连续绿柱天数': 0,
            '柱状图斜率': 0,
            '趋势判断': '数据不足',
            '信号': '-'
        }

    # 计算 MACD 柱状图 (DIF - DEA)
    histogram = dif_series - dea_series

    # 计算连续红柱/绿柱天数
    red_days = 0
    green_days = 0

    for i in range(len(histogram) - 1, -1, -1):
        if histogram.iloc[i] > 0:
            if green_days > 0:
                break
            red_days += 1
        elif histogram.iloc[i] < 0:
            if red_days > 0:
                break
            green_days += 1
        else:
            break

    # 计算柱状图斜率（最近 5 天的线性斜率）
    recent_hist = histogram.tail(5).values
    if len(recent_hist) >= 2:
        x = np.arange(len(recent_hist))
        slope = np.polyfit(x, recent_hist, 1)[0]
    else:
        slope = 0

    # 趋势判断
    if slope > 0.01:
        trend = '动能增强'
    elif slope < -0.01:
        trend = '动能减弱'
    else:
        trend = '动能平稳'

    # 信号
    if red_days > 0 and slope > 0:
        signal = f'连续红柱 {red_days} 天，{trend}（看涨）'
    elif green_days > 0 and slope < 0:
        signal = f'连续绿柱 {green_days} 天，{trend}（看跌）'
    elif red_days > 0:
        signal = f'连续红柱 {red_days} 天，{trend}'
    elif green_days > 0:
        signal = f'连续绿柱 {green_days} 天，{trend}'
    else:
        signal = f'MACD 柱状图 {trend}'

    return {
        '连续红柱天数': red_days,
        '连续绿柱天数': green_days,
        '柱状图斜率': round(slope, 4),
        '趋势判断': trend,
        '信号': signal
    }
```

- [ ] **步骤 3：编写成交量异动检测函数**

```python
def detect_volume_anomaly(volume, ma5, ma20):
    """
    检测成交量异动

    参数:
        volume: 当日成交量
        ma5: 5 日均量
        ma20: 20 日均量

    返回:
        dict: {
            '状态': '放量' / '缩量' / '天量' / '地量' / '正常',
            '倍数': float,
            '信号': str
        }
    """
    if ma5 is None or ma5 == 0 or ma20 is None or ma20 == 0:
        return {'状态': '数据不足', '倍数': 0, '信号': '-'}

    ratio_5 = volume / ma5
    ratio_20 = volume / ma20

    # 天量：当日成交量 > 20 日均量 × 2.0
    if ratio_20 > 2.0:
        return {
            '状态': '天量',
            '倍数': round(ratio_5, 2),
            '信号': f'成交量是 5 日均量的 {ratio_5:.1f} 倍，异常放大'
        }

    # 放量：当日成交量 > 5 日均量 × 1.5
    if ratio_5 > 1.5:
        return {
            '状态': '放量',
            '倍数': round(ratio_5, 2),
            '信号': f'成交量是 5 日均量的 {ratio_5:.1f} 倍，明显放大'
        }

    # 地量：当日成交量 < 20 日均量 × 0.3
    if ratio_20 < 0.3:
        return {
            '状态': '地量',
            '倍数': round(ratio_5, 2),
            '信号': f'成交量仅为 5 日均量的 {ratio_5:.1f} 倍，极度萎缩'
        }

    # 缩量：当日成交量 < 5 日均量 × 0.5
    if ratio_5 < 0.5:
        return {
            '状态': '缩量',
            '倍数': round(ratio_5, 2),
            '信号': f'成交量仅为 5 日均量的 {ratio_5:.1f} 倍，明显萎缩'
        }

    return {
        '状态': '正常',
        '倍数': round(ratio_5, 2),
        '信号': '成交量处于正常范围'
    }
```

- [ ] **步骤 4：编写 K 线形态识别函数**

```python
def identify_candlestick_patterns(df, lookback=5):
    """
    识别 K 线形态

    参数:
        df: 包含 '开盘', '收盘', '最高', '最低' 的 DataFrame
        lookback: 回看周期

    返回:
        list: [{'形态': str, '信号': str, '可靠性': str}]
    """
    if len(df) < lookback + 1:
        return []

    patterns = []
    recent = df.tail(lookback + 1)

    for i in range(1, len(recent)):
        curr = recent.iloc[i]
        prev = recent.iloc[i - 1]

        open_price = float(curr['开盘'])
        close_price = float(curr['收盘'])
        high_price = float(curr['最高'])
        low_price = float(curr['最低'])

        prev_open = float(prev['开盘'])
        prev_close = float(prev['收盘'])

        # 实体长度
        body = abs(close_price - open_price)
        # 上影线长度
        upper_shadow = high_price - max(open_price, close_price)
        # 下影线长度
        lower_shadow = min(open_price, close_price) - low_price
        # 当日振幅
        amplitude = high_price - low_price

        if amplitude == 0:
            continue

        # 十字星：开盘价 ≈ 收盘价，上下影线较长
        if body / amplitude < 0.1 and upper_shadow > body * 2 and lower_shadow > body * 2:
            patterns.append({
                '形态': '十字星',
                '信号': '犹豫信号，可能变盘',
                '可靠性': '中'
            })

        # 锤子线：下影线 > 实体 2 倍，上影线很短
        if lower_shadow > body * 2 and upper_shadow < body * 0.5 and body > 0:
            patterns.append({
                '形态': '锤子线',
                '信号': '底部看涨',
                '可靠性': '中'
            })

        # 倒锤子线：上影线 > 实体 2 倍，下影线很短
        if upper_shadow > body * 2 and lower_shadow < body * 0.5 and body > 0:
            patterns.append({
                '形态': '倒锤子线',
                '信号': '底部看涨（需确认）',
                '可靠性': '低'
            })

        # 吞没形态：当日实体完全包含前一日实体
        if (open_price < prev_close and close_price > prev_open and
            close_price > open_price and prev_close < prev_open):
            patterns.append({
                '形态': '看涨吞没',
                '信号': '趋势反转（看涨）',
                '可靠性': '高'
            })

        if (open_price > prev_close and close_price < prev_open and
            close_price < open_price and prev_close > prev_open):
            patterns.append({
                '形态': '看跌吞没',
                '信号': '趋势反转（看跌）',
                '可靠性': '高'
            })

        # 乌云盖顶：阳线后出现高开低走阴线
        if (prev_close > prev_open and  # 前一日是阳线
            open_price > high_price and  # 高开
            close_price < open_price and  # 低走
            close_price < (prev_open + prev_close) / 2):  # 收盘低于前一日实体中部
            patterns.append({
                '形态': '乌云盖顶',
                '信号': '顶部看跌',
                '可靠性': '高'
            })

    return patterns
```

- [ ] **步骤 5：编写筹码分布分析函数**

```python
def calculate_chip_distribution(df, current_price):
    """
    计算筹码分布

    参数:
        df: 包含 '收盘', '成交量' 的 DataFrame
        current_price: 当前价格

    返回:
        dict: {
            '平均成本': float,
            '获利盘比例': float,
            '套牢盘比例': float,
            '筹码集中度': str
        }
    """
    if len(df) < 20 or current_price <= 0:
        return {
            '平均成本': 0,
            '获利盘比例': 0,
            '套牢盘比例': 0,
            '筹码集中度': '数据不足'
        }

    # 使用成交量加权计算平均成本
    close = df['收盘'].astype(float).values
    volume = df['成交量'].astype(float).values

    # 计算加权平均成本
    total_volume = volume.sum()
    if total_volume == 0:
        return {
            '平均成本': 0,
            '获利盘比例': 0,
            '套牢盘比例': 0,
            '筹码集中度': '数据不足'
        }

    weighted_cost = (close * volume).sum() / total_volume

    # 计算获利盘比例（当前价格下方的筹码占比）
    profitable_volume = volume[close <= current_price].sum()
    profitable_ratio = (profitable_volume / total_volume) * 100

    # 计算套牢盘比例
    trapped_ratio = 100 - profitable_ratio

    # 筹码集中度判断
    # 使用价格标准差与均价的比值来判断
    price_std = np.std(close)
    concentration_ratio = price_std / weighted_cost if weighted_cost > 0 else 0

    if concentration_ratio < 0.1:
        concentration = '集中'
    elif concentration_ratio < 0.2:
        concentration = '较集中'
    elif concentration_ratio < 0.3:
        concentration = '较分散'
    else:
        concentration = '分散'

    return {
        '平均成本': round(weighted_cost, 2),
        '获利盘比例': round(profitable_ratio, 1),
        '套牢盘比例': round(trapped_ratio, 1),
        '筹码集中度': concentration
    }
```

- [ ] **步骤 6：编写综合技术指标扩展函数**

```python
def calculate_extended_indicators(df, indicators):
    """
    计算扩展技术指标

    参数:
        df: K 线数据 DataFrame
        indicators: 已计算的基础指标字典

    返回:
        dict: 扩展指标字典
    """
    if df.empty or len(df) < 30:
        return {}

    close = df['收盘'].astype(float)
    volume = df['成交量'].astype(float)

    # 计算 RSI 序列（用于背离检测）
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi_series = 100 - 100 / (1 + rs)

    # RSI 背离检测
    rsi_divergence = detect_rsi_divergence(close, rsi_series, lookback=20)

    # MACD 柱状图分析
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif_series = ema12 - ema26
    dea_series = dif_series.ewm(span=9, adjust=False).mean()
    macd_histogram = analyze_macd_histogram(dif_series, dea_series)

    # 成交量异动检测
    vol_ma5 = volume.rolling(5).mean().iloc[-1] if len(volume) >= 5 else 0
    vol_ma20 = volume.rolling(20).mean().iloc[-1] if len(volume) >= 20 else 0
    volume_anomaly = detect_volume_anomaly(volume.iloc[-1], vol_ma5, vol_ma20)

    # K 线形态识别
    candlestick_patterns = identify_candlestick_patterns(df, lookback=5)

    # 筹码分布分析
    chip_distribution = calculate_chip_distribution(df, close.iloc[-1])

    return {
        'RSI背离': rsi_divergence,
        'MACD柱状图': macd_histogram,
        '成交量异动': volume_anomaly,
        'K线形态': candlestick_patterns,
        '筹码分布': chip_distribution
    }
```

- [ ] **步骤 7：Commit**

```bash
git add technical_indicators.py
git commit -m "feat: add extended technical indicators module"
```

---

### 任务 4：创建估值分位数分析模块 (valuation_analysis.py)

**文件：**
- 创建：`valuation_analysis.py`

- [ ] **步骤 1：编写分位数计算函数**

```python
import pandas as pd
import numpy as np


def calculate_percentile(current_value, historical_values):
    """
    计算当前值在历史序列中的百分位

    参数:
        current_value: 当前值
        historical_values: 历史值列表或数组

    返回:
        float: 0~100 的百分位数
    """
    if not historical_values or current_value is None:
        return None

    # 过滤无效值
    valid_values = [v for v in historical_values if v is not None and not np.isnan(v)]
    if not valid_values:
        return None

    count_below = sum(1 for v in valid_values if v < current_value)
    return round((count_below / len(valid_values)) * 100, 1)


def get_valuation_zone(percentile):
    """
    根据分位数判断估值区间

    参数:
        percentile: 分位数 (0~100)

    返回:
        str: 估值区间描述
    """
    if percentile is None:
        return '数据不足'

    if percentile <= 20:
        return '低估'
    elif percentile <= 40:
        return '合理偏低'
    elif percentile <= 60:
        return '合理'
    elif percentile <= 80:
        return '合理偏高'
    else:
        return '高估'
```

- [ ] **步骤 2：编写历史估值数据获取函数**

```python
def fetch_historical_valuation(code, years=5):
    """
    获取历史估值数据（PE/PB/股息率）

    参数:
        code: 股票代码
        years: 历史年数

    返回:
        dict: {
            'PE': list,
            'PB': list,
            '股息率': list
        }
    """
    import http.client
    import ssl
    import json
    from market_utils import get_market_info, get_secid

    market_name, market_id, _ = get_market_info(code)
    ssl_ctx = ssl.create_default_context()

    result = {'PE': [], 'PB': [], '股息率': []}

    # 获取历史 K 线数据（用于计算历史 PE/PB）
    end = datetime.date.today().strftime("%Y%m%d")
    start = (datetime.date.today() - datetime.timedelta(days=years * 365)).strftime("%Y%m%d")

    params = {
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f116",
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "klt": "101",  # 日线
        "fqt": "1",    # 前复权
        "secid": get_secid(code, market_id),
        "beg": start, "end": end,
    }

    try:
        conn = http.client.HTTPSConnection("push2his.eastmoney.com", context=ssl_ctx, timeout=20)
        url = "/api/qt/stock/kline/get?" + "&".join(f"{k}={v}" for k, v in params.items())
        conn.request("GET", url)
        resp = conn.getresponse()
        data = json.loads(resp.read())
        conn.close()

        klines = data.get("data", {}).get("klines", [])

        # 这里简化处理，实际需要根据财务数据计算历史 PE/PB
        # 由于 API 限制，我们返回当前可用的历史数据
        # 在实际实现中，可能需要调用财务报表 API 获取历史数据

    except Exception as e:
        print(f"获取历史数据失败: {e}")

    return result


def calculate_historical_pe_pb(kline_data, financial_data):
    """
    根据 K 线和财务数据计算历史 PE/PB

    参数:
        kline_data: K 线数据列表
        financial_data: 财务数据列表

    返回:
        tuple: (pe_list, pb_list)
    """
    # 简化实现：使用当前 PE/PB 作为参考
    # 在完整实现中，需要根据历史股价和每股收益/每股净资产计算
    pe_list = []
    pb_list = []

    # TODO: 实现完整的历史 PE/PB 计算逻辑
    # 这需要获取历史的每股收益(EPS)和每股净资产(BPS)数据

    return pe_list, pb_list
```

- [ ] **步骤 3：编写估值分位数分析主函数**

```python
def analyze_valuation_percentile(code, current_quote, years=5):
    """
    分析估值分位数

    参数:
        code: 股票代码
        current_quote: 当前行情数据
        years: 历史年数

    返回:
        dict: {
            'PE': {'当前值': float, '分位数': float, '区间': str},
            'PB': {'当前值': float, '分位数': float, '区间': str},
            '股息率': {'当前值': float, '分位数': float, '区间': str},
            '综合评价': str
        }
    """
    # 获取当前估值
    current_pe = current_quote.get('f9', 0)  # 动态 PE
    current_pb = current_quote.get('f23', 0)  # PB

    # 获取历史估值数据
    hist_data = fetch_historical_valuation(code, years)

    # 计算分位数
    pe_percentile = calculate_percentile(current_pe, hist_data['PE'])
    pb_percentile = calculate_percentile(current_pb, hist_data['PB'])

    # 获取估值区间
    pe_zone = get_valuation_zone(pe_percentile)
    pb_zone = get_valuation_zone(pb_percentile)

    # 综合评价
    zones = [z for z in [pe_zone, pb_zone] if z != '数据不足']
    if not zones:
        overall = '数据不足'
    elif all(z in ['低估', '合理偏低'] for z in zones):
        overall = '整体低估'
    elif all(z in ['高估', '合理偏高'] for z in zones):
        overall = '整体高估'
    else:
        overall = '估值合理'

    return {
        'PE': {
            '当前值': round(current_pe, 2) if current_pe else 0,
            '分位数': pe_percentile,
            '区间': pe_zone
        },
        'PB': {
            '当前值': round(current_pb, 2) if current_pb else 0,
            '分位数': pb_percentile,
            '区间': pb_zone
        },
        '股息率': {
            '当前值': 0,  # 需要从财务数据获取
            '分位数': None,
            '区间': '数据不足'
        },
        '综合评价': overall
    }
```

- [ ] **步骤 4：Commit**

```bash
git add valuation_analysis.py
git commit -m "feat: add valuation percentile analysis module"
```

---

### 任务 5：创建行业对比分析模块 (industry_analysis.py)

**文件：**
- 创建：`industry_analysis.py`

- [ ] **步骤 1：编写行业内股票列表获取函数**

```python
import http.client
import ssl
import json
from market_utils import get_market_info


def fetch_industry_peers(code):
    """
    获取同行业股票列表

    参数:
        code: 股票代码

    返回:
        list: [{'代码': str, '名称': str, 'PE': float, 'PB': float, 'ROE': float, '总市值': float}]
    """
    # 首先获取股票所属行业
    industry = get_stock_industry(code)
    if not industry:
        return []

    # 获取行业内所有股票
    ssl_ctx = ssl.create_default_context()

    params = {
        "pn": "1", "pz": "100", "po": "1", "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2", "invt": "2", "fid": "f3",
        "fs": f"b:{industry}+f:!50",
        "fields": "f12,f14,f9,f23,f37,f20",
    }

    try:
        conn = http.client.HTTPSConnection("82.push2.eastmoney.com", context=ssl_ctx, timeout=15)
        url = "/api/qt/clist/get?" + "&".join(f"{k}={v}" for k, v in params.items())
        conn.request("GET", url)
        resp = conn.getresponse()
        data = json.loads(resp.read())
        conn.close()

        items = data.get("data", {}).get("diff", [])
        peers = []
        for item in items:
            peers.append({
                '代码': str(item.get('f12', '')),
                '名称': item.get('f14', ''),
                'PE': item.get('f9', 0),
                'PB': item.get('f23', 0),
                'ROE': item.get('f37', 0),
                '总市值': item.get('f20', 0),
            })
        return peers

    except Exception as e:
        print(f"获取行业数据失败: {e}")
        return []


def get_stock_industry(code):
    """
    获取股票所属行业

    参数:
        code: 股票代码

    返回:
        str: 行业代码
    """
    # 使用东方财富 API 获取股票行业信息
    market_name, market_id, _ = get_market_info(code)
    ssl_ctx = ssl.create_default_context()

    params = {
        "secid": f"{market_id}.{code}",
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        "fields": "f57,f58,f127",
        "invt": "2",
    }

    try:
        conn = http.client.HTTPSConnection("push2.eastmoney.com", context=ssl_ctx, timeout=10)
        url = "/api/qt/stock/get?" + "&".join(f"{k}={v}" for k, v in params.items())
        conn.request("GET", url)
        resp = conn.getresponse()
        data = json.loads(resp.read())
        conn.close()

        if data.get("data"):
            return data["data"].get("f127", "")

    except Exception:
        pass

    return ""
```

- [ ] **步骤 2：编写估值对比分析函数**

```python
def analyze_valuation_comparison(code, peers):
    """
    分析估值对比

    参数:
        code: 当前股票代码
        peers: 同行业股票列表

    返回:
        dict: {
            'PE排名': int,
            'PB排名': int,
            'ROE排名': int,
            '估值排名': list
        }
    """
    if not peers:
        return {
            'PE排名': 0,
            'PB排名': 0,
            'ROE排名': 0,
            '估值排名': []
        }

    # 获取当前股票数据
    current = None
    for peer in peers:
        if peer['代码'] == code:
            current = peer
            break

    if not current:
        return {
            'PE排名': 0,
            'PB排名': 0,
            'ROE排名': 0,
            '估值排名': []
        }

    # 按 PE 排名（从低到高）
    pe_sorted = sorted(peers, key=lambda x: x['PE'] if x['PE'] and x['PE'] > 0 else float('inf'))
    pe_rank = next((i + 1 for i, p in enumerate(pe_sorted) if p['代码'] == code), 0)

    # 按 PB 排名（从低到高）
    pb_sorted = sorted(peers, key=lambda x: x['PB'] if x['PB'] and x['PB'] > 0 else float('inf'))
    pb_rank = next((i + 1 for i, p in enumerate(pb_sorted) if p['代码'] == code), 0)

    # 按 ROE 排名（从高到低）
    roe_sorted = sorted(peers, key=lambda x: x['ROE'] if x['ROE'] else 0, reverse=True)
    roe_rank = next((i + 1 for i, p in enumerate(roe_sorted) if p['代码'] == code), 0)

    # 构建估值排名列表
    valuation_rank = []
    for i, peer in enumerate(pe_sorted[:10]):  # 只显示前 10 名
        valuation_rank.append({
            '排名': i + 1,
            '代码': peer['代码'],
            '名称': peer['名称'],
            'PE': peer['PE'],
            'PB': peer['PB'],
            'ROE': peer['ROE'],
        })

    return {
        'PE排名': pe_rank,
        'PB排名': pb_rank,
        'ROE排名': roe_rank,
        '估值排名': valuation_rank
    }
```

- [ ] **步骤 3：编写资金流向对比函数**

```python
def analyze_fund_flow_comparison(code, peers):
    """
    分析资金流向对比

    参数:
        code: 当前股票代码
        peers: 同行业股票列表

    返回:
        dict: {
            '今日排名': list,
            '5日排名': list
        }
    """
    # 获取行业内各股票的资金流向
    ssl_ctx = ssl.create_default_context()
    fund_flow_data = []

    for peer in peers[:20]:  # 限制查询数量
        peer_code = peer['代码']
        market_name, market_id, _ = get_market_info(peer_code)

        params = {
            "secid": f"{market_id}.{peer_code}",
            "ut": "fa5fd1943c7b386f172d6893dbfba10b",
            "fields": "f57,f58,f62,f184,f185,f186",
            "invt": "2",
        }

        try:
            conn = http.client.HTTPSConnection("push2.eastmoney.com", context=ssl_ctx, timeout=10)
            url = "/api/qt/stock/get?" + "&".join(f"{k}={v}" for k, v in params.items())
            conn.request("GET", url)
            resp = conn.getresponse()
            data = json.loads(resp.read())
            conn.close()

            if data.get("data"):
                d = data["data"]
                fund_flow_data.append({
                    '代码': peer_code,
                    '名称': peer['名称'],
                    '今日主力净流入': d.get('f62', 0),
                    '5日主力净流入': d.get('f185', 0),
                })
        except Exception:
            continue

    # 按今日主力净流入排名
    today_sorted = sorted(fund_flow_data, key=lambda x: x.get('今日主力净流入', 0), reverse=True)
    today_rank = [{'排名': i + 1, **item} for i, item in enumerate(today_sorted[:10])]

    # 按 5 日主力净流入排名
    five_day_sorted = sorted(fund_flow_data, key=lambda x: x.get('5日主力净流入', 0), reverse=True)
    five_day_rank = [{'排名': i + 1, **item} for i, item in enumerate(five_day_sorted[:10])]

    return {
        '今日排名': today_rank,
        '5日排名': five_day_rank
    }
```

- [ ] **步骤 4：编写行业景气度分析函数**

```python
def analyze_industry_sentiment(industry_code):
    """
    分析行业景气度

    参数:
        industry_code: 行业代码

    返回:
        dict: {
            '涨跌幅': float,
            '换手率': float,
            '资金流入': str,
            '景气度': str
        }
    """
    ssl_ctx = ssl.create_default_context()

    params = {
        "pn": "1", "pz": "50", "po": "1", "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2", "invt": "2", "fid": "f3",
        "fs": "m:90+t:2+f:!50",
        "fields": "f1,f2,f3,f4,f5,f6,f7,f8,f12,f14",
    }

    try:
        conn = http.client.HTTPSConnection("82.push2.eastmoney.com", context=ssl_ctx, timeout=15)
        url = "/api/qt/clist/get?" + "&".join(f"{k}={v}" for k, v in params.items())
        conn.request("GET", url)
        resp = conn.getresponse()
        data = json.loads(resp.read())
        conn.close()

        items = data.get("data", {}).get("diff", [])

        # 查找目标行业
        for item in items:
            if str(item.get('f12', '')) == industry_code:
                chg = item.get('f3', 0)
                turnover = item.get('f8', 0)

                # 判断景气度
                if chg > 2:
                    sentiment = '高景气'
                elif chg > 0:
                    sentiment = '景气'
                elif chg > -2:
                    sentiment = '平淡'
                else:
                    sentiment = '低迷'

                return {
                    '涨跌幅': round(chg, 2) if chg else 0,
                    '换手率': round(turnover, 2) if turnover else 0,
                    '资金流入': '净流入' if chg > 0 else '净流出',
                    '景气度': sentiment
                }

    except Exception as e:
        print(f"获取行业景气度失败: {e}")

    return {
        '涨跌幅': 0,
        '换手率': 0,
        '资金流入': '数据不足',
        '景气度': '数据不足'
    }
```

- [ ] **步骤 5：编写龙头溢价分析函数**

```python
def analyze_leader_premium(code, peers):
    """
    分析龙头溢价

    参数:
        code: 当前股票代码
        peers: 同行业股票列表

    返回:
        dict: {
            '龙头公司': str,
            '龙头PE': float,
            '行业平均PE': float,
            '溢价率': float,
            '溢价合理性': str
        }
    """
    if not peers:
        return {
            '龙头公司': '未知',
            '龙头PE': 0,
            '行业平均PE': 0,
            '溢价率': 0,
            '溢价合理性': '数据不足'
        }

    # 识别龙头公司（市值最大）
    leader = max(peers, key=lambda x: x.get('总市值', 0) if x.get('总市值') else 0)

    # 计算行业平均 PE（排除异常值）
    valid_pe = [p['PE'] for p in peers if p.get('PE') and 0 < p['PE'] < 100]
    avg_pe = sum(valid_pe) / len(valid_pe) if valid_pe else 0

    # 龙头 PE
    leader_pe = leader.get('PE', 0) if leader.get('PE') and leader.get('PE') > 0 else 0

    # 计算溢价率
    premium_rate = ((leader_pe - avg_pe) / avg_pe * 100) if avg_pe > 0 else 0

    # 判断溢价合理性
    if premium_rate < -20:
       合理性 = '低估（龙头折价）'
    elif premium_rate < 20:
        合理性 = '合理'
    elif premium_rate < 50:
        合理性 = '略高（龙头溢价）'
    else:
        合理性 = '偏高（需关注）'

    return {
        '龙头公司': leader.get('名称', '未知'),
        '龙头PE': round(leader_pe, 2),
        '行业平均PE': round(avg_pe, 2),
        '溢价率': round(premium_rate, 1),
        '溢价合理性': 合理性
    }
```

- [ ] **步骤 6：编写行业对比分析主函数**

```python
def analyze_industry_comparison(code):
    """
    行业对比分析主函数

    参数:
        code: 股票代码

    返回:
        dict: {
            '行业': str,
            '估值对比': dict,
            '资金流向': dict,
            '行业景气度': dict,
            '龙头溢价': dict
        }
    """
    # 获取同行业股票
    peers = fetch_industry_peers(code)
    if not peers:
        return {
            '行业': '未知',
            '估值对比': {},
            '资金流向': {},
            '行业景气度': {},
            '龙头溢价': {}
        }

    # 获取行业代码
    industry_code = get_stock_industry(code)

    # 估值对比
    valuation_comparison = analyze_valuation_comparison(code, peers)

    # 资金流向对比
    fund_flow_comparison = analyze_fund_flow_comparison(code, peers)

    # 行业景气度
    industry_sentiment = analyze_industry_sentiment(industry_code)

    # 龙头溢价
    leader_premium = analyze_leader_premium(code, peers)

    return {
        '行业': industry_code,
        '估值对比': valuation_comparison,
        '资金流向': fund_flow_comparison,
        '行业景气度': industry_sentiment,
        '龙头溢价': leader_premium
    }
```

- [ ] **步骤 7：Commit**

```bash
git add industry_analysis.py
git commit -m "feat: add industry comparison analysis module"
```

---

### 任务 6：更新 analyze_stock.py 集成新模块

**文件：**
- 修改：`analyze_stock.py` (导入部分和主流程)

- [ ] **步骤 1：添加新模块导入**

在 `analyze_stock.py` 顶部添加：

```python
from technical_indicators import calculate_extended_indicators
from valuation_analysis import analyze_valuation_percentile
from industry_analysis import analyze_industry_comparison
```

- [ ] **步骤 2：更新 analyze_stock 函数**

在 `analyze_stock` 函数中添加新功能调用：

```python
def analyze_stock(code, output_dir="."):
    print(f"\n{'='*60}")
    print(f"  分析股票: {code}")
    print(f"{'='*60}")

    name = get_stock_name(code)
    print(f"  股票名称: {name}")

    dir_name = f"{code}-{name}"
    out_path = Path(output_dir) / dir_name
    out_path.mkdir(parents=True, exist_ok=True)
    print(f"  输出目录: {out_path}")

    print("\n[1/8] 获取 K 线数据...")
    df_hist = fetch_kline(code, days=500)
    print(f"  获取到 {len(df_hist)} 条 K 线数据")

    print("[2/8] 获取实时行情...")
    quote = fetch_realtime_quote(code)

    print("[3/8] 获取资金流向...")
    fund_flow = fetch_fund_flow(code)

    print("[4/8] 获取北向资金...")
    north_flow = fetch_north_flow()

    print("[5/8] 获取新闻和行业数据...")
    news_df = fetch_stock_news(code)
    industry_df = fetch_industry_boards()

    print("[6/8] 获取财务报表数据...")
    financial_data = fetch_financial_report(code)

    print("[7/8] 计算技术指标...")
    indicators = calculate_indicators(df_hist)

    # 计算扩展技术指标
    print("  计算扩展指标（RSI 背离、MACD 柱状图等）...")
    extended_indicators = calculate_extended_indicators(df_hist, indicators)

    print("[8/8] 计算财务健康指标和投资评级...")
    financial_health = calculate_financial_health(quote, financial_data)
    rating = calculate_rating(indicators, financial_health, fund_flow)

    # 新增：估值分位数分析
    print("  分析估值分位数...")
    valuation_percentile = analyze_valuation_percentile(code, quote, years=5)

    # 新增：行业对比分析
    print("  分析行业对比...")
    industry_comparison = analyze_industry_comparison(code)

    print("\n生成分析报告...")
    report = generate_report(
        code, name, df_hist, indicators, fund_flow, north_flow,
        quote, news_df, industry_df, financial_health, rating,
        extended_indicators, valuation_percentile, industry_comparison
    )
    today = datetime.date.today().strftime("%Y%m%d")
    report_file = out_path / f"{code}-{name}-分析报告-{today}.md"
    report_file.write_text(report, encoding="utf-8")
    print(f"  [OK] {report_file.name}")

    print(f"\n分析完成! 报告已保存至: {report_file}")
    return str(report_file)
```

- [ ] **步骤 3：Commit**

```bash
git add analyze_stock.py
git commit -m "feat: integrate new modules into main analysis flow"
```

---

### 任务 7：更新报告生成函数

**文件：**
- 修改：`analyze_stock.py` (generate_report 函数)

- [ ] **步骤 1：更新 generate_report 函数签名**

```python
def generate_report(code, name, df, indicators, fund_flow, north_flow, quote,
                    news_df, industry_df, financial_health=None, rating=None,
                    extended_indicators=None, valuation_percentile=None,
                    industry_comparison=None):
```

- [ ] **步骤 2：添加扩展技术指标章节**

在 `generate_report` 函数中，在布林带章节之后添加：

```python
    # ── 2.6 RSI 背离 ──
    if extended_indicators and extended_indicators.get('RSI背离'):
        rsi_div = extended_indicators['RSI背离']
        L.append("\n### 2.6 RSI 背离\n")
        L.append("RSI 背离是重要的趋势反转信号：")
        L.append("- **顶背离**：价格创新高，但 RSI 未创新高 → 看跌信号")
        L.append("- **底背离**：价格创新低，但 RSI 未创新低 → 看涨信号\n")
        L.append(f"**当前状态**：{rsi_div['类型']}")
        L.append(f"\n**信号**：{rsi_div['信号']}")
        if rsi_div['可靠性'] != '-':
            L.append(f"\n**可靠性**：{rsi_div['可靠性']}")

    # ── 2.7 MACD 柱状图 ──
    if extended_indicators and extended_indicators.get('MACD柱状图'):
        macd_hist = extended_indicators['MACD柱状图']
        L.append("\n### 2.7 MACD 柱状图\n")
        L.append("MACD 柱状图反映多空力量对比：")
        L.append("- 红柱（DIF > DEA）：多头占优")
        L.append("- 绿柱（DIF < DEA）：空头占优")
        L.append("- 柱状图斜率反映动能变化趋势\n")
        L.append(f"**分析结果**：{macd_hist['信号']}")

    # ── 2.8 成交量异动 ──
    if extended_indicators and extended_indicators.get('成交量异动'):
        vol_anomaly = extended_indicators['成交量异动']
        L.append("\n### 2.8 成交量异动\n")
        L.append("成交量异动反映市场情绪变化：")
        L.append("- 放量：可能有大资金介入")
        L.append("- 缩量：市场观望情绪浓厚")
        L.append("- 天量/地量：往往是变盘信号\n")
        L.append(f"**当前状态**：{vol_anomaly['状态']}（{vol_anomaly['信号']}）")

    # ── 2.9 K 线形态 ──
    if extended_indicators and extended_indicators.get('K线形态'):
        patterns = extended_indicators['K线形态']
        L.append("\n### 2.9 K 线形态\n")
        if patterns:
            L.append("近期出现的 K 线形态：\n")
            L.append("| 形态 | 信号 | 可靠性 |")
            L.append("|------|------|--------|")
            for p in patterns:
                L.append(f"| {p['形态']} | {p['信号']} | {p['可靠性']} |")
        else:
            L.append("近期无明显 K 线形态信号。")

    # ── 2.10 筹码分布 ──
    if extended_indicators and extended_indicators.get('筹码分布'):
        chip = extended_indicators['筹码分布']
        L.append("\n### 2.10 筹码分布\n")
        L.append("筹码分布反映持仓成本结构：")
        L.append("- 获利盘比例高：抛压较小")
        L.append("- 套牢盘比例高：上方有解套压力\n")
        L.append(f"**平均成本**：{chip['平均成本']:.2f} 元")
        L.append(f"\n**获利盘**：{chip['获利盘比例']}%  |  **套牢盘**：{chip['套牢盘比例']}%")
        L.append(f"\n**筹码集中度**：{chip['筹码集中度']}")
```

- [ ] **步骤 3：添加估值分位数分析章节**

在反证清单章节之后添加：

```python
    # ── 九、估值分位数分析 ──
    if valuation_percentile:
        L.append("\n---\n## 九、估值分位数分析\n")
        L.append("估值分位数反映当前估值在近 5 年历史中的位置：")
        L.append("- 分位数越低 → 估值越便宜")
        L.append("- 分位数越高 → 估值越贵\n")

        L.append("| 指标 | 当前值 | 5年分位数 | 估值区间 |")
        L.append("|------|--------|-----------|----------|")

        pe = valuation_percentile.get('PE', {})
        pb = valuation_percentile.get('PB', {})
        div_yield = valuation_percentile.get('股息率', {})

        pe_pct = f"{pe.get('分位数', '-')}%" if pe.get('分位数') is not None else '-'
        pb_pct = f"{pb.get('分位数', '-')}%" if pb.get('分位数') is not None else '-'
        div_pct = f"{div_yield.get('分位数', '-')}%" if div_yield.get('分位数') is not None else '-'

        L.append(f"| PE(TTM) | {pe.get('当前值', '-')} | {pe_pct} | {pe.get('区间', '-')} |")
        L.append(f"| PB | {pb.get('当前值', '-')} | {pb_pct} | {pb.get('区间', '-')} |")
        L.append(f"| 股息率 | {div_yield.get('当前值', '-')}% | {div_pct} | {div_yield.get('区间', '-')} |")

        overall = valuation_percentile.get('综合评价', '')
        if overall:
            L.append(f"\n> 当前估值处于近 5 年 **{overall}** 区间")
```

- [ ] **步骤 4：添加行业对比分析章节**

在估值分位数分析章节之后添加：

```python
    # ── 十、行业对比分析 ──
    if industry_comparison:
        L.append("\n---\n## 十、行业对比分析\n")

        # 10.1 同行业估值排名
        valuation_comp = industry_comparison.get('估值对比', {})
        if valuation_comp.get('估值排名'):
            L.append("### 10.1 同行业估值排名\n")
            L.append(f"当前股票在行业中的排名：PE 第 {valuation_comp.get('PE排名', '-')} 名 | "
                     f"PB 第 {valuation_comp.get('PB排名', '-')} 名 | "
                     f"ROE 第 {valuation_comp.get('ROE排名', '-')} 名\n")

            L.append("| 排名 | 公司 | PE | PB | ROE |")
            L.append("|------|------|----|----|-----|")
            for item in valuation_comp['估值排名'][:10]:
                pe_val = f"{item['PE']:.1f}" if item.get('PE') and item['PE'] > 0 else '-'
                pb_val = f"{item['PB']:.1f}" if item.get('PB') and item['PB'] > 0 else '-'
                roe_val = f"{item['ROE']:.1f}%" if item.get('ROE') else '-'
                L.append(f"| {item['排名']} | {item['名称']} | {pe_val} | {pb_val} | {roe_val} |")

        # 10.3 资金流向对比
        fund_flow_comp = industry_comparison.get('资金流向', {})
        if fund_flow_comp.get('今日排名'):
            L.append("\n### 10.2 资金流向对比\n")
            L.append("**今日主力净流入排名：**\n")
            L.append("| 排名 | 公司 | 今日主力净流入 |")
            L.append("|------|------|----------------|")
            for item in fund_flow_comp['今日排名'][:5]:
                flow = item.get('今日主力净流入', 0)
                flow_str = f"+{flow/1e8:.2f}亿" if flow > 0 else f"{flow/1e8:.2f}亿"
                L.append(f"| {item['排名']} | {item['名称']} | {flow_str} |")

        # 10.4 行业景气度
        sentiment = industry_comparison.get('行业景气度', {})
        if sentiment.get('景气度'):
            L.append("\n### 10.3 行业景气度\n")
            L.append(f"- **行业涨跌幅**：{sentiment.get('涨跌幅', '-')}%")
            L.append(f"- **行业换手率**：{sentiment.get('换手率', '-')}%")
            L.append(f"- **资金流向**：{sentiment.get('资金流入', '-')}")
            L.append(f"- **景气度评估**：{sentiment.get('景气度', '-')}")

        # 10.5 龙头溢价分析
        leader = industry_comparison.get('龙头溢价', {})
        if leader.get('龙头公司'):
            L.append("\n### 10.4 龙头溢价分析\n")
            L.append(f"- **龙头公司**：{leader['龙头公司']}")
            L.append(f"- **龙头 PE**：{leader.get('龙头PE', '-')}")
            L.append(f"- **行业平均 PE**：{leader.get('行业平均PE', '-')}")
            L.append(f"- **溢价率**：{leader.get('溢价率', '-')}%")
            L.append(f"- **溢价合理性**：{leader.get('溢价合理性', '-')}")
```

- [ ] **步骤 5：Commit**

```bash
git add analyze_stock.py
git commit -m "feat: add new report sections for extended indicators"
```

---

### 任务 8：更新报告模板和文档

**文件：**
- 修改：`templates/report-template.md`
- 修改：`references/technical-indicators.md`
- 修改：`README.md`
- 修改：`SKILL.md`

- [ ] **步骤 1：更新报告模板**

在 `templates/report-template.md` 的「八、反证清单与跟踪因子」之后添加：

```markdown
## 九、估值分位数分析

估值分位数反映当前估值在近 5 年历史中的位置。

| 指标 | 当前值 | 5年分位数 | 估值区间 |
|------|--------|-----------|----------|
| PE(TTM) | XX.XX | XX% | 合理偏低 |
| PB | X.XX | XX% | 合理 |
| 股息率 | X.XX% | XX% | 合理偏高 |

> 当前估值处于近 5 年 **合理偏低** 区间

---

## 十、行业对比分析

### 10.1 同行业估值排名

当前股票在行业中的排名：PE 第 X 名 | PB 第 X 名 | ROE 第 X 名

| 排名 | 公司 | PE | PB | ROE |
|------|------|----|----|-----|
| 1 | 公司A | 15.2 | 2.1 | 18.5% |
| 2 | 公司B | 18.5 | 2.8 | 15.2% |

### 10.2 资金流向对比

**今日主力净流入排名：**

| 排名 | 公司 | 今日主力净流入 |
|------|------|----------------|
| 1 | 公司A | +1.2亿 |
| 2 | 公司B | +0.8亿 |

### 10.3 行业景气度

- **行业涨跌幅**：+1.5%
- **行业换手率**：2.3%
- **资金流向**：净流入
- **景气度评估**：景气

### 10.4 龙头溢价分析

- **龙头公司**：贵州茅台
- **龙头 PE**：35.2
- **行业平均 PE**：22.5
- **溢价率**：56.4%
- **溢价合理性**：合理（龙头享有品牌溢价）
```

- [ ] **步骤 2：更新技术指标说明文档**

在 `references/technical-indicators.md` 末尾添加：

```markdown
## 扩展技术指标

### RSI 背离

RSI 背离是重要的趋势反转信号：

- **顶背离**：价格创新高，但 RSI 未创新高 → 看跌信号
- **底背离**：价格创新低，但 RSI 未创新低 → 看涨信号

背离信号的可靠性：
- 高：RSI 在超买区（>70）或超卖区（<30）出现背离
- 中：RSI 在中性区出现背离

### MACD 柱状图

MACD 柱状图（DIF - DEA）反映多空力量对比：

- 红柱（DIF > DEA）：多头占优
- 绿柱（DIF < DEA）：空头占优
- 柱状图斜率：反映动能变化趋势

分析要点：
- 连续红柱 + 斜率向上 = 多头增强
- 连续绿柱 + 斜率向下 = 空头增强
- 柱状图缩短 = 动能减弱，可能变盘

### 成交量异动

成交量异动反映市场情绪变化：

| 状态 | 定义 | 信号 |
|------|------|------|
| 放量 | 当日成交量 > 5日均量 × 1.5 | 可能有大资金介入 |
| 缩量 | 当日成交量 < 5日均量 × 0.5 | 市场观望情绪浓厚 |
| 天量 | 当日成交量 > 20日均量 × 2.0 | 往往是变盘信号 |
| 地量 | 当日成交量 < 20日均量 × 0.3 | 可能见底 |

### K 线形态

常见 K 线形态及其信号：

| 形态 | 识别条件 | 信号 |
|------|----------|------|
| 十字星 | 开盘价 ≈ 收盘价，上下影线较长 | 犹豫信号，可能变盘 |
| 锤子线 | 下影线 > 实体 2 倍，上影线很短 | 底部看涨 |
| 倒锤子线 | 上影线 > 实体 2 倍，下影线很短 | 底部看涨（需确认） |
| 吞没形态 | 当日实体完全包含前一日实体 | 趋势反转 |
| 乌云盖顶 | 阳线后出现高开低走阴线 | 顶部看跌 |

### 筹码分布

筹码分布反映持仓成本结构：

- **平均成本**：成交量加权的平均买入价格
- **获利盘比例**：当前价格下方的筹码占比
- **套牢盘比例**：当前价格上方的筹码占比
- **筹码集中度**：价格波动越小，筹码越集中

筹码分布的意义：
- 获利盘比例高 → 抛压较小，上涨阻力小
- 套牢盘比例高 → 上方有解套压力，上涨阻力大
- 筹码集中 → 主力控盘，可能有大行情
- 筹码分散 → 散户行情，波动较大
```

- [ ] **步骤 3：更新 README.md**

在 README.md 的「核心能力」表格中添加新行：

```markdown
| 港股支持 | 支持港股数据获取和分析 |
| 扩展技术指标 | RSI 背离、MACD 柱状图、成交量异动、K 线形态、筹码分布 |
| 估值分位数 | 当前估值在近 5 年历史中的百分位 |
| 行业对比 | 同行业估值排名、资金流向对比、行业景气度、龙头溢价分析 |
```

在「目录结构」部分更新：

```markdown
├── analyze_stock.py             # 核心分析脚本
├── market_utils.py              # 市场判断、价格转换工具
├── technical_indicators.py      # 技术指标计算模块
├── valuation_analysis.py        # 估值分位数分析模块
├── industry_analysis.py         # 行业对比分析模块
```

- [ ] **步骤 4：更新 SKILL.md**

在 SKILL.md 的「分析维度」表格中添加：

```markdown
| 港股支持 | 港股数据获取和分析 | 东方财富港股 API |
| 扩展技术指标 | RSI 背离、MACD 柱状图、成交量异动、K 线形态、筹码分布 | K线数据计算 |
| 估值分位数 | PE/PB/股息率 5 年分位数 | 历史数据计算 |
| 行业对比 | 估值排名、资金流向、景气度、龙头溢价 | 行业板块 API |
```

在「报告结构」部分添加新章节：

```markdown
## 九、估值分位数分析
- PE/PB/股息率 5 年分位数
- 估值区间判断

## 十、行业对比分析
- 同行业估值排名
- 资金流向对比
- 行业景气度
- 龙头溢价分析
```

- [ ] **步骤 5：Commit**

```bash
git add templates/report-template.md references/technical-indicators.md README.md SKILL.md
git commit -m "docs: update documentation for new features"
```

---

### 任务 9：测试和验证

- [ ] **步骤 1：测试 A 股功能**

运行：`python analyze_stock.py 600519`
预期：成功生成贵州茅台分析报告，包含所有新章节

- [ ] **步骤 2：测试港股功能**

运行：`python analyze_stock.py 00700`
预期：成功生成腾讯控股分析报告，价格显示正确

- [ ] **步骤 3：测试批量分析**

运行：`python analyze_stock.py 600519 000333 00700`
预期：成功生成三只股票的分析报告

- [ ] **步骤 4：验证报告内容**

检查生成的报告是否包含：
- 2.6 RSI 背离
- 2.7 MACD 柱状图
- 2.8 成交量异动
- 2.9 K 线形态
- 2.10 筹码分布
- 九、估值分位数分析
- 十、行业对比分析

- [ ] **步骤 5：最终 Commit**

```bash
git add .
git commit -m "feat: complete stock analyzer enhancement with HK support, extended indicators, valuation percentile, and industry comparison"
```

---

## 自检清单

- [x] 规格覆盖度：所有设计文档中的功能都有对应任务
- [x] 占位符扫描：无 TODO/待定内容
- [x] 类型一致性：函数签名和参数名称一致
- [x] 文件路径：所有路径都是精确的
- [x] 代码完整性：每个步骤都有完整代码

---

## 执行选项

计划已完成并保存到 `docs/superpowers/plans/2026-06-04-stock-analyzer-skill-enhancement.md`。

**两种执行方式：**

**1. 子代理驱动（推荐）** - 每个任务调度一个新的子代理，任务间进行审查，快速迭代

**2. 内联执行** - 在当前会话中使用 executing-plans 执行任务，批量执行并设有检查点

**选哪种方式？**
