#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
行业对比分析模块 — 分析同行业股票的估值、资金流向、行业景气度和龙头溢价

功能：
- get_stock_industry: 获取股票所属行业代码
- fetch_industry_peers: 获取同行业股票列表
- analyze_valuation_comparison: 估值对比分析
- analyze_fund_flow_comparison: 资金流向对比
- analyze_industry_sentiment: 行业景气度分析
- analyze_leader_premium: 龙头溢价分析
- analyze_industry_comparison: 行业对比分析主函数

依赖：
- analyze_stock 中的 _http_get_safe（复用已有 HTTP 封装）
- market_utils 中的 get_market_info、get_secid
"""

from .utils import _http_get_safe, safe_num as _safe_float
from .market_utils import get_market_info, get_secid

# API 常量 — 板块接口专用 token（与个股接口 token 不同）
UT_TOKEN = "bd1d9ddb04089700cf9c27f6f7426281"


def get_stock_industry(code):
    """
    获取股票所属行业。

    使用东方财富 API 获取股票的行业板块信息。

    Args:
        code: 股票代码（如 '600519'）

    Returns:
        str: 行业代码（如 'BK0477'），获取失败返回空字符串

    Examples:
        >>> get_stock_industry('600519')
        'BK0477'
    """
    try:
        market_code, market_id, _ = get_market_info(code)
    except ValueError:
        return ""

    # 使用东方财富个股信息接口获取行业
    params = {
        "secid": get_secid(code, market_id),
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        "fields": "f57,f58,f127,f128,f193",
        "invt": "2",
    }
    j = _http_get_safe("push2.eastmoney.com", "/api/qt/stock/get", params)
    if not j or not j.get("data"):
        return ""

    data = j["data"]
    # f127 是行业板块代码
    industry_code = data.get("f127", "")
    if industry_code:
        return str(industry_code)

    # 备用方案：从行业板块列表中查找
    return _find_industry_from_board(code, market_code)


def _find_industry_from_board(code, market_code):
    """
    从行业板块列表中查找股票所属行业（备用方案）。

    Args:
        code: 股票代码
        market_code: 市场代码（'SH'/'SZ'/'HK'）

    Returns:
        str: 行业代码，未找到返回空字符串
    """
    # 获取行业板块列表
    params = {
        "pn": "1", "pz": "200", "po": "1", "np": "1",
        "ut": UT_TOKEN,
        "fltt": "2", "invt": "2", "fid": "f3",
        "fs": "m:90+t:2+f:!50",
        "fields": "f12,f14",
    }
    j = _http_get_safe("82.push2.eastmoney.com", "/api/qt/clist/get", params)
    if not j or not j.get("data"):
        return ""

    boards = j.get("data", {}).get("diff", [])
    # 遍历行业板块，查找股票所属行业（限制最多遍历 30 个板块，避免过多请求）
    # 性能影响：每个板块需一次 API 请求获取成员列表，最多 30 次串行请求
    for board in boards[:30]:
        board_code = board.get("f12", "")
        if not board_code:
            continue
        # 检查股票是否在该板块中
        member_params = {
            "pn": "1", "pz": "5000", "po": "1", "np": "1",
            "ut": UT_TOKEN,
            "fltt": "2", "invt": "2", "fid": "f12",
            "fs": f"b:{board_code}+f:!50",
            "fields": "f12",
        }
        member_j = _http_get_safe("82.push2.eastmoney.com", "/api/qt/clist/get", member_params)
        if not member_j or not member_j.get("data"):
            continue
        members = member_j.get("data", {}).get("diff", [])
        for member in members:
            if str(member.get("f12", "")) == code:
                return board_code

    return ""


def fetch_industry_peers(code):
    """
    获取同行业股票列表。

    首先获取股票所属行业，然后获取行业内所有股票的基本信息。

    Args:
        code: 股票代码（如 '600519'）

    Returns:
        list[dict]: 同行业股票列表，每项包含：
            - '代码': str
            - '名称': str
            - 'PE': float
            - 'PB': float
            - 'ROE': float
            - '总市值': float
        获取失败返回空列表

    Examples:
        >>> peers = fetch_industry_peers('600519')
        >>> len(peers) > 0
        True
    """
    industry_code = get_stock_industry(code)
    if not industry_code:
        return []

    # 获取行业内所有股票
    params = {
        "pn": "1", "pz": "5000", "po": "1", "np": "1",
        "ut": UT_TOKEN,
        "fltt": "2", "invt": "2", "fid": "f20",
        "fs": f"b:{industry_code}+f:!50",
        "fields": "f2,f3,f9,f12,f14,f20,f21,f23,f37,f115,f128,f152",
    }
    j = _http_get_safe("82.push2.eastmoney.com", "/api/qt/clist/get", params)
    if not j or not j.get("data"):
        return []

    items = j.get("data", {}).get("diff", [])
    peers = []
    for item in items:
        stock_code = str(item.get("f12", ""))
        if not stock_code:
            continue
        peers.append({
            '代码': stock_code,
            '名称': item.get("f14", ""),
            'PE': _safe_float(item.get("f9", 0)),
            'PB': _safe_float(item.get("f23", 0)),
            'ROE': _safe_float(item.get("f37", 0)),
            '总市值': _safe_float(item.get("f20", 0)),
        })

    return peers


def analyze_valuation_comparison(code, peers):
    """
    分析估值对比。

    按 PE 排名（从低到高）、PB 排名（从低到高）、ROE 排名（从高到低），
    并生成综合估值排名。

    Args:
        code: 股票代码（如 '600519'）
        peers: 同行业股票列表（来自 fetch_industry_peers）

    Returns:
        dict: {
            'PE排名': int,
            'PB排名': int,
            'ROE排名': int,
            '估值排名': list  # 综合估值排名，按 PE 升序排列的股票列表
        }

    Examples:
        >>> result = analyze_valuation_comparison('600519', peers)
        >>> 'PE排名' in result
        True
    """
    if not peers:
        return {'PE排名': 0, 'PB排名': 0, 'ROE排名': 0, '估值排名': [], '排名说明': '无同行数据'}

    # 过滤有效数据（PE > 0 的股票）
    valid_peers = [p for p in peers if p.get('PE', 0) > 0]

    if not valid_peers:
        return {'PE排名': 0, 'PB排名': 0, 'ROE排名': 0, '估值排名': [], '排名说明': '不适用（亏损或数据缺失）'}

    # 按 PE 排名（从低到高）
    pe_sorted = sorted(valid_peers, key=lambda x: x.get('PE', float('inf')))
    pe_rank = 0
    for i, p in enumerate(pe_sorted, 1):
        if p['代码'] == code:
            pe_rank = i
            break

    # 按 PB 排名（从低到高）
    pb_sorted = sorted(valid_peers, key=lambda x: x.get('PB', float('inf')))
    pb_rank = 0
    for i, p in enumerate(pb_sorted, 1):
        if p['代码'] == code:
            pb_rank = i
            break

    # 按 ROE 排名（从高到低）
    roe_sorted = sorted(valid_peers, key=lambda x: x.get('ROE', float('-inf')), reverse=True)
    roe_rank = 0
    for i, p in enumerate(roe_sorted, 1):
        if p['代码'] == code:
            roe_rank = i
            break

    # 综合估值排名（按 PE 升序）
    valuation_rank = []
    for i, p in enumerate(pe_sorted, 1):
        valuation_rank.append({
            '排名': i,
            '代码': p['代码'],
            '名称': p['名称'],
            'PE': p['PE'],
            'PB': p['PB'],
            'ROE': p['ROE'],
            '总市值': p['总市值'],
        })

    result = {
        'PE排名': pe_rank,
        'PB排名': pb_rank,
        'ROE排名': roe_rank,
        '估值排名': valuation_rank,
    }

    # 排名为 0 表示该股票不在有效对比范围内（亏损或数据缺失）
    if pe_rank == 0 and pb_rank == 0 and roe_rank == 0:
        result['排名说明'] = '不适用（亏损或数据缺失）'

    return result


def analyze_fund_flow_comparison(code, peers):
    """
    分析资金流向对比。

    获取行业内各股票的资金流向，按今日主力净流入和 5 日主力净流入排名。

    Args:
        code: 股票代码（如 '600519'）
        peers: 同行业股票列表（来自 fetch_industry_peers）

    Returns:
        dict: {
            '今日排名': list,  # 按今日主力净流入排名
            '5日排名': list,   # 按 5 日主力净流入排名
        }

    Examples:
        >>> result = analyze_fund_flow_comparison('600519', peers)
        >>> '今日排名' in result
        True
    """
    if not peers:
        return {'今日排名': [], '5日排名': []}

    # 限制请求数量：只取市值前 15 名，避免大量 API 请求导致被限流
    top_peers = sorted(peers, key=lambda x: x.get('总市值', 0), reverse=True)[:15]

    # 获取行业内各股票的资金流向
    # 性能瓶颈：逐股调用 API，每只股票一次 HTTP 请求，15 只约需 30-60 秒
    flow_data = []
    for i, peer in enumerate(top_peers):
        peer_code = peer['代码']
        peer_name = peer['名称']
        print(f"  获取资金流向 {i+1}/{len(top_peers)}...")

        # 获取个股资金流向
        params = {
            "secid": get_secid(peer_code, _get_market_id(peer_code)),
            "ut": "7eea3edcaed734bea9cbfc24409ed989",
            "fields": "f62,f184,f164,f174",
        }
        j = _http_get_safe("push2.eastmoney.com", "/api/qt/stock/get", params)
        if not j or not j.get("data"):
            flow_data.append({
                '代码': peer_code,
                '名称': peer_name,
                '今日主力净流入': 0,
                '5日主力净流入': 0,
            })
            continue

        data = j["data"]
        flow_data.append({
            '代码': peer_code,
            '名称': peer_name,
            '今日主力净流入': _safe_float(data.get("f62", 0)),
            '5日主力净流入': _safe_float(data.get("f164", 0)),
        })

    # 按今日主力净流入排名（从高到低）
    today_sorted = sorted(flow_data, key=lambda x: x['今日主力净流入'], reverse=True)
    today_rank = []
    for i, item in enumerate(today_sorted, 1):
        today_rank.append({
            '排名': i,
            '代码': item['代码'],
            '名称': item['名称'],
            '今日主力净流入': item['今日主力净流入'],
        })

    # 按 5 日主力净流入排名（从高到低）
    five_day_sorted = sorted(flow_data, key=lambda x: x['5日主力净流入'], reverse=True)
    five_day_rank = []
    for i, item in enumerate(five_day_sorted, 1):
        five_day_rank.append({
            '排名': i,
            '代码': item['代码'],
            '名称': item['名称'],
            '5日主力净流入': item['5日主力净流入'],
        })

    return {
        '今日排名': today_rank,
        '5日排名': five_day_rank,
    }


def _get_market_id(code):
    """
    获取股票的市场 ID。

    Args:
        code: 股票代码

    Returns:
        int: 市场 ID（116/1/0），失败返回 0
    """
    try:
        _, market_id, _ = get_market_info(code)
        return market_id
    except ValueError:
        return 0


def analyze_industry_sentiment(industry_code):
    """
    分析行业景气度。

    获取行业涨跌幅、换手率，判断资金流入/流出，评估景气度。

    Args:
        industry_code: 行业代码（如 'BK0477'）

    Returns:
        dict: {
            '涨跌幅': float,
            '换手率': float,
            '资金流入': str,  # '流入' 或 '流出'
            '景气度': str     # '高景气' / '中性' / '低景气'
        }

    Examples:
        >>> result = analyze_industry_sentiment('BK0477')
        >>> '景气度' in result
        True
    """
    result = {
        '涨跌幅': 0.0,
        '换手率': 0.0,
        '资金流入': '未知',
        '景气度': '中性',
    }

    if not industry_code:
        return result

    # 获取行业板块数据
    params = {
        "pn": "1", "pz": "200", "po": "1", "np": "1",
        "ut": UT_TOKEN,
        "fltt": "2", "invt": "2", "fid": "f3",
        "fs": "m:90+t:2+f:!50",
        "fields": "f2,f3,f8,f12,f14,f62,f104,f105",
    }
    j = _http_get_safe("82.push2.eastmoney.com", "/api/qt/clist/get", params)
    if not j or not j.get("data"):
        return result

    boards = j.get("data", {}).get("diff", [])
    for board in boards:
        if board.get("f12", "") == industry_code:
            change_pct = _safe_float(board.get("f3", 0))
            turnover = _safe_float(board.get("f8", 0))
            fund_flow = _safe_float(board.get("f62", 0))
            up_count = _safe_float(board.get("f104", 0))
            down_count = _safe_float(board.get("f105", 0))

            result['涨跌幅'] = change_pct
            result['换手率'] = turnover

            # 判断资金流入/流出
            if fund_flow > 0:
                result['资金流入'] = '流入'
            elif fund_flow < 0:
                result['资金流入'] = '流出'
            else:
                result['资金流入'] = '平衡'

            # 评估景气度
            result['景气度'] = _evaluate_sentiment(change_pct, turnover, fund_flow, up_count, down_count)
            break

    return result


def _evaluate_sentiment(change_pct, turnover, fund_flow, up_count, down_count):
    """
    评估行业景气度。

    Args:
        change_pct: 行业涨跌幅
        turnover: 行业换手率
        fund_flow: 行业资金净流入
        up_count: 上涨家数
        down_count: 下跌家数

    Returns:
        str: '高景气' / '中性' / '低景气'
    """
    score = 0

    # 涨跌幅评分
    if change_pct > 2:
        score += 2
    elif change_pct > 0:
        score += 1
    elif change_pct < -2:
        score -= 2
    elif change_pct < 0:
        score -= 1

    # 资金流向评分
    if fund_flow > 0:
        score += 1
    elif fund_flow < 0:
        score -= 1

    # 涨跌家数比评分
    total = up_count + down_count
    if total > 0:
        up_ratio = up_count / total
        if up_ratio > 0.7:
            score += 1
        elif up_ratio < 0.3:
            score -= 1

    # 换手率评分（适度活跃是好事）
    if turnover > 3:
        score += 0.5
    elif turnover < 0.5:
        score -= 0.5

    # 综合判断
    if score >= 2:
        return '高景气'
    elif score <= -1:
        return '低景气'
    else:
        return '中性'


def analyze_leader_premium(code, peers):
    """
    分析龙头溢价。

    识别龙头公司（市值最大），计算行业平均 PE，计算溢价率，判断溢价合理性。

    Args:
        code: 股票代码（如 '600519'）
        peers: 同行业股票列表（来自 fetch_industry_peers）

    Returns:
        dict: {
            '龙头公司': str,
            '龙头PE': float,
            '行业平均PE': float,
            '溢价率': float,
            '溢价合理性': str
        }

    Examples:
        >>> result = analyze_leader_premium('600519', peers)
        >>> '龙头公司' in result
        True
    """
    result = {
        '龙头公司': '',
        '龙头PE': 0.0,
        '行业平均PE': 0.0,
        '溢价率': 0.0,
        '溢价合理性': '数据不足',
    }

    if not peers:
        return result

    # 过滤有效数据
    valid_peers = [p for p in peers if p.get('PE', 0) > 0 and p.get('总市值', 0) > 0]

    if not valid_peers:
        return result

    # 识别龙头公司（市值最大）
    leader = max(valid_peers, key=lambda x: x['总市值'])
    result['龙头公司'] = leader['名称']
    result['龙头PE'] = leader['PE']

    # 计算行业平均 PE（排除极端值）
    pe_values = [p['PE'] for p in valid_peers if 0 < p['PE'] < 1000]
    if pe_values:
        avg_pe = sum(pe_values) / len(pe_values)
        result['行业平均PE'] = round(avg_pe, 2)

        # 计算溢价率
        if avg_pe > 0:
            premium_rate = (leader['PE'] - avg_pe) / avg_pe * 100
            result['溢价率'] = round(premium_rate, 2)

            # 判断溢价合理性
            result['溢价合理性'] = _evaluate_premium_reasonableness(
                premium_rate, leader['ROE'], leader['PE'], avg_pe
            )

    return result


def _evaluate_premium_reasonableness(premium_rate, leader_roe, leader_pe, avg_pe):
    """
    判断龙头溢价的合理性。

    Args:
        premium_rate: 溢价率（百分比）
        leader_roe: 龙头 ROE
        leader_pe: 龙头 PE
        avg_pe: 行业平均 PE

    Returns:
        str: 溢价合理性描述
    """
    # 高 ROE 可以支撑一定溢价
    if leader_roe > 20 and premium_rate < 50:
        return '合理（高 ROE 支撑）'
    elif leader_roe > 15 and premium_rate < 30:
        return '合理（ROE 较高）'

    # 根据溢价率判断
    if premium_rate < 0:
        return '低估（低于行业平均）'
    elif premium_rate < 20:
        return '合理（小幅溢价）'
    elif premium_rate < 50:
        return '偏高（中等溢价）'
    elif premium_rate < 100:
        return '较高（大幅溢价）'
    else:
        return '过高（溢价过高，需警惕）'


def analyze_industry_comparison(code):
    """
    行业对比分析主函数。

    调用所有子函数，返回完整的行业对比分析结果。

    Args:
        code: 股票代码（如 '600519'）

    Returns:
        dict: {
            '行业': str,
            '估值对比': dict,
            '资金流向': dict,
            '行业景气度': dict,
            '龙头溢价': dict
        }

    Examples:
        >>> result = analyze_industry_comparison('600519')
        >>> '行业' in result
        True
    """
    # 1. 获取行业信息
    industry_code = get_stock_industry(code)

    # 2. 获取同行业股票列表
    peers = fetch_industry_peers(code)

    # 3. 分析估值对比
    valuation_comparison = analyze_valuation_comparison(code, peers)

    # 4. 分析资金流向对比
    fund_flow_comparison = analyze_fund_flow_comparison(code, peers)

    # 5. 分析行业景气度
    industry_sentiment = analyze_industry_sentiment(industry_code)

    # 6. 分析龙头溢价
    leader_premium = analyze_leader_premium(code, peers)

    return {
        '行业': industry_code,
        '估值对比': valuation_comparison,
        '资金流向': fund_flow_comparison,
        '行业景气度': industry_sentiment,
        '龙头溢价': leader_premium,
    }
