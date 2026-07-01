#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据源可用性检查 & 报告数据校验模块

职责：
1. 分析启动前：预检所有数据源，缓存可用性结果
2. 分析过程中：智能路由——跳过已知不可用的源，避免 120s 超时等待
3. 报告生成后：扫描 Markdown 报告，检测数据缺失/异常并汇总

使用方式：
    from .data_validator import run_preflight, is_host_available, validate_report

    # 启动时预检
    health = run_preflight()

    # 查询某个数据源是否可用
    if is_host_available("push2.eastmoney.com"):
        ...  # 使用东方财富 push2

    # 报告生成后校验
    issues = validate_report("分析报告/600276-恒瑞医药-分析报告-20260701.md")
"""

import os
import re
import time
import json
import http.client

# ============================================================
# 数据源定义
# ============================================================

# 每个分析维度对应的数据源及测试端点
_SOURCE_REGISTRY = {
    "实时行情": {
        "primary": "push2.eastmoney.com",
        "test_path": "/api/qt/stock/get?secid=1.600519&fields=f43,f57,f58",
        "fallbacks": ["腾讯财经", "新浪财经"],
        "impact": "高 — 影响 PE/PB/市值/价格",
        "data_fields": ["f2(最新价)", "f9(PE)", "f23(PB)", "f20(总市值)", "f21(流通市值)"],
    },
    "财务指标": {
        "primary": "datacenter.eastmoney.com",
        "test_path": "/api/data/get?type=RPT_F10_FINANCE_MAINFINADATA&sty=ALL&filter=(SECUCODE=%22600519.SH%22)&p=1&ps=1&sr=-1&st=REPORT_DATE&source=HSF10&client=PC",
        "fallbacks": ["腾讯(datacenter补全)"],
        "impact": "高 — 影响 ROE/毛利率/净利增速/负债率/EPS",
        "data_fields": ["f37(ROE)", "f49(毛利率)", "f40(营收)", "f41(净利增速)", "f34(负债率)", "f115(EPS)"],
    },
    "K线数据": {
        "primary": "push2his.eastmoney.com",
        "test_path": "/api/qt/stock/kline/get?secid=1.600519&fields1=f1,f2&fields2=f51&klt=101&fqt=1&end=20500101&lmt=1",
        "fallbacks": ["腾讯K线", "新浪K线", "AKShare"],
        "impact": "高 — 影响所有技术指标计算",
        "data_fields": ["开盘/收盘/最高/最低/成交量"],
    },
    "资金流向": {
        "primary": "push2his.eastmoney.com",
        "test_path": "/api/qt/stock/fflow/daykline/get?secid=1.600519&ut=fa5fd1943c7b386f172d6893dbfba10b&fields1=f1,f2&fields2=f51,f52&klt=101&fqt=1&end=20500101&lmt=1",
        "fallbacks": ["腾讯(外盘-内盘估算)"],
        "impact": "中 — 影响主力资金分析，多日数据降级",
        "data_fields": ["主力/超大单/大单/中单/小单净流入"],
    },
    "板块资金全景": {
        "primary": "push2.eastmoney.com",
        "test_path": "/api/qt/clist/get?pn=1&pz=1&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f12&fs=m:90+t:2&fields=f2,f3,f12,f14",
        "fallbacks": ["无 — 缺失时章节显示暂无数据"],
        "impact": "低 — 仅板块资金全景章节受影响",
        "data_fields": ["板块排名/主力净流入"],
    },
    "逐笔成交": {
        "primary": "push2.eastmoney.com",
        "test_path": "/api/qt/stock/details/get?secid=1.600519&field1=f1,f2&field2=f51,f52&pos=-0&lmt=1",
        "fallbacks": ["无 — 缺失时章节显示暂无数据"],
        "impact": "低 — 仅逐笔成交章节受影响",
        "data_fields": ["逐笔交易明细"],
    },
    "研报公告": {
        "primary": "reportapi.eastmoney.com",
        "test_path": "/report/list?cb=test&industryCode=0&pageSize=1&stockCode=600519",
        "fallbacks": ["AKShare"],
        "impact": "低 — 影响新闻动态章节",
        "data_fields": ["研报标题/机构/日期"],
    },
    "公司概况": {
        "primary": "datacenter.eastmoney.com",
        "test_path": "/api/data/get?type=RPT_F10_FN_MAINOP&sty=ALL&filter=(SECUCODE=%22600519.SH%22)&p=1&ps=1&sr=-1&st=REPORT_DATE&source=HSF10&client=PC",
        "fallbacks": ["腾讯"],
        "impact": "中 — 影响主营业务构成/股权结构",
        "data_fields": ["主营业务/股东"],
    },
}


def _quick_connect(host, path, timeout=6):
    """快速连通性测试，返回 (ok, status_code_or_error)"""
    conn = None
    try:
        conn = http.client.HTTPSConnection(host, timeout=timeout)
        conn.request("GET", path, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })
        resp = conn.getresponse()
        resp.read()  # 消费响应体
        return True, resp.status
    except Exception as e:
        msg = str(e)
        if len(msg) > 60:
            msg = msg[:57] + "..."
        return False, msg
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


# 全局健康缓存
_health_cache = {}
_last_health_check = 0
_HEALTH_TTL = 300  # 缓存有效期 5 分钟


def run_preflight(force=False):
    """预检所有数据源可用性，缓存结果。

    Returns:
        dict: {host: {"ok": bool, "status": str/int, "checked_at": float}}
    """
    global _health_cache, _last_health_check

    now = time.time()
    if not force and _health_cache and (now - _last_health_check) < _HEALTH_TTL:
        return _health_cache

    print("  [预检] 检测数据源可用性...")

    # 收集所有需要检测的 host
    hosts_to_check = {}
    for dimension, config in _SOURCE_REGISTRY.items():
        host = config["primary"]
        if host not in hosts_to_check:
            hosts_to_check[host] = config["test_path"]

    results = {}
    for host, path in hosts_to_check.items():
        ok, status = _quick_connect(host, path)
        results[host] = {"ok": ok, "status": status, "checked_at": now}
        time.sleep(0.2)  # 请求间隔

    _health_cache = results
    _last_health_check = now

    # 同步到 utils._preflight_cache，使 _http_get() 自动跳过不可用 host
    try:
        from .utils import set_preflight_cache
        set_preflight_cache({host: {"ok": r["ok"]} for host, r in results.items()})
    except Exception:
        pass

    # 打印摘要
    ok_count = sum(1 for r in results.values() if r["ok"])
    total = len(results)
    print(f"  [预检] {ok_count}/{total} 数据源可用")

    for dimension, config in _SOURCE_REGISTRY.items():
        host = config["primary"]
        if not results.get(host, {}).get("ok", True):
            fallback_desc = " → ".join(config["fallbacks"][:2])
            print(f"    [!] {dimension}: {host} 不可用 → {fallback_desc}")

    return results


def is_host_available(host):
    """查询指定 host 当前是否可用。必须先调用 run_preflight()。"""
    if not _health_cache:
        run_preflight()
    entry = _health_cache.get(host)
    if entry is None:
        return True  # 未知 host，不阻止
    return entry.get("ok", True)


def get_health_summary():
    """获取数据源健康摘要供报告使用。"""
    if not _health_cache:
        run_preflight()
    lines = []
    for dimension, config in _SOURCE_REGISTRY.items():
        host = config["primary"]
        entry = _health_cache.get(host, {"ok": True})
        status = "OK" if entry["ok"] else "降级"
        source_note = host
        if not entry["ok"]:
            source_note += f" → {config['fallbacks'][0] if config['fallbacks'] else '无备选'}"
        lines.append(f"| {dimension} | {status} | {source_note} |")
    return "\n".join(lines)


# ============================================================
# 报告数据校验
# ============================================================

# 不应该出现 '-' 的关键章节及对应字段
_CRITICAL_FIELDS = [
    ("五、基本面分析", ["市盈率", "市净率", "每股收益", "总市值"]),
    ("五、基本面分析", ["加权净资产收益率", "毛利率", "营业收入", "净利润同比", "资产负债率"]),
    ("六、财务排雷", ["市盈率", "市净率", "ROE", "毛利率"]),
]

# 可能为空的章节（属正常情况）
_OPTIONAL_SECTIONS = [
    "逐笔成交分析",
    "板块资金全景",
    "历史财务趋势",
]


def validate_report(report_path):
    """扫描生成的 Markdown 报告，检测数据质量问题。

    Returns:
        list[str]: 发现的问题列表，空列表表示无问题
    """
    issues = []

    if not os.path.exists(report_path):
        return [f"报告文件不存在: {report_path}"]

    with open(report_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. 检查是否有 '暂无数据' / '暂无' 的章节
    missing_sections = []
    for section in _OPTIONAL_SECTIONS:
        # 在 ## 章节标题之后查找 "暂无"
        pattern = rf"## \w+、{section}.*?\n\n> 暂无"
        if re.search(pattern, content, re.DOTALL):
            missing_sections.append(section)

    if missing_sections:
        issues.append(f"[数据缺失] 以下章节无数据: {', '.join(missing_sections)}")

    # 2. 检查关键字段是否显示为 '-'
    for section, fields in _CRITICAL_FIELDS:
        section_start = content.find(section)
        if section_start < 0:
            continue
        # 提取该章节内容（约 50 行）
        section_text = content[section_start:section_start + 3000]
        for field in fields:
            # 匹配表格行: | 字段名 | - |
            pattern = rf"\|\s*{re.escape(field)}\s*\|\s*-"
            if re.search(pattern, section_text):
                issues.append(f"[数据缺失] {section} → {field} 显示为 '-'")

    # 3. 检查是否有"财务数据不全"的排雷警告
    if re.search(r"财务数据不全.*部分检查已跳过", content):
        issues.append("[数据缺失] 财务排雷章节因数据不全跳过检查")
        # 只有真正缺失时才报（如果是备选源补齐了就不会触发）

    # 4. 检查是否有备选源提示（说明主源不可用）
    alt_sources = []
    alt_patterns = [
        (r"腾讯财经.*不可用", "实时行情: 来自腾讯财经"),
        (r"新浪财经.*不可用", "实时行情: 来自新浪财经"),
        (r"腾讯财经.*外盘.*内盘", "资金流向: 外盘内盘估算"),
        (r"K线数据来自.*腾讯", "K线: 来自腾讯财经"),
    ]
    for pattern, desc in alt_patterns:
        if re.search(pattern, content):
            alt_sources.append(desc)

    if alt_sources:
        issues.insert(0, f"[降级提示] 以下数据来自备选源: {'; '.join(alt_sources)}")

    # 5. 分析评分章节找到评分异常
    rating_match = re.search(r"综合评级：[★☆]+（(\d+)/5星）", content)
    if rating_match:
        stars = int(rating_match.group(1))
        if stars <= 2:
            # 检查是否因为数据缺失导致评分偏低
            if any("数据不全" in i for i in issues) or any("暂无数据" in i for i in issues):
                issues.append("[评分预警] 综合评级偏低可能与数据缺失有关")

    return issues


def print_validation_report(report_path):
    """打印报告数据校验结果。"""
    issues = validate_report(report_path)
    if not issues:
        print("  [校验] 报告数据完整，未发现问题 ✓")
        return

    print(f"\n  {'─' * 50}")
    print(f"  [校验] 发现 {len(issues)} 个数据问题:")
    for issue in issues:
        print(f"    {issue}")
    print(f"  {'─' * 50}")


# ============================================================
# 命令行
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("数据源预检")
    print("=" * 60)
    run_preflight(force=True)
    print()
    print(get_health_summary())
