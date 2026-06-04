#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市场工具模块 - 判断股票市场类型和转换价格

支持市场：
- 港股 (HK)：5 位数字代码，如 00700、09988
- 上海 A 股 (SH)：6 开头的 6 位代码，如 600519
- 深圳 A 股 (SZ)：0 或 3 开头的 6 位代码，如 000001、300750

东方财富 API 市场 ID：
- 港股：116
- 上海：1
- 深圳：0
"""


def get_market_info(code):
    """
    根据股票代码判断市场类型。

    Args:
        code: 股票代码（字符串或数字）

    Returns:
        tuple: (market_code, market_id, price_divisor)
            - market_code: 市场代码，'HK'/'SH'/'SZ'
            - market_id: 东方财富 API 市场 ID，116/1/0
            - price_divisor: 价格除数，1000/100

    Raises:
        ValueError: 无法识别的股票代码格式

    Examples:
        >>> get_market_info('00700')
        ('HK', 116, 1000)
        >>> get_market_info('600519')
        ('SH', 1, 100)
        >>> get_market_info('000001')
        ('SZ', 0, 100)
    """
    code = str(code).strip()

    # 港股：5 位数字
    if len(code) == 5 and code.isdigit():
        return ('HK', 116, 1000)

    # A 股：6 位数字
    if len(code) == 6 and code.isdigit():
        if code.startswith('6'):
            return ('SH', 1, 100)
        elif code[0] in '03':
            return ('SZ', 0, 100)

    raise ValueError(f"无法识别的股票代码格式: {code}")


def convert_price(raw_price, market):
    """
    根据市场类型转换价格。

    Args:
        raw_price: 原始价格值（可能是数字、字符串、None 或 '-'）
        market: 市场代码，'HK'/'SH'/'SZ'

    Returns:
        float: 转换后的价格（浮点数），异常值返回 0.0 而非抛异常

    Raises:
        ValueError: 无效的市场类型（非 HK/SH/SZ）

    Examples:
        >>> convert_price(458200, 'HK')
        458.2
        >>> convert_price(8250, 'SH')
        82.5
        >>> convert_price(None, 'HK')
        0.0
    """
    # 处理异常值
    if raw_price is None or raw_price == '-' or raw_price == '':
        return 0.0

    try:
        price = float(raw_price)
    except (ValueError, TypeError):
        return 0.0

    # 根据市场类型除以对应除数
    divisors = {'HK': 1000, 'SH': 100, 'SZ': 100}
    if market not in divisors:
        raise ValueError(f"无效的市场类型: {market}")
    return price / divisors[market]


def is_hk_stock(code):
    """
    判断是否为港股。

    Args:
        code: 股票代码（字符串或数字）

    Returns:
        bool: 是港股返回 True，否则返回 False

    Examples:
        >>> is_hk_stock('00700')
        True
        >>> is_hk_stock('600519')
        False
    """
    try:
        market_code, _, _ = get_market_info(code)
        return market_code == 'HK'
    except ValueError:
        return False


def get_secid(code, market_id):
    """
    获取东方财富 API 的 secid 参数。

    Args:
        code: 股票代码
        market_id: 市场 ID（116/1/0）

    Returns:
        str: secid 字符串，格式为 "{market_id}.{code}"

    Examples:
        >>> get_secid('00700', 116)
        '116.00700'
        >>> get_secid('600519', 1)
        '1.600519'
    """
    return f"{market_id}.{code}"
