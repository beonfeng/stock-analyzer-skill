# API 参考文档

## 概述

Stock Analyzer 使用东方财富 API 获取股票数据。本文档描述了各个 API 的用途和返回数据格式。

## API 列表

### 1. K 线数据 API

**用途**：获取股票历史 K 线数据

**API 地址**：`push2his.eastmoney.com/api/qt/stock/kline/get`

**请求参数**：

| 参数 | 说明 | 示例值 |
|------|------|--------|
| fields1 | 基本字段 | f1,f2,f3,f4,f5,f6 |
| fields2 | 详细字段 | f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f116 |
| ut | 用户标识 | 7eea3edcaed734bea9cbfc24409ed989 |
| klt | K线类型 | 101（日K） |
| fqt | 复权类型 | 1（前复权） |
| secid | 证券ID | 1.600519（上海）或 0.000333（深圳） |
| beg | 开始日期 | 20250101 |
| end | 结束日期 | 20260604 |

**返回数据**：

```json
{
  "data": {
    "klines": [
      "2025-01-02,1800.00,1820.00,1830.00,1790.00,50000,900000000,2.22,1.11,20.00,0.40"
    ]
  }
}
```

**K 线数据格式**：

| 字段 | 说明 |
|------|------|
| 日期 | YYYY-MM-DD |
| 开盘 | 开盘价 |
| 收盘 | 收盘价 |
| 最高 | 最高价 |
| 最低 | 最低价 |
| 成交量 | 成交股数 |
| 成交额 | 成交金额 |
| 振幅 | 振幅百分比 |
| 涨跌幅 | 涨跌幅百分比 |
| 涨跌额 | 涨跌金额 |
| 换手率 | 换手率百分比 |

### 2. 实时行情 API

**用途**：获取股票实时行情和财务指标

**API 地址**：
- 列表查询：`82.push2.eastmoney.com/api/qt/clist/get`
- 单只查询：`push2.eastmoney.com/api/qt/stock/get`

**请求参数（列表查询）**：

| 参数 | 说明 | 示例值 |
|------|------|--------|
| pn | 页码 | 1 |
| pz | 每页数量 | 5000 |
| po | 排序方向 | 1 |
| np | 页数 | 1 |
| ut | 用户标识 | bd1d9ddb04089700cf9c27f6f7426281 |
| fltt | 浮点类型 | 2 |
| invt | 投资类型 | 2 |
| fid | 排序字段 | f12 |
| fs | 市场过滤 | m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048 |
| fields | 返回字段 | f1,f2,f3,... |

**返回字段说明**：

| 字段 | 说明 | 处理方式 |
|------|------|----------|
| f14 | 股票名称 | 直接使用 |
| f2 | 最新价 | 除以100 |
| f3 | 涨跌幅 | 除以100 |
| f9 | 市盈率(动态) | 除以100 |
| f23 | 市净率 | 除以100 |
| f20 | 总市值 | 直接使用（元） |
| f21 | 流通市值 | 直接使用（元） |
| f37 | ROE | 直接使用（百分比） |
| f49 | 毛利率 | 直接使用（百分比） |
| f40 | 营收同比 | 直接使用 |
| f41 | 净利润同比 | 直接使用（百分比） |
| f34 | 资产负债率 | 直接使用（百分比） |

### 3. 资金流向 API

**用途**：获取个股资金流向数据

**API 地址**：`push2.eastmoney.com/api/qt/clist/get`

**请求参数**：

| 参数 | 说明 | 示例值 |
|------|------|--------|
| fid | 排序字段 | f62（今日）、f267（3日）、f164（5日）、f174（10日） |
| po | 排序方向 | 1 |
| pz | 每页数量 | 5000 |
| pn | 页码 | 1 |
| np | 页数 | 1 |
| fltt | 浮点类型 | 2 |
| invt | 投资类型 | 2 |
| ut | 用户标识 | b2884a393a59ad64002292a3e90d46a5 |
| fs | 市场过滤 | m:0+t:6+f:!2,... |
| fields | 返回字段 | f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f124 |

**返回字段说明**：

| 字段 | 说明 |
|------|------|
| f62 | 主力净流入 |
| f184 | 主力净流入占比 |
| f66 | 超大单净流入 |
| f69 | 超大单净流入占比 |
| f72 | 大单净流入 |
| f75 | 大单净流入占比 |
| f78 | 中单净流入 |
| f81 | 中单净流入占比 |
| f84 | 小单净流入 |
| f87 | 小单净流入占比 |

