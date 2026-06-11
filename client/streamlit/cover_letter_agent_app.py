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
            with zipfile.ZipFile(path, "r") as zf:
                xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
            xml = re.sub(r"<w:p[^>]*>", "\n", xml)
            xml = re.sub(r"<[^>]+>", "", xml)
            return re.sub(r"\n{2,}", "\n", xml).strip()
    except Exception:
        return ""
    return ""


def _extract_sections(text: str):
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


def _normalize_scenario(text: str):
    t = (text or "").strip().lower()
    if not t:
        return ""
    if t in {"a", "email", "邮件", "邮件投递", "正式求职信"}:
        return "email"
    if t in {"b", "chat", "打招呼", "招聘软件", "boss", "boss直聘", "猎聘", "拉勾"}:
        return "chat"
    if any(k in t for k in ["邮件", "mail", "求职信", "cover letter"]):
        return "email"
    if any(k in t for k in ["打招呼", "boss", "猎聘", "拉勾", "招聘软件", "chat"]):
        return "chat"
    return ""


def _normalize_language(text: str):
    t = (text or "").strip().lower()
    if not t:
        return ""
    if any(k in t for k in ["中英文", "双语", "both"]):
        return "both"
    if any(k in t for k in ["英文", "english", " en", "en ", "en"]):
        return "en"
    if any(k in t for k in ["中文", "chinese", " zh", "zh ", "zh"]):
        return "zh"
    return ""


def _append(role: str, content: str):
    st.session_state.messages.append({"role": role, "content": content})


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
                        "我们用纯对话来完成求职信。\n\n"
                        "请先发两项材料（可直接粘贴）：\n"
                        "【简历】...\n"
                        "【目标岗位JD】...\n\n"
                        "然后告诉我：\n"
                        "- 场景：A（邮件求职信）或 B（招聘软件打招呼）\n"
                        "- 语言：中文 / 英文 / 中英文两版\n"
                        "- 公司名（可选）\n"
                        "- 想强调的点（可选）"
                    ),
                }
            ]
    elif has_saved_profile:
        msgs = st.session_state.messages
        if (
            isinstance(msgs, list)
            and len(msgs) == 1
            and msgs[0].get("role") == "assistant"
            and "我们用纯对话来完成求职信" in (msgs[0].get("content") or "")
        ):
            st.session_state.messages = [{"role": "assistant", "content": choice_prompt}]
    if "resume_text" not in st.session_state:
        st.session_state.resume_text = ""
    if "jd_text" not in st.session_state:
        st.session_state.jd_text = ""
    if "target_role" not in st.session_state:
        st.session_state.target_role = ""
    if "scenario" not in st.session_state:
        st.session_state.scenario = ""
    if "language" not in st.session_state:
        st.session_state.language = ""
    if "company_name" not in st.session_state:
        st.session_state.company_name = ""
    if "emphasis" not in st.session_state:
        st.session_state.emphasis = ""
    if "last_result" not in st.session_state:
        st.session_state.last_result = None
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


def _missing_fields():
    missing = []
    if not (st.session_state.jd_text or "").strip():
        missing.append("目标岗位 JD")
    if not (st.session_state.resume_text or "").strip():
        missing.append("简历")
    if not (st.session_state.scenario or "").strip():
        missing.append("投递场景（A 邮件 / B 招聘软件）")
    if not (st.session_state.language or "").strip():
        missing.append("目标语言（中文/英文/中英文）")
    return missing


