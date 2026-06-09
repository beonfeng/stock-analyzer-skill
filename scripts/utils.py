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
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:139.0) Gecko/20100101 Firefox/139.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36 Edg/137.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.4 Safari/605.1.15",
]

# 请求缓存（避免重复请求相同数据）
_request_cache = {}
_cache_ttl = 300  # 缓存有效期 5 分钟

# ============================================================
# 全局速率控制（防封锁核心策略）
# ============================================================
# 东方财富 API 对请求频率非常敏感，经验值：
# - 单分钟 >15 次 → 开始被拒绝连接
# - 累计 10 分钟内 >60 次 → 触发 IP 级封锁（数小时）
# - 连续请求（间隔 <0.5s）→ 被视为爬虫即刻封锁
#
# 策略：
# 1. 每分钟最多 12 次（留安全余量）
# 2. 请求间隔 1-4 秒随机（模拟人类浏览行为）
# 3. 单 Host 连续失败时自动冷却
# 4. 会话累计超过 60 次强制冷却 5 分钟
# 5. 非交易日自动降频（周末没必要频繁请求）

_last_request_time = 0
_min_request_interval = 2.0  # 最小请求间隔（秒），从 1.0 提高到 2.0
_max_request_interval = 4.0  # 最大随机间隔（秒）
_request_count = 0
_request_window_start = 0
_max_requests_per_minute = 12  # 每分钟最大请求数，从 30 降到 12

# Host 级冷却追踪
_host_error_counts = {}  # {'host': error_count}
_host_cooldown_until = {}  # {'host': timestamp}
_HOST_COOLDOWN_SECONDS = 120  # Host 冷却 2 分钟
_HOST_MAX_CONSECUTIVE_ERRORS = 2  # 连续失败 2 次即冷却

# 会话级统计与硬上限
_session_request_count = 0
_session_cache_hits = 0
_session_start_time = None
_SESSION_HARD_LIMIT = 60  # 会话累计超过此值强制冷却
_SESSION_COOLDOWN_SECONDS = 300  # 会话冷却 5 分钟
_last_cooldown_time = 0


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
        "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="137", "Google Chrome";v="137"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
    }


