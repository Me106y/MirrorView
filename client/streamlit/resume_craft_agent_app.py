import html
import os
import queue
import re
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.services.careerforge_agent import CareerForgeAgent
from utils.logger_handler import logger


SKILL_FILE = ROOT / "skills" / "CareerForge" / "skills" / "resume-craft" / "SKILL.md"
BASE_TEMPLATE_FILE = ROOT / "skills" / "CareerForge" / "skills" / "resume-craft" / "templates" / "resume-template.html"
PREVIEW_TEMPLATE_FILE = ROOT / "skills" / "CareerForge" / "skills" / "resume-craft" / "templates" / "CareerForge-模板预览.html"


TEMPLATE_MAP = {
    "01": ("Editorial", "Editorial 杂志编辑风"),
    "02": ("Minimal", "Minimal 极简主义"),
    "03": ("Sidebar Navy", "Sidebar Navy 深蓝双栏"),
    "04": ("Sidebar Dark", "Sidebar Dark 深灰左栏"),
    "05": ("Dark Header", "Dark Header 深色头部"),
    "06": ("Clean Teal", "Clean Teal 清新青色"),
    "07": ("Elegant", "Elegant 优雅对称"),
}


INITIAL_MESSAGE = """我们按“从零制作简历”开始，先完成第一轮信息收集。请直接按下面 3 项回复我：

目标岗位是什么？
如果有 JD，请一起贴上（越完整越好）。

你要哪种版本？
中文 / 英文 / 中英文双版

选一个模板编号 + 是否放照片
01 Editorial 杂志编辑风
02 Minimal 极简主义
03 Sidebar Navy 深蓝双栏
04 Sidebar Dark 深灰左栏
05 Dark Header 深色头部
06 Clean Teal 清新青色
07 Elegant 优雅对称
另外告诉我：放照片 或 不放照片（放的话后面再传图）。

你回复这 3 项后，我就进入下一轮，帮你快速出可投递初稿。"""


def _load_local_env():
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


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _load_resume_sources():
    if "resume_sources" in st.session_state:
        return st.session_state.resume_sources

    skill_spec = _read_text(SKILL_FILE)
    base_template = _read_text(BASE_TEMPLATE_FILE)
    preview_template = _read_text(PREVIEW_TEMPLATE_FILE)

    sources = {
        "skill_spec": skill_spec,
        "base_template": base_template,
        "preview_template": preview_template,
        "skill_ok": bool(skill_spec),
        "base_ok": bool(base_template),
        "preview_ok": bool(preview_template),
    }
    st.session_state.resume_sources = sources

    logger.info(
        "[resume-craft-ui] loaded sources: skill=%s(%d), base=%s(%d), preview=%s(%d)",
        sources["skill_ok"],
        len(skill_spec),
        sources["base_ok"],
        len(base_template),
        sources["preview_ok"],
        len(preview_template),
    )
    return sources


def _init_state():
    _load_local_env()
    _load_resume_sources()
    if "agent" not in st.session_state:
        st.session_state.agent = CareerForgeAgent()
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": INITIAL_MESSAGE}]
    if "run_state" not in st.session_state:
        st.session_state.run_state = {
            "running": False,
            "run_id": "",
            "queue": None,
            "cancel_event": None,
            "thread": None,
            "assistant_buffer": "",
            "generated_html": "",
            "stage": "",
            "stage_index": 0,
            "stage_total": 100,
            "progress_pct": 0,
            "stage_logs": [],
            "error": "",
            "canceled": False,
            "finalized": False,
            "started_at": 0.0,
            "output_file_path": "",
            "output_file_name": "",
            "should_save_output": False,
            "output_error": "",
            "used_fallback_html": False,
            "selected_template_code": "",
            "selected_template_name": "",
        }


def _append(role: str, content: str):
    st.session_state.messages.append({"role": role, "content": content})


