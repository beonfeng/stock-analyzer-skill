#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
共享工具模块 — 提供 HTTP 客户端等公共工具函数

反封锁策略（六层防护）：
1. 断路器模式：Host 级三态断路器，防止对故障端点持续请求
2. 端点故障转移：主 Host 被封自动切换备用 CDN / IP 直连
3. 自适应调节：根据成功率/延迟动态调整请求频率
4. 渐进降级：请求额度不足时按优先级跳过非关键数据
5. 请求队列可视化：实时进度条 + 预计剩余时间
6. 跨分析缓存：市场级数据/Memoization 复用

功能：
- _http_get: 直连 HTTPS GET 请求（绕过系统代理，带重试/故障转移）
- _http_get_safe: 安全版 _http_get，失败返回默认值而非抛异常
"""

import json
import time
import random
import copy
import http.client
import ssl
import gzip
import zlib
from urllib.parse import urlencode
from datetime import datetime, date
from enum import Enum


# ============================================================
# 断路器模式（Circuit Breaker）
# ============================================================

class CircuitState(Enum):
    CLOSED = "closed"      # 正常
    OPEN = "open"          # 熔断
    HALF_OPEN = "half_open"  # 试探


class CircuitBreaker:
    """Host 级断路器：防止对故障端点持续请求

    状态转换：
    CLOSED ──连续失败N次──▶ OPEN ──等待T秒──▶ HALF_OPEN
    HALF_OPEN ──成功──▶ CLOSED
    HALF_OPEN ──失败──▶ OPEN (重新计时)
    """

    def __init__(self, host, failure_threshold=2, cooldown_seconds=120):
        self.host = host
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        self.opened_at = 0

    def record_success(self):
        self.failure_count = 0
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            if self.state == CircuitState.CLOSED:
                self.state = CircuitState.OPEN
                self.opened_at = time.time()
            elif self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                self.opened_at = time.time()

    def allow_request(self):
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            elapsed = time.time() - self.opened_at
            if elapsed >= self.cooldown_seconds:
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        return True  # HALF_OPEN: allow probe

    def cooldown_remaining(self):
        if self.state == CircuitState.OPEN:
            remaining = self.cooldown_seconds - (time.time() - self.opened_at)
            return max(0, remaining)
        return 0

    def to_dict(self):
        return {
            "host": self.host,
            "state": self.state.value,
            "failures": self.failure_count,
            "cooldown_remaining": self.cooldown_remaining(),
        }


# ============================================================
# 端点故障转移链
# ============================================================

# 主 Host → 备用 Host 映射
_HOST_FALLBACKS = {
    "push2.eastmoney.com": [
        "push2ncg.eastmoney.com",
        "push2his.eastmoney.com",
    ],
    "push2his.eastmoney.com": [
        "push2ncg.eastmoney.com",
        "push2.eastmoney.com",
    ],
    "push2ncg.eastmoney.com": [
        "push2.eastmoney.com",
        "push2his.eastmoney.com",
    ],
    "82.push2.eastmoney.com": [
        "push2.eastmoney.com",
    ],
}

# 用于故障转移的公共 ut token 映射
# 不同域名可能需要不同的 ut token，这里映射备用 token
_UT_FALLBACKS = {
    "key1": "7eea3edcaed734bea9cbfc24409ed989",
    "key2": "b2884a393a59ad64002292a3e90d46a5",
    "key3": "fa5fd1943c7b386f172d6893dbfba10b",
}


def _get_fallback_hosts(host):
    """获取指定 Host 的故障转移列表"""
    return _HOST_FALLBACKS.get(host, [])


# ============================================================
# TLS 指纹伪装
# ============================================================

try:
    import brotli  # type: ignore[import-untyped]
    HAS_BROTLI = True
except ImportError:
    HAS_BROTLI = False

# TLS 上下文池（不同密码套件组合，增加指纹多样性）
_ssl_contexts = []
try:
    # 标准 TLS 1.2+ 上下文
    ctx1 = ssl.create_default_context()
    ctx1.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS')
    _ssl_contexts.append(ctx1)

    # 兼容模式上下文（模拟较旧浏览器）
    ctx2 = ssl.create_default_context()
    _ssl_contexts.append(ctx2)
except Exception:
    _ssl_contexts.append(ssl.create_default_context())


def _get_random_ssl_context():
    """随机选择 TLS 上下文，增加指纹多样性"""
    return random.choice(_ssl_contexts)


# ============================================================
# 反封锁策略配置
# ============================================================

_USER_AGENTS = [
    # Windows Chrome
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:139.0) Gecko/20100101 Firefox/139.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:138.0) Gecko/20100101 Firefox/138.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36 Edg/137.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36",
]

_REFERER_POOL = [
    "https://quote.eastmoney.com/",
    "https://quote.eastmoney.com/concept/",
    "https://quote.eastmoney.com/center/gridlist.html",
    "https://www.eastmoney.com/",
    "https://so.eastmoney.com/",
    "https://data.eastmoney.com/",
    "https://data.eastmoney.com/zjlx/",
    "https://emweb.securities.eastmoney.com/",
]

_SEC_CH_UA_POOL = [
    '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
    '"Google Chrome";v="136", "Chromium";v="136", "Not/A)Brand";v="24"',
    '"Microsoft Edge";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
    '"Chromium";v="137", "Not(A:Brand";v="24", "Google Chrome";v="137"',
    '"Not_A Brand";v="8", "Chromium";v="137", "Google Chrome";v="137"',
]

# 请求缓存
_request_cache = {}
_cache_ttl = 300
_MEMO_CACHE = {}  # 跨分析 Memoization 缓存

_CACHE_TTL_MAP = {
    "/api/qt/stock/kline/get": 1800,
    "/api/qt/stock/get": 300,
    "/api/qt/clist/get": 600,
    "/api/data/get": 86400,         # 财务/主营业务/股东数据季度更新，缓存 1 天
    "/api/news/get": 900,
    "/PC_HSF10/CompanySurvey": 86400,  # 公司基本资料极少变化，缓存 1 天
}

# ============================================================
# 自适应调节 + 速率控制
# ============================================================

_last_request_time = 0
_min_request_interval = 2.0
_max_request_interval = 4.0
_request_count = 0
_request_window_start = 0
_max_requests_per_minute = 12  # 基础值，自适应调节会动态修改

# 自适应调节参数
_success_count_window = 0
_failure_count_window = 0
_adaptive_check_interval = 20  # 每 20 次请求评估一次
_adaptive_direction = 0  # 0=稳态, +1=加速, -2=减速

# 断路器注册表
_circuit_breakers = {}  # {'host': CircuitBreaker}

# 会话统计
_session_request_count = 0
_session_cache_hits = 0
_session_start_time = None
_SESSION_HARD_LIMIT = 60
_SESSION_COOLDOWN_SECONDS = 300
_last_cooldown_time = 0

# 请求队列可视化
_queue_total = 0
_queue_completed = 0
_queue_start_time = 0


def _get_or_create_breaker(host):
    """获取或创建 Host 级断路器"""
    if host not in _circuit_breakers:
        _circuit_breakers[host] = CircuitBreaker(host)
    return _circuit_breakers[host]


def _get_random_headers():
    """生成随机请求头，模拟不同浏览器/设备组合"""
    ua = random.choice(_USER_AGENTS)
    accept_enc = "gzip, deflate" if not HAS_BROTLI else "gzip, deflate, br"

    if "Macintosh" in ua:
        platform = '"macOS"'
    elif "Linux" in ua and "Android" not in ua:
        platform = '"Linux"'
    elif "iPhone" in ua or "iPad" in ua:
        platform = '"iOS"'
    elif "Android" in ua:
        platform = '"Android"'
    else:
        platform = '"Windows"'

    is_mobile = any(k in ua for k in ["Mobile", "iPhone", "Android"])

    headers = {
        "User-Agent": ua,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": random.choice([
            "zh-CN,zh;q=0.9,en;q=0.8",
            "zh-CN,zh;q=0.9",
            "zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3",
            "zh,zh-CN;q=0.9,en;q=0.8",
        ]),
        "Accept-Encoding": accept_enc,
        "Referer": random.choice(_REFERER_POOL),
        "Connection": "keep-alive",
        "Cache-Control": random.choice(["no-cache", "max-age=0"]),
        "Sec-Ch-Ua": random.choice(_SEC_CH_UA_POOL),
        "Sec-Ch-Ua-Mobile": "?1" if is_mobile else "?0",
        "Sec-Ch-Ua-Platform": platform,
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": random.choice(["same-site", "same-origin"]),
    }

    if random.random() < 0.3:
        headers["DNT"] = random.choice(["0", "1"])
    if random.random() < 0.2:
        headers["Upgrade-Insecure-Requests"] = "1"

    return headers


def _adaptive_adjust():
    """自适应调节：根据成功率/延迟动态调整请求频率"""
    global _success_count_window, _failure_count_window, _max_requests_per_minute
    global _min_request_interval, _max_request_interval, _adaptive_direction

    total_window = _success_count_window + _failure_count_window
    if total_window < _adaptive_check_interval:
        return  # 样本不足

    success_rate = _success_count_window / total_window if total_window > 0 else 1.0

    # 根据成功率调整频率
    if success_rate >= 0.95:
        # 成功率很高 → 可以稍快
        new_max = min(15, _max_requests_per_minute + 1)
        if new_max != _max_requests_per_minute:
            _max_requests_per_minute = new_max
            _min_request_interval = max(1.0, _min_request_interval - 0.3)
            _adaptive_direction = 1
    elif success_rate < 0.7:
        # 成功率低 → 需要大幅减速
        new_max = max(4, _max_requests_per_minute - 3)
        if new_max != _max_requests_per_minute:
            _max_requests_per_minute = new_max
            _min_request_interval = min(8.0, _min_request_interval + 1.0)
            _adaptive_direction = -2
    elif success_rate < 0.85:
        # 成功率偏低 → 轻微减速
        new_max = max(6, _max_requests_per_minute - 1)
        if new_max != _max_requests_per_minute:
            _max_requests_per_minute = new_max
            _min_request_interval = min(6.0, _min_request_interval + 0.5)
            _adaptive_direction = -1
    else:
        _adaptive_direction = 0

    # 重置窗口
    _success_count_window = 0
    _failure_count_window = 0


def _rate_limit():
    """
    多层速率限制策略：
    1. 自适应频率调节（根据成功率动态变化）
    2. 每请求间隔 2-4 秒随机（模拟人类）
    3. 每分钟 ≤动态上限
    4. 会话累计 >60 次 → 强制冷却 5 分钟
    5. 非交易日自动降频
    """
    global _last_request_time, _request_count, _request_window_start
    global _session_request_count, _session_start_time, _last_cooldown_time

    if _session_start_time is None:
        _session_start_time = time.time()

    now = time.time()

    # ── 自适应调节检测 ──
    _adaptive_adjust()

    # ── 层 0：会话硬上限 ──
    if _session_request_count >= _SESSION_HARD_LIMIT:
        cooldown_remaining = _SESSION_COOLDOWN_SECONDS - (now - _last_cooldown_time)
        if cooldown_remaining > 0:
            print(f"  [冷却] 已发 {_session_request_count} 次请求，强制冷却 {cooldown_remaining:.0f} 秒...")
            time.sleep(cooldown_remaining)
        _session_request_count = 0
        _request_count = 0
        _request_window_start = time.time()
        _last_cooldown_time = time.time()
        _session_start_time = time.time()
        print("  [冷却] 冷却完成，恢复请求")

    # ── 层 1：非交易日降频 ──
    is_weekend = date.today().weekday() >= 5
    effective_max_per_min = max(4, _max_requests_per_minute // 2) if is_weekend else _max_requests_per_minute
    effective_min_interval = _max_request_interval if is_weekend else _min_request_interval

    # ── 层 2：每分钟限制 ──
    if now - _request_window_start > 60:
        _request_count = 0
        _request_window_start = now

    if _request_count >= effective_max_per_min:
        wait_time = 60 - (now - _request_window_start) + random.uniform(1, 3)
        time.sleep(wait_time)
        _request_count = 0
        _request_window_start = time.time()

    # ── 层 3：随机间隔 ──
    elapsed = time.time() - _last_request_time
    random_interval = random.uniform(effective_min_interval, _max_request_interval)
    if elapsed < random_interval:
        time.sleep(random_interval - elapsed)

    _last_request_time = time.time()
    _request_count += 1
    _session_request_count += 1

    # ── 层 4：预警 ──
    if _session_request_count == 30:
        print(f"  [注意] 已发 30 次，剩余 {_SESSION_HARD_LIMIT - _session_request_count} 次")
    elif _session_request_count == 50:
        print(f"  [警告] 已发 50 次！仅剩 {_SESSION_HARD_LIMIT - _session_request_count} 次")
    elif _session_request_count >= 55:
        print(f"  [警告] 已发 {_session_request_count} 次，即将强制冷却")


def _get_cache_key(host, path, params):
    param_str = urlencode(sorted(params.items())) if params else ""
    return f"{host}:{path}:{param_str}"


def _get_from_cache(cache_key):
    if cache_key in _request_cache:
        data, timestamp, ttl = _request_cache[cache_key]
        if time.time() - timestamp < ttl:
            return data
        else:
            del _request_cache[cache_key]
    return None


def _get_ttl_for_path(path):
    for pattern, ttl in _CACHE_TTL_MAP.items():
        if pattern in path:
            return ttl
    return _cache_ttl


def _set_cache(cache_key, data, path=""):
    while len(_request_cache) > 1000:
        oldest_key = next(iter(_request_cache))
        del _request_cache[oldest_key]
    ttl = _get_ttl_for_path(path)
    _request_cache[cache_key] = (data, time.time(), ttl)


def _is_connection_error(err):
    err_str = str(err)
    rejection_keywords = [
        'RemoteDisconnected', 'Connection refused', 'Connection reset',
        'ConnectionResetError', 'Remote end closed', 'timed out', 'TimeoutError',
    ]
    return any(kw.lower() in err_str.lower() for kw in rejection_keywords)


def safe_num(v, default=0):
    if v is None or v == "-" or v == "":
        return default
    if isinstance(v, str) and v.strip() in ("N/A", "--", "nan", "NaN", "NA", "null"):
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def safe_display(v, fmt=".2f", show_zero=False):
    """安全显示数值，缺失数据返回 '-' 而非 '0'，避免歧义。

    Args:
        v: 待显示的值
        fmt: 数值格式化字符串
        show_zero: True 时 0 显示为 "0.00"（用于 ROE/增长率等 0 是合法值的场景）
    """
    if v is None or v == "-" or v == "":
        return "-"
    if isinstance(v, str) and v.strip() in ("N/A", "--", "nan", "NaN", "NA", "null"):
        return "-"
    if isinstance(v, (int, float)):
        if not show_zero and v == 0:
            return "-"
        return f"{v:{fmt}}"
    try:
        fv = float(v)
        if not show_zero and fv == 0:
            return "-"
        return f"{fv:{fmt}}"
    except (ValueError, TypeError):
        return "-"


# ============================================================
# 请求队列可视化
# ============================================================

def init_request_queue(total):
    """初始化请求队列（用于进度条显示）"""
    global _queue_total, _queue_completed, _queue_start_time
    _queue_total = total
    _queue_completed = 0
    _queue_start_time = time.time()


def tick_request_queue(label=""):
    """请求完成一次，更新进度条"""
    global _queue_completed
    _queue_completed += 1
    if _queue_total > 0:
        pct = _queue_completed / _queue_total * 100
        bar_len = 20
        filled = int(bar_len * _queue_completed / _queue_total)
        bar = "#" * filled + "-" * (bar_len - filled)
        elapsed = time.time() - _queue_start_time
        if _queue_completed > 0:
            eta = elapsed / _queue_completed * (_queue_total - _queue_completed)
        else:
            eta = 0
        label_str = f"  {label}" if label else ""
        print(f"  [{bar}] {_queue_completed}/{_queue_total} ({pct:.0f}%) 剩余约 {eta:.0f}s{label_str}")


# ============================================================
# Memoization 跨分析缓存
# ============================================================

def memo_get(key):
    """从跨分析缓存获取数据"""
    if key in _MEMO_CACHE:
        data, timestamp = _MEMO_CACHE[key]
        if time.time() - timestamp < 3600:  # 1 小时过期
            return data
        else:
            del _MEMO_CACHE[key]
    return None


def memo_set(key, data):
    """设置跨分析缓存"""
    _MEMO_CACHE[key] = (data, time.time())


def memo_clear():
    """清空跨分析缓存"""
    _MEMO_CACHE.clear()


# ============================================================
# 核心 HTTP 客户端（带故障转移）
# ============================================================

def _try_single_request(host, path, params, timeout=15):
    """尝试向单个 Host 发送请求（无重试，无缓存，无速率限制）"""
    url = path
    if params:
        noisy_params = copy.deepcopy(params)
        noisy_params["_"] = str(int(time.time() * 1000))
        url = path + "?" + urlencode(noisy_params)

    headers = _get_random_headers()
    ctx = _get_random_ssl_context()

    conn = http.client.HTTPSConnection(host, context=ctx, timeout=timeout)
    try:
        conn.request("GET", url, headers=headers)
        resp = conn.getresponse()

        if resp.status in (429, 503):
            raise ConnectionError(f"HTTP {resp.status}: rate limited")

        data = resp.read()

        # 处理压缩
        encoding = resp.getheader('Content-Encoding', '')
        try:
            if encoding == 'br' and HAS_BROTLI:
                data = brotli.decompress(data)
            elif encoding == 'gzip' or data[:2] == b'\x1f\x8b':
                data = gzip.decompress(data)
            elif encoding == 'deflate':
                data = zlib.decompress(data, -zlib.MAX_WBITS)
            elif data[:1] == b'\x1b' and HAS_BROTLI:
                try:
                    data = brotli.decompress(data)
                except Exception:
                    pass
        except Exception:
            pass

        # 解码
        text = None
        for enc in ['utf-8', 'gbk', 'gb2312']:
            try:
                text = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            text = data.decode('latin-1')

        result = json.loads(text)
        return result
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _http_get(host, path, params=None, timeout=15, retries=2, use_cache=True):
    """
    直连 HTTPS GET，带断路器 + 故障转移 + 智能重试。

    防护策略（六层）：
    1. 缓存检查（5分钟~1小时 按接口差异化）
    2. 断路器检查（Host 级三态断路器）
    3. 故障转移（主 Host 失败自动切换备用）
    4. 速率限制（自适应频率 + 随机间隔）
    5. 连接拒绝不重试，其他错误指数退避
    6. 成功后更新断路器 + 自适应计数器
    """
    # ── 缓存 ──
    if use_cache:
        cache_key = _get_cache_key(host, path, params)
        cached = _get_from_cache(cache_key)
        if cached is not None:
            global _session_cache_hits
            _session_cache_hits += 1
            return cached

    # ── 断路器检查 ──
    breaker = _get_or_create_breaker(host)
    if not breaker.allow_request():
        remaining = breaker.cooldown_remaining()
        # 尝试故障转移
        fallbacks = _get_fallback_hosts(host)
        for fallback_host in fallbacks:
            fallback_breaker = _get_or_create_breaker(fallback_host)
            if fallback_breaker.allow_request():
                try:
                    result = _try_single_request(fallback_host, path, params, timeout)
                    fallback_breaker.record_success()
                    if use_cache and result is not None:
                        _set_cache(cache_key, result, path)
                    global _success_count_window
                    _success_count_window += 1
                    return result
                except Exception:
                    fallback_breaker.record_failure()
                    global _failure_count_window
                    _failure_count_window += 1

        raise ConnectionError(f"Host {host} is OPEN and no fallback available ({remaining:.0f}s remaining)")

    # ── 主请求循环 ──
    last_err = None
    for attempt in range(retries):
        try:
            if attempt == 0:
                _rate_limit()

            result = _try_single_request(host, path, params, timeout)

            # 成功 → 清理状态
            breaker.record_success()
            if use_cache and result is not None:
                _set_cache(cache_key, result, path)

            _success_count_window += 1

            return result

        except Exception as e:
            last_err = e
            _failure_count_window += 1

            # JSON 解析错误不重试（数据本身有问题，非瞬态网络故障）
            if isinstance(e, json.JSONDecodeError):
                raise

            if _is_connection_error(e):
                breaker.record_failure()
                if not breaker.allow_request():
                    cooldown = breaker.cooldown_remaining()
                    print(f"  [熔断] {host} 断路器 OPEN（{cooldown:.0f}s），尝试故障转移...")
                    # 尝试故障转移
                    fallbacks = _get_fallback_hosts(host)
                    fallback_success = False
                    for fallback_host in fallbacks:
                        fb = _get_or_create_breaker(fallback_host)
                        if fb.allow_request():
                            try:
                                result = _try_single_request(fallback_host, path, params, timeout)
                                fb.record_success()
                                _success_count_window += 1
                                if use_cache and result is not None:
                                    _set_cache(cache_key, result, path)
                                fallback_success = True
                                return result
                            except Exception:
                                fb.record_failure()
                                _failure_count_window += 1
                    # 只有断路器 OPEN 且所有 fallback 都失败才 raise
                    if not fallback_success:
                        raise last_err
                # 断路器未 OPEN → 连接错误可能是瞬态的，不立即 raise，继续重试循环
            else:
                # 非连接错误 → 指数退避重试
                if attempt < retries - 1:
                    wait_time = (2.0 ** (attempt + 1)) + random.uniform(1.0, 2.0)
                    time.sleep(wait_time)

    raise last_err


def _http_get_safe(host, path, params=None, timeout=15, retries=2, default=None, use_cache=True):
    """安全版 _http_get，失败返回默认值而非抛异常"""
    if default is None:
        default = {}
    try:
        return _http_get(host, path, params, timeout, retries, use_cache)
    except Exception as e:
        if _is_connection_error(e):
            print(f"  [跳过] {host} 暂时不可用，返回默认值")
        return default


# ============================================================
# 缓存与统计
# ============================================================

def clear_cache():
    global _request_cache
    _request_cache.clear()


def get_cache_stats():
    return {
        "cache_size": len(_request_cache),
        "request_count": _request_count,
        "window_start": _request_window_start,
    }


def is_trading_day(dt=None):
    if dt is None:
        dt = date.today()
    return dt.weekday() < 5


def get_session_request_stats():
    duration = time.time() - _session_start_time if _session_start_time else 0
    return {
        "total_requests": _session_request_count,
        "cache_hits": _session_cache_hits,
        "session_duration": duration,
    }


def print_request_stats():
    stats = get_session_request_stats()
    total = stats["total_requests"]
    hits = stats["cache_hits"]
    duration = stats["session_duration"]
    remaining = max(0, _SESSION_HARD_LIMIT - total)

    print(f"\n{'='*50}")
    print(f"  [统计] API 请求统计")
    print(f"  实际请求: {total} / {_SESSION_HARD_LIMIT} (剩余 {remaining} 次)")
    print(f"  缓存命中: {hits}")
    print(f"  耗时: {duration:.1f}s")
    print(f"  频率: <= {_max_requests_per_minute}/min, 间隔 {_min_request_interval:.1f}-{_max_request_interval:.1f}s")
    if _adaptive_direction > 0:
        print(f"  [自适应] 频率放宽 -> {_max_requests_per_minute}/min")
    elif _adaptive_direction < 0:
        print(f"  [自适应] 频率收紧 -> {_max_requests_per_minute}/min")

    if not is_trading_day():
        print(f"  [提示] 非交易日，频率已自动降低")

    # 断路器状态
    open_breakers = [(h, b) for h, b in _circuit_breakers.items() if b.state != CircuitState.CLOSED]
    if open_breakers:
        for host, br in open_breakers:
            print(f"  [断路器] {host} -> {br.state.value} (失败 {br.failure_count} 次)")
    print(f"{'='*50}")


def get_circuit_breaker_status():
    """获取所有断路器状态"""
    return {h: b.to_dict() for h, b in _circuit_breakers.items()}


def reset_request_stats():
    global _session_request_count, _session_cache_hits, _session_start_time
    global _queue_total, _queue_completed, _queue_start_time
    _session_request_count = 0
    _session_cache_hits = 0
    _session_start_time = time.time()
    _queue_total = 0
    _queue_completed = 0