### 4. 北向资金 API

**用途**：获取北向资金（沪股通、深股通）数据

**API 地址**：`push2his.eastmoney.com/api/qt/stock/kline/get`

**请求参数**：

| 参数 | 说明 | 示例值 |
|------|------|--------|
| fields1 | 基本字段 | f1,f2,f3,f4 |
| fields2 | 详细字段 | f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63 |
| klt | K线类型 | 101（日K） |
| lmt | 数据限制 | 10 |
| ut | 用户标识 | b2884a393a59ad64002292a3e90d46a5 |
| secid | 证券ID | 1.000300（沪股通）或 0.399001（深股通） |

### 5. 新闻数据 API

**用途**：获取个股新闻

**API 地址**：`np-listapi.eastmoney.com/api/news/get`

**请求参数**：

| 参数 | 说明 | 示例值 |
|------|------|--------|
| page_index | 页码 | 1 |
| page_size | 每页数量 | 20 |
| columns | 返回列 | title,source,publish_date |
| source | 来源 | web |
| client | 客户端 | web |
| biz | 业务 | web_news_col |
| column | 栏目 | 350 |
| filter | 过滤条件 | (code="000333") |

### 6. 行业数据 API

**用途**：获取行业板块数据

**API 地址**：`82.push2.eastmoney.com/api/qt/clist/get`

**请求参数**：

| 参数 | 说明 | 示例值 |
|------|------|--------|
| pn | 页码 | 1 |
| pz | 每页数量 | 50 |
| po | 排序方向 | 1 |
| np | 页数 | 1 |
| ut | 用户标识 | bd1d9ddb04089700cf9c27f6f7426281 |
| fltt | 浮点类型 | 2 |
| invt | 投资类型 | 2 |
| fid | 排序字段 | f3 |
| fs | 市场过滤 | m:90+t:2+f:!50 |
| fields | 返回字段 | f1,f2,f3,... |

### 7. 财务报表 API

**用途**：获取财务报表数据

**API 地址**：`datacenter.eastmoney.com/api/data/get`

**请求参数**：

| 参数 | 说明 | 示例值 |
|------|------|--------|
| type | 类型 | 0 |
| sty | 样式 | APP_F10_FinanceSumFinance |
| filter | 过滤条件 | (SECUCODE="000333.SZ") |
| p | 页码 | 1 |
| ps | 每页数量 | 5 |
| sr | 排序方向 | -1 |
| st | 排序字段 | REPORT_DATE |
| source | 来源 | HSF10 |
| client | 客户端 | PC |

## 错误处理

### HTTP 错误

- 自动重试最多 8 次
- 每次重试间隔递增（2秒 + 0.5秒 × 尝试次数）
- 最终失败抛出异常

### 数据异常

- 缺失字段返回默认值 0
- 非数字值安全转换为 0
- 空字符串返回 "-"

## 使用限制

- **请求频率**：建议控制批量股票数量，避免请求过于频繁
- **超时时间**：15 秒
- **代理**：绕过系统代理，直连 API

## 代码示例

### Python 示例

```python
import http.client
import json
import ssl

# 创建 SSL 上下文
ssl_ctx = ssl.create_default_context()

# 获取 K 线数据
def fetch_kline(code, days=500):
    market = 1 if code.startswith("6") else 0
    params = {
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f116",
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "klt": "101", "fqt": "1",
        "secid": f"{market}.{code}",
        "beg": "20250101", "end": "20260604",
    }
    
    conn = http.client.HTTPSConnection("push2his.eastmoney.com", context=ssl_ctx, timeout=15)
    url = "/api/qt/stock/kline/get?" + "&".join(f"{k}={v}" for k, v in params.items())
    conn.request("GET", url)
    resp = conn.getresponse()
    data = json.loads(resp.read())
    conn.close()
    
    return data.get("data", {}).get("klines", [])
```

## 更新日志

| 版本 | 日期 | 更新内容 |
|------|------|----------|
| v1.0 | 2026-06-04 | 初始版本，支持 K 线、行情、资金流向、北向资金、新闻、行业、财务报表 |
