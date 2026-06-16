# -*- coding: utf-8 -*-
"""
Stock Analyzer 脚本模块
"""

from .analyzer import (
    fetch_kline,
    fetch_realtime_quote,
    fetch_fund_flow,
    fetch_north_flow,
    fetch_stock_news,
    fetch_industry_boards,
    fetch_financial_report,
    get_stock_name,
    calculate_indicators,
    calculate_financial_health,
    calculate_rating,
    calculate_weighted_score,
    compare_stocks_wrapper,
    analyze_sector_wrapper,
    generate_report,
    analyze_stock,
)

from .market_utils import get_market_info, convert_price, is_hk_stock, get_secid
from .technical_indicators import calculate_extended_indicators
from .valuation_analysis import analyze_valuation_percentile
from .industry_analysis import analyze_industry_comparison
from .sentiment import analyze_sentiment, summarize_sentiment
from .risk_control import (
    calc_dynamic_stop_loss,
    calc_target_price,
    calc_support_resistance,
    calc_position_size,
    check_risk_rules,
    detect_board_type,
)
from .comparison import (
    compare_two_stocks,
    generate_comparison_table,
    get_sector_stocks,
    analyze_sector,
)
from .utils import _http_get, _http_get_safe

# AKShare 备选数据源（可选依赖，未安装时自动降级）
try:
    from .akshare_sources import (
        HAS_AKSHARE, check_akshare_health,
        fetch_kline_akshare, fetch_quote_akshare,
        fetch_financial_report_akshare,
    )
except ImportError:
    HAS_AKSHARE = False
    check_akshare_health = lambda: {"AKShare(未安装)": False}
    fetch_kline_akshare = None
    fetch_quote_akshare = None
    fetch_financial_report_akshare = None

# 统一数据源管理器
from .datasource_manager import DataSourceManager, get_datasource_manager
