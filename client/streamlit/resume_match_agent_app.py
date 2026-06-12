import json
import os
import queue
import re
import sys
import threading
import time
import zipfile
from datetime import datetime
from html import escape
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "test-output"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.services.careerforge_agent import CareerForgeAgent

HTML_OFFER_TEXT = "要不要把这份分析报告生成一个精美的 HTML 页面？可以在浏览器里打开、截图或分享。"
WEIGHT_MAP = {
    "硬性技能匹配度": 25,
    "工作经验相关度": 25,
    "软性能力匹配度": 15,
    "教育背景匹配度": 10,
    "关键词覆盖率": 15,
    "简历质量": 10,
}


def _load_local_env():
    """
    Load API keys from project-local .env_tts for Streamlit subprocesses.
    Supports lines like:
      export DEEPSEEK_API_KEY="sk-xxx"
      OPENAI_API_KEY=sk-xxx
    """
    env_file = ROOT / ".env_tts"
    if not env_file.exists():
        return
    try:
        for raw in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].strip()
            if "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and val and not os.environ.get(key):
                os.environ[key] = val
    except Exception:
        pass


def _to_int(value, default=0):
    try:
        return int(round(float(value)))
    except Exception:
        return default


def _normalize_level(raw_level: str, score: int) -> str:
    text = (raw_level or "").strip().upper()
    if text.startswith("A"):
        return "A. Strong Fit"
    if text.startswith("B"):
        return "B. Stretch Fit"
    if text.startswith("C"):
        return "C. Poor Fit"
    if score >= 75:
        return "A. Strong Fit"
    if score >= 50:
        return "B. Stretch Fit"
    return "C. Poor Fit"


def _progress_bar(score: int) -> str:
    score = max(0, min(100, _to_int(score)))
    filled = max(0, min(20, int(round(score / 5))))
    return ("█" * filled) + ("░" * (20 - filled))


def _as_list(value):
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        items = [x.strip(" -\t") for x in value.splitlines() if x.strip()]
        return [x for x in items if x]
    return []


def _extract_candidate_name(resume_text: str) -> str:
    text = (resume_text or "").strip()
    if not text:
        return "候选人"
    m = re.search(r"(?:姓名|Name)\s*[:：]\s*([^\n，,。；;]+)", text, re.I)
    if m:
        name = m.group(1).strip()
        if name:
            return name[:24]
    first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    first_line = re.sub(r"\s+", "", first_line)
    if 1 <= len(first_line) <= 24 and not any(ch in first_line for ch in "：:，,。;；"):
        return first_line
    return "候选人"


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", (name or "").strip())
    cleaned = cleaned.strip(" ._")
    return cleaned or "候选人"