def _history_to_text(max_turns=22):
    msgs = st.session_state.messages[-max_turns:]
    lines = []
    for m in msgs:
        role = "用户" if m["role"] == "user" else "助手"
        lines.append(f"{role}: {m['content']}")
    return "\n".join(lines)


def _get_last_assistant_message() -> str:
    for msg in reversed(st.session_state.messages):
        if msg.get("role") == "assistant":
            return (msg.get("content") or "").strip()
    return ""


def _detect_template_choice(history_text: str):
    text = history_text or ""
    lower = text.lower()

    name_alias = {
        "01": ["editorial", "杂志编辑"],
        "02": ["minimal", "极简"],
        "03": ["sidebar navy", "深蓝双栏"],
        "04": ["sidebar dark", "深灰左栏"],
        "05": ["dark header", "深色头部"],
        "06": ["clean teal", "清新青色"],
        "07": ["elegant", "优雅对称"],
    }

    for code, aliases in name_alias.items():
        for alias in aliases:
            if alias in lower:
                english, display = TEMPLATE_MAP[code]
                return code, english, display

    num_hits = re.findall(r"(?:模板|编号|选择|选|风格)?\s*0?([1-7])\b", text)
    if num_hits:
        code = f"0{num_hits[-1]}"
        english, display = TEMPLATE_MAP[code]
        return code, english, display

    english, display = TEMPLATE_MAP["02"]
    return "02", english, display


def _extract_preview_snippet(preview_html: str, template_code: str) -> str:
    if not preview_html:
        return ""
    idx = int(template_code)

    css_marker = f"/* == T{idx}:"
    css_start = preview_html.find(css_marker)
    css_part = ""
    if css_start != -1:
        css_part = preview_html[css_start:css_start + 2500]

    card_marker = f"<!-- T{idx}"
    card_start = preview_html.find(card_marker)
    card_part = ""
    if card_start != -1:
        card_part = preview_html[card_start:card_start + 3500]

    return (css_part + "\n\n" + card_part).strip()[:5000]


def _detect_photo_preference(history_text: str):
    t = (history_text or "").lower()
    if "不放照片" in t or ("不放" in t and "照片" in t):
        return "不放照片"
    if "放照片" in t:
        return "放照片"
    return "未明确"


def _detect_language(history_text: str):
    t = (history_text or "").lower()
    if "中英文" in t or "双版" in t:
        return "中英文双版"
    if "英文" in t and "中文" not in t:
        return "英文"
    return "中文"


def _is_final_confirmation_context(last_assistant: str):
    t = (last_assistant or "").lower()
    patterns = [
        ("确认后", "生成"),
        ("最后确认", "生成"),
        ("没有其他补充", "生成"),
        ("立即为你生成", "html"),
        ("请稍等", "生成"),
        ("生成完毕后", "链接"),
    ]
    return any(a in t and b in t for a, b in patterns)


def _should_save_output_for_turn(user_text: str):
    text = (user_text or "").strip().lower()
    if not text:
        return False

    direct_keywords = [
        "生成简历",
        "生成html",
        "输出简历",
        "导出简历",
        "最终简历",
        "最终版",
        "定稿",
        "请生成",
        "generate resume",
        "final resume",
    ]
    if any(k in text for k in direct_keywords):
        return True

    last_assistant = _get_last_assistant_message()
    if not _is_final_confirmation_context(last_assistant):
        return False

    deny_words = ["修改", "调整", "改成", "想改", "还有", "补充", "先不要", "等等", "等下"]
    if any(w in text for w in deny_words):
        return False

    return True


