#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票综合分析工具 — 绕过系统代理直连东方财富 API
用法: python stock_analyzer.py 000001 600519 00700 ...
输出: 在当前目录下创建 股票代码-股票名称/ 文件夹，内含多维度分析报告
"""

import argparse
import traceback

from scripts.analyzer import analyze_stock


def main():
    parser = argparse.ArgumentParser(description="股票综合分析工具（支持 A 股和港股）")
    parser.add_argument("codes", nargs="+", help="股票代码，如 000001 600519 00700")
    parser.add_argument("--output", "-o", default=".", help="输出目录（默认当前目录）")
    args = parser.parse_args()

    for code in args.codes:
        code = code.strip()
        try:
            analyze_stock(code, args.output)
        except Exception as e:
            print(f"\n分析 {code} 时出错: {e}")
            traceback.print_exc()


if __name__ == "__main__":
    main()
