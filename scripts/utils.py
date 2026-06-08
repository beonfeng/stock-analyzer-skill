#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
共享工具模块 — 提供 HTTP 客户端等公共工具函数

本模块用于打破 analyze_stock、valuation_analysis、industry_analysis 之间的循环依赖。

功能：
- _http_get: 直连 HTTPS GET 请求（绕过系统代理，带重试）
- _http_get_safe: 安全版 _http_get，失败返回默认值而非抛异常
- 反封锁策略：随机延迟、请求头轮换、请求缓存、速率限制
"""

import json
import time
import random
import http.client
import ssl
import gzip
import zlib
from urllib.parse import urlencode
from functools import lru_cache
from datetime import datetime

try:
    import brotli
    HAS_BROTLI = True
except ImportError:
    HAS_BROTLI = False


# ============================================================
# 直连 HTTP 客户端（绕过系统代理，带重试）
# ============================================================

_ssl_ctx = ssl.create_default_context()

# ============================================================
# 反封锁策略配置
# ============================================================

# 请求头池（随机轮换，降低被识别为爬虫的概率）
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]

# 请求缓存（避免重复请求相同数据）
_request_cache = {}
_cache_ttl = 300  # 缓存有效期 5 分钟

# 全局速率控制
_last_request_time = 0
_min_request_interval = 1.0  # 最小请求间隔（秒）
_request_count = 0
_request_window_start = 0
_max_requests_per_minute = 30  # 每分钟最大请求数

# 会话级请求统计
_session_request_count = 0
_session_cache_hits = 0
_session_start_time = None


def _get_random_headers():
    """生成随机请求头，模拟不同浏览器"""
    ua = random.choice(_USER_AGENTS)
    # 如果没有 brotli 库，不请求 br 编码
    accept_enc = "gzip, deflate" if not HAS_BROTLI else "gzip, deflate, br"
    return {
        "User-Agent": ua,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": accept_enc,
        "Referer": random.choice([
            "https://quote.eastmoney.com/",
            "https://www.eastmoney.com/",
            "https://so.eastmoney.com/",
        ]),
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
        "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
    }


def _rate_limit():
    """速率限制：确保请求间隔和频率在安全范围内"""
    global _last_request_time, _request_count, _request_window_start
    global _session_request_count, _session_start_time

    # 初始化会话计时
    if _session_start_time is None:
        _session_start_time = time.time()

    now = time.time()

    # 检查每分钟请求数限制
    if now - _request_window_start > 60:
        _request_count = 0
        _request_window_start = now

    if _request_count >= _max_requests_per_minute:
        # 超过每分钟限制，等待到下一分钟
        wait_time = 60 - (now - _request_window_start) + random.uniform(1, 3)
        time.sleep(wait_time)
        _request_count = 0
        _request_window_start = time.time()

    # 确保最小请求间隔
    elapsed = time.time() - _last_request_time
    if elapsed < _min_request_interval:
        # 添加随机抖动，模拟人类行为
        jitter = random.uniform(0.1, 0.5)
        time.sleep(_min_request_interval - elapsed + jitter)

    _last_request_time = time.time()
    _request_count += 1
    _session_request_count += 1

    # 会话级请求警告
    if _session_request_count == 50:
        print("  ⚠️  本次会话已发送 50 次 API 请求，建议稍后再试以避免被限流")
    elif _session_request_count == 100:
        print("  🔴  本次会话已发送 100 次 API 请求！继续频繁调用可能导致 IP 被限流")
    elif _session_request_count > 0 and _session_request_count % 50 == 0:
        print(f"  🔴  本次会话已发送 {_session_request_count} 次 API 请求，请注意控制频率")


def _get_cache_key(host, path, params):
    """生成缓存键"""
    param_str = urlencode(sorted(params.items())) if params else ""
    return f"{host}:{path}:{param_str}"


def _get_from_cache(cache_key):
    """从缓存获取数据"""
    if cache_key in _request_cache:
        data, timestamp = _request_cache[cache_key]
        if time.time() - timestamp < _cache_ttl:
            return data
        else:
            del _request_cache[cache_key]
    return None


def _set_cache(cache_key, data):
    """设置缓存"""
    # 限制缓存大小
    if len(_request_cache) > 1000:
        # 删除最旧的缓存
        oldest_key = min(_request_cache.keys(), key=lambda k: _request_cache[k][1])
        del _request_cache[oldest_key]
    _request_cache[cache_key] = (data, time.time())


def safe_num(v, default=0):
    """
    安全转换为浮点数，None/非数值返回默认值。

    Args:
        v: 待转换的值
        default: 转换失败时的默认值

    Returns:
        float
    """
    if v is None or v == "-" or v == "":
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def _http_get(host, path, params=None, timeout=15, retries=3, use_cache=True):
    """
    直连 HTTPS GET，绕过系统代理，自动重试。

    反封锁策略：
    1. 随机请求头轮换
    2. 速率限制（每分钟最多 30 次请求）
    3. 随机延迟（1.5-3.5 秒）
    4. 请求缓存（5 分钟内相同请求直接返回缓存）
    5. 减少重试次数（从 8 次改为 3 次）
    """
    # 检查缓存
    if use_cache:
        cache_key = _get_cache_key(host, path, params)
        cached = _get_from_cache(cache_key)
        if cached is not None:
            global _session_cache_hits
            _session_cache_hits += 1
            return cached

    url = path
    if params:
        url = path + "?" + urlencode(params)

    last_err = None
    for attempt in range(retries):
        conn = None
        try:
            # 速率限制
            _rate_limit()

            # 获取随机请求头
            headers = _get_random_headers()

            conn = http.client.HTTPSConnection(host, context=_ssl_ctx, timeout=timeout)
            conn.request("GET", url, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
            conn.close()

            # 处理压缩
            encoding = resp.getheader('Content-Encoding', '')
            try:
                if encoding == 'br' and HAS_BROTLI:
                    # Brotli 解压
                    data = brotli.decompress(data)
                elif encoding == 'gzip' or data[:2] == b'\x1f\x8b':
                    data = gzip.decompress(data)
                elif encoding == 'deflate':
                    data = zlib.decompress(data, -zlib.MAX_WBITS)
                elif data[:1] == b'\x1b':
                    # 尝试 Brotli 解压（某些服务器不设置 Content-Encoding）
                    if HAS_BROTLI:
                        try:
                            data = brotli.decompress(data)
                        except:
                            pass
            except Exception:
                pass  # 如果解压失败，使用原始数据

            # 尝试多种编码
            for enc in ['utf-8', 'gbk', 'gb2312', 'latin-1']:
                try:
                    text = data.decode(enc)
                    result = json.loads(text)
                    break
                except (UnicodeDecodeError, json.JSONDecodeError) as e:
                    continue
            else:
                # 如果所有编码都失败，使用 latin-1（不会失败）
                text = data.decode('latin-1')
                result = json.loads(text)

            # 缓存结果
            if use_cache and result:
                _set_cache(cache_key, result)

            return result
        except Exception as e:
            last_err = e
            if conn:
                try:
                    conn.close()
                except:
                    pass
            if attempt < retries - 1:
                # 指数退避 + 随机抖动
                wait_time = (2.0 ** attempt) + random.uniform(1.0, 3.0)
                time.sleep(wait_time)
                continue
    raise last_err


def _http_get_safe(host, path, params=None, timeout=15, retries=3, default=None, use_cache=True):
    """安全版 _http_get，失败返回默认值而非抛异常"""
    try:
        return _http_get(host, path, params, timeout, retries, use_cache)
    except Exception:
        return default if default is not None else {}


def clear_cache():
    """清空请求缓存"""
    global _request_cache
    _request_cache.clear()


def get_cache_stats():
    """获取缓存统计信息"""
    return {
        "cache_size": len(_request_cache),
        "request_count": _request_count,
        "window_start": _request_window_start,
    }


def is_trading_day(date=None):
    """
    判断指定日期是否为交易日（排除周末）。

    注意：不包含节假日判断（如春节、国庆等），仅排除周六日。

    Args:
        date: datetime.date 对象，默认为今天

    Returns:
        bool: True 表示是交易日（周一~周五）
    """
    if date is None:
        from datetime import date as _date
        date = _date.today()
    return date.weekday() < 5  # 0=周一, 4=周五, 5=周六, 6=周日


def get_session_request_stats():
    """
    获取本次会话的请求统计。

    Returns:
        dict: {
            'total_requests': int,      # 实际 API 请求数
            'cache_hits': int,          # 缓存命中数
            'session_duration': float,  # 会话时长（秒）
        }
    """
    duration = time.time() - _session_start_time if _session_start_time else 0
    return {
        "total_requests": _session_request_count,
        "cache_hits": _session_cache_hits,
        "session_duration": duration,
    }


def print_request_stats():
    """打印本次会话的请求统计摘要"""
    stats = get_session_request_stats()
    total = stats["total_requests"]
    hits = stats["cache_hits"]
    duration = stats["session_duration"]

    print(f"\n{'─'*40}")
    print(f"  📊 API 请求统计")
    print(f"  实际请求数: {total}")
    print(f"  缓存命中数: {hits}")
    print(f"  会话时长: {duration:.1f} 秒")

    # 建议提示
    if total > 100:
        print(f"  🔴 请求次数过多，建议间隔 10 分钟以上再继续分析")
    elif total > 50:
        print(f"  ⚠️  请求次数偏多，建议适当控制分析频率")
    else:
        print(f"  ✅ 请求次数在安全范围内")

    # 交易日提示
    if not is_trading_day():
        print(f"  📅 今天不是交易日，数据为最近交易日的快照")
    print(f"{'─'*40}")


def reset_request_stats():
    """重置会话请求统计（用于新一轮分析开始时）"""
    global _session_request_count, _session_cache_hits, _session_start_time
    _session_request_count = 0
    _session_cache_hits = 0
    _session_start_time = time.time()
