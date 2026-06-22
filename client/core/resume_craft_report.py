import re
from datetime import datetime
from html import escape
from typing import Any, Dict, List, Tuple


def _as_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        return [x.strip(" -\t") for x in value.splitlines() if x.strip()]
    return []


def _extract_candidate_name(result: Dict[str, Any], resume_markdown: str) -> str:
    title = str(result.get("title") or "").strip()
    if title:
        # e.g. "张三 - AI应用开发简历"
        first = re.split(r"\s*[-|｜]\s*", title, maxsplit=1)[0].strip()
        if first:
            return first[:24]

    m = re.search(r"^\s*#\s*([^\n#]{1,32})", resume_markdown or "", re.M)
    if m:
        name = m.group(1).strip()
        if name:
            return name[:24]
    return "候选人"


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", (name or "").strip())
    cleaned = cleaned.strip(" ._")
    return cleaned or "候选人"


def _extract_template_code(template: str) -> str:
    t = (template or "").strip()
    if not t:
        return "02"
    m = re.search(r"\b0?([1-7])\b", t)
    if m:
        return f"0{m.group(1)}"
    return "02"


def _theme_by_template(template_code: str) -> Dict[str, str]:
    themes = {
        "01": {"ink": "#263238", "accent": "#2d6b5f", "bg": "#f7f3ec"},
        "02": {"ink": "#111827", "accent": "#334155", "bg": "#f8fafc"},
        "03": {"ink": "#102a43", "accent": "#1d4ed8", "bg": "#eff6ff"},
        "04": {"ink": "#1f2937", "accent": "#374151", "bg": "#f3f4f6"},
        "05": {"ink": "#0f172a", "accent": "#111827", "bg": "#f8fafc"},
        "06": {"ink": "#0f172a", "accent": "#0f766e", "bg": "#f0fdfa"},
        "07": {"ink": "#1f2937", "accent": "#7c3f00", "bg": "#fffaf0"},
    }
    return themes.get(template_code, themes["02"])


def _inline_md(text: str) -> str:
    out = escape(text or "")
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"`(.+?)`", r"<code>\1</code>", out)
    return out


def _markdown_to_html(markdown_text: str) -> str:
    text = (markdown_text or "").strip()
    if not text:
        return "<p>暂无内容。</p>"

    lines = text.splitlines()
    parts: List[str] = []
    in_list = False
    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            if in_list:
                parts.append("</ul>")
                in_list = False
            continue

        bullet = re.match(r"^\s*[-*]\s+(.+)$", line)
        if bullet:
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{_inline_md(bullet.group(1).strip())}</li>")
            continue

        if in_list:
            parts.append("</ul>")
            in_list = False

        if re.match(r"^\s*###\s+", line):
            heading = re.sub(r"^\s*###\s+", "", line)
            parts.append(f"<h3>{_inline_md(heading)}</h3>")
        elif re.match(r"^\s*##\s+", line):
            heading = re.sub(r"^\s*##\s+", "", line)
            parts.append(f"<h2>{_inline_md(heading)}</h2>")
        elif re.match(r"^\s*#\s+", line):
            heading = re.sub(r"^\s*#\s+", "", line)
            parts.append(f"<h1>{_inline_md(heading)}</h1>")
        else:
            parts.append(f"<p>{_inline_md(line)}</p>")

    if in_list:
        parts.append("</ul>")
    return "\n".join(parts) if parts else "<p>暂无内容。</p>"


