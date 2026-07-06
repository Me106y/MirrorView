import re
from datetime import datetime
from html import escape

WEIGHT_MAP = {
    "硬性技能匹配度": 25,
    "工作经验相关度": 25,
    "软性能力匹配度": 15,
    "教育背景匹配度": 10,
    "关键词覆盖率": 15,
    "简历质量": 10,
}

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


def build_resume_match_html_report(result: dict, resume_text: str, target_role: str, jd_text: str) -> tuple[str, str]:
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
      --bg: #f7f3ea;
      --card: #ffffff;
      --border: #e5e7eb;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
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

