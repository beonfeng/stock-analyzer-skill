#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票综合分析工具 — 绕过系统代理直连东方财富 API

用法:
  python stock_analyzer.py 000001 600519           # 分析股票
  python stock_analyzer.py compare 600519 000858   # 双股对比
  python stock_analyzer.py sector 白酒             # 板块分析
  python stock_analyzer.py monitor                 # 反证清单监控
"""

import argparse
import traceback
import datetime

from scripts.analyzer import (
    analyze_stock,
    resolve_stock_code,
    fetch_realtime_quote,
    fetch_kline,
    calculate_indicators,
    fetch_fund_flow,
    calculate_financial_health,
    calculate_rating,
    get_stock_name,
    safe_num,
)
from scripts.comparison import generate_comparison_table, compare_two_stocks, get_sector_stocks, analyze_sector
from scripts.monitor import monitor_reports, format_monitor_report
from scripts.exporter import md_to_html, md_to_pdf, HAS_MARKDOWN, HAS_WEASYPRINT
from scripts.market_utils import is_us_stock


def _export_report(report_path: str, fmt: str):
    """根据格式导出报告（HTML/PDF）"""
    from pathlib import Path
    p = Path(report_path)
    md_content = p.read_text(encoding="utf-8")
    title = p.stem  # 文件名作为标题

    if fmt == "html":
        html_content = md_to_html(md_content, title)
        html_path = p.with_suffix(".html")
        html_path.write_text(html_content, encoding="utf-8")
        print(f"  [HTML] {html_path.name}")
        return str(html_path)
    elif fmt == "pdf":
        pdf_path = p.with_suffix(".pdf")
        actual_path = md_to_pdf(md_content, str(pdf_path), title)
        print(f"  [{'PDF' if actual_path.endswith('.pdf') else 'HTML降级'}] {Path(actual_path).name}")
        return actual_path
    return report_path


def cmd_analyze(args):
    """分析股票"""
    fmt = getattr(args, "format", "md") or "md"
    for code in args.codes:
        code = code.strip()
        # 支持股票名称输入，自动转换为代码
        code = resolve_stock_code(code)
        try:
            report_path = analyze_stock(code, args.output)
            # 导出 HTML/PDF
            if fmt != "md" and report_path:
                _export_report(report_path, fmt)
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
        # 获取股票 A 数据
        name_a = get_stock_name(code_a)
        quote_a = fetch_realtime_quote(code_a)
        df_a = fetch_kline(code_a, days=120)
        indicators_a = calculate_indicators(df_a)
        fund_flow_a = fetch_fund_flow(code_a)
        financial_health_a = calculate_financial_health(quote_a, {})
        rating_a = calculate_rating(indicators_a, financial_health_a, fund_flow_a)

        # 获取股票 B 数据
        name_b = get_stock_name(code_b)
        quote_b = fetch_realtime_quote(code_b)
        df_b = fetch_kline(code_b, days=120)
        indicators_b = calculate_indicators(df_b)
        fund_flow_b = fetch_fund_flow(code_b)
        financial_health_b = calculate_financial_health(quote_b, {})
        rating_b = calculate_rating(indicators_b, financial_health_b, fund_flow_b)

        # 构建对比数据
        stock_a = {
            "code": code_a,
            "name": name_a,
            "price": indicators_a.get("最新价", 0),
            "pe": quote_a.get("f9", 0),
            "pb": quote_a.get("f23", 0),
            "market_cap": safe_num(quote_a.get("f20", 0)),
            "change_pct": indicators_a.get("涨跌幅_今日", 0),
            "indicators": indicators_a,
            "fund_flow": fund_flow_a,
            "quote": quote_a,
            "rating": rating_a,
        }

        stock_b = {
            "code": code_b,
            "name": name_b,
            "price": indicators_b.get("最新价", 0),
            "pe": quote_b.get("f9", 0),
            "pb": quote_b.get("f23", 0),
            "market_cap": safe_num(quote_b.get("f20", 0)),
            "change_pct": indicators_b.get("涨跌幅_今日", 0),
            "indicators": indicators_b,
            "fund_flow": fund_flow_b,
            "quote": quote_b,
            "rating": rating_b,
        }

        # 执行对比
        result = compare_two_stocks(stock_a, stock_b)

        # 生成增强版报告
        report = generate_enhanced_comparison_report(stock_a, stock_b, result)

        # 打印摘要
        print(f"\n{report[:2000]}...")

        # 保存报告
        if args.output:
            from pathlib import Path
            today = datetime.date.today().strftime("%Y%m%d")
            out_dir = Path(args.output) / "分析报告"
            out_dir.mkdir(parents=True, exist_ok=True)
            filename = f"对比-{name_a}vs{name_b}-{today}.md"
            filepath = out_dir / filename
            filepath.write_text(report, encoding="utf-8")
            print(f"\n报告已保存: {filepath}")

            # 导出 HTML/PDF
            fmt = getattr(args, "format", "md") or "md"
            if fmt != "md":
                _export_report(str(filepath), fmt)

    except Exception as e:
        print(f"\n对比分析时出错: {e}")
        traceback.print_exc()


def generate_enhanced_comparison_report(stock_a, stock_b, result):
    """生成增强版对比报告"""
    name_a = stock_a["name"]
    name_b = stock_b["name"]
    L = []

    L.append(f"# 双股深度对比: {name_a} vs {name_b}\n")
    L.append(f"> 生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    # 总结
    L.append("## 对比总结\n")
    L.append(f"**{result['summary']}**\n")

    # 对比表格
    table = generate_comparison_table(result["comparison"], name_a, name_b)
    L.append(table)
    L.append("")

    # 个股详情
    L.append("\n## 个股详情\n")

    for stock, label in [(stock_a, "A"), (stock_b, "B")]:
        name = stock["name"]
        code = stock["code"]
        price = stock["price"]
        pe = stock["pe"]
        pb = stock["pb"]
        mv = stock["market_cap"]
        chg = stock["change_pct"]
        indicators = stock["indicators"]
        fund_flow = stock.get("fund_flow", {})

        L.append(f"\n### {label}. {name}（{code}）\n")
        L.append(f"| 指标 | 数值 |")
        L.append(f"|------|------|")
        L.append(f"| 最新价 | {price} 元（{chg:+.2f}%）|")
        L.append(f"| 市盈率 | {pe:.2f} |")
        L.append(f"| 市净率 | {pb:.2f} |")
        L.append(f"| 总市值 | {mv/1e8:.2f} 亿 |")
        L.append(f"| MACD | {'金叉' if indicators.get('DIF', 0) > indicators.get('DEA', 0) else '死叉'} |")
        L.append(f"| RSI6 | {indicators.get('RSI6', 50):.2f} |")

        # 资金流向
        main_flow = safe_num(fund_flow.get("今日", {}).get("f62", 0))
        L.append(f"| 主力资金 | {'+' if main_flow > 0 else ''}{main_flow/1e8:.2f} 亿 |")

    # 投资建议
    L.append("\n## 投资建议\n")

    # 根据对比结果给出建议
    score_a = result.get("score_a", 0)
    score_b = result.get("score_b", 0)

    if score_a > score_b:
        L.append(f"**推荐 {name_a}**：综合评分更高（{score_a}:{score_b}）\n")
    elif score_b > score_a:
        L.append(f"**推荐 {name_b}**：综合评分更高（{score_b}:{score_a}）\n")
    else:
        L.append(f"**两者相当**：综合评分相同（{score_a}:{score_b}）\n")

    # 风险提示
    L.append("\n## 风险提示\n")
    L.append("- 以上分析基于公开数据自动计算，请结合自身风险承受能力做出投资决策")
    L.append("- 股市有风险，投资需谨慎")

    return "\n".join(L)


def cmd_sector(args):
    """板块分析"""
    sector_name = args.sector.strip()

    print(f"\n{'='*60}")
    print(f"  板块分析: {sector_name}")
    print(f"{'='*60}")

    try:
        codes = get_sector_stocks(sector_name)

        if not codes:
            print(f"\n错误: 未知板块 '{sector_name}'")
            print(f"支持的板块: 白酒、新能源、半导体、银行、医药、消费、科技、地产、军工、汽车")
            return

        # 获取每只股票的详细数据
        stocks_data = []
        for code in codes:
            try:
                name = get_stock_name(code)
                quote = fetch_realtime_quote(code)
                df = fetch_kline(code, days=60)
                indicators = calculate_indicators(df)
                fund_flow = fetch_fund_flow(code)

                main_flow = safe_num(fund_flow.get("今日", {}).get("f62", 0))

                stocks_data.append({
                    "code": code,
                    "name": name,
                    "price": indicators.get("最新价", 0),
                    "change_pct": indicators.get("涨跌幅_今日", 0),
                    "pe": safe_num(quote.get("f9", 0)),
                    "pb": safe_num(quote.get("f23", 0)),
                    "market_cap": safe_num(quote.get("f20", 0)),
                    "main_flow": main_flow,
                    "macd_signal": "金叉" if indicators.get("DIF", 0) > indicators.get("DEA", 0) else "死叉",
                    "rsi6": indicators.get("RSI6", 50),
                    "indicators": indicators,
                })
            except Exception as e:
                print(f"  获取 {code} 数据失败: {e}")
                continue

        if not stocks_data:
            print("\n错误: 无法获取板块数据")
            return

        # 分析板块
        sector_data = {
            "sector_name": sector_name,
            "stocks": stocks_data,
        }
        result = analyze_sector(sector_data)

        # 生成增强版报告
        report = generate_enhanced_sector_report(sector_name, stocks_data, result)

        # 打印摘要
        print(f"\n{report[:2000]}...")

        # 保存报告
        if args.output:
            from pathlib import Path
            today = datetime.date.today().strftime("%Y%m%d")
            out_dir = Path(args.output) / "分析报告"
            out_dir.mkdir(parents=True, exist_ok=True)
            filename = f"板块-{sector_name}-{today}.md"
            filepath = out_dir / filename
            filepath.write_text(report, encoding="utf-8")
            print(f"\n报告已保存: {filepath}")

            # 导出 HTML/PDF
            fmt = getattr(args, "format", "md") or "md"
            if fmt != "md":
                _export_report(str(filepath), fmt)

    except Exception as e:
        print(f"\n板块分析时出错: {e}")
        traceback.print_exc()


def cmd_monitor(args):
    """反证清单监控"""
    report_dir = args.report_dir
    codes = args.codes if args.codes else None
    days = args.days

    print(f"\n{'='*60}")
    print(f"  反证清单监控")
    print(f"{'='*60}")
    print(f"  报告目录: {report_dir}")
    if codes:
        print(f"  股票过滤: {', '.join(codes)}")
    if days:
        print(f"  时间范围: 最近 {days} 天")
    print()

    try:
        data = monitor_reports(report_dir, codes, days)

        # 终端输出用 ASCII 兼容版本（避免 Windows GBK 编码问题）
        report_safe = format_monitor_report(data, use_emoji=False)
        print(report_safe)

        # 保存完整 emoji 版本到文件
        if args.output:
            from pathlib import Path
            report_full = format_monitor_report(data, use_emoji=True)
            today = datetime.date.today().strftime("%Y%m%d")
            out_dir = Path(args.output) / "分析报告"
            out_dir.mkdir(parents=True, exist_ok=True)
            filename = f"监控报告-{today}.md"
            filepath = out_dir / filename
            filepath.write_text(report_full, encoding="utf-8")
            print(f"\n监控报告已保存: {filepath}")

    except Exception as e:
        print(f"\n监控检查时出错: {e}")
        traceback.print_exc()


def generate_enhanced_sector_report(sector_name, stocks_data, result):
    """生成增强版板块分析报告"""
    L = []

    L.append(f"# 板块深度分析: {sector_name}\n")
    L.append(f"> 生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    # 板块概况
    L.append("## 板块概况\n")
    L.append(f"| 指标 | 数值 |")
    L.append(f"|------|------|")
    L.append(f"| 板块趋势 | {result['trend']} |")
    L.append(f"| 平均涨跌 | {result['avg_change']:+.2f}% |")
    L.append(f"| 上涨家数 | {result['up_count']} 家 |")
    L.append(f"| 下跌家数 | {result['down_count']} 家 |")
    L.append(f"| 分析股票数 | {result['stocks_count']} 家 |")

    # 代表性股票详情
    L.append("\n## 代表性股票\n")
    L.append("| 代码 | 名称 | 最新价 | 涨跌幅 | PE | PB | 主力资金 | MACD | RSI6 |")
    L.append("|------|------|--------|--------|-----|-----|----------|------|------|")

    for stock in stocks_data:
        main_flow_str = f"{stock['main_flow']/1e8:+.2f}亿" if abs(stock['main_flow']) > 0 else "0"
        L.append(f"| {stock['code']} | {stock['name']} | {stock['price']:.2f} | {stock['change_pct']:+.2f}% | {stock['pe']:.2f} | {stock['pb']:.2f} | {main_flow_str} | {stock['macd_signal']} | {stock['rsi6']:.2f} |")

    # 板块趋势分析
    L.append("\n## 趋势分析\n")

    # 统计技术面信号
    bullish_count = sum(1 for s in stocks_data if s['macd_signal'] == '金叉')
    bearish_count = len(stocks_data) - bullish_count

    L.append(f"- **技术面**: {bullish_count} 只金叉，{bearish_count} 只死叉")

    # 统计资金流向
    inflow_count = sum(1 for s in stocks_data if s['main_flow'] > 0)
    outflow_count = len(stocks_data) - inflow_count

    L.append(f"- **资金面**: {inflow_count} 只主力净流入，{outflow_count} 只主力净流出")

    # 估值水平
    avg_pe = sum(s['pe'] for s in stocks_data if s['pe'] > 0) / max(1, sum(1 for s in stocks_data if s['pe'] > 0))
    avg_pb = sum(s['pb'] for s in stocks_data if s['pb'] > 0) / max(1, sum(1 for s in stocks_data if s['pb'] > 0))

    L.append(f"- **估值水平**: 平均 PE {avg_pe:.2f}，平均 PB {avg_pb:.2f}")

    # 投资建议
    L.append("\n## 投资建议\n")

    if result['avg_change'] > 2 and inflow_count > outflow_count:
        L.append("**板块强势**：整体上涨且资金流入，可关注龙头股机会")
    elif result['avg_change'] < -2 and outflow_count > inflow_count:
        L.append("**板块弱势**：整体下跌且资金流出，建议观望或减仓")
    else:
        L.append("**板块震荡**：多空交织，建议精选个股，控制仓位")

    # 风险提示
    L.append("\n## 风险提示\n")
    L.append("- 以上分析基于公开数据自动计算，请结合自身风险承受能力做出投资决策")
    L.append("- 板块分析基于代表性股票，不能完全代表整个板块")
    L.append("- 股市有风险，投资需谨慎")

    return "\n".join(L)


def main():
    import sys

    # 预处理参数：如果没有指定子命令，默认使用 analyze
    args_list = sys.argv[1:]
    known_commands = ["analyze", "compare", "sector", "monitor", "--help", "-h", "--version", "-v"]

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

  # 分析美股（需要 pip install yfinance）
  python stock_analyzer.py AAPL
  python stock_analyzer.py TSLA NVDA

  # 导出为 HTML
  python stock_analyzer.py 000333 --format html

  # 导出为 PDF（需要 pip install weasyprint，不可用时自动降级为 HTML）
  python stock_analyzer.py 000333 --format pdf

  # 双股对比分析
  python stock_analyzer.py compare 600519 000858

  # 板块分析
  python stock_analyzer.py sector 白酒

  # 反证清单监控（检查所有报告）
  python stock_analyzer.py monitor

  # 反证清单监控（检查指定股票）
  python stock_analyzer.py monitor 000333 600519

  # 反证清单监控（只检查最近 3 天的报告）
  python stock_analyzer.py monitor --days 3

  # 指定输出目录
  python stock_analyzer.py -o ./reports 600519

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
支持板块:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  白酒 | 新能源 | 半导体 | 银行 | 医药 | 消费 | 科技 | 地产 | 军工 | 汽车
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
输出说明:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  所有报告统一保存到: 分析报告/ 目录下（由 --output 指定父目录）
  分析报告: 分析报告/<code>-<name>-分析报告-YYYYMMDD.md
  对比报告: 分析报告/对比-<名称A>vs<名称B>-YYYYMMDD.md
  板块报告: 分析报告/板块-<板块名称>-YYYYMMDD.md
  监控报告: 分析报告/监控报告-YYYYMMDD.md
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
        help="股票代码（支持 A 股 6 位代码、港股 5 位代码、美股 ticker 如 AAPL）"
    )
    analyze_parser.add_argument(
        "--format", "-f",
        choices=["md", "html", "pdf"],
        default="md",
        help="输出格式：md=Markdown（默认），html=HTML，pdf=PDF"
    )

    # compare 子命令
    compare_parser = subparsers.add_parser(
        "compare",
        help="双股对比",
        description="从7个维度横向对比两只股票：PE/PB/市值/涨跌/RSI/MACD/评级"
    )
    compare_parser.add_argument("code_a", help="股票 A 代码")
    compare_parser.add_argument("code_b", help="股票 B 代码")
    compare_parser.add_argument(
        "--format", "-f",
        choices=["md", "html", "pdf"],
        default="md",
        help="输出格式：md=Markdown（默认），html=HTML，pdf=PDF"
    )

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
    sector_parser.add_argument(
        "--format", "-f",
        choices=["md", "html", "pdf"],
        default="md",
        help="输出格式：md=Markdown（默认），html=HTML，pdf=PDF"
    )

    # monitor 子命令
    monitor_parser = subparsers.add_parser(
        "monitor",
        help="反证清单监控",
        description="扫描历史分析报告，检查反证清单中的条件是否已触发"
    )
    monitor_parser.add_argument(
        "codes",
        nargs="*",
        help="股票代码过滤（不指定则检查所有报告）"
    )
    monitor_parser.add_argument(
        "--report-dir", "-d",
        default="分析报告",
        help="分析报告目录（默认: 分析报告）"
    )
    monitor_parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="只检查最近 N 天的报告"
    )

    args = parser.parse_args()

    # 执行对应命令
    if args.command == "analyze":
        cmd_analyze(args)
    elif args.command == "compare":
        cmd_compare(args)
    elif args.command == "sector":
        cmd_sector(args)
    elif args.command == "monitor":
        cmd_monitor(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