def _rate_limit():
    """
    多层速率限制策略：
    1. 每请求间隔 2-4 秒随机（模拟人类）
    2. 每分钟 ≤12 次
    3. 会话累计 >60 次 → 强制冷却 5 分钟
    4. 非交易日自动降频
    """
    global _last_request_time, _request_count, _request_window_start
    global _session_request_count, _session_start_time, _last_cooldown_time

    # 初始化会话计时
    if _session_start_time is None:
        _session_start_time = time.time()

    now = time.time()

    # ── 层 0：会话硬上限检查 ──
    if _session_request_count >= _SESSION_HARD_LIMIT:
        cooldown_remaining = _SESSION_COOLDOWN_SECONDS - (now - _last_cooldown_time)
        if cooldown_remaining > 0:
            print(f"  [冷却] 本次会话已发 {_session_request_count} 次请求，强制冷却 {cooldown_remaining:.0f} 秒...")
            time.sleep(cooldown_remaining)
        # 重置计数器
        _session_request_count = 0
        _request_count = 0
        _request_window_start = time.time()
        _last_cooldown_time = time.time()
        _session_start_time = time.time()
        print("  [冷却] 冷却完成，恢复请求")

    # ── 层 1：非交易日降频 ──
    from datetime import date as _date
    is_weekend = _date.today().weekday() >= 5
    effective_max_per_min = max(6, _max_requests_per_minute // 2) if is_weekend else _max_requests_per_minute
    effective_min_interval = _max_request_interval if is_weekend else _min_request_interval

    # ── 层 2：每分钟请求数限制 ──
    if now - _request_window_start > 60:
        _request_count = 0
        _request_window_start = now

    if _request_count >= effective_max_per_min:
        wait_time = 60 - (now - _request_window_start) + random.uniform(1, 3)
        time.sleep(wait_time)
        _request_count = 0
        _request_window_start = time.time()

    # ── 层 3：请求间隔（随机 2-4 秒） ──
    elapsed = time.time() - _last_request_time
    random_interval = random.uniform(effective_min_interval, _max_request_interval)
    if elapsed < random_interval:
        time.sleep(random_interval - elapsed)

    _last_request_time = time.time()
    _request_count += 1
    _session_request_count += 1

    # ── 层 4：会话级预警 ──
    if _session_request_count == 30:
        print(f"  [注意] 已发送 30 次请求，剩余额度 {_SESSION_HARD_LIMIT - _session_request_count} 次")
    elif _session_request_count == 50:
        print(f"  [警告] 已发送 50 次请求！仅剩 {_SESSION_HARD_LIMIT - _session_request_count} 次额度")
    elif _session_request_count >= 55:
        print(f"  [警告] 已发送 {_session_request_count} 次，即将触发强制冷却")


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
        # 删除最早的缓存条目（近似 FIFO，O(1) 替代 O(n) 扫描）
        oldest_key = next(iter(_request_cache))
        del _request_cache[oldest_key]
    _request_cache[cache_key] = (data, time.time())


def _is_connection_error(err):
    """判断错误是否为服务器主动拒绝连接"""
    err_str = str(err)
    rejection_keywords = [
        'RemoteDisconnected',
        'Connection refused',
        'Connection reset',
        'ConnectionResetError',
        'Remote end closed',
        'timed out',
        'TimeoutError',
    ]
    return any(kw.lower() in err_str.lower() for kw in rejection_keywords)


def _check_host_cooldown(host):
    """检查 Host 是否处于冷却期，返回还需等待的秒数"""
    if host in _host_cooldown_until:
        remaining = _host_cooldown_until[host] - time.time()
        if remaining > 0:
            return remaining
    return 0


def _mark_host_error(host):
    """记录 Host 错误，连续失败达到阈值时进入冷却"""
    global _host_error_counts
    _host_error_counts[host] = _host_error_counts.get(host, 0) + 1
    if _host_error_counts[host] >= _HOST_MAX_CONSECUTIVE_ERRORS:
        _host_cooldown_until[host] = time.time() + _HOST_COOLDOWN_SECONDS


def _clear_host_error(host):
    """请求成功时清除错误计数"""
    if host in _host_error_counts:
        del _host_error_counts[host]
    if host in _host_cooldown_until:
        del _host_cooldown_until[host]


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
    if isinstance(v, str) and v.strip() in ("N/A", "--", "nan", "NaN", "NA", "null"):
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def _http_get(host, path, params=None, timeout=15, retries=2, use_cache=True):
    """
    直连 HTTPS GET，绕过系统代理，智能重试。

    反封锁策略（四层防护）：
    1. 请求前：速率限制（2-4s 间隔，≤12次/分）+ Host 冷却检查
    2. 请求时：随机请求头轮换，模拟不同浏览器
    3. 失败时：连接拒绝类错误不重试（服务器主动拒绝，重试只会加剧封禁）
    4. 成功后：缓存 5 分钟，清除 Host 错误计数
    """
    # 检查缓存
    if use_cache:
        cache_key = _get_cache_key(host, path, params)
        cached = _get_from_cache(cache_key)
        if cached is not None:
            global _session_cache_hits
            _session_cache_hits += 1
            return cached

    # 检查 Host 冷却
    cooldown_sec = _check_host_cooldown(host)
    if cooldown_sec > 0:
        global _session_request_count, _session_start_time
        print(f"  [保护] Host {host} 处于冷却期（{cooldown_sec:.0f}秒），跳过请求")
        raise ConnectionError(f"Host {host} is in cooldown ({cooldown_sec:.0f}s remaining)")

    url = path
    if params:
        url = path + "?" + urlencode(params)

    last_err = None
    for attempt in range(retries):
        conn = None
        try:
            # 速率限制（仅在首次尝试时执行，重试跳过）
            if attempt == 0:
                _rate_limit()

            # 获取随机请求头
            headers = _get_random_headers()

            conn = http.client.HTTPSConnection(host, context=_ssl_ctx, timeout=timeout)
            conn.request("GET", url, headers=headers)
            resp = conn.getresponse()

            # HTTP 429/503 → 服务器要求放慢速度
            if resp.status in (429, 503):
                raise ConnectionError(f"HTTP {resp.status}: rate limited by server")

            data = resp.read()
            conn.close()

            # 处理压缩
            encoding = resp.getheader('Content-Encoding', '')
            try:
                if encoding == 'br' and HAS_BROTLI:
                    data = brotli.decompress(data)
                elif encoding == 'gzip' or data[:2] == b'\x1f\x8b':
                    data = gzip.decompress(data)
                elif encoding == 'deflate':
                    data = zlib.decompress(data, -zlib.MAX_WBITS)
                elif data[:1] == b'\x1b':
                    if HAS_BROTLI:
                        try:
                            data = brotli.decompress(data)
                        except Exception:
                            pass
            except Exception:
                pass

            # 尝试多种编码
            for enc in ['utf-8', 'gbk', 'gb2312', 'latin-1']:
                try:
                    text = data.decode(enc)
                    result = json.loads(text)
                    break
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
            else:
                text = data.decode('latin-1')
                result = json.loads(text)

            # 缓存结果
            if use_cache and result is not None:
                _set_cache(cache_key, result)

            # 成功 → 清除该 Host 的错误计数
            _clear_host_error(host)

            return result

        except Exception as e:
            last_err = e
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

            # 连接拒绝类错误 → 标记 Host 错误，不重试
            if _is_connection_error(e):
                if attempt == 0:
                    _mark_host_error(host)
                    cooldown = _check_host_cooldown(host)
                    if cooldown > 0:
                        print(f"  [保护] {host} 连接被拒绝，进入 {cooldown:.0f} 秒冷却期")
                # 连接拒绝类错误不重试，直接抛异常
                raise last_err

            # 其他错误（如 JSON 解析失败）→ 指数退避重试
            if attempt < retries - 1:
                wait_time = (2.0 ** (attempt + 1)) + random.uniform(1.0, 2.0)
                time.sleep(wait_time)
                continue

    raise last_err


def _http_get_safe(host, path, params=None, timeout=15, retries=2, default={}, use_cache=True):
    """安全版 _http_get，失败返回默认值而非抛异常"""
    try:
        return _http_get(host, path, params, timeout, retries, use_cache)
    except Exception as e:
        # 连接拒绝类错误 → 不打印堆栈，仅输出简洁提示
        if _is_connection_error(e):
            print(f"  [跳过] {host} 暂时不可用，返回默认值")
        return default


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

    remaining = max(0, _SESSION_HARD_LIMIT - total)

    print(f"\n{'─'*40}")
    print(f"  [统计] API 请求统计")
    print(f"  实际请求数: {total} / {_SESSION_HARD_LIMIT}（剩余 {remaining} 次额度）")
    print(f"  缓存命中数: {hits}")
    print(f"  会话时长: {duration:.1f} 秒")
    print(f"  请求频率: 每分钟 ≤{_max_requests_per_minute} 次，间隔 {_min_request_interval}-{_max_request_interval} 秒")

    # 交易日提示
    if not is_trading_day():
        print(f"  [提示] 今天不是交易日，数据为最近交易日的快照，请求频率已自动降低")

    # Host 冷却状态
    if _host_cooldown_until:
        active = [(h, max(0, int(t - time.time()))) for h, t in _host_cooldown_until.items() if t > time.time()]
        if active:
            for host, remaining_sec in active:
                print(f"  [保护] {host} 冷却中（剩余 {remaining_sec} 秒）")
    print(f"{'─'*40}")


def reset_request_stats():
    """
    重置会话请求统计计数器（用于新一轮分析开始时）。

    注意：仅重置统计计数器（请求数、缓存命中数、会话起始时间），
    不影响速率限制状态（如 _last_request_time、_request_count、
    _host_cooldown_until 等），也不会清空请求缓存。
    """
    global _session_request_count, _session_cache_hits, _session_start_time
    _session_request_count = 0
    _session_cache_hits = 0
    _session_start_time = time.time()