def _build_html_report(result: dict, resume_text: str, target_role: str, jd_text: str) -> tuple[str, str]:
    candidate_name = _extract_candidate_name(resume_text)
    safe_name = _safe_filename(candidate_name)

    score = max(0, min(100, _to_int(result.get("overall_score"), 0)))
    match_level = _normalize_level(result.get("match_level"), score)
    summary = (result.get("summary") or "该候选人与岗位具备一定匹配度，可通过定向优化提升投递命中率。").strip()
    dimensions = result.get("dimension_scores") or []
    missing = _as_list(result.get("critical_missing"))
    advantages = _as_list(result.get("extra_advantages"))
    suggestions = _as_list(result.get("optimization_suggestions"))

    if not dimensions:
        dimensions = [
            {"name": "硬性技能匹配度", "score": 0, "highlight": "未提供", "gap": "未提供", "advice": "未提供"},
            {"name": "工作经验相关度", "score": 0, "highlight": "未提供", "gap": "未提供", "advice": "未提供"},
            {"name": "软性能力匹配度", "score": 0, "highlight": "未提供", "gap": "未提供", "advice": "未提供"},
            {"name": "教育背景匹配度", "score": 0, "highlight": "未提供", "gap": "未提供", "advice": "未提供"},
            {"name": "关键词覆盖率", "score": 0, "highlight": "未提供", "gap": "未提供", "advice": "未提供"},
            {"name": "简历质量", "score": 0, "highlight": "未提供", "gap": "未提供", "advice": "未提供"},
        ]

    ring_circumference = 439.82
    ring_offset = ring_circumference * (1 - score / 100.0)

    dim_cards = []
    weighted_rows = []
    total_weighted = 0.0
    for item in dimensions:
        name = str(item.get("name") or "维度").strip()
        dim_score = max(0, min(100, _to_int(item.get("score"), 0)))
        weight = WEIGHT_MAP.get(name, 0)
        weighted = dim_score * weight / 100.0
        total_weighted += weighted
        weighted_rows.append(
            f"""
            <tr>
              <td>{escape(name)}</td>
              <td>{dim_score}</td>
              <td>{weight}%</td>
              <td>{weighted:.1f}</td>
            </tr>
            """
        )

        if dim_score >= 70:
            cls = "green"
        elif dim_score >= 50:
            cls = "orange"
        else:
            cls = "red"
        highlight = escape(str(item.get("highlight") or "暂无"))
        gap = escape(str(item.get("gap") or "暂无"))
        advice = escape(str(item.get("advice") or "暂无"))
        dim_cards.append(
            f"""
            <article class="dim-card">
              <div class="dim-top">
                <div>
                  <h3 class="dim-title">{escape(name)}</h3>
                  <div class="dim-sub">权重 {weight}%</div>
                </div>
                <div class="dim-score">{dim_score} / 100</div>
              </div>
              <div class="bar"><div class="fill {cls}" style="width: {dim_score}%;"></div></div>
              <div class="block match"><strong>匹配亮点</strong><br>{highlight}</div>
              <div class="block gap"><strong>差距与不足</strong><br>{gap}</div>
              <div class="block tip"><strong>该维度优化建议</strong><br>{advice}</div>
            </article>
            """
        )

    if not missing:
        missing = ["暂无明确缺失项，建议结合岗位高频关键词继续补充。"]
    if not advantages:
        advantages = ["暂无额外优势项。"]
    if not suggestions:
        suggestions = ["建议先确认每条优化建议的真实性，再生成最终简历。"]

    missing_items = "\n".join(
        f"""<li><span class="num red">{i}</span><span>{escape(item)}</span></li>"""
        for i, item in enumerate(missing, 1)
    )
    advantage_items = "\n".join(
        f"""<li><span class="num green">{i}</span><span>{escape(item)}</span></li>"""
        for i, item in enumerate(advantages, 1)
    )

    suggestion_cards = []
    for idx, tip in enumerate(suggestions, 1):
        text = str(tip).strip()
        old = "（原文未提供）"
        new = text
        if "->" in text:
            old, new = [seg.strip() for seg in text.split("->", 1)]
        elif "→" in text:
            old, new = [seg.strip() for seg in text.split("→", 1)]
        suggestion_cards.append(
            f"""
            <article class="advice-card">
              <h5>建议 {idx}</h5>
              <div class="compare">
                <div class="line old">原文：{escape(old or "（原文未提供）")}</div>
                <div class="line new">建议改写：{escape(new or "（建议未提供）")}</div>
              </div>
            </article>
            """
        )

    date_str = datetime.now().strftime("%Y-%m-%d")
    role_text = (target_role or "").strip() or "未指定（基于 JD 自动推断）"
    jd_preview = (jd_text or "").strip().splitlines()[0].strip() if (jd_text or "").strip() else "未提供"
    file_name = f"{safe_name}-匹配分析报告.html"

    html_doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(safe_name)}-匹配分析报告</title>
  <style>
    :root {{
      --ink: #1a1f2e;
      --ink-light: #4a5568;
      --ink-muted: #718096;
      --accent: #2d6b5f;
      --accent-light: #e8f4f0;
      --accent-warm: #d4a853;
      --blue: #3b82f6;
      --red: #ef4444;
      --green: #22c55e;
      --orange: #f59e0b;
      --bg: #f8f9fa;
      --card: #ffffff;
      --border: #e5e7eb;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: radial-gradient(circle at 10% 10%, #eef3f1 0%, transparent 42%),
                  radial-gradient(circle at 90% 80%, #f6efe1 0%, transparent 38%),
                  var(--bg);
      color: var(--ink);
      font-family: "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
      line-height: 1.65;
    }}
    .container {{
      max-width: 860px;
      margin: 28px auto 44px;
      padding: 0 20px;
    }}
    .panel-head {{
      background: linear-gradient(135deg, #1a1f2e, #2d3748);
      color: #fff;
      border-radius: 16px 16px 0 0;
      padding: 26px 28px;
      border: 1px solid #2f3a51;
      border-bottom: 0;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.14);
      font-size: 12px;
      letter-spacing: 0.4px;
      margin-bottom: 12px;
    }}
    h1 {{
      margin: 0 0 10px;
      font-size: 30px;
      line-height: 1.2;
      font-family: "Noto Serif SC", "Songti SC", "STSong", serif;
      font-weight: 650;
    }}
    .meta {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px 16px;
      font-size: 14px;
      color: #d6dde8;
    }}
    .panel-body {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 0 0 16px 16px;
      overflow: hidden;
    }}
    section {{
      padding: 24px 28px;
      border-top: 1px solid var(--border);
    }}
    section:first-child {{ border-top: 0; }}
    .section-title {{
      margin: 0 0 16px;
      padding-left: 12px;
      border-left: 4px solid var(--accent);
      font-family: "Noto Serif SC", "Songti SC", "STSong", serif;
      font-size: 21px;
      line-height: 1.2;
    }}
    .score-grid {{
      display: grid;
      grid-template-columns: 260px 1fr;
      gap: 20px;
      align-items: center;
    }}
    .ring-wrap {{
      display: flex;
      justify-content: center;
      align-items: center;
    }}
    .ring {{
      position: relative;
      width: 200px;
      height: 200px;
    }}
    .ring svg {{
      width: 100%;
      height: 100%;
      transform: rotate(-90deg);
    }}
    .ring .center {{
      position: absolute;
      inset: 0;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
    }}
    .score-num {{
      font-size: 44px;
      line-height: 1;
      font-weight: 700;
      color: var(--ink);
    }}
    .score-den {{
      color: var(--ink-muted);
      margin-top: 4px;
    }}
    .fit-badge {{
      display: inline-block;
      border-radius: 999px;
      background: #fff7ed;
      color: #c2410c;
      border: 1px solid #fdba74;
      padding: 6px 12px;
      font-weight: 600;
      font-size: 13px;
      margin-bottom: 10px;
    }}
    .summary {{
      margin: 0;
      color: var(--ink-light);
    }}
    .dim-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }}
    .dim-card {{
      border-radius: 12px;
      border: 1px solid var(--border);
      background: var(--bg);
      padding: 14px;
    }}
    .dim-top {{
      display: flex;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 8px;
      align-items: baseline;
    }}
    .dim-title {{
      margin: 0;
      font-size: 16px;
    }}
    .dim-sub {{
      color: var(--ink-muted);
      font-size: 12px;
    }}
    .dim-score {{
      font-weight: 700;
      font-size: 16px;
    }}
    .bar {{
      height: 8px;
      background: #e5e7eb;
      border-radius: 4px;
      overflow: hidden;
      margin-bottom: 11px;
    }}
    .fill {{
      height: 100%;
      border-radius: 4px;
    }}
    .fill.green {{ background: linear-gradient(90deg, #16a34a, #4ade80); }}
    .fill.orange {{ background: linear-gradient(90deg, #d97706, #f59e0b); }}
    .fill.red {{ background: linear-gradient(90deg, #dc2626, #ef4444); }}
    .block {{
      border-radius: 8px;
      border: 1px solid;
      padding: 8px 10px;
      margin-top: 7px;
      font-size: 13px;
    }}
    .block strong {{
      display: inline-block;
      margin-bottom: 4px;
    }}
    .block.match {{
      background: #ecfdf3;
      border-color: #bbf7d0;
      color: #166534;
    }}
    .block.gap {{
      background: #fff1f2;
      border-color: #fecdd3;
      color: #9f1239;
    }}
    .block.tip {{
      background: #eff6ff;
      border-color: #bfdbfe;
      color: #1d4ed8;
    }}
    .twocol {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }}
    .panel {{
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 14px;
      background: var(--bg);
    }}
    .panel.red {{
      background: #fff1f2;
      border-color: #fecdd3;
    }}
    .panel.green {{
      background: #ecfdf3;
      border-color: #bbf7d0;
    }}
    .panel h4 {{
      margin: 0 0 10px;
      font-size: 16px;
    }}
    .number-list {{
      margin: 0;
      padding: 0;
      list-style: none;
      display: grid;
      gap: 9px;
    }}
    .number-list li {{
      display: grid;
      grid-template-columns: 24px 1fr;
      gap: 10px;
      align-items: start;
      font-size: 14px;
      color: var(--ink-light);
    }}
    .num {{
      width: 24px;
      height: 24px;
      border-radius: 50%;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      color: #fff;
      font-size: 12px;
      font-weight: 700;
      margin-top: 1px;
    }}
    .num.red {{ background: var(--red); }}
    .num.green {{ background: var(--green); }}
    .advice-grid {{
      display: grid;
      gap: 10px;
    }}
    .advice-card {{
      border-radius: 12px;
      border: 1px solid var(--border);
      background: var(--bg);
      padding: 12px;
    }}
    .advice-card h5 {{
      margin: 0 0 9px;
      font-size: 14px;
      color: var(--ink);
    }}
    .compare {{
      display: grid;
      gap: 8px;
      margin-bottom: 8px;
    }}
    .line {{
      border-radius: 8px;
      padding: 8px 10px;
      border: 1px solid var(--border);
      font-size: 13px;
    }}
    .line.old {{
      background: #fff7ed;
      border-color: #fed7aa;
      color: #9a3412;
    }}
    .line.new {{
      background: #ecfdf5;
      border-color: #bbf7d0;
      color: #166534;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      overflow: hidden;
      border-radius: 12px;
      border: 1px solid var(--border);
    }}
    th, td {{
      padding: 10px 12px;
      text-align: left;
      border-bottom: 1px solid var(--border);
      font-size: 14px;
    }}
    th {{
      background: #eef2f7;
      color: var(--ink-light);
    }}
    tr:last-child td {{ border-bottom: 0; }}
    .actions {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }}
    .action {{
      border: 1px solid var(--border);
      background: var(--bg);
      border-radius: 12px;
      padding: 12px;
    }}
    .action .icon {{
      width: 32px;
      height: 32px;
      border-radius: 8px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      margin-bottom: 8px;
      color: #fff;
      font-size: 15px;
    }}
    .icon.a {{ background: var(--blue); }}
    .icon.b {{ background: var(--accent); }}
    .icon.c {{ background: var(--orange); }}
    .action h5 {{
      margin: 0 0 6px;
      font-size: 15px;
    }}
    .action p {{
      margin: 0;
      font-size: 13px;
      color: var(--ink-light);
    }}
    .footer {{
      margin-top: 16px;
      text-align: center;
      font-size: 12px;
      color: var(--ink-muted);
    }}
    @media (max-width: 860px) {{
      .score-grid {{ grid-template-columns: 1fr; }}
      .ring-wrap {{ justify-content: flex-start; }}
      .dim-grid {{ grid-template-columns: 1fr; }}
      .twocol {{ grid-template-columns: 1fr; }}
      .actions {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main class="container">
    <header class="panel-head">
      <div class="badge">Resume Match Report</div>
      <h1>简历与岗位匹配分析报告</h1>
      <div class="meta">
        <div>候选人：{escape(candidate_name)}</div>
        <div>目标岗位：{escape(role_text)}</div>
        <div>JD 概要：{escape(jd_preview[:60])}</div>
        <div>报告日期：{escape(date_str)}</div>
      </div>
    </header>
    <div class="panel-body">
      <section>
        <h2 class="section-title">整体匹配总览</h2>
        <div class="score-grid">
          <div class="ring-wrap">
            <div class="ring">
              <svg viewBox="0 0 200 200" aria-hidden="true">
                <defs>
                  <linearGradient id="gauge" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#d4a853"></stop>
                    <stop offset="100%" stop-color="#2d6b5f"></stop>
                  </linearGradient>
                </defs>
                <circle cx="100" cy="100" r="70" fill="none" stroke="#e5e7eb" stroke-width="14"></circle>
                <circle cx="100" cy="100" r="70" fill="none" stroke="url(#gauge)" stroke-width="14"
                  stroke-linecap="round" stroke-dasharray="{ring_circumference:.2f}" stroke-dashoffset="{ring_offset:.2f}"></circle>
              </svg>
              <div class="center">
                <div class="score-num">{score}</div>
                <div class="score-den">/ 100</div>
              </div>
            </div>
          </div>
          <div>
            <div class="fit-badge">{escape(match_level)}</div>
            <p class="summary">{escape(summary)}</p>
          </div>
        </div>
      </section>
      <section>
        <h2 class="section-title">六维度评分详情</h2>
        <div class="dim-grid">
          {''.join(dim_cards)}
        </div>
      </section>
      <section>
        <h2 class="section-title">关键差距分析</h2>
        <div class="twocol">
          <div class="panel red">
            <h4>🔴 JD 要求但简历缺失的关键项</h4>
            <ol class="number-list">{missing_items}</ol>
          </div>
          <div class="panel green">
            <h4>🟢 简历中的优势但未被 JD 提及</h4>
            <ol class="number-list">{advantage_items}</ol>
          </div>
        </div>
      </section>
      <section>
        <h2 class="section-title">优化建议卡片</h2>
        <div class="advice-grid">
          {''.join(suggestion_cards)}
        </div>
      </section>
      <section>
        <h2 class="section-title">评分总表</h2>
        <table>
          <thead>
            <tr>
              <th>维度</th>
              <th>分数</th>
              <th>权重</th>
              <th>加权得分</th>
            </tr>
          </thead>
          <tbody>
            {''.join(weighted_rows)}
            <tr>
              <td><strong>总分</strong></td>
              <td><strong>{score}</strong></td>
              <td><strong>100%</strong></td>
              <td><strong>{total_weighted:.1f}</strong></td>
            </tr>
          </tbody>
        </table>
      </section>
      <section>
        <h2 class="section-title">下一步行动</h2>
        <div class="actions">
          <article class="action">
            <div class="icon a">CV</div>
            <h5>resume-craft</h5>
            <p>将确认后的优化内容直接生成排版精美的 HTML + PDF 简历版本。</p>
          </article>
          <article class="action">
            <div class="icon b">✉</div>
            <h5>cover-letter</h5>
            <p>基于目标 JD 生成定制化求职信与平台招呼语。</p>
          </article>
          <article class="action">
            <div class="icon c">🎯</div>
            <h5>mock-interview</h5>
            <p>针对本次识别的短板做面试问答强化训练。</p>
          </article>
        </div>
      </section>
    </div>
    <p class="footer">说明：本报告基于你提供的简历与 JD 文本客观生成。</p>
  </main>
</body>
</html>
"""
    return file_name, html_doc


def _format_analysis(result: dict) -> str:
    if not result:
        return "未返回结果。"
    if result.get("error"):
        msg = result.get("message") or result.get("error")
        return (
            "当前暂时无法完成匹配分析。\n"
            f"原因：{msg}\n\n"
            "请检查模型配置（例如 DEEPSEEK_API_KEY / OPENAI_API_KEY），"
            "然后重新提交简历与 JD。"
        )
    if result.get("raw_text"):
        return f"模型返回了非结构化结果：\n{result.get('raw_text')}"

    score = max(0, min(100, _to_int(result.get("overall_score"), 0)))
    level = _normalize_level(result.get("match_level"), score)
    summary = (result.get("summary") or "暂无总结").strip()
    dimensions = result.get("dimension_scores") or []
    critical_missing = _as_list(result.get("critical_missing"))
    extra_advantages = _as_list(result.get("extra_advantages"))
    suggestions = _as_list(result.get("optimization_suggestions"))

    lines = [
        "### 1. 总览",
        "",
        f"📊 整体匹配度评分：{score} / 100",
        f"🏷️ 匹配等级：{level}",
        f"📝 一句话总结：{summary}",
        "",
        "### 2. 各维度评分详情",
        "",
    ]

    for item in dimensions:
        name = str(item.get("name") or "维度").strip()
        dim_score = max(0, min(100, _to_int(item.get("score"), 0)))
        lines.extend(
            [
                f"#### {name}：{dim_score} / 100",
                "",
                f"{_progress_bar(dim_score)} {dim_score}%",
                "",
                "**匹配亮点：**",
                f"- {(item.get('highlight') or '暂无').strip()}",
                "",
                "**差距与不足：**",
                f"- {(item.get('gap') or '暂无').strip()}",
                "",
                "**该维度优化建议：**",
                f"- {(item.get('advice') or '暂无').strip()}",
                "",
            ]
        )

    lines.extend(
        [
            "### 3. 关键差距分析",
            "",
            "#### 🔴 JD 要求但简历缺失的关键项",
        ]
    )
    if critical_missing:
        lines.extend([f"{idx}. {txt}" for idx, txt in enumerate(critical_missing, 1)])
    else:
        lines.append("1. 暂无明确缺失项，建议结合 JD 继续核对工程化要求。")
    lines.extend(["", "#### 🟢 简历中的优势但未被 JD 提及的项"])
    if extra_advantages:
        lines.extend([f"{idx}. {txt}" for idx, txt in enumerate(extra_advantages, 1)])
    else:
        lines.append("1. 暂无额外优势项。")

    lines.extend(["", "### 4. 优化建议"])
    if suggestions:
        lines.extend([f"- {txt}" for txt in suggestions])
    else:
        lines.append("- 暂无优化建议。")

    lines.extend(
        [
            "",
            "### 5. 确认优化建议 → 生成完整简历",
            "",
            "请先确认以下三点，我再生成优化后的完整 Markdown 简历：",
            "- 哪些建议采纳、哪些不采纳",
            "- 标注了 ⚠️ 的改写是否符合事实",
            "- 是否有需要补充或修改的地方",
            "",
            "### 6. HTML 报告输出（可选）",
            "",
            f"「{HTML_OFFER_TEXT}」",
        ]
    )

    if result.get("optimized_resume_markdown"):
        lines.append("")
        lines.append("（已检测到可用的优化简历草稿，等您确认采纳项后我再输出最终版。）")

    return "\n".join(lines)


def _query_value(name: str) -> str:
    try:
        value = st.query_params.get(name, "")
    except Exception:
        try:
            value = st.experimental_get_query_params().get(name, [""])
        except Exception:
            return ""
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value or "").strip()


def _load_profile_prefill() -> dict:
    payload = {}
    prefill_file = _query_value("prefill_file")
    if prefill_file:
        try:
            path = Path(prefill_file).expanduser()
            if path.exists() and path.is_file():
                data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
                if isinstance(data, dict):
                    payload.update(data)
        except Exception:
            pass

    role = _query_value("target_role")
    jd_text = _query_value("target_jd")
    resume_path = _query_value("resume_path")
    has_resume = _query_value("has_resume")
    if role and not payload.get("target_role"):
        payload["target_role"] = role
    if jd_text and not payload.get("target_jd"):
        payload["target_jd"] = jd_text
    if resume_path and not payload.get("resume_path"):
        payload["resume_path"] = resume_path
    if has_resume and ("has_resume" not in payload):
        payload["has_resume"] = has_resume
    payload["profile_source"] = _query_value("profile_source")
    return payload


def _to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "on"}


def _normalize_choice_text(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").strip().lower())


def _resolve_profile_choice(text: str) -> str:
    norm = _normalize_choice_text(text)
    if norm in {"1", "选1", "选择1", "使用已保存信息"}:
        return "saved"
    if any(k in norm for k in ("使用已保存", "用已保存", "已保存", "saved")):
        return "saved"
    if norm in {"2", "选2", "选择2", "使用新提交信息"}:
        return "new"
    if any(k in norm for k in ("使用新提交", "用新提交", "新提交", "重新提交", "new")):
        return "new"
    if any(k in (text or "") for k in ("【目标岗位JD】", "[目标岗位JD]")):
        return "new"
    if (text or "").startswith(("JD：", "jd：", "职位JD：", "岗位：")):
        return "new"
    return ""


def _is_choice_command_only(text: str) -> bool:
    norm = _normalize_choice_text(text)
    command_only = {
        "使用已保存信息", "使用已保存", "已保存", "saved", "1", "选1", "选择1",
        "使用新提交信息", "使用新提交", "新提交", "重新提交", "new", "2", "选2", "选择2",
    }
    return norm in command_only


def _init_state():
    _load_local_env()
    prefill = _load_profile_prefill()
    role = (prefill.get("target_role") or "").strip()
    jd_text = (prefill.get("target_jd") or "").strip()
    has_saved_profile = bool(role and jd_text)

    choice_prompt = (
        "检测到您已保存目标岗位和 JD。\n"
        "请选择：\n"
        "1) 使用已保存信息\n"
        "2) 使用新提交信息\n\n"
        "你可以直接回复“使用已保存信息”或“使用新提交信息”。"
    )

    if "agent" not in st.session_state:
        st.session_state.agent = CareerForgeAgent()
    if "messages" not in st.session_state:
        if has_saved_profile:
            st.session_state.messages = [{"role": "assistant", "content": choice_prompt}]
        else:
            st.session_state.messages = [
                {
                    "role": "assistant",
                    "content": (
                        "请先给我两项材料，我就能直接开始做匹配度分析：\n"
                        "简历（PDF/DOCX/文字都行）\n"
                        "目标岗位 JD（文字/截图/链接都行）\n\n"
                        "您可以直接按这个格式发我（最省时间）：\n"
                        "【简历】\n"
                        "（粘贴全文，或告诉我文件路径）\n\n"
                        "【目标岗位JD】\n"
                        "（粘贴全文，或给链接/截图）\n\n"
                        "收到后我会给您一份完整报告：总分、A/B/C 匹配等级、6 维度评分、关键差距和可执行优化建议。"
                    ),
                }
            ]
    elif has_saved_profile:
        msgs = st.session_state.messages
        if (
            isinstance(msgs, list)
            and len(msgs) == 1
            and msgs[0].get("role") == "assistant"
            and "请先给我两项材料" in (msgs[0].get("content") or "")
        ):
            st.session_state.messages = [{"role": "assistant", "content": choice_prompt}]
    if "resume_text" not in st.session_state:
        st.session_state.resume_text = ""
    if "jd_text" not in st.session_state:
        st.session_state.jd_text = ""
    if "target_role" not in st.session_state:
        st.session_state.target_role = ""
    if "analysis_result" not in st.session_state:
        st.session_state.analysis_result = None
    if "html_offer_pending" not in st.session_state:
        st.session_state.html_offer_pending = False
    if "html_report_path" not in st.session_state:
        st.session_state.html_report_path = ""
    if "html_report_name" not in st.session_state:
        st.session_state.html_report_name = ""
    if "html_state" not in st.session_state:
        st.session_state.html_state = {
            "running": False,
            "run_id": "",
            "queue": None,
            "thread": None,
            "progress_pct": 0,
            "stage": "",
            "started_at": 0.0,
            "error": "",
        }
    if "saved_target_role" not in st.session_state:
        st.session_state.saved_target_role = ""
    if "saved_target_jd" not in st.session_state:
        st.session_state.saved_target_jd = ""
    if "saved_resume_path" not in st.session_state:
        st.session_state.saved_resume_path = ""
    if "saved_has_resume" not in st.session_state:
        st.session_state.saved_has_resume = False
    if "saved_resume_text" not in st.session_state:
        st.session_state.saved_resume_text = ""
    if "profile_choice" not in st.session_state:
        st.session_state.profile_choice = "none"
    if "_profile_prefill_loaded" not in st.session_state:
        st.session_state._profile_prefill_loaded = False

    if not st.session_state._profile_prefill_loaded:
        if has_saved_profile:
            st.session_state.saved_target_role = role
            st.session_state.saved_target_jd = jd_text
            st.session_state.saved_resume_path = (prefill.get("resume_path") or "").strip()
            st.session_state.saved_has_resume = _to_bool(prefill.get("has_resume"))
            st.session_state.profile_choice = "pending"
        else:
            st.session_state.profile_choice = "none"
        st.session_state._profile_prefill_loaded = True


def _append(role: str, content: str):
    st.session_state.messages.append({"role": role, "content": content})


def _read_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        parts = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        return "\n".join(parts).strip()
    except Exception:
        return ""


def _read_text_from_path(path_text: str) -> str:
    raw = (path_text or "").strip()
    if not raw:
        return ""
    # Most user inputs are resume body text; only treat as a file path if it
    # looks like one (single line + extension/path separators).
    looks_like_path = (
        "\n" not in raw
        and len(raw) <= 260
        and (
            raw.startswith("/")
            or raw.startswith("~/")
            or raw.startswith("./")
            or raw.startswith("../")
            or re.match(r"^[A-Za-z]:\\", raw) is not None
            or raw.lower().endswith((".pdf", ".docx", ".txt", ".md"))
        )
    )
    if not looks_like_path:
        return ""

    path = Path(raw).expanduser()
    try:
        if not path.exists() or not path.is_file():
            return ""
    except OSError:
        return ""
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            return _read_pdf_text(path)
        if suffix in {".txt", ".md"}:
            return path.read_text(encoding="utf-8", errors="ignore").strip()
        if suffix == ".docx":
            # Lightweight DOCX text extraction without extra deps.
            with zipfile.ZipFile(path, "r") as zf:
                xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
            xml = re.sub(r"<w:p[^>]*>", "\n", xml)
            xml = re.sub(r"<[^>]+>", "", xml)
            return re.sub(r"\n{2,}", "\n", xml).strip()
    except Exception:
        return ""
    return ""


def _extract_sections(text: str):
    # Support both Chinese brackets and ASCII brackets:
    # 【简历】 / [简历], 【目标岗位JD】 / [目标岗位JD]
    resume_match = re.search(
        r"(?:【简历】|\[简历\])\s*(.*?)(?=(?:【目标岗位JD】|\[目标岗位JD\])|$)",
        text,
        re.S,
    )
    jd_match = re.search(r"(?:【目标岗位JD】|\[目标岗位JD\])\s*(.*)", text, re.S)
    resume_text = resume_match.group(1).strip() if resume_match else ""
    jd_text = jd_match.group(1).strip() if jd_match else ""
    return resume_text, jd_text


def _read_resume_from_path(path_text: str) -> str:
    raw = (path_text or "").strip()
    if not raw:
        return ""
    path = Path(raw).expanduser()
    try:
        if not path.exists() or not path.is_file():
            return ""
    except OSError:
        return ""
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            return _read_pdf_text(path)
        if suffix in {".txt", ".md"}:
            return path.read_text(encoding="utf-8", errors="ignore").strip()
        if suffix == ".docx":
            with zipfile.ZipFile(path, "r") as zf:
                xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
            xml = re.sub(r"<w:p[^>]*>", "\n", xml)
            xml = re.sub(r"<[^>]+>", "", xml)
            return re.sub(r"\n{2,}", "\n", xml).strip()
    except Exception:
        return ""
    return ""


def _ensure_saved_resume_loaded() -> str:
    cached = (st.session_state.saved_resume_text or "").strip()
    if cached:
        return cached
    if not st.session_state.saved_has_resume:
        return ""
    resume_path = (st.session_state.saved_resume_path or "").strip()
    if not resume_path:
        return ""
    parsed = _read_resume_from_path(resume_path)
    if parsed:
        st.session_state.saved_resume_text = parsed
    return parsed


def _emit_html_event(run_queue, event_type: str, **kwargs):
    payload = {"type": event_type}
    payload.update(kwargs)
    run_queue.put(payload)


def _worker_generate_html_report(run_id: str, run_queue, analysis_result: dict, resume_text: str, target_role: str, jd_text: str):
    try:
        _emit_html_event(run_queue, "stage", text="正在整理匹配分析数据...", progress=15)
        time.sleep(0.25)
        _emit_html_event(run_queue, "stage", text="正在构建报告页面结构...", progress=45)
        report_name, html_doc = _build_html_report(analysis_result, resume_text, target_role, jd_text)
        time.sleep(0.25)
        _emit_html_event(run_queue, "stage", text="正在写入 HTML 文件...", progress=78)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = OUTPUT_DIR / report_name
        out_path.write_text(html_doc, encoding="utf-8")
        time.sleep(0.2)
        _emit_html_event(run_queue, "done", progress=100, output_file=str(out_path), output_name=report_name)
    except Exception as e:
        _emit_html_event(run_queue, "error", message=str(e))


def _start_html_generation():
    analysis_result = st.session_state.analysis_result
    if not analysis_result:
        _append("assistant", "请先完成简历与 JD 匹配分析，再生成 HTML 报告。")
        return
    html_state = st.session_state.html_state
    if html_state.get("running"):
        return

    run_id = datetime.now().strftime("%Y%m%d%H%M%S")
    run_queue = queue.Queue()
    thread = threading.Thread(
        target=_worker_generate_html_report,
        args=(
            run_id,
            run_queue,
            analysis_result,
            (st.session_state.resume_text or "").strip(),
            (st.session_state.target_role or "").strip(),
            (st.session_state.jd_text or "").strip(),
        ),
        daemon=True,
    )
    html_state.update(
        {
            "running": True,
            "run_id": run_id,
            "queue": run_queue,
            "thread": thread,
            "progress_pct": 0,
            "stage": "任务已启动",
            "started_at": time.time(),
            "error": "",
        }
    )
    st.session_state.html_offer_pending = False
    thread.start()


def _drain_html_events():
    html_state = st.session_state.html_state
    if not html_state.get("running"):
        return
    run_queue = html_state.get("queue")
    if run_queue is None:
        return

    while True:
        try:
            ev = run_queue.get_nowait()
        except queue.Empty:
            break

        ev_type = ev.get("type")
        if ev_type == "stage":
            html_state["stage"] = (ev.get("text") or "").strip() or "生成中"
            html_state["progress_pct"] = max(0, min(100, _to_int(ev.get("progress"), 0)))
        elif ev_type == "done":
            html_state["running"] = False
            html_state["stage"] = "已完成"
            html_state["progress_pct"] = 100
            output_file = (ev.get("output_file") or "").strip()
            output_name = (ev.get("output_name") or "").strip()
            st.session_state.html_report_path = output_file
            st.session_state.html_report_name = output_name
            _append(
                "assistant",
                f"HTML 报告已生成完成：`{output_file}`\n\n"
                "可以直接在浏览器打开、截图或分享；如果你愿意，我还可以继续帮你导出 PDF 版本。",
            )
        elif ev_type == "error":
            html_state["running"] = False
            html_state["stage"] = "运行失败"
            html_state["progress_pct"] = 0
            html_state["error"] = (ev.get("message") or "HTML 报告生成失败").strip()
            _append("assistant", f"HTML 报告生成失败：{html_state['error']}")

    thread = html_state.get("thread")
    if html_state.get("running") and thread and (not thread.is_alive()):
        html_state["running"] = False
        if not st.session_state.html_report_path and not html_state.get("error"):
            html_state["error"] = "生成线程已结束，但未检测到有效输出。"
            _append("assistant", "HTML 报告生成异常结束，请重试一次。")


def _render_html_generation_panel():
    html_state = st.session_state.html_state
    if not html_state.get("running"):
        return
    stage = html_state.get("stage") or "生成中..."
    progress = max(0, min(100, _to_int(html_state.get("progress_pct"), 0)))
    elapsed = int(time.time() - float(html_state.get("started_at") or time.time()))
    st.progress(progress, text=f"{stage}（已运行 {elapsed}s）")


def _render_report_download():
    output_path = (st.session_state.html_report_path or "").strip()
    if not output_path:
        return
    path = Path(output_path)
    if not path.exists():
        st.warning(f"已记录输出文件路径，但文件不存在：{output_path}")
        return
    st.success(f"HTML 报告已保存：`{path}`")
    st.download_button(
        "下载 HTML 报告",
        data=path.read_text(encoding="utf-8", errors="ignore"),
        file_name=path.name,
        mime="text/html",
        use_container_width=True,
    )


def _run_analysis():
    resume_text = (st.session_state.resume_text or "").strip()
    jd_text = (st.session_state.jd_text or "").strip()
    target_role = (st.session_state.target_role or "").strip()

    missing = []
    if not resume_text:
        missing.append("简历内容")
    if not jd_text:
        missing.append("岗位JD")

    if missing:
        _append("assistant", f"还缺少：{', '.join(missing)}。请补充后再输入“开始分析”。")
        return

    payload = {
        "resume_text": resume_text[:20000],
        "jd_text": jd_text[:12000],
        "target_role": target_role,
    }

    with st.chat_message("assistant"):
        placeholder = st.empty()
        raw_stream = ""
        status = "正在进行匹配度分析..."
        placeholder.markdown(status)
        for chunk in st.session_state.agent.stream_resume_match(payload):
            raw_stream += chunk
            preview = raw_stream[-1200:]
            placeholder.markdown(
                "正在进行匹配度分析...\n\n"
                "```json\n"
                f"{preview}"
                "\n```"
            )

        result = st.session_state.agent.parse_json_output(raw_stream) or {
            "error": "invalid_json_output",
            "message": "模型返回内容不是有效 JSON",
            "raw_text": raw_stream[-3000:],
        }
        st.session_state.analysis_result = result

        if result.get("error"):
            final_text = _format_analysis(result)
            placeholder.markdown(final_text)
            _append("assistant", final_text)
            return

        if not result.get("dimension_scores"):
            final_text = (
                "分析结果结构不完整，我先把原始结果展示给您，请检查材料是否过短或模型配置是否正常：\n"
                + json.dumps(result, ensure_ascii=False, indent=2)[:3000]
            )
            placeholder.markdown(final_text)
            _append("assistant", final_text)
            return

        final_text = _format_analysis(result)
        placeholder.markdown(final_text)
        _append("assistant", final_text)
        st.session_state.html_offer_pending = True
        st.session_state.html_report_path = ""
        st.session_state.html_report_name = ""


def _answer_followup(question: str):
    analysis = st.session_state.analysis_result
    if not analysis:
        _append("assistant", "请先提供简历与 JD，并输入“开始分析”。")
        return
    content = st.session_state.agent.run_resume_match_followup(analysis, question)
    _append("assistant", content)


def _is_yes_reply(text: str) -> bool:
    raw = re.sub(r"\s+", "", (text or "").strip().lower())
    if not raw:
        return False
    yes_set = {
        "要", "好的", "好", "可以", "行", "需要", "同意", "yes", "y",
        "要生成", "生成", "生成html", "生成html页面", "生成报告", "继续生成",
    }
    return raw in yes_set


def _is_no_reply(text: str) -> bool:
    raw = re.sub(r"\s+", "", (text or "").strip().lower())
    if not raw:
        return False
    no_set = {"不要", "不用", "不需要", "先不用", "no", "n", "暂时不用"}
    return raw in no_set


def _wants_html_generation(text: str) -> bool:
    t = (text or "").strip()
    if not t or _is_no_reply(t):
        return False
    norm = re.sub(r"\s+", "", t.lower())

    # Avoid false positives from long resume/JD bodies containing words like
    # "生成" and "报告". Only explicit generation commands should trigger.
    explicit = {
        "生成html",
        "生成html报告",
        "生成html页面",
        "生成一个html页面",
        "生成一个html报告",
        "生成报告html",
        "导出html",
        "导出html报告",
        "做个html报告",
        "做一个html报告",
        "生成精美html页面",
        "生成精美html报告",
        "生成一个精美html页面",
        "生成一个精美的html页面",
        "生成精美的html页面",
        "生成一个精美html报告",
        "生成一个精美的html报告",
    }
    if norm in explicit:
        return True

    # Natural language fallback: short command + html keyword + generation verb.
    # This keeps intent robust while avoiding accidental triggers from long resume/JD text.
    if (
        len(norm) <= 42
        and ("html" in norm)
        and any(k in norm for k in ("生成", "导出", "做", "输出"))
        and any(k in norm for k in ("报告", "页面", "网页"))
    ):
        return True

    patterns = [
        r"^(请)?(帮我)?(生成|导出|做|输出)(一份|一下|个|一个)?(精美)?(的)?html(报告|页面|网页)?$",
        r"^(请)?(帮我)?(生成|导出|做|输出)(一份|一下|个|一个)?(匹配分析)?(报告|页面|网页)(html版)?$",
    ]
    return any(re.match(p, norm) for p in patterns)


def _apply_user_message(user_text: str):
    text = (user_text or "").strip()
    if not text:
        return
    _append("user", text)

    if st.session_state.profile_choice == "pending":
        choice = _resolve_profile_choice(text)
        if not choice:
            _append(
                "assistant",
                "先确认这一步：回复“使用已保存信息”或“使用新提交信息”。",
            )
            return

        if choice == "saved":
            st.session_state.profile_choice = "saved"
            if not (st.session_state.target_role or "").strip():
                st.session_state.target_role = st.session_state.saved_target_role
            if not (st.session_state.jd_text or "").strip():
                st.session_state.jd_text = st.session_state.saved_target_jd
            resume_loaded = False
            if not (st.session_state.resume_text or "").strip():
                saved_resume = _ensure_saved_resume_loaded()
                if saved_resume:
                    st.session_state.resume_text = saved_resume
                    resume_loaded = True
            if resume_loaded:
                _append("assistant", "已切换为“使用已保存信息”，并已读取已保存简历。可直接输入“开始分析”。")
            else:
                _append("assistant", "已切换为“使用已保存信息”。请继续提交简历，或直接输入“开始分析”。")
        else:
            st.session_state.profile_choice = "new"
            _append("assistant", "已切换为“使用新提交信息”。请发送新的目标岗位/JD。")

        if _is_choice_command_only(text):
            return

    lower = text.lower().strip()

    # Structured format:
    # 【简历】...【目标岗位JD】...
    resume_sec, jd_sec = _extract_sections(text)
    if resume_sec:
        maybe_file = _read_text_from_path(resume_sec)
        st.session_state.resume_text = maybe_file or resume_sec
    if jd_sec:
        st.session_state.jd_text = jd_sec

    # Lightweight shortcuts
    if text.startswith("简历："):
        raw = text.split("：", 1)[1].strip()
        st.session_state.resume_text = _read_text_from_path(raw) or raw
    elif text.startswith("JD：") or text.startswith("jd：") or text.startswith("职位JD："):
        st.session_state.jd_text = text.split("：", 1)[1].strip()
    elif text.startswith("岗位："):
        st.session_state.target_role = text.split("：", 1)[1].strip()

    if lower in {"开始分析", "分析", "run", "start"}:
        _run_analysis()
        return

    # Auto-run as soon as both materials are ready.
    # Keep this before HTML intent detection to avoid mis-triggering from
    # resume/JD text that happens to contain words like "生成" or "报告".
    if (st.session_state.resume_text or "").strip() and (st.session_state.jd_text or "").strip() and not st.session_state.analysis_result:
        _append("assistant", "材料已收到，正在开始匹配度分析...")
        _run_analysis()
        return

    if st.session_state.html_offer_pending:
        if _is_yes_reply(text) or _wants_html_generation(text):
            _append("assistant", "收到，开始为你生成精美 HTML 报告。生成期间会暂时锁定输入。")
            _start_html_generation()
            return
        if _is_no_reply(text):
            st.session_state.html_offer_pending = False
            _append("assistant", "好的，暂不生成 HTML 报告。你可以继续追问，或随时说“生成 HTML 报告”。")
            return

    if _wants_html_generation(text):
        if not st.session_state.analysis_result:
            _append("assistant", "请先完成简历与 JD 的匹配分析，分析完成后我会马上为你生成 HTML 报告。")
            return
        _append("assistant", "收到，开始为你生成精美 HTML 报告。生成期间会暂时锁定输入。")
        _start_html_generation()
        return

    if st.session_state.analysis_result:
        _answer_followup(text)
        return

    _append(
        "assistant",
        "我已收到。请继续发送两项材料：\n"
        "1) 简历  2) 目标岗位JD。\n"
        "推荐格式：\n"
        "【简历】... \n【目标岗位JD】...",
    )


def main():
    st.set_page_config(page_title="简历匹配分析助手", page_icon="📊", layout="wide")
    _init_state()
    _drain_html_events()

    st.title("简历匹配分析助手")
    if st.session_state.agent.llm is None:
        st.warning("模型未就绪：请先配置 DEEPSEEK_API_KEY / OPENAI_API_KEY。")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    _render_report_download()

    if st.session_state.html_state.get("running"):
        with st.chat_message("assistant"):
            st.markdown("正在生成 HTML 报告，请稍候...")
        _render_html_generation_panel()
        st.chat_input("正在生成 HTML 报告中，暂时不可输入", disabled=True)
        time.sleep(0.35)
        st.rerun()
    else:
        user_msg = st.chat_input("直接发送简历与JD，或继续追问")
        if user_msg:
            _apply_user_message(user_msg)
            st.rerun()


if __name__ == "__main__":
    main()
