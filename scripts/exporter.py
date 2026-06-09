#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
报告导出模块 — Markdown → HTML / PDF

- HTML: 使用 markdown 库转换，内嵌 CSS 样式
- PDF: 优先使用 weasyprint，不可用时降级为 HTML
"""

import datetime
import html
import re

try:
    import markdown
    from markdown.extensions.tables import TableExtension
    from markdown.extensions.fenced_code import FencedCodeExtension
    HAS_MARKDOWN = True
except ImportError:
    HAS_MARKDOWN = False

try:
    import weasyprint
    HAS_WEASYPRINT = True
except (ImportError, OSError):
    # OSError 可能在缺少系统库（如 GTK）时抛出
    HAS_WEASYPRINT = False


# 内嵌 CSS 样式
_REPORT_CSS = """
<style>
:root {
    --primary: #1a73e8;
    --danger: #d93025;
    --success: #188038;
    --warning: #e37400;
    --bg: #ffffff;
    --bg-alt: #f8f9fa;
    --text: #202124;
    --text-secondary: #5f6368;
    --border: #dadce0;
}

* { box-sizing: border-box; }

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial,
                 "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    font-size: 14px;
    line-height: 1.8;
    color: var(--text);
    max-width: 960px;
    margin: 0 auto;
    padding: 24px 32px;
    background: var(--bg);
}

h1 {
    font-size: 28px;
    font-weight: 700;
    color: var(--primary);
    border-bottom: 3px solid var(--primary);
    padding-bottom: 12px;
    margin-top: 32px;
}

h2 {
    font-size: 22px;
    font-weight: 600;
    color: var(--text);
    border-bottom: 2px solid var(--border);
    padding-bottom: 8px;
    margin-top: 28px;
}

h3 {
    font-size: 18px;
    font-weight: 600;
    color: var(--text-secondary);
    margin-top: 20px;
}

table {
    width: 100%;
    border-collapse: collapse;
    margin: 16px 0;
    font-size: 13px;
}

th, td {
    border: 1px solid var(--border);
    padding: 10px 14px;
    text-align: left;
}

th {
    background: var(--bg-alt);
    font-weight: 600;
    color: var(--text);
    white-space: nowrap;
}