def _format_cover_letter(result: dict, scenario: str, language: str) -> str:
    if result.get("error"):
        msg = result.get("message") or result.get("error")
        return (
            "当前暂时无法完成求职信生成。\n"
            f"原因：{msg}\n\n"
            "请检查模型配置（例如 DEEPSEEK_API_KEY / OPENAI_API_KEY）后重试。"
        )

    scene = scenario or result.get("scenario", "")
    lang = language or result.get("language", "")
    cover_text = (result.get("cover_letter") or "").strip()
    greeting_text = (result.get("greeting_message") or "").strip()

    lines = []
    if scene == "chat":
        lines.extend(["【招聘软件打招呼】", greeting_text or "（未返回内容）"])
        if cover_text:
            lines.extend(["", "【可选：邮件版求职信】", cover_text])
    elif scene == "email":
        lines.extend(["【邮件版求职信】", cover_text or "（未返回内容）"])
        if greeting_text:
            lines.extend(["", "【可选：招聘软件打招呼】", greeting_text])
    else:
        lines.extend(
            [
                "【邮件版求职信】",
                cover_text or "（未返回内容）",
                "",
                "【招聘软件打招呼】",
                greeting_text or "（未返回内容）",
            ]
        )

    if result.get("key_points"):
        lines.append("")
        lines.append("【核心卖点】")
        lines.extend([f"- {x}" for x in (result.get("key_points") or [])])
    if result.get("tailoring_notes"):
        lines.append("")
        lines.append("【定制说明】")
        lines.extend([f"- {x}" for x in (result.get("tailoring_notes") or [])])

    lines.extend(
        [
            "",
            "求职信已经写好了，你看看有什么需要调整的？比如想换个角度强调、增减某段经历、调整语气风格等。",
        ]
    )
    if lang == "both":
        lines.append("如果你确认这版中文内容，我下一条会给你英文版（英文将按英文求职信习惯重写，不直译）。")
    return "\n".join(lines)


def _run_cover_letter(force_language: str = ""):
    missing = _missing_fields()
    if missing:
        _append("assistant", "还缺少这些信息：\n- " + "\n- ".join(missing))
        return

    language = force_language or st.session_state.language
    # Backend schema currently supports zh/en. For both, generate zh first, then en.
    backend_language = "zh" if language == "both" else language

    payload = {
        "resume_text": (st.session_state.resume_text or "").strip()[:20000],
        "jd_text": (st.session_state.jd_text or "").strip()[:12000],
        "scenario": (st.session_state.scenario or "").strip() or "email",
        "language": backend_language or "zh",
        "company_name": (st.session_state.company_name or "").strip(),
    }
    if (st.session_state.target_role or "").strip():
        payload["target_role"] = (st.session_state.target_role or "").strip()
    if st.session_state.emphasis:
        payload["emphasis"] = st.session_state.emphasis

    with st.chat_message("assistant"):
        with st.spinner("正在生成求职信..."):
            result = st.session_state.agent.run_cover_letter(payload)

    st.session_state.last_result = result
    text = _format_cover_letter(result or {}, payload["scenario"], language)
    _append("assistant", text)


def _answer_followup(user_text: str):
    result = st.session_state.last_result
    if not result:
        _append("assistant", "请先把简历、JD、场景和语言发我，我先生成初稿。")
        return

    # When user asks another language after first draft, regenerate directly.
    lang = _normalize_language(user_text)
    if lang in {"zh", "en"}:
        st.session_state.language = lang
        _run_cover_letter(force_language=lang)
        return
    if lang == "both":
        st.session_state.language = "both"
        _run_cover_letter(force_language="zh")
        return

    if st.session_state.agent.llm is None:
        _append("assistant", "当前模型未就绪，请先配置 API Key 后再调整文案。")
        return

    prompt = f"""
你是资深求职顾问。请基于用户简历、JD、当前版本文案和用户修改要求，重写文案。
要求：
1) 仅基于已提供事实，不编造经历。
2) 语气自然，避免模板腔和空洞套话。
3) 如果是招聘软件打招呼，控制在 80-150 字。
4) 如果是邮件求职信，控制在 300-500 字（中文）或 200-350 words（英文）。

简历：
{st.session_state.resume_text}

目标岗位：
{st.session_state.target_role}

JD：
{st.session_state.jd_text}

当前生成结果(JSON)：
{json.dumps(result, ensure_ascii=False)}

用户修改要求：
{user_text}
"""
    try:
        out = st.session_state.agent.llm.invoke(prompt)
        content = getattr(out, "content", str(out))
        _append("assistant", content)
    except Exception as e:
        _append("assistant", f"调整失败：{e}")


