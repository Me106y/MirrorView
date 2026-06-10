import json
import os
import re
import sys
import zipfile
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.services.careerforge_agent import CareerForgeAgent


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

    lines = [
        f"整体匹配度：{result.get('overall_score', '-')}/100",
        f"匹配等级：{result.get('match_level', '-')}",
        f"总结：{result.get('summary', '无')}",
        "",
        "【维度评分】",
    ]
    for item in result.get("dimension_scores", []) or []:
        lines.append(f"- {item.get('name', '维度')}: {item.get('score', '-')}/100")
        if item.get("highlight"):
            lines.append(f"  亮点：{item.get('highlight')}")
        if item.get("gap"):
            lines.append(f"  差距：{item.get('gap')}")
        if item.get("advice"):
            lines.append(f"  建议：{item.get('advice')}")
    if result.get("critical_missing"):
        lines.append("")
        lines.append("【关键缺失项】")
        lines.extend([f"- {x}" for x in result.get("critical_missing", [])])
    if result.get("optimization_suggestions"):
        lines.append("")
        lines.append("【优化建议】")
        lines.extend([f"- {x}" for x in result.get("optimization_suggestions", [])])
    return "\n".join(lines)


def _init_state():
    _load_local_env()
    if "agent" not in st.session_state:
        st.session_state.agent = CareerForgeAgent()
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": (
                    "请先给我两项材料，我就能直接开始做匹配度分析：\n"
                    "简历（PDF/DOCX/文字都行）\n"
                    "目标岗位 JD（文字/截图/链接都行）\n\n"
                    "你可以直接按这个格式发我（最省时间）：\n"
                    "【简历】\n"
                    "（粘贴全文，或告诉我文件路径）\n\n"
                    "【目标岗位JD】\n"
                    "（粘贴全文，或给链接/截图）\n\n"
                    "收到后我会给你一份完整报告：总分、A/B/C 匹配等级、6 维度评分、关键差距和可执行优化建议。"
                ),
            }
        ]
    if "resume_text" not in st.session_state:
        st.session_state.resume_text = ""
    if "jd_text" not in st.session_state:
        st.session_state.jd_text = ""
    if "target_role" not in st.session_state:
        st.session_state.target_role = ""
    if "analysis_result" not in st.session_state:
        st.session_state.analysis_result = None


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
                "正在进行匹配度分析（流式输出中）...\n\n"
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
                "分析结果结构不完整，我先把原始结果展示给你，请检查材料是否过短或模型配置是否正常：\n"
                + json.dumps(result, ensure_ascii=False, indent=2)[:3000]
            )
            placeholder.markdown(final_text)
            _append("assistant", final_text)
            return

        final_text = _format_analysis(result)
        placeholder.markdown(final_text)
        _append("assistant", final_text)


def _answer_followup(question: str):
    analysis = st.session_state.analysis_result
    if not analysis:
        _append("assistant", "请先提供简历与 JD，并输入“开始分析”。")
        return
    if st.session_state.agent.llm is None:
        _append("assistant", "当前模型未就绪，请先配置 API Key 后再进行追问。")
        return

    prompt = f"""
你是职业顾问。基于下面的简历匹配分析结果，回答用户追问。
要求：回答具体、简洁、可执行，不编造经历。

分析结果JSON：
{json.dumps(analysis, ensure_ascii=False)}

用户问题：
{question}
"""
    try:
        text = st.session_state.agent.llm.invoke(prompt)
        content = getattr(text, "content", str(text))
        _append("assistant", content)
    except Exception as e:
        _append("assistant", f"回答追问失败：{e}")


def _apply_user_message(user_text: str):
    text = (user_text or "").strip()
    if not text:
        return
    _append("user", text)

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
    if (st.session_state.resume_text or "").strip() and (st.session_state.jd_text or "").strip() and not st.session_state.analysis_result:
        _append("assistant", "材料已收到，正在开始匹配度分析...")
        _run_analysis()
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

    st.title("简历匹配分析助手")
    if st.session_state.agent.llm is None:
        st.warning("模型未就绪：请先配置 DEEPSEEK_API_KEY / OPENAI_API_KEY。")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_msg = st.chat_input("直接发送简历与JD，或继续追问")
    if user_msg:
        _apply_user_message(user_msg)
        st.rerun()


if __name__ == "__main__":
    main()