tr:nth-child(even) { background: var(--bg-alt); }
tr:hover { background: #e8f0fe; }

blockquote {
    margin: 16px 0;
    padding: 12px 20px;
    border-left: 4px solid var(--primary);
    background: #e8f0fe;
    color: var(--text-secondary);
    border-radius: 0 4px 4px 0;
}

blockquote strong { color: var(--text); }

hr {
    border: none;
    border-top: 1px solid var(--border);
    margin: 24px 0;
}

code {
    background: var(--bg-alt);
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 13px;
    font-family: "SF Mono", "Fira Code", "Consolas", monospace;
}

pre {
    background: var(--bg-alt);
    padding: 16px;
    border-radius: 6px;
    overflow-x: auto;
    border: 1px solid var(--border);
}

pre code {
    background: none;
    padding: 0;
}

ul, ol {
    padding-left: 24px;
    margin: 8px 0;
}

li { margin: 4px 0; }

strong { font-weight: 600; }

/* 打印优化 */
@media print {
    body { max-width: none; padding: 0; font-size: 12px; }
    h1 { font-size: 22px; }
    h2 { font-size: 18px; }
    table { font-size: 11px; }
    tr:hover { background: none; }
    blockquote { break-inside: avoid; }
}
</style>
"""


def md_to_html(md_content: str, title: str = "分析报告") -> str:
    """
    将 Markdown 内容转换为完整的 HTML 页面。

    Args:
        md_content: Markdown 格式的报告内容
        title: HTML 页面标题

    Returns:
        完整的 HTML 字符串
    """
    if not md_content:
        return ""

    if not HAS_MARKDOWN:
        # 简单降级：手动处理基本格式
        html_body = _simple_md_to_html(md_content)
    else:
        html_body = markdown.markdown(
            md_content,
            extensions=[
                TableExtension(),
                FencedCodeExtension(),
                "nl2br",
            ],
        )

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    safe_title = html.escape(title)
    result = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{safe_title}</title>
    {_REPORT_CSS}
</head>
<body>
    <div style="text-align: right; color: #5f6368; font-size: 12px; margin-bottom: 16px;">
        导出时间: {now} | Stock Analyzer
    </div>
    {html_body}
</body>
</html>"""
    return result


def md_to_pdf(md_content: str, output_path: str, title: str = "分析报告") -> str:
    """
    将 Markdown 内容转换为 PDF 文件。

    如果 weasyprint 不可用，降级为 HTML 文件。

    Args:
        md_content: Markdown 格式的报告内容
        output_path: 输出文件路径
        title: 报告标题

    Returns:
        实际输出的文件路径（.pdf 或 .html）
    """
    html_content = md_to_html(md_content, title)

    def _fallback_to_html(content, pdf_path, report_title):
        """降级为 HTML 输出"""
        print("  [警告] weasyprint 不可用，已降级为 HTML 输出")
        html_path = pdf_path.rsplit(".", 1)[0] + ".html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(content)
        return html_path

    if HAS_WEASYPRINT:
        try:
            weasyprint.HTML(string=html_content).write_pdf(output_path)
            return output_path
        except Exception:
            return _fallback_to_html(html_content, output_path, title)

    return _fallback_to_html(html_content, output_path, title)


def _simple_md_to_html(md_content: str) -> str:
    """
    简单的 Markdown → HTML 转换（不依赖 markdown 库）。
    处理基本的标题、表格、粗体、引用块。
    """
    lines = md_content.split("\n")
    html_lines = []
    in_table = False
    in_blockquote = False

    for line in lines:
        stripped = line.strip()

        # 空行
        if not stripped:
            if in_table:
                html_lines.append("</table>")
                in_table = False
            if in_blockquote:
                html_lines.append("</blockquote>")
                in_blockquote = False
            html_lines.append("")
            continue

        # 标题
        if stripped.startswith("#"):
            level = 0
            for ch in stripped:
                if ch == "#":
                    level += 1
                else:
                    break
            level = min(level, 6)
            text = stripped[level:].strip()
            html_lines.append(f"<h{level}>{html.escape(text)}</h{level}>")
            continue

        # 分隔线
        if stripped in ("---", "***", "___"):
            html_lines.append("<hr>")
            continue

        # 引用块
        if stripped.startswith(">"):
            text = stripped[1:].strip()
            if not in_blockquote:
                html_lines.append("<blockquote>")
                in_blockquote = True
            html_lines.append(f"<p>{_inline_format(text)}</p>")
            continue
        elif in_blockquote:
            html_lines.append("</blockquote>")
            in_blockquote = False

        # 表格
        if "|" in stripped and stripped.startswith("|"):
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            # 跳过分隔行
            if all(set(c) <= set("-: ") for c in cells):
                continue
            if not in_table:
                html_lines.append("<table>")
                in_table = True
                tag = "th"
            else:
                tag = "td"
            row = "".join(f"<{tag}>{_inline_format(c)}</{tag}>" for c in cells)
            html_lines.append(f"<tr>{row}</tr>")
            continue
        elif in_table:
            html_lines.append("</table>")
            in_table = False

        # 普通段落
        html_lines.append(f"<p>{_inline_format(stripped)}</p>")

    if in_table:
        html_lines.append("</table>")
    if in_blockquote:
        html_lines.append("</blockquote>")

    return "\n".join(html_lines)


def _inline_format(text: str) -> str:
    """处理行内格式：粗体、行内代码"""
    # 先转义 HTML 特殊字符
    text = html.escape(text)
    # 行内代码（先处理，避免被粗体正则干扰）
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    # 粗体
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    return text
