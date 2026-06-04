#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票综合分析工具 — 绕过系统代理直连东方财富 API

用法:
  python stock_analyzer.py 000001 600519           # 分析股票
  python stock_analyzer.py compare 600519 000858   # 双股对比
  python stock_analyzer.py sector 白酒             # 板块分析
"""

import argparse
import traceback

from scripts.analyzer import (
    analyze_stock,
    compare_stocks_wrapper,
    analyze_sector_wrapper,
    resolve_stock_code,
)
from scripts.comparison import generate_comparison_table


def cmd_analyze(args):
    """分析股票"""
    for code in args.codes:
        code = code.strip()
        # 支持股票名称输入，自动转换为代码
        code = resolve_stock_code(code)
        try:
            analyze_stock(code, args.output)
        except Exception as e:
            print(f"\n分析 {code} 时出错: {e}")
            traceback.print_exc()


def cmd_compare(args):
    """双股对比"""
    # 支持股票名称输入，自动转换为代码
    code_a = resolve_stock_code(args.code_a.strip())
    code_b = resolve_stock_code(args.code_b.strip())

    print(f"\n{'='*60}")
    print(f"  双股对比: {code_a} vs {code_b}")
    print(f"{'='*60}")

    try:
        result = compare_stocks_wrapper(code_a, code_b)

        # 打印对比表格
        name_a = result.get("comparison", [{}])[0].get("stock_a", code_a)
        name_b = result.get("comparison", [{}])[0].get("stock_b", code_b)

        # 从结果中获取名称
        from scripts.analyzer import get_stock_name
        name_a = get_stock_name(code_a)
        name_b = get_stock_name(code_b)

        table = generate_comparison_table(result["comparison"], name_a, name_b)
        print(f"\n{table}")
        print(f"\n**结论**: {result['summary']}")

        # 保存报告
        if args.output:
            from pathlib import Path
            import datetime
            today = datetime.date.today().strftime("%Y%m%d")
            filename = f"对比-{code_a}vs{code_b}-{today}.md"
            filepath = Path(args.output) / filename

            report = f"# 双股对比: {name_a} vs {name_b}\n\n"
            report += f"> 生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            report += f"## 对比总结\n\n**{result['summary']}**\n\n"
            report += f"{table}\n\n"
            report += "## 风险提示\n\n- 以上分析基于公开数据自动计算，仅供参考，不构成投资建议\n- 股市有风险，投资需谨慎\n"

            filepath.write_text(report, encoding="utf-8")
            print(f"\n报告已保存: {filepath}")

    except Exception as e:
        print(f"\n对比分析时出错: {e}")
        traceback.print_exc()


def cmd_sector(args):
    """板块分析"""
    sector_name = args.sector.strip()

    print(f"\n{'='*60}")
    print(f"  板块分析: {sector_name}")
    print(f"{'='*60}")

    try:
        result = analyze_sector_wrapper(sector_name)

        if "error" in result:
            print(f"\n错误: {result['error']}")
            return

        # 打印板块概况
        print(f"\n**板块趋势**: {result['trend']}")
        print(f"**平均涨跌**: {result['avg_change']}%")
        print(f"**上涨家数**: {result['up_count']} 家")
        print(f"**下跌家数**: {result['down_count']} 家")
        print(f"**分析股票数**: {result['stocks_count']} 家")

        # 打印个股详情
        if "stocks" in result:
            print(f"\n**代表性股票**:")
            print(f"| 代码 | 名称 | 涨跌幅 |")
            print(f"|------|------|--------|")
            for stock in result.get("stocks", []):
                print(f"| {stock.get('code', '')} | {stock.get('name', '')} | {stock.get('change_pct', 0):.2f}% |")

        # 保存报告
        if args.output:
            from pathlib import Path
            import datetime
            today = datetime.date.today().strftime("%Y%m%d")
            filename = f"板块-{sector_name}-{today}.md"
            filepath = Path(args.output) / filename

            report = f"# 板块分析: {sector_name}\n\n"
            report += f"> 生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            report += f"## 板块概况\n\n"
            report += f"- **板块趋势**: {result['trend']}\n"
            report += f"- **平均涨跌**: {result['avg_change']}%\n"
            report += f"- **上涨家数**: {result['up_count']} 家\n"
            report += f"- **下跌家数**: {result['down_count']} 家\n"
            report += f"- **分析股票数**: {result['stocks_count']} 家\n\n"

            if "stocks" in result:
                report += "## 代表性股票\n\n"
                report += "| 代码 | 名称 | 涨跌幅 |\n"
                report += "|------|------|--------|\n"
                for stock in result.get("stocks", []):
                    report += f"| {stock.get('code', '')} | {stock.get('name', '')} | {stock.get('change_pct', 0):.2f}% |\n"

            report += "\n## 风险提示\n\n- 以上分析基于公开数据自动计算，仅供参考，不构成投资建议\n- 股市有风险，投资需谨慎\n"

            filepath.write_text(report, encoding="utf-8")
            print(f"\n报告已保存: {filepath}")

    except Exception as e:
        print(f"\n板块分析时出错: {e}")
        traceback.print_exc()


def main():
    import sys

    # 预处理参数：如果没有指定子命令，默认使用 analyze
    args_list = sys.argv[1:]
    known_commands = ["analyze", "compare", "sector", "--help", "-h", "--version", "-v"]

    # 检查是否需要添加默认子命令
    need_analyze = False
    if not args_list:
        # 没有参数，显示帮助
        need_analyze = False
    elif args_list[0] not in known_commands and not args_list[0].startswith('-'):
        # 第一个参数不是已知命令也不是选项，认为是股票代码
        need_analyze = True

    if need_analyze:
        sys.argv = [sys.argv[0], "analyze"] + args_list

    parser = argparse.ArgumentParser(
        prog="stock_analyzer",
        description="""