def build_resume_craft_html_report(
    result: Dict[str, Any],
    target_role: str = "",
    language: str = "zh",
    template: str = "",
) -> Tuple[str, str]:
    if not isinstance(result, dict):
        raise ValueError("resume-craft result must be dict")

    raw_html = str(result.get("resume_html") or "").strip()
    candidate_name = _extract_candidate_name(result, str(result.get("resume_markdown") or ""))
    safe_name = _safe_filename(candidate_name)
    file_name = f"{safe_name}-简历预览.html"
    if raw_html and ("<html" in raw_html.lower()):
        return file_name, raw_html

    title = str(result.get("title") or f"{candidate_name} - 简历").strip()
    profile_summary = str(result.get("profile_summary") or "").strip()
    resume_markdown = str(result.get("resume_markdown") or "").strip()
    sections = result.get("sections") or []
    style_advice = _as_list(result.get("style_advice"))
    next_actions = _as_list(result.get("next_actions"))

    template_code = _extract_template_code(template)
    theme = _theme_by_template(template_code)

    section_blocks: List[str] = []
    if isinstance(sections, list) and sections:
        for item in sections:
            if not isinstance(item, dict):
                continue
            sec_title = str(item.get("title") or "").strip() or "未命名章节"
            sec_md = str(item.get("content_markdown") or "").strip()
            section_blocks.append(
                f"""
                <section class="section">
                  <h2>{escape(sec_title)}</h2>
                  <div class="content">
                    {_markdown_to_html(sec_md)}
                  </div>
                </section>
                """
            )
    elif resume_markdown:
        section_blocks.append(
            f"""
            <section class="section">
              <h2>简历内容</h2>
              <div class="content">
                {_markdown_to_html(resume_markdown)}
              </div>
            </section>
            """
        )

    if not section_blocks:
        section_blocks.append(
            """
            <section class="section">
              <h2>简历内容</h2>
              <div class="content"><p>当前未返回完整简历正文，请补充经历后重试生成。</p></div>
            </section>
            """
        )

    style_html = ""
    if style_advice:
        style_html = (
            '<section class="section"><h2>风格建议</h2><ul>'
            + "".join(f"<li>{escape(x)}</li>" for x in style_advice)
            + "</ul></section>"
        )

    next_html = ""
    if next_actions:
        next_html = (
            '<section class="section"><h2>下一步建议</h2><ul>'
            + "".join(f"<li>{escape(x)}</li>" for x in next_actions)
            + "</ul></section>"
        )

    lang_map = {"zh": "中文", "en": "英文", "both": "中英文双版"}
    lang_label = lang_map.get((language or "zh").lower(), language or "中文")
    role_label = (target_role or "").strip() or "未指定"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    html_doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(title)}</title>
  <style>
    :root {{
      --ink: {theme["ink"]};
      --accent: {theme["accent"]};
      --bg: {theme["bg"]};
      --card: #ffffff;
      --line: #e5e7eb;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background: linear-gradient(120deg, var(--bg) 0%, #ffffff 100%);
      font-family: "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
      line-height: 1.6;
    }}
    .wrap {{
      max-width: 900px;
      margin: 26px auto 42px;
      padding: 0 16px;
    }}
    .hero {{
      background: var(--card);
      border: 1px solid var(--line);
      border-top: 5px solid var(--accent);
      border-radius: 14px;
      padding: 22px 24px;
      box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
    }}
    .meta {{
      margin-top: 10px;
      color: #475569;
      font-size: 14px;
      display: flex;
      gap: 10px 18px;
      flex-wrap: wrap;
    }}
    .badge {{
      display: inline-block;
      padding: 3px 10px;
      border-radius: 999px;
      font-size: 12px;
      color: var(--accent);
      background: color-mix(in srgb, var(--accent) 12%, white);
      border: 1px solid color-mix(in srgb, var(--accent) 25%, white);
    }}
    .summary {{
      margin-top: 14px;
      padding: 12px 14px;
      border-left: 4px solid var(--accent);
      background: #f8fafc;
      border-radius: 8px;
    }}
    .section {{
      margin-top: 16px;
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 18px 20px;
    }}
    h1 {{ margin: 0; font-size: 30px; line-height: 1.2; }}
    h2 {{ margin: 0 0 12px; font-size: 22px; color: var(--accent); }}
    h3 {{ margin: 14px 0 8px; font-size: 18px; }}
    p {{ margin: 8px 0; }}
    ul {{ margin: 8px 0 8px 20px; }}
    li {{ margin: 4px 0; }}
    code {{
      background: #f1f5f9;
      border-radius: 6px;
      padding: 1px 6px;
      font-family: ui-monospace, "SFMono-Regular", Menlo, monospace;
      font-size: 0.9em;
    }}
    @media print {{
      body {{ background: white; }}
      .wrap {{ margin: 0; max-width: 100%; }}
      .hero, .section {{ box-shadow: none; break-inside: avoid-page; }}
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <span class="badge">Resume Craft</span>
      <h1>{escape(title)}</h1>
      <div class="meta">
        <span>目标岗位：{escape(role_label)}</span>
        <span>语言：{escape(lang_label)}</span>
        <span>模板：{escape(template_code)}</span>
        <span>生成时间：{escape(now_str)}</span>
      </div>
      <div class="summary">{escape(profile_summary or "已完成简历生成。")}</div>
    </section>
    {''.join(section_blocks)}
    {style_html}
    {next_html}
  </main>
</body>
</html>
"""

    return file_name, html_doc