def _chunk_to_text(chunk):
    if isinstance(chunk, str):
        return chunk
    content = getattr(chunk, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                val = item.get("text", "")
                if val:
                    parts.append(val)
            else:
                val = getattr(item, "text", "")
                if val:
                    parts.append(val)
        return "".join(parts)
    return ""


def _extract_html_document(text: str):
    raw = (text or "").strip()
    if not raw:
        return ""

    fenced = re.search(r"```(?:html)?\s*(.*?)```", raw, re.IGNORECASE | re.DOTALL)
    candidate = fenced.group(1).strip() if fenced else raw

    m = re.search(r"(?is)<!doctype\s+html.*?</html>", candidate)
    if m:
        return m.group(0).strip()
    m = re.search(r"(?is)<html.*?</html>", candidate)
    if m:
        doc = m.group(0).strip()
        if "<!doctype" not in doc.lower():
            doc = "<!DOCTYPE html>\n" + doc
        return doc
    return ""


def _build_fallback_html(raw_text: str, template_display: str):
    safe = html.escape((raw_text or "").strip()[:12000]).replace("\n", "<br>")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>简历生成结果</title>
<style>
  body {{
    font-family: -apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;
    background: #f5f6f7;
    margin: 0;
  }}
  .export-bar {{
    position: fixed; top: 0; left: 0; right: 0;
    background: rgba(17,17,17,0.92); color: #fff;
    padding: 10px 16px; display: flex; gap: 12px; align-items: center; z-index: 1000;
  }}
  .export-btn {{
    border: none; background: #14b8a6; color: #fff; padding: 8px 16px; border-radius: 6px; cursor: pointer;
  }}
  .resume {{
    max-width: 820px; margin: 72px auto 40px; background: #fff; padding: 28px; box-shadow: 0 8px 28px rgba(0,0,0,.08);
  }}
  .warn {{
    background: #fff8e1; border: 1px solid #f5d489; color: #7a5c00; padding: 10px 12px; border-radius: 8px; margin-bottom: 14px;
    font-size: 14px;
  }}
  .content {{ color: #222; line-height: 1.65; font-size: 14px; }}
  @page {{ size: A4; margin: 0; }}
  @media print {{
    html, body {{
      -webkit-print-color-adjust: exact !important;
      print-color-adjust: exact !important;
      background: #fff !important;
    }}
    .export-bar {{ display: none !important; }}
    .resume {{ margin: 0; box-shadow: none; max-width: 100%; }}
  }}
</style>
</head>
<body>
  <div class="export-bar">
    <button class="export-btn" onclick="exportPDF()">导出 PDF</button>
    <span>⚠️ 另存为 PDF → A4 → 边距“无” → 勾选“背景图形”</span>
  </div>
  <div class="resume">
    <div class="warn">已进入兜底 HTML 模式（模板：{html.escape(template_display)}）。建议点击“重新生成最终简历”获取完整排版版式。</div>
    <div class="content">{safe}</div>
  </div>
  <script>
    function exportPDF() {{
      window.print();
    }}
  </script>
</body>
</html>"""


def _build_dialog_prompt(user_text: str, sources: dict):
    skill_spec = sources.get("skill_spec", "")
    return f"""
你是“简历生成助手”，需要和用户进行多轮 human-in-the-loop 对话，目标是收集完整简历信息并逐步打磨到可投递状态。

执行规则（必须遵守）：
1) 始终围绕简历生成，不跑题。
2) 每轮最多追问 2-3 个问题。
3) 不得编造用户经历，不夸大资历；信息不完整时先追问。
4) 当用户已经选择模板编号后，后续不要再次要求确认模板，除非用户主动更换。
5) 不输出 JSON，不输出代码块，只输出给用户可直接阅读的话。

[SKILL.md 核心规范]
{skill_spec[:13000]}

[最近对话]
{_history_to_text()}

[用户最新输入]
{user_text}
"""


def _build_final_html_prompt(sources: dict, template_code: str, template_en: str, template_display: str):
    skill_spec = sources.get("skill_spec", "")
    base_template = sources.get("base_template", "")
    preview_template = sources.get("preview_template", "")
    preview_snippet = _extract_preview_snippet(preview_template, template_code)
    language = _detect_language(_history_to_text(24))
    photo_pref = _detect_photo_preference(_history_to_text(24))

    return f"""