╔══════════════════════════════════════════════════════════════╗
║           Stock Analyzer - A股综合分析工具                   ║
║           基于东方财富 API 直连，自动生成分析报告             ║
╚══════════════════════════════════════════════════════════════╝
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
使用示例:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  # 分析单只股票
  python stock_analyzer.py 000333

  # 批量分析多只股票
  python stock_analyzer.py 000333 600519 300750

  # 双股对比分析
  python stock_analyzer.py compare 600519 000858

  # 板块分析
  python stock_analyzer.py sector 白酒

  # 指定输出目录
  python stock_analyzer.py -o ./reports 600519

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
支持板块:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  白酒 | 新能源 | 半导体 | 银行 | 医药 | 消费 | 科技 | 地产 | 军工 | 汽车
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
输出说明:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  分析报告保存到: 股票代码-股票名称/股票代码-股票名称-分析报告-日期.md
  对比报告保存到: 对比-代码A vs 代码B-日期.md
  板块报告保存到: 板块-板块名称-日期.md
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        """
    )
    parser.add_argument("--output", "-o", default=".", help="输出目录（默认当前目录）")
    parser.add_argument("--version", "-v", action="version", version="%(prog)s 1.1.0")

    # 创建子命令
    subparsers = parser.add_subparsers(dest="command", help="可用子命令")

    # analyze 子命令（默认）
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="分析股票（默认）",
        description="对股票进行多维度综合分析，生成16章节的完整报告"
    )
    analyze_parser.add_argument(
        "codes",
        nargs="+",
        help="股票代码（支持 A 股 6 位代码和港股 5 位代码）"
    )

    # compare 子命令
    compare_parser = subparsers.add_parser(
        "compare",
        help="双股对比",
        description="从7个维度横向对比两只股票：PE/PB/市值/涨跌/RSI/MACD/评级"
    )
    compare_parser.add_argument("code_a", help="股票 A 代码")
    compare_parser.add_argument("code_b", help="股票 B 代码")

    # sector 子命令
    sector_parser = subparsers.add_parser(
        "sector",
        help="板块分析",
        description="分析指定板块的代表性股票和整体趋势"
    )
    sector_parser.add_argument(
        "sector",
        help="板块名称",
        choices=["白酒", "新能源", "半导体", "银行", "医药", "消费", "科技", "地产", "军工", "汽车"]
    )

    args = parser.parse_args()

    # 执行对应命令
    if args.command == "analyze":
        cmd_analyze(args)
    elif args.command == "compare":
        cmd_compare(args)
    elif args.command == "sector":
        cmd_sector(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