def _apply_user_message(user_text: str):
    text = (user_text or "").strip()
    if not text:
        return
    _append("user", text)

    if st.session_state.profile_choice == "pending":
        choice = _resolve_profile_choice(text)
        if not choice:
            _append("assistant", "先确认这一步：回复“使用已保存信息”或“使用新提交信息”。")
            return

        if choice == "saved":
            st.session_state.profile_choice = "saved"
            if not (st.session_state.target_role or "").strip():
                st.session_state.target_role = st.session_state.saved_target_role
            if not (st.session_state.jd_text or "").strip():
                st.session_state.jd_text = st.session_state.saved_target_jd
            loaded_saved_resume = False
            if not (st.session_state.resume_text or "").strip():
                saved_resume = _ensure_saved_resume_loaded()
                if saved_resume:
                    st.session_state.resume_text = saved_resume
                    loaded_saved_resume = True
            if loaded_saved_resume:
                _append("assistant", "已切换为“使用已保存信息”，并已读取已保存简历。请补充场景/语言，或直接回复“开始生成”。")
            else:
                _append("assistant", "已切换为“使用已保存信息”。你可以继续补充简历/场景/语言。")
        else:
            st.session_state.profile_choice = "new"
            _append("assistant", "已切换为“使用新提交信息”。请发送新的目标岗位/JD。")

        if _is_choice_command_only(text):
            return

    resume_sec, jd_sec = _extract_sections(text)
    if resume_sec:
        maybe_file = _read_text_from_path(resume_sec)
        st.session_state.resume_text = maybe_file or resume_sec
    if jd_sec:
        st.session_state.jd_text = jd_sec

    # Support inline key-value input in one message:
    # 场景=B，语言=中文，公司=XX，强调=YY
    for field, raw_val in re.findall(r"(场景|语言|公司|强调)\s*[:：=]\s*([^，,\n]+)", text):
        val = (raw_val or "").strip()
        if not val:
            continue
        if field == "场景":
            st.session_state.scenario = _normalize_scenario(val) or st.session_state.scenario
        elif field == "语言":
            st.session_state.language = _normalize_language(val) or st.session_state.language
        elif field == "公司":
            st.session_state.company_name = val
        elif field == "强调":
            st.session_state.emphasis = val

    if text.startswith("简历："):
        raw = text.split("：", 1)[1].strip()
        st.session_state.resume_text = _read_text_from_path(raw) or raw
    elif text.startswith("JD：") or text.startswith("jd：") or text.startswith("职位JD："):
        st.session_state.jd_text = text.split("：", 1)[1].strip()
    elif text.startswith("公司："):
        st.session_state.company_name = text.split("：", 1)[1].strip()
    elif text.startswith("强调："):
        st.session_state.emphasis = text.split("：", 1)[1].strip()
    elif text.startswith("场景："):
        st.session_state.scenario = _normalize_scenario(text.split("：", 1)[1].strip()) or st.session_state.scenario
    elif text.startswith("语言："):
        st.session_state.language = _normalize_language(text.split("：", 1)[1].strip()) or st.session_state.language

    # Natural language extraction
    scenario = _normalize_scenario(text)
    if scenario:
        st.session_state.scenario = scenario
    language = _normalize_language(text)
    if language:
        st.session_state.language = language

    generate_intent = any(k in text.lower() for k in ["生成", "写", "输出", "cover letter", "求职信", "打招呼"])
    has_all = len(_missing_fields()) == 0

    if has_all and (generate_intent or st.session_state.last_result is None):
        _run_cover_letter()
        return

    if has_all and st.session_state.last_result is not None:
        _answer_followup(text)
        return

    missing = _missing_fields()
    if missing:
        _append("assistant", "我已收到。为了继续生成，还缺：\n- " + "\n- ".join(missing))
    else:
        _append("assistant", "信息已齐全。你回复“开始生成”我就给你出文案。")


def main():
    st.set_page_config(page_title="求职信撰写助手", page_icon="✉️", layout="wide")
    _init_state()

    st.title("求职信撰写助手")
    if st.session_state.agent.llm is None:
        st.warning("模型未就绪：请先配置 DEEPSEEK_API_KEY / OPENAI_API_KEY。")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_msg = st.chat_input("直接和我对话：发简历、JD、场景、语言，我来写求职信")
    if user_msg:
        _apply_user_message(user_msg)
        st.rerun()


if __name__ == "__main__":
    main()