你是简历 HTML 生成器。请直接输出最终 HTML，不要任何解释文字。

必须严格遵守以下要求：
1) 只输出完整 HTML 文档（从 <!DOCTYPE html> 到 </html>）。
2) 目标模板：{template_code} / {template_en} / {template_display}。
3) 语言要求：{language}。
4) 照片偏好：{photo_pref}。
5) 必须包含导出按钮（window.print）、@page A4、@media print、分页控制。
6) 内容结构与视觉风格遵循 SKILL.md，且不编造事实。
7) 若用户已在早期选定模板，禁止再次确认模板。

[SKILL.md 规范全文节选]
{skill_spec[:18000]}

[resume-template.html 参考（Editorial 完整结构）]
{base_template[:22000]}

[CareerForge-模板预览.html 选中模板片段]
{preview_snippet[:5000]}

[已确认对话事实]
{_history_to_text(28)}
"""


def _emit_event(run_queue, ev_type: str, **payload):
    run_queue.put({"type": ev_type, **payload})


def _emit_stage(run_queue, text: str, progress: int):
    _emit_event(run_queue, "stage", text=text, progress=max(0, min(100, progress)))


def _worker_generate_reply(
    run_id: str,
    run_queue,
    cancel_event,
    agent,
    dialog_prompt: str,
    html_prompt: str,
    final_mode: bool,
    template_display: str,
):
    try:
        logger.info("[resume-craft-ui][%s] run started (final_mode=%s)", run_id, final_mode)
        _emit_stage(run_queue, "已接收请求，准备处理...", 5)

        if cancel_event.is_set():
            _emit_event(run_queue, "canceled")
            return

        if agent.llm is None:
            _emit_event(
                run_queue,
                "error",
                message="当前模型未就绪，请先配置 DEEPSEEK_API_KEY / OPENAI_API_KEY。",
            )
            return

        if not final_mode:
            _emit_stage(run_queue, "模型思考中...", 40)
            generated = False
            for chunk in agent.llm.stream(dialog_prompt):
                if cancel_event.is_set():
                    _emit_event(run_queue, "canceled")
                    return
                piece = _chunk_to_text(chunk)
                if piece:
                    generated = True
                    _emit_event(run_queue, "chunk", text=piece)

            if not generated:
                _emit_stage(run_queue, "模型返回较慢，进行兜底生成...", 55)
                text = agent.llm.invoke(dialog_prompt)
                content = getattr(text, "content", str(text))
                final = (content or "").strip() or "我已收到，继续把下一轮信息发我即可。"
                _emit_event(run_queue, "chunk", text=final)

            _emit_stage(run_queue, "输出整理完成", 95)
            _emit_event(run_queue, "done")
            return

        _emit_event(run_queue, "chunk", text="好的，已收到确认。我正在生成最终 HTML 简历文件。")
        _emit_stage(run_queue, "已进入最终生成阶段", 20)
        _emit_stage(run_queue, "已读取 SKILL.md、resume-template.html、CareerForge-模板预览.html", 30)
        _emit_stage(run_queue, "正在生成 HTML 简历文件...", 40)

        html_parts = []
        streamed_chars = 0
        for chunk in agent.llm.stream(html_prompt):
            if cancel_event.is_set():
                _emit_event(run_queue, "canceled")
                return
            piece = _chunk_to_text(chunk)
            if piece:
                html_parts.append(piece)
                streamed_chars += len(piece)
                # Stream phase progress 40-75
                p = min(75, 40 + streamed_chars // 120)
                _emit_stage(run_queue, "正在生成 HTML 简历文件...", p)

        html_raw = "".join(html_parts).strip()
        if not html_raw:
            _emit_stage(run_queue, "HTML流式结果为空，正在重试一次...", 78)
            text = agent.llm.invoke(html_prompt)
            html_raw = getattr(text, "content", str(text)) or ""

        _emit_stage(run_queue, "正在校验 HTML 结构...", 85)
        html_doc = _extract_html_document(html_raw)
        if not html_doc:
            _emit_stage(run_queue, "未检测到有效 HTML，正在启用兜底生成...", 90)
            second_prompt = (
                html_prompt
                + "\n\n再次强调：现在必须只输出完整HTML（<!DOCTYPE html>... </html>），不得有其他文字。"
            )
            text = agent.llm.invoke(second_prompt)
            html_doc = _extract_html_document(getattr(text, "content", str(text)))

        used_fallback = False
        if not html_doc:
            used_fallback = True
            html_doc = _build_fallback_html(html_raw, template_display)

        _emit_event(run_queue, "html_output", html=html_doc, fallback=used_fallback)
        _emit_stage(run_queue, "HTML 文件生成完成，准备写入 output...", 96)
        _emit_event(run_queue, "done")
    except Exception as e:
        logger.exception("[resume-craft-ui][%s] run failed: %s", run_id, e)
        _emit_event(run_queue, "error", message=f"当前生成异常：{e}")


def _save_resume_output(html_doc: str, run_id: str):
    doc = _extract_html_document(html_doc)
    if not doc:
        return None
    output_dir = ROOT / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"resume_{ts}_{run_id}.html"
    file_path = output_dir / file_name
    file_path.write_text(doc + "\n", encoding="utf-8")
    logger.info("[resume-craft-ui][%s] output saved: %s", run_id, file_path)
    return file_path


def _start_generation(user_text: str):
    _append("user", user_text)
    run_id = uuid.uuid4().hex[:8]
    run_queue = queue.Queue()
    cancel_event = threading.Event()

    sources = _load_resume_sources()
    should_save_output = _should_save_output_for_turn(user_text)
    history = _history_to_text(28)
    template_code, template_en, template_display = _detect_template_choice(history)

    dialog_prompt = _build_dialog_prompt(user_text, sources)
    html_prompt = ""
    if should_save_output:
        html_prompt = _build_final_html_prompt(sources, template_code, template_en, template_display)

    run_state = st.session_state.run_state
    run_state.update(
        {
            "running": True,
            "run_id": run_id,
            "queue": run_queue,
            "cancel_event": cancel_event,
            "thread": None,
            "assistant_buffer": "",
            "generated_html": "",
            "stage": "任务已启动",
            "stage_index": 0,
            "stage_total": 100,
            "progress_pct": 0,
            "stage_logs": [f"{time.strftime('%H:%M:%S')} 任务已启动"],
            "error": "",
            "canceled": False,
            "finalized": False,
            "started_at": time.time(),
            "output_file_path": "",
            "output_file_name": "",
            "should_save_output": should_save_output,
            "output_error": "",
            "used_fallback_html": False,
            "selected_template_code": template_code,
            "selected_template_name": template_display,
        }
    )

    logger.info(
        "[resume-craft-ui][%s] queued by user (final_mode=%s, template=%s %s)",
        run_id,
        should_save_output,
        template_code,
        template_display,
    )

    thread = threading.Thread(
        target=_worker_generate_reply,
        args=(
            run_id,
            run_queue,
            cancel_event,
            st.session_state.agent,
            dialog_prompt,
            html_prompt,
            should_save_output,
            template_display,
        ),
        daemon=True,
    )
    run_state["thread"] = thread
    thread.start()


def _finalize_run(reason: str):
    run_state = st.session_state.run_state
    if run_state.get("finalized"):
        return

    final_text = ""
    if reason == "canceled":
        partial = (run_state.get("assistant_buffer") or "").strip()
        final_text = f"{partial}\n\n（已终止本次生成）" if partial else "已终止本次生成。"
    elif reason == "error":
        partial = (run_state.get("assistant_buffer") or "").strip()
        err = run_state.get("error") or "生成失败，请稍后重试。"
        final_text = partial if partial else err
    elif run_state.get("should_save_output"):
        html_doc = (run_state.get("generated_html") or "").strip()
        saved = None
        if html_doc:
            try:
                saved = _save_resume_output(html_doc, run_state.get("run_id", "unknown"))
            except Exception as e:
                logger.exception("[resume-craft-ui][%s] failed to save output: %s", run_state.get("run_id"), e)
        if saved:
            run_state["output_file_path"] = str(saved)
            run_state["output_file_name"] = saved.name
            run_state["output_error"] = ""
            if run_state.get("used_fallback_html"):
                final_text = "HTML 简历已生成（兜底结构版），链接见下方。建议再点一次“重新生成最终简历”。"
            else:
                final_text = "HTML 简历已生成完成，链接见下方。"
        else:
            run_state["output_error"] = "本轮已进入最终生成阶段，但未成功生成可保存的 HTML。"
            final_text = "最终生成阶段未产出有效 HTML。请回复“重新生成最终简历”重试。"
    else:
        final_text = (run_state.get("assistant_buffer") or "").strip() or "我已收到，继续把下一轮信息发我即可。"

    _append("assistant", final_text)
    run_state["finalized"] = True
    logger.info("[resume-craft-ui][%s] finalized with reason=%s", run_state.get("run_id"), reason)


def _drain_events():
    run_state = st.session_state.run_state
    if not run_state.get("running"):
        return
    run_queue = run_state.get("queue")
    if run_queue is None:
        return

    while True:
        try:
            ev = run_queue.get_nowait()
        except queue.Empty:
            break

        ev_type = ev.get("type")
        if ev_type == "stage":
            text = ev.get("text", "")
            progress = int(ev.get("progress", run_state.get("progress_pct", 0)))
            run_state["progress_pct"] = max(0, min(100, progress))
            run_state["stage"] = text
            if text:
                now_line = f"{time.strftime('%H:%M:%S')} {text}"
                logs = run_state["stage_logs"]
                if logs:
                    last = logs[-1]
                    last_text = last.split(" ", 1)[1] if " " in last else last
                    if last_text == text:
                        logs[-1] = now_line
                    else:
                        logs.append(now_line)
                else:
                    logs.append(now_line)
        elif ev_type == "chunk":
            run_state["assistant_buffer"] = (run_state.get("assistant_buffer") or "") + (ev.get("text", "") or "")
        elif ev_type == "html_output":
            run_state["generated_html"] = ev.get("html", "") or ""
            run_state["used_fallback_html"] = bool(ev.get("fallback", False))
        elif ev_type == "canceled":
            run_state["canceled"] = True
            run_state["running"] = False
            run_state["stage"] = "已终止"
            run_state["progress_pct"] = 0
            run_state["stage_logs"].append(f"{time.strftime('%H:%M:%S')} 已终止")
            _finalize_run("canceled")
        elif ev_type == "error":
            run_state["error"] = ev.get("message", "生成失败")
            run_state["running"] = False
            run_state["stage"] = "运行失败"
            run_state["progress_pct"] = 0
            run_state["stage_logs"].append(f"{time.strftime('%H:%M:%S')} 运行失败")
            _finalize_run("error")
        elif ev_type == "done":
            run_state["running"] = False
            run_state["stage"] = "已完成"
            run_state["progress_pct"] = 100
            run_state["stage_logs"].append(f"{time.strftime('%H:%M:%S')} 已完成")
            _finalize_run("done")

    thread = run_state.get("thread")
    if run_state.get("running") and thread and (not thread.is_alive()):
        run_state["running"] = False
        run_state["stage"] = "任务结束"
        run_state["stage_logs"].append(f"{time.strftime('%H:%M:%S')} 任务线程已结束")
        if run_state.get("error"):
            _finalize_run("error")
        else:
            _finalize_run("done")


def _request_cancel():
    run_state = st.session_state.run_state
    if not run_state.get("running"):
        return
    cancel_event = run_state.get("cancel_event")
    if cancel_event and not cancel_event.is_set():
        cancel_event.set()
        run_state["stage"] = "收到终止请求，正在停止..."
        run_state["stage_logs"].append(f"{time.strftime('%H:%M:%S')} 收到终止请求")
        logger.info("[resume-craft-ui][%s] cancel requested by user", run_state.get("run_id"))


def _render_run_panel():
    run_state = st.session_state.run_state
    if not run_state.get("running"):
        return
    stage = run_state.get("stage") or "运行中..."
    progress = int(run_state.get("progress_pct", 0))
    elapsed = int(time.time() - float(run_state.get("started_at") or time.time()))
    st.progress(max(0, min(100, progress)), text=f"{stage}（已运行 {elapsed}s）")
    with st.expander("查看运行流程", expanded=True):
        for line in run_state.get("stage_logs", [])[-16:]:
            st.markdown(f"- {line}")


def _render_output_link():
    run_state = st.session_state.run_state
    output_file_path = (run_state.get("output_file_path") or "").strip()
    if not output_file_path:
        if (not run_state.get("running")) and run_state.get("should_save_output"):
            output_error = (run_state.get("output_error") or "").strip()
            if output_error:
                st.warning(output_error)
        return

    path = Path(output_file_path)
    if not path.exists():
        st.warning(f"已记录输出文件路径，但文件不存在：{output_file_path}")
        return

    st.success(f"简历文件已保存到 output 目录：`{path}`")
    uri = path.as_uri()
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown(f"[打开生成文件]({uri})")
    with col2:
        st.download_button(
            "下载 HTML 简历",
            data=path.read_text(encoding="utf-8", errors="ignore"),
            file_name=path.name,
            mime="text/html",
            use_container_width=True,
        )


def _render_running_controls():
    spinner_frames = ["|", "/", "-", "\\"]
    frame = spinner_frames[int(time.time() * 6) % len(spinner_frames)]
    col1, col2 = st.columns([3, 1])
    with col1:
        st.button(f"{frame} 正在运行中...", disabled=True, use_container_width=True)
    with col2:
        if st.button("终止", use_container_width=True):
            _request_cancel()
    st.chat_input("正在生成中，暂时不可输入", disabled=True)


def _render_source_status():
    s = _load_resume_sources()
    ok = s.get("skill_ok") and s.get("base_ok") and s.get("preview_ok")
    if ok:
        st.caption("已加载：SKILL.md、resume-template.html、CareerForge-模板预览.html")
    else:
        st.warning(
            "模板源文件加载不完整："
            f"skill={s.get('skill_ok')} base={s.get('base_ok')} preview={s.get('preview_ok')}。"
        )


def main():
    st.set_page_config(page_title="简历生成助手", page_icon="📝", layout="wide")
    _init_state()
    _drain_events()

    st.title("简历生成助手")
    _render_source_status()
    if st.session_state.agent.llm is None:
        st.warning("模型未就绪：请先配置 DEEPSEEK_API_KEY / OPENAI_API_KEY。")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    run_state = st.session_state.run_state
    _render_run_panel()
    _render_output_link()

    if run_state.get("running"):
        with st.chat_message("assistant"):
            partial = (run_state.get("assistant_buffer") or "").strip()
            if partial:
                st.markdown(partial + "▌")
            else:
                st.markdown("正在处理，请稍候...")
        _render_running_controls()
        time.sleep(0.35)
        st.rerun()
    else:
        user_msg = st.chat_input("直接回复信息，助手会分轮引导你完成简历")
        if user_msg:
            _start_generation(user_msg)
            st.rerun()


if __name__ == "__main__":
    main()
