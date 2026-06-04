#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
共享工具模块 — 提供 HTTP 客户端等公共工具函数

本模块用于打破 analyze_stock、valuation_analysis、industry_analysis 之间的循环依赖。

功能：
- _http_get: 直连 HTTPS GET 请求（绕过系统代理，带重试）
- _http_get_safe: 安全版 _http_get，失败返回默认值而非抛异常
"""

import json
import time
import http.client
import ssl
from urllib.parse import urlencode


# ============================================================
# 直连 HTTP 客户端（绕过系统代理，带重试）
# ============================================================

_ssl_ctx = ssl.create_default_context()


def _http_get(host, path, params=None, timeout=15, retries=8):
    """直连 HTTPS GET，绕过系统代理，自动重试"""
    url = path
    if params:
        url = path + "?" + urlencode(params)
    last_err = None
    for attempt in range(retries):
        conn = None
        try:
            conn = http.client.HTTPSConnection(host, context=_ssl_ctx, timeout=timeout)
            conn.request("GET", url)
            resp = conn.getresponse()
            data = resp.read()
            conn.close()
            return json.loads(data)
        except Exception as e:
            last_err = e
            if conn:
                try: conn.close()
                except: pass
            if attempt < retries - 1:
                time.sleep(2 + attempt * 0.5)
                continue
    raise last_err


def _http_get_safe(host, path, params=None, timeout=15, retries=8, default=None):
    """安全版 _http_get，失败返回默认值而非抛异常"""
    try:
        return _http_get(host, path, params, timeout, retries)
    except Exception:
        return default if default is not None else {}
