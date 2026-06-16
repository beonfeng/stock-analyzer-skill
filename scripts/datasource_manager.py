#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一数据源管理器 — 多源自动回退 + 健康检查 + 调用统计

提供 DataSourceManager 类，封装各数据源（东方财富/AKShare/腾讯/新浪）的
优先级链和自动回退逻辑。不替代 analyzer.py 中的现有回退实现，而是作为
统一的抽象层，便于后续数据源的扩展和管理。

设计目标：
- 每个数据类型的 fetch 方法按优先级链尝试各数据源
- 自动标记 _source 便于报告溯源
- 健康检查支持主动探测数据源可用性
- 统计各源调用次数，辅助监控数据源质量

使用示例:
    from scripts.datasource_manager import DataSourceManager
    mgr = DataSourceManager()
    df, source = mgr.fetch_kline("600519", days=500)
    print(f"K线来自: {source}")
    print(mgr.get_stats())
"""

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple


class DataSourceManager:
    """
    统一数据源管理器。

    按优先级链管理多个数据源，提供统一的 fetch 接口和自动回退。
    每个 fetch 方法返回 (data, source_name)，失败均返回 (None, None)。

    数据源优先级：
    - K线:         EastMoney > AKShare > Tencent > Sina
    - 实时行情:    EastMoney > AKShare > Tencent > Sina
    - 资金流向:    EastMoney > Tencent（AKShare 暂不支持）
    - 财务报表:    EastMoney > AKShare（Tencent/Sina 不覆盖）
    - 公司概况:    EastMoney > AKShare（Tencent/Sina 不覆盖）
    - 资讯:        EastMoney > AKShare（Tencent/Sina 不覆盖）
    - 行业板块:    EastMoney only
    - 北向资金:    EastMoney only
    """

    def __init__(self):
        self._stats: Dict[str, int] = defaultdict(int)  # 各源成功调用次数
        self._fails: Dict[str, int] = defaultdict(int)  # 各源失败次数

        # 延迟导入以避免循环依赖
        self._akshare_imported = None

    # ---- 内部工具 ----

    def _record(self, source: str, success: bool):
        if success:
            self._stats[source] += 1
        else:
            self._fails[source] += 1

    def _has_akshare(self) -> bool:
        if self._akshare_imported is None:
            try:
                from . import akshare_sources
                self._akshare_imported = akshare_sources.HAS_AKSHARE
            except ImportError:
                self._akshare_imported = False
        return self._akshare_imported

    # ---- K 线 ----

    def fetch_kline(self, code: str, days: int = 500) -> Tuple[Any, Optional[str]]:
        """
        按优先级链获取 K 线数据。

        Returns:
            (pd.DataFrame, source_name): 成功时 source_name 为数据源名称
            (pd.DataFrame(), None): 所有数据源均失败
        """
        import pandas as pd
        from . import analyzer as _analyzer
        from . import alternative_sources as _alt

        # 优先级 1: 东方财富
        try:
            # 直接调用 analyzer 的 fetch_kline（包含完整的东方财富逻辑）
            # 但这里我们需要分步尝试，所以手动实现
            from .market_utils import get_market_info, get_secid
            from .utils import _http_get, _http_get_safe
            import datetime

            market_code, market_id, _ = get_market_info(code)
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
            if market_code == 'HK':
                j = _http_get("push2his.eastmoney.com", "/api/qt/stock/kline/get",
                             params, timeout=20, retries=12)
            else:
                j = _http_get("push2his.eastmoney.com", "/api/qt/stock/kline/get", params)
            klines = j.get("data", {}).get("klines", [])
            if klines:
                from .analyzer import safe_num
                rows = []
                for line in klines:
                    parts = line.split(",")
                    if len(parts) >= 11:
                        rows.append({
                            "日期": parts[0],
                            "开盘": safe_num(parts[1], 0.0),
                            "收盘": safe_num(parts[2], 0.0),
                            "最高": safe_num(parts[3], 0.0),
                            "最低": safe_num(parts[4], 0.0),
                            "成交量": safe_num(parts[5], 0.0),
                            "成交额": safe_num(parts[6], 0.0),
                            "振幅": safe_num(parts[7], 0.0),
                            "涨跌幅": safe_num(parts[8], 0.0),
                            "涨跌额": safe_num(parts[9], 0.0),
                            "换手率": safe_num(parts[10], 0.0),
                        })
                self._record("EastMoney", True)
                return pd.DataFrame(rows), "EastMoney"
        except Exception:
            pass
        self._record("EastMoney", False)

        # 优先级 2: AKShare
        if self._has_akshare():
            try:
                from . import akshare_sources as _ak
                df = _ak.fetch_kline_akshare(code, days=days)
                if df is not None and not df.empty:
                    self._record("AKShare", True)
                    return df, "AKShare"
            except Exception:
                pass
        self._record("AKShare", False)

        # 优先级 3: 腾讯
        try:
            df = _alt.fetch_kline_tencent(code, days=days)
            if df is not None and not df.empty:
                self._record("Tencent", True)
                return df, "Tencent"
        except Exception:
            pass
        self._record("Tencent", False)

        # 优先级 4: 新浪
        try:
            df = _alt.fetch_kline_sina(code, days=days)
            if df is not None and not df.empty:
                self._record("Sina", True)
                return df, "Sina"
        except Exception:
            pass
        self._record("Sina", False)

        return pd.DataFrame(), None

    # ---- 实时行情 ----

    def fetch_quote(self, code: str) -> Tuple[Optional[Dict], Optional[str]]:
        """
        按优先级链获取实时行情。

        Returns:
            (dict, source_name): 成功时返回东方财富兼容格式 dict
            (None, None): 所有数据源均失败
        """
        from . import analyzer as _analyzer

        # 优先级 1: EastMoney
        try:
            quote = _analyzer.fetch_realtime_quote(code)
            if quote and quote.get("f2", 0) > 0:
                src = quote.get("_source", "EastMoney")
                self._record(src, True)
                return quote, src if src != "EastMoney" else "EastMoney"
        except Exception:
            pass
        self._record("EastMoney", False)

        # 优先级 2: AKShare
        if self._has_akshare():
            try:
                from . import akshare_sources as _ak
                q = _ak.fetch_quote_akshare(code)
                if q and q.get("f2", 0) > 0:
                    self._record("AKShare", True)
                    return q, "AKShare"
            except Exception:
                pass
        self._record("AKShare", False)

        # 优先级 3: 腾讯
        try:
            from . import alternative_sources as _alt
            q = _alt.fetch_quote_tencent(code)
            if q and q.get("f2", 0) > 0:
                self._record("Tencent", True)
                return q, "Tencent"
        except Exception:
            pass
        self._record("Tencent", False)

        # 优先级 4: 新浪
        try:
            from . import alternative_sources as _alt
            q = _alt.fetch_quote_sina(code)
            if q and q.get("f2", 0) > 0:
                self._record("Sina", True)
                return q, "Sina"
        except Exception:
            pass
        self._record("Sina", False)

        return None, None

    # ---- 财务报表 ----

    def fetch_financial(self, code: str) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """
        按优先级链获取财务报表。

        Returns:
            (list[dict], source_name)
            (None, None): 全部失败
        """
        from . import analyzer as _analyzer

        # 优先级 1: EastMoney
        try:
            data = _analyzer.fetch_financial_report(code)
            if data:
                self._record("EastMoney", True)
                return data, "EastMoney"
        except Exception:
            pass
        self._record("EastMoney", False)

        # 优先级 2: AKShare（此时无其他备选源）
        if self._has_akshare():
            try:
                from . import akshare_sources as _ak
                data = _ak.fetch_financial_report_akshare(code)
                if data:
                    self._record("AKShare", True)
                    return data, "AKShare"
            except Exception:
                pass
        self._record("AKShare", False)

        return None, None

    # ---- 公司概况 ----

    def fetch_company_profile(self, code: str) -> Tuple[Optional[Dict], Optional[str]]:
        """
        按优先级链获取公司概况。

        Returns:
            (dict, source_name)
            (None, None): 全部失败
        """
        from . import analyzer as _analyzer

        # 优先级 1: EastMoney
        try:
            profile = _analyzer.fetch_company_profile(code)
            if profile and profile.get("基本信息"):
                self._record("EastMoney", True)
                return profile, "EastMoney"
        except Exception:
            pass
        self._record("EastMoney", False)

        # 优先级 2: AKShare
        if self._has_akshare():
            try:
                from . import akshare_sources as _ak
                profile = _ak.fetch_company_profile_akshare(code)
                if profile and profile.get("基本信息"):
                    self._record("AKShare", True)
                    return profile, "AKShare"
            except Exception:
                pass
        self._record("AKShare", False)

        return None, None

    # ---- 健康检查 ----

    def check_all_health(self) -> Dict[str, Dict[str, bool]]:
        """
        全源健康检查。

        Returns:
            {source_group: {source_name: bool}}
            例如: {"main": {"EastMoney": True}, "alt": {"Tencent": True, ...}, "akshare": {"K线": True, ...}}
        """
        from . import alternative_sources as _alt

        health: Dict[str, Dict[str, bool]] = {}

        # 备选源（腾讯/新浪）
        health["alt"] = _alt.check_source_health()

        # AKShare
        if self._has_akshare():
            try:
                from . import akshare_sources as _ak
                health["akshare"] = _ak.check_akshare_health()
            except Exception:
                health["akshare"] = {"AKShare(异常)": False}
        else:
            health["akshare"] = {"AKShare(未安装)": False}

        return health

    # ---- 统计 ----

    def get_stats(self) -> Dict[str, Dict[str, int]]:
        """
        获取数据源调用统计。

        Returns:
            {"success": {source: count}, "fail": {source: count}}
        """
        return {
            "success": dict(self._stats),
            "fail": dict(self._fails),
        }

    def reset_stats(self):
        """重置统计数据。"""
        self._stats.clear()
        self._fails.clear()


# ============================================================
# 模块级单例
# ============================================================

_data_source_manager: Optional[DataSourceManager] = None


def get_datasource_manager() -> DataSourceManager:
    """获取模块级单例 DataSourceManager。"""
    global _data_source_manager
    if _data_source_manager is None:
        _data_source_manager = DataSourceManager()
    return _data_source_manager


# ============================================================
# 模块自测
# ============================================================

if __name__ == "__main__":
    import sys
    sys.path.insert(0, "..")

    print("=" * 60)
    print("DataSourceManager 测试")
    print("=" * 60)

    mgr = DataSourceManager()

    print("\n--- 健康检查 ---")
    health = mgr.check_all_health()
    for group, srcs in health.items():
        for name, ok in srcs.items():
            print(f"  {'[OK]' if ok else '[FAIL]'} {group}/{name}")

    print("\n--- K线获取 (600519) ---")
    df, src = mgr.fetch_kline("600519", days=10)
    if src:
        print(f"  来源: {src}, 行数: {len(df)}")
    else:
        print("  全部失败")

    print("\n--- 调用统计 ---")
    print(mgr.get_stats())
    print("=" * 60)
