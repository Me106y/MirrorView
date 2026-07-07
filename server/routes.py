from flask import Blueprint, request, jsonify, current_app, Response, stream_with_context
from client.core.resume_match_report import build_resume_match_html_report
from server.models import db, User, Interview, Message, InviteCode, Listener
from server.services.ai_service import AIService
from server.services.careerforge_command_agent import CareerForgeCommandAgent
from server.services.rtmp_service import RTMPService
from server.services.resume_service import ResumeService
from server.runtime_request import build_runtime_meta, parse_runtime_payload
from server.security import enforce_high_cost_guard
from server.config import Config
from utils.logger_handler import logger
from datetime import datetime
import uuid
import tempfile
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

api = Blueprint('api', __name__)

ai_service = AIService()
command_agent = CareerForgeCommandAgent(ai_service)
rtmp_service = RTMPService(Config.RTMP_SERVER_URL)

HIGH_COST_ENDPOINTS = {
    "resume-match",
    "resume-craft",
    "cover-letter",
    "mock-interview",
}

RESUME_CRAFT_TEMPLATE_MAP: Dict[str, Tuple[str, str]] = {
    "01": ("Editorial", "Editorial 杂志编辑风"),
    "02": ("Minimal", "Minimal 极简主义"),
    "03": ("Sidebar Navy", "Sidebar Navy 深蓝双栏"),
    "04": ("Sidebar Dark", "Sidebar Dark 深灰左栏"),
    "05": ("Dark Header", "Dark Header 深色头部"),
    "06": ("Clean Teal", "Clean Teal 清新青色"),
    "07": ("Elegant", "Elegant 优雅对称"),
}
RESUME_CRAFT_PHOTO_TOKEN = "__PHOTO_DATA_URL__"
RESUME_CRAFT_MAX_PHOTO_DATA_URL_LENGTH = 2_000_000
RESUME_CRAFT_FIELD_ORDER = ["target_role", "education", "experience", "skills", "contact"]
RESUME_CRAFT_ROLE_HINTS = [
    "开发",
    "工程师",
    "产品",
    "运营",
    "设计",
    "算法",
    "测试",
    "经理",
    "顾问",
    "分析师",
    "架构师",
    "dev",
    "developer",
    "engineer",
    "manager",
    "analyst",
    "scientist",
]
RESUME_CRAFT_FIELD_PROMPTS = {
    "target_role": "请先补充目标岗位这个字段（例如：AI 应用开发工程师）。",
    "education": "请补充教育背景这个字段（学校/专业/学位/时间）。",
    "experience": "请补充项目或工作经历这个字段（公司/项目/职责/成果）。",
    "skills": "请补充技能与工具这个字段（技术栈/工具/熟练度）。",
    "contact": "请补充联系方式这个字段（邮箱/电话/城市/GitHub 等）。",
    "conversation_turns": "请继续补充信息，我们每轮只收集一个字段。",
    "photo": "你选择了放照片，请先上传 PNG/JPG 照片。",
}
RESUME_CRAFT_READY_KEYWORDS: Dict[str, List[str]] = {
    "target_role": [
        "目标岗位",
        "求职岗位",
        "岗位",
        "职位",
        "应聘",
        "target role",
        "desired role",
        "job target",
        "position",
        "job role",
    ],
    "education": [
        "教育",
        "学历",
        "学校",
        "大学",
        "学院",
        "专业",
        "学位",
        "education",
        "university",
        "college",
        "major",
        "degree",
    ],
    "experience": [
        "经历",
        "项目",
        "工作",
        "实习",
        "公司",
        "职责",
        "成果",
        "experience",
        "project",
        "projects",
        "intern",
        "employment",
        "worked",
    ],
    "skills": [
        "技能",
        "技术",
        "技术栈",
        "工具",
        "熟悉",
        "掌握",
        "skill",
        "skills",
        "tech",
        "stack",
        "framework",
        "language",
    ],
    "contact": [
        "联系方式",
        "联系",
        "手机",
        "电话",
        "邮箱",
        "邮件",
        "github",
        "linkedin",
        "城市",
        "email",
        "phone",
        "location",
    ],
}


@api.route('/health', methods=['GET'])
def health():
    return jsonify(
        {
            "ok": True,
            "service": "mirrorview-api",
            "env": "vercel" if (os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV")) else "local",
        }
    ), 200

@api.route('/auth/register', methods=['POST'])
def register():
    data = request.json
    if User.query.filter_by(username=data.get('username')).first():
        return jsonify({'message': 'Username already exists'}), 400

    target_role = (data.get('target_role') or data.get('job_intention') or '').strip()
    user = User(
        username=data.get('username'),
        # email=data.get('email'), # Removed
        job_intention=target_role,
        target_role=target_role,
        target_jd=(data.get('target_jd') or '').strip(),
        work_experience=data.get('work_experience')
    )
    user.set_password(data.get('password'))
    db.session.add(user)
    db.session.commit()
    return jsonify({'message': 'User registered successfully', 'user_id': user.id}), 201

@api.route('/auth/login', methods=['POST'])
def login():
    data = request.json
    user = User.query.filter_by(username=data.get('username')).first()
    if user and user.check_password(data.get('password')):
        role = user.target_role or user.job_intention
        return jsonify({
            'message': 'Login successful', 
            'user_id': user.id,
            'username': user.username,
            'job_intention': role,
            'target_role': role,
            'target_jd': user.target_jd,
            'work_experience': user.work_experience,
            'has_resume': bool(user.has_resume),
            'resume_path': user.resume_path,
        }), 200
    return jsonify({'message': 'Invalid username or password'}), 401

import json

def _is_interview_expired(interview):
    if not interview or not interview.start_time:
        return False
    if interview.status == 3:
        return False
    ttl = getattr(Config, 'INTERVIEW_TTL_SECONDS', 3600)
    return (datetime.utcnow() - interview.start_time).total_seconds() > ttl

def _delete_interview(interview):
    if not interview:
        return
    Message.query.filter_by(interview_id=interview.id).delete(synchronize_session=False)
    InviteCode.query.filter_by(interview_id=interview.id).delete(synchronize_session=False)
    Listener.query.filter_by(interview_id=interview.id).delete(synchronize_session=False)
    db.session.delete(interview)
    db.session.commit()

def _normalize_interview_language(language):
    lang = (language or "zh").strip().lower()
    if lang.startswith("en"):
        return "en"
    return "zh"


def _extract_resume_text(data):
    """
    Extract resume text from JSON field or uploaded file.
    Supports:
    - data["resume_text"] in JSON/form
    - request.files["resume"] (pdf/txt/md/docx as plain fallback)
    """
    resume_text = (data or {}).get('resume_text', '') or ''
    resume_text = resume_text.strip()
    if resume_text:
        return resume_text

    if 'resume' not in request.files:
        return ""

    file = request.files['resume']
    if not file or not file.filename:
        return ""

    suffix = os.path.splitext(file.filename)[1].lower() or ".txt"
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            file.save(tmp.name)
            temp_path = tmp.name

        if suffix == ".pdf":
            resume_service = ResumeService()
            return (resume_service.parse_resume(temp_path) or "").strip()

        with open(temp_path, "rb") as f:
            return f.read().decode("utf-8", errors="ignore").strip()
    except Exception as e:
        logger.error(f"Failed to parse uploaded resume: {e}")
        return ""
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


def _coerce_request_data() -> Dict[str, Any]:
    data = request.get_json(silent=True)
    if data is None:
        data = request.form.to_dict() if request.form else {}
    if not isinstance(data, dict):
        return {}
    return data


def _resolve_runtime(data: Dict[str, Any]) -> Tuple[Optional[Dict[str, str]], Optional[Tuple[Dict[str, Any], int]], Dict[str, str]]:
    runtime, runtime_error = parse_runtime_payload(data)
    if runtime_error:
        return None, ({"error": "invalid_runtime", "message": runtime_error}, 400), {}
    return runtime, None, build_runtime_meta(runtime or {})


def _guard_high_cost_request(endpoint_name: str, data: Dict[str, Any]) -> Optional[Tuple[Dict[str, Any], int]]:
    if endpoint_name not in HIGH_COST_ENDPOINTS:
        return None

    token = str(data.get("turnstile_token") or "").strip()
    allowed, status_code, err = enforce_high_cost_guard(
        endpoint=endpoint_name,
        token=token,
        remote_ip=request.remote_addr or "",
    )
    if allowed:
        return None
    return err, status_code


def _resolve_repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "skills").exists() and (parent / "server").exists():
            return parent
    return current.parents[1]


REPO_ROOT = _resolve_repo_root()
RESUME_CRAFT_DIR = REPO_ROOT / "skills" / "CareerForge" / "skills" / "resume-craft"
RESUME_CRAFT_BASE_TEMPLATE_FILE = RESUME_CRAFT_DIR / "templates" / "resume-template.html"
RESUME_CRAFT_PREVIEW_TEMPLATE_FILE = RESUME_CRAFT_DIR / "templates" / "CareerForge-模板预览.html"


@lru_cache(maxsize=1)
def _load_resume_craft_templates() -> Dict[str, str]:
    base_template = ""
    preview_template = ""
    try:
        if RESUME_CRAFT_BASE_TEMPLATE_FILE.exists():
            base_template = RESUME_CRAFT_BASE_TEMPLATE_FILE.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        logger.warning("failed to load resume-craft base template: %s", e)

    try:
        if RESUME_CRAFT_PREVIEW_TEMPLATE_FILE.exists():
            preview_template = RESUME_CRAFT_PREVIEW_TEMPLATE_FILE.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        logger.warning("failed to load resume-craft preview template: %s", e)

    return {"base_template": base_template, "preview_template": preview_template}


def _normalize_resume_craft_template_code(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "02"
    m = re.search(r"([1-7])", text)
    if not m:
        return "02"
    return f"0{m.group(1)}"


def _normalize_resume_craft_language(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"en", "english", "英文"}:
        return "英文"
    if text in {"both", "zh-en", "zh_en", "双语", "中英文", "中英文双版"}:
        return "中英文双版"
    return "中文"


def _normalize_resume_craft_photo_pref(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"with_photo", "with-photo", "photo", "yes", "1", "放照片", "放"}:
        return "放照片"
    return "不放照片"


def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "on", "y"}


def _history_to_text(history: Any, max_turns: int = 32) -> str:
    if not isinstance(history, list):
        return ""
    lines: List[str] = []
    for item in history[-max_turns:]:
        if not isinstance(item, dict):
            continue
        role_raw = str(item.get("role") or "").strip().lower()
        role = "用户" if role_raw == "user" else "助手"
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        lines.append(f"{role}：{content}")
    return "\n".join(lines)


def _extract_preview_snippet(preview_html: str, template_code: str) -> str:
    if not preview_html:
        return ""
    try:
        idx = int(template_code)
    except Exception:
        idx = 2
    css_marker = f"/* == T{idx}:"
    css_start = preview_html.find(css_marker)
    css_part = preview_html[css_start:css_start + 2500] if css_start != -1 else ""

    card_marker = f"<!-- T{idx}"
    card_start = preview_html.find(card_marker)
    card_part = preview_html[card_start:card_start + 3500] if card_start != -1 else ""
    return (css_part + "\n\n" + card_part).strip()[:5000]


def _extract_html_document(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""

    fenced = re.search(r"```(?:html)?\s*(.*?)```", raw, re.IGNORECASE | re.DOTALL)
    candidate = fenced.group(1).strip() if fenced else raw

    matched = re.search(r"(?is)<!doctype\s+html.*?</html>", candidate)
    if matched:
        return matched.group(0).strip()

    matched = re.search(r"(?is)<html.*?</html>", candidate)
    if matched:
        doc = matched.group(0).strip()
        if "<!doctype" not in doc.lower():
            doc = "<!DOCTYPE html>\n" + doc
        return doc
    return ""


def _resume_craft_user_turns(history: Any, latest_user_input: str = "", max_turns: int = 32) -> List[str]:
    turns: List[str] = []
    if isinstance(history, list):
        for item in history[-max_turns:]:
            if not isinstance(item, dict):
                continue
            role_raw = str(item.get("role") or "").strip().lower()
            if role_raw != "user":
                continue
            content = str(item.get("content") or "").strip()
            if content:
                turns.append(content)
    latest = str(latest_user_input or "").strip()
    if latest:
        turns.append(latest)
    return turns


def _has_any_keyword(text_lower: str, keywords: List[str]) -> bool:
    return any(keyword.lower() in text_lower for keyword in keywords)


def _extract_target_role_from_turns(user_turns: List[str]) -> str:
    for raw in reversed(user_turns):
        turn = str(raw or "").strip()
        if not turn:
            continue
        labeled = re.search(
            r"(?:目标岗位|求职岗位|应聘岗位|岗位|职位)\s*[:：]\s*([^\n，。,；;]+)",
            turn,
            re.IGNORECASE,
        )
        if labeled:
            value = labeled.group(1).strip()
            if value:
                return value[:80]

    for raw in reversed(user_turns):
        turn = str(raw or "").strip()
        low = turn.lower()
        if not turn:
            continue
        if any(marker in low for marker in RESUME_CRAFT_ROLE_HINTS) and len(turn) <= 64:
            return turn[:80]

    return ""


def _evaluate_resume_craft_readiness(
    history: Any,
    latest_user_input: str,
    template_code: str,
    language: str,
    photo_pref: str,
    photo_uploaded: bool,
) -> Dict[str, Any]:
    missing_fields: List[str] = []
    if template_code not in RESUME_CRAFT_TEMPLATE_MAP:
        missing_fields.append("template")
    if language not in {"中文", "英文", "中英文双版"}:
        missing_fields.append("language")
    if photo_pref not in {"放照片", "不放照片"}:
        missing_fields.append("photo_pref")
    if photo_pref == "放照片" and not photo_uploaded:
        missing_fields.append("photo")

    user_turns = _resume_craft_user_turns(history, latest_user_input=latest_user_input, max_turns=32)
    if len(user_turns) < 2:
        missing_fields.append("conversation_turns")

    combined_text_lower = "\n".join(user_turns).lower()

    # 目标岗位识别：优先结构化提取，其次关键词/岗位短语特征。
    extracted_target_role = _extract_target_role_from_turns(user_turns)
    role_hint_in_any_turn = any(
        any(marker in turn.lower() for marker in RESUME_CRAFT_ROLE_HINTS)
        for turn in user_turns
    )
    short_role_phrase_in_any_turn = any(len(turn.strip()) <= 32 for turn in user_turns)
    target_role_provided = bool(extracted_target_role) or (
        _has_any_keyword(combined_text_lower, RESUME_CRAFT_READY_KEYWORDS["target_role"])
        or role_hint_in_any_turn
        or short_role_phrase_in_any_turn
    )
    if not target_role_provided:
        missing_fields.append("target_role")

    for field in RESUME_CRAFT_FIELD_ORDER[1:]:
        keywords = RESUME_CRAFT_READY_KEYWORDS[field]
        if not _has_any_keyword(combined_text_lower, keywords):
            missing_fields.append(field)

    return {
        "render_ready": len(missing_fields) == 0,
        "missing_fields": missing_fields,
    }


def _next_resume_craft_prompt(missing_fields: List[str]) -> str:
    ordered = [field for field in RESUME_CRAFT_FIELD_ORDER if field in missing_fields]
    for field in ordered:
        if field in RESUME_CRAFT_FIELD_PROMPTS:
            return RESUME_CRAFT_FIELD_PROMPTS[field]
    for field in missing_fields:
        if field in RESUME_CRAFT_FIELD_PROMPTS:
            return RESUME_CRAFT_FIELD_PROMPTS[field]
    return "请继续补充下一项字段信息。"


def _is_target_role_prompt_reply(text: str) -> bool:
    t = str(text or "").strip()
    if not t:
        return False
    has_target_role = any(token in t for token in ["目标岗位", "求职岗位", "岗位", "职位", "第一个字段"])
    has_ask = any(token in t for token in ["补充", "告诉", "填写", "提供", "先", "请", "需要"])
    return has_target_role and has_ask


def _assistant_recently_asked_target_role(history: Any, max_turns: int = 6) -> bool:
    if not isinstance(history, list):
        return False
    for item in reversed(history[-max_turns:]):
        if not isinstance(item, dict):
            continue
        role_raw = str(item.get("role") or "").strip().lower()
        if role_raw != "assistant":
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        if any(token in content for token in ["目标岗位", "求职岗位", "岗位", "职位", "第一个字段"]):
            return True
    return False


def _looks_like_target_role_answer(message: str) -> bool:
    text = str(message or "").strip()
    if not text:
        return False
    low = text.lower()
    if re.search(r"(?:目标岗位|求职岗位|岗位|职位)\s*[:：]\s*", text):
        return True
    if any(marker in low for marker in RESUME_CRAFT_ROLE_HINTS) and len(text) <= 64:
        return True
    return False


def _validate_photo_data_url(photo_data_url: str) -> Tuple[bool, str]:
    value = str(photo_data_url or "").strip()
    if not value:
        return False, "missing_photo"
    if len(value) > RESUME_CRAFT_MAX_PHOTO_DATA_URL_LENGTH:
        return False, "photo_too_large"
    pattern = re.compile(r"^data:image/(png|jpe?g);base64,[a-z0-9+/=\r\n]+$", re.IGNORECASE)
    if not pattern.match(value):
        return False, "invalid_photo_format"
    return True, ""


def _inject_photo_data_url_into_html(html_doc: str, photo_data_url: str, token: str) -> str:
    html_text = str(html_doc or "")
    photo_src = str(photo_data_url or "").strip()
    if not html_text or not photo_src:
        return ""

    if token and token in html_text:
        return html_text.replace(token, photo_src)

    with_src = re.sub(
        r'(<img\b[^>]*class=["\'][^"\']*header-photo[^"\']*["\'][^>]*\bsrc=["\'])([^"\']*)(["\'])',
        rf"\1{photo_src}\3",
        html_text,
        count=1,
        flags=re.IGNORECASE,
    )
    if with_src != html_text:
        return with_src

    def _append_src(match: re.Match[str]) -> str:
        tag = match.group(0)
        if re.search(r'\bsrc=["\']', tag, flags=re.IGNORECASE):
            return tag
        return tag[:-1] + f' src="{photo_src}">'

    appended = re.sub(
        r'<img\b[^>]*class=["\'][^"\']*header-photo[^"\']*["\'][^>]*>',
        _append_src,
        html_text,
        count=1,
        flags=re.IGNORECASE,
    )
    if appended != html_text:
        return appended
    return ""

@api.route('/user/<int:user_id>/upload_resume', methods=['POST'])
def upload_resume(user_id):
    if 'resume' not in request.files:
        return jsonify({'message': 'No file part'}), 400
    file = request.files['resume']
    if file.filename == '':
        return jsonify({'message': 'No selected file'}), 400
    
    if file and file.filename.endswith('.pdf'):
        user = User.query.get_or_404(user_id)

        # Keep only the latest resume for each user.
        filename = f"resume_{user_id}.pdf"
        file_path = os.path.join(Config.RESUME_UPLOAD_FOLDER, filename)
        file.save(file_path)
        
        user.resume_path = file_path
        user.has_resume = True
        user.resume_uploaded_at = datetime.utcnow()
        db.session.commit()
        
        # Index resume immediately for RAG
        from server.services.resume_service import ResumeService
        resume_service = ResumeService()
        resume_service.index_resume(user_id, file_path)
        
        return jsonify({'message': 'Resume uploaded successfully'}), 200
    
    return jsonify({'message': 'Invalid file type'}), 400


@api.route('/user/<int:user_id>/profile', methods=['GET'])
def get_profile(user_id):
    user = User.query.get_or_404(user_id)
    role = user.target_role or user.job_intention or ''
    return jsonify(
        {
            'user_id': user.id,
            'username': user.username,
            'target_role': role,
            'job_intention': role,
            'target_jd': user.target_jd or '',
            'work_experience': user.work_experience or '',
            'has_resume': bool(user.has_resume),
            'resume_path': user.resume_path,
        }
    ), 200

@api.route('/user/<int:user_id>/update_profile', methods=['POST'])
def update_profile(user_id):
    data = request.json or {}
    user = User.query.get_or_404(user_id)

    target_role = None
    if 'target_role' in data:
        target_role = (data.get('target_role') or '').strip()
    elif 'job_intention' in data:
        target_role = (data.get('job_intention') or '').strip()

    if target_role is not None:
        user.target_role = target_role
        # Keep legacy field in sync for old code paths.
        user.job_intention = target_role

    if 'target_jd' in data:
        user.target_jd = (data.get('target_jd') or '').strip()
    if 'work_experience' in data:
        user.work_experience = data['work_experience']
        
    db.session.commit()
    return jsonify({'message': 'Profile updated successfully'}), 200


@api.route('/careerforge/resume-match', methods=['POST'])
def careerforge_resume_match():
    data = _coerce_request_data()
    runtime, runtime_error, meta = _resolve_runtime(data)
    if runtime_error:
        payload, status = runtime_error
        return jsonify(payload), status

    guard_error = _guard_high_cost_request("resume-match", data)
    if guard_error:
        payload, status = guard_error
        return jsonify(payload), status

    resume_text = _extract_resume_text(data)
    jd_text = (data.get('jd_text') or '').strip()
    target_role = (data.get('target_role') or '').strip()

    if not resume_text:
        return jsonify({'message': 'Please provide resume_text or upload a resume file.'}), 400
    if not jd_text:
        return jsonify({'message': 'Please provide jd_text.'}), 400

    result = ai_service.run_resume_match(
        {
            "resume_text": resume_text[:20000],
            "jd_text": jd_text[:12000],
            "target_role": target_role,
        },
        runtime=runtime,
    )

    report_name = ""
    report_html = ""
    try:
        report_name, report_html = build_resume_match_html_report(
            result=result if isinstance(result, dict) else {},
            resume_text=resume_text,
            target_role=target_role,
            jd_text=jd_text,
        )
    except Exception as e:
        logger.warning("resume-match html report generation failed: %s", e)

    return jsonify(
        {
            "skill": "resume-match",
            "result": result,
            "report_name": report_name,
            "report_html": report_html,
            "meta": meta,
            "process": [
                "Loaded CareerForge resume-match skill",
                "Parsed resume and JD context",
                "Generated matching report",
            ],
        }
    ), 200


@api.route('/careerforge/resume-craft', methods=['POST'])
def careerforge_resume_craft():
    data = _coerce_request_data()
    runtime, runtime_error, meta = _resolve_runtime(data)
    if runtime_error:
        payload, status = runtime_error
        return jsonify(payload), status

    guard_error = _guard_high_cost_request("resume-craft", data)
    if guard_error:
        payload, status = guard_error
        return jsonify(payload), status

    resume_text = _extract_resume_text(data)
    target_role = (data.get('target_role') or '').strip()
    language = (data.get('language') or 'zh').strip()
    template_name = (data.get('template') or '').strip()
    optimization_goal = (data.get('optimization_goal') or '').strip()

    if not resume_text:
        return jsonify({'message': 'Please provide resume_text or upload a resume file.'}), 400

    result = ai_service.run_resume_craft(
        {
            "resume_text": resume_text[:24000],
            "target_role": target_role,
            "language": language,
            "template": template_name,
            "optimization_goal": optimization_goal,
        },
        runtime=runtime,
    )
    return jsonify(
        {
            "skill": "resume-craft",
            "result": result,
            "meta": meta,
            "process": [
                "Loaded CareerForge resume-craft skill",
                "Built optimized resume content",
                "Prepared visual style and next actions",
            ],
        }
    ), 200


@api.route('/careerforge/resume-craft/chat-turn', methods=['POST'])
def careerforge_resume_craft_chat_turn():
    data = _coerce_request_data()
    runtime, runtime_error, meta = _resolve_runtime(data)
    if runtime_error:
        payload, status = runtime_error
        return jsonify(payload), status

    guard_error = _guard_high_cost_request("resume-craft", data)
    if guard_error:
        payload, status = guard_error
        return jsonify(payload), status

    message = (data.get("message") or "").strip()
    if not message:
        return jsonify(
            {
                "reply": "请先输入消息内容。",
                "intent": "resume-craft",
                "action": "noop",
                "render_ready": False,
                "missing_fields": ["message"],
                "meta": meta,
                "error": "empty_message",
            }
        ), 400

    template_code = _normalize_resume_craft_template_code(data.get("template_code"))
    language = _normalize_resume_craft_language(data.get("language"))
    photo_pref = _normalize_resume_craft_photo_pref(data.get("photo_pref"))
    photo_uploaded = _normalize_bool(data.get("photo_uploaded"))
    history = data.get("history") or []
    history_text = _history_to_text(history, max_turns=24)
    readiness = _evaluate_resume_craft_readiness(
        history=history,
        latest_user_input=message,
        template_code=template_code,
        language=language,
        photo_pref=photo_pref,
        photo_uploaded=photo_uploaded,
    )
    user_turns = _resume_craft_user_turns(history, latest_user_input=message, max_turns=32)
    extracted_target_role = _extract_target_role_from_turns(user_turns)
    role_context_line = f"- 已确认目标岗位: {extracted_target_role}\n" if extracted_target_role else ""

    control_context = (
        "【页面参数（优先）】\n"
        f"- 模板编号: {template_code}\n"
        f"- 语言: {language}\n"
        f"- 照片偏好: {photo_pref}\n"
        f"{role_context_line}"
        "- 当前页面仅做从零生成简历，不切换到优化已有简历流程。"
    )
    dialog_payload = {
        "profile_context": control_context,
        "history_text": history_text,
        "user_input": message,
        "next_prompt": _next_resume_craft_prompt(readiness["missing_fields"]),
    }
    reply = (ai_service.run_resume_craft_dialog(dialog_payload, runtime=runtime) or "").strip()
    if not reply:
        reply = f"我已收到你的信息。{_next_resume_craft_prompt(readiness['missing_fields'])}"
    elif "target_role" not in readiness["missing_fields"] and _is_target_role_prompt_reply(reply):
        reply = f"我已收到你的信息。{_next_resume_craft_prompt(readiness['missing_fields'])}"

    # 强制兜底：目标岗位已确认后，任何“继续追问目标岗位”的回复都改写为下一字段。
    if "target_role" not in readiness["missing_fields"] and _is_target_role_prompt_reply(reply):
        reply = f"我已收到你的信息。{_next_resume_craft_prompt(readiness['missing_fields'])}"

    # 最终兜底：若用户本轮看起来已经回答了岗位，且上一轮助手在问岗位，
    # 则无条件移除 target_role，杜绝重复追问。
    if (
        "target_role" in readiness["missing_fields"]
        and _assistant_recently_asked_target_role(history)
        and _looks_like_target_role_answer(message)
    ):
        readiness["missing_fields"] = [field for field in readiness["missing_fields"] if field != "target_role"]
        readiness["render_ready"] = len(readiness["missing_fields"]) == 0
        reply = f"我已收到你的信息。{_next_resume_craft_prompt(readiness['missing_fields'])}"

    return jsonify(
        {
            "reply": reply,
            "intent": "resume-craft",
            "action": "chat_turn",
            "render_ready": readiness["render_ready"],
            "missing_fields": readiness["missing_fields"],
            "meta": {**meta, "resume_craft_chat_turn_version": "2026-07-07-v3"},
            "error": "",
        }
    ), 200


@api.route('/careerforge/resume-craft/render', methods=['POST'])
def careerforge_resume_craft_render():
    data = _coerce_request_data()
    runtime, runtime_error, meta = _resolve_runtime(data)
    if runtime_error:
        payload, status = runtime_error
        return jsonify(payload), status

    guard_error = _guard_high_cost_request("resume-craft", data)
    if guard_error:
        payload, status = guard_error
        return jsonify(payload), status

    history = data.get("history") or []
    history_text = _history_to_text(history, max_turns=32)
    if not history_text.strip():
        return jsonify({"error": "missing_history", "message": "请先和助手对话，再生成简历。"}), 400

    template_code = _normalize_resume_craft_template_code(data.get("template_code"))
    template_en, template_display = RESUME_CRAFT_TEMPLATE_MAP.get(template_code, RESUME_CRAFT_TEMPLATE_MAP["02"])
    language = _normalize_resume_craft_language(data.get("language"))
    photo_pref = _normalize_resume_craft_photo_pref(data.get("photo_pref"))
    photo_data_url = str(data.get("photo_data_url") or "").strip()
    if photo_pref == "放照片":
        ok, reason = _validate_photo_data_url(photo_data_url)
        if not ok:
            return jsonify({"error": reason, "message": "请上传 PNG/JPG 照片后再生成简历。", "meta": meta}), 400

    templates = _load_resume_craft_templates()
    preview_snippet = _extract_preview_snippet(templates.get("preview_template", ""), template_code)

    html_payload = {
        "template_code": template_code,
        "template_en": template_en,
        "template_display": template_display,
        "language": language,
        "photo_pref": photo_pref,
        "base_template": templates.get("base_template", ""),
        "preview_snippet": preview_snippet,
        "profile_context": (
            "【页面参数（优先）】\n"
            f"- 模板编号: {template_code}\n"
            f"- 语言: {language}\n"
            f"- 照片偏好: {photo_pref}\n"
            "- 当前页面仅做从零生成简历，不切换到优化已有简历流程。"
        ),
        "history_text": history_text,
        "photo_token": RESUME_CRAFT_PHOTO_TOKEN,
    }

    raw_html = ai_service.run_resume_craft_html(html_payload, runtime=runtime)
    report_html = _extract_html_document(raw_html)
    if report_html and photo_pref == "放照片":
        report_html = _inject_photo_data_url_into_html(report_html, photo_data_url, RESUME_CRAFT_PHOTO_TOKEN)
    if not report_html:
        strict_payload = dict(html_payload)
        if photo_pref == "放照片":
            strict_payload["extra_instruction"] = (
                "再次强调：仅输出完整HTML文档，并且必须包含照片标签。"
                f'照片标签使用 <img class="header-photo" src="{RESUME_CRAFT_PHOTO_TOKEN}" ...> 的形式，'
                "不要输出解释文本。"
            )
        else:
            strict_payload["extra_instruction"] = (
                "再次强调：仅输出完整HTML文档。必须包含<!DOCTYPE html>和</html>，"
                "不要输出解释文本。"
            )
        retry_html = _extract_html_document(ai_service.run_resume_craft_html(strict_payload, runtime=runtime))
        if retry_html and photo_pref == "放照片":
            retry_html = _inject_photo_data_url_into_html(retry_html, photo_data_url, RESUME_CRAFT_PHOTO_TOKEN)
        report_html = retry_html

    if not report_html:
        return jsonify(
            {
                "error": "render_failed",
                "message": "模型未返回有效 HTML，请继续补充信息后重试。",
                "meta": meta,
            }
        ), 500

    report_name = f"resume-craft-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.html"
    return jsonify(
        {
            "report_name": report_name,
            "report_html": report_html,
            "meta": meta,
            "error": "",
        }
    ), 200


@api.route('/careerforge/cover-letter', methods=['POST'])
def careerforge_cover_letter():
    data = _coerce_request_data()
    runtime, runtime_error, meta = _resolve_runtime(data)
    if runtime_error:
        payload, status = runtime_error
        return jsonify(payload), status

    guard_error = _guard_high_cost_request("cover-letter", data)
    if guard_error:
        payload, status = guard_error
        return jsonify(payload), status

    resume_text = _extract_resume_text(data)
    jd_text = (data.get('jd_text') or '').strip()
    scenario = (data.get('scenario') or 'email').strip()
    language = (data.get('language') or 'zh').strip()
    company_name = (data.get('company_name') or '').strip()

    if not jd_text:
        return jsonify({'message': 'Please provide jd_text.'}), 400
    if not resume_text:
        return jsonify({'message': 'Please provide resume_text or upload a resume file.'}), 400

    result = ai_service.run_cover_letter(
        {
            "resume_text": resume_text[:20000],
            "jd_text": jd_text[:12000],
            "scenario": scenario,
            "language": language,
            "company_name": company_name,
        },
        runtime=runtime,
    )
    return jsonify(
        {
            "skill": "cover-letter",
            "result": result,
            "meta": meta,
            "process": [
                "Loaded CareerForge cover-letter skill",
                "Matched resume highlights to JD",
                "Generated tailored output",
            ],
        }
    ), 200


@api.route('/careerforge/job-hunt', methods=['POST'])
def careerforge_job_hunt():
    data = _coerce_request_data()
    runtime, runtime_error, meta = _resolve_runtime(data)
    if runtime_error:
        payload, status = runtime_error
        return jsonify(payload), status

    resume_text = _extract_resume_text(data)
    target_role = (data.get('target_role') or data.get('job_intention') or '').strip()
    target_jd = (data.get('target_jd') or data.get('jd_text') or '').strip()
    work_experience = (data.get('work_experience') or '').strip()
    target_regions = data.get('target_regions') or data.get('target_region') or []
    target_cities = data.get('target_cities') or data.get('target_city') or []
    salary_range = (data.get('salary_range') or '').strip()
    hard_requirements = data.get('hard_requirements') or []
    platforms = data.get('platforms') or []

    if isinstance(target_regions, str):
        target_regions = [target_regions]
    if isinstance(target_cities, str):
        target_cities = [target_cities]
    if isinstance(hard_requirements, str):
        hard_requirements = [hard_requirements]
    if isinstance(platforms, str):
        platforms = [platforms]

    if not target_role and not resume_text:
        return jsonify({'message': 'Please provide target_role or resume_text.'}), 400

    result = ai_service.run_job_hunt(
        {
            "resume_text": resume_text[:24000],
            "target_role": target_role,
            "target_jd": target_jd[:12000],
            "work_experience": work_experience,
            "target_regions": target_regions,
            "target_cities": target_cities,
            "salary_range": salary_range,
            "hard_requirements": hard_requirements,
            "platforms": platforms,
        },
        runtime=runtime,
    )
    return jsonify(
        {
            "skill": "job-hunt",
            "result": result,
            "meta": meta,
            "process": [
                "Loaded CareerForge job-hunt skill",
                "Built search strategy from profile and constraints",
                "Generated prioritized opportunities",
            ],
        }
    ), 200


@api.route('/careerforge/agent/chat', methods=['POST'])
def careerforge_agent_chat():
    data = _coerce_request_data()
    runtime, runtime_error, meta = _resolve_runtime(data)
    if runtime_error:
        payload, status = runtime_error
        return jsonify(payload), status

    guard_error = _guard_high_cost_request("mock-interview", data)
    if guard_error:
        payload, status = guard_error
        return jsonify(payload), status

    user_id = data.get('user_id')
    message = (data.get('message') or '').strip()
    history = data.get('history') or []

    if not message:
        return (
            jsonify(
                {
                    "reply": "请输入消息内容。",
                    "intent": "unknown",
                    "action": "noop",
                    "missing_fields": [],
                    "result": {},
                    "meta": meta,
                    "artifacts": [],
                    "error": "empty_message",
                }
            ),
            400,
        )

    if isinstance(user_id, str):
        user_id = user_id.strip() or None
        if user_id is not None:
            try:
                user_id = int(user_id)
            except ValueError:
                user_id = None
    elif user_id is not None:
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            user_id = None

    if not isinstance(history, list):
        history = []

    result = command_agent.handle_chat(
        user_id=user_id,
        message=message,
        history=history,
        runtime=runtime,
    )
    if isinstance(result, dict):
        result.setdefault("meta", meta)

    status_code = 200
    if result.get("error"):
        status_code = 400
    return jsonify(result), status_code

@api.route('/interview/create', methods=['POST'])
def create_interview():
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    interview_language = _normalize_interview_language((data or {}).get('language'))
    
    user = User.query.get(user_id)
    if not user:
         return jsonify({'message': 'User not found'}), 404
         
    # Check if user has active interview
    active_interview = Interview.query.filter_by(user_id=user_id, status=1).first()
    if active_interview:
        if _is_interview_expired(active_interview):
            _delete_interview(active_interview)
        else:
            return jsonify({'message': 'You have an ongoing interview. Please finish it before starting a new one.'}), 400

    # Prefer new profile field and keep backward compatibility.
    job_position = user.target_role or user.job_intention
    if not job_position:
        return jsonify({'message': 'Please set your target role in your profile first.'}), 400

    resume_text = None
    projects_summary = None
    
    if user.has_resume and user.resume_path and os.path.exists(user.resume_path):
        from server.services.resume_service import ResumeService
        resume_service = ResumeService()
        resume_text = resume_service.parse_resume(user.resume_path)
        
        if resume_text:
            # Analyze resume only to extract projects, NOT to override job intention
            analysis = ai_service.analyze_resume_and_update_job(user_id, resume_text, job_position)
            projects_summary = analysis.get('projects_summary')

    interview = Interview(
        user_id=user_id,
        title=f"{job_position} Interview - {datetime.now().strftime('%Y-%m-%d')}",
        job_position=job_position,
        language=interview_language,
        questions_count=10,
        status=1, # Ongoing
        start_time=datetime.utcnow()
    )
    
    db.session.add(interview)
    db.session.flush() # Generate ID
    
    interview.rtmp_push_url = rtmp_service.generate_push_url(interview.id, user_id)
    interview.rtmp_play_url = rtmp_service.generate_play_url(interview.rtmp_push_url)
    
    # Initial greeting from mock-interview skill runtime
    greeting = ai_service.generate_mock_interview_opening(
        job_position=job_position,
        resume_summary=(projects_summary or ""),
        language=interview_language,
    )
    
    initial_msg = Message(
        interview_id=interview.id,
        role='agent',
        content=greeting
    )
    db.session.add(initial_msg)
    
    db.session.commit()
    
    return jsonify({
        'interview_id': interview.id,
        'rtmp_push_url': interview.rtmp_push_url,
        'initial_message': greeting,
        'language': interview.language or "zh",
    }), 201

@api.route('/interview/<int:interview_id>/messages', methods=['GET', 'POST'])
def handle_messages(interview_id):
    if request.method == 'POST':
        interview = Interview.query.get(interview_id)
        if not interview:
            return jsonify({'message': 'Interview not found'}), 404
        if _is_interview_expired(interview):
            _delete_interview(interview)
            return jsonify({'message': 'Interview expired and has been deleted.'}), 410

        data = request.json
        user_msg = Message(
            interview_id=interview_id,
            role='user',
            content=data.get('content'),
            original_content=data.get('original_content'),
            question_type=data.get('question_type')
        )
        db.session.add(user_msg)
        db.session.commit() # Commit user message first
        
        if data.get('stream'):
            # Pre-fetch data to avoid DetachedInstanceError inside generator
            user_content = data.get('content')
            
            def generate():
                with current_app.app_context():
                    interview = Interview.query.get(interview_id)
                    job_position = interview.job_position if interview else "General"
                    interview_language = _normalize_interview_language(getattr(interview, "language", "zh"))
                    
                    messages = Message.query.filter_by(interview_id=interview_id).order_by(Message.created_at).all()
                    messages_list = [{'role': m.role, 'content': m.content} for m in messages]
                    
                    full_response = ""
                    for chunk in ai_service.chat_response_stream(
                        messages_list,
                        user_content,
                        job_position,
                        language=interview_language,
                    ):
                        full_response += chunk
                        yield f"data: {json.dumps({'content': chunk})}\n\n"
                    
                    ai_msg = Message(
                        interview_id=interview_id,
                        role='agent',
                        content=full_response
                    )
                    db.session.add(ai_msg)
                    db.session.commit()
                    
                    yield f"data: {json.dumps({'done': True})}\n\n"

            return Response(stream_with_context(generate()), mimetype='text/event-stream')
        
        else:
            # Existing non-streaming logic
            # Evaluate user's answer
            last_agent_msg = Message.query.filter_by(interview_id=interview_id, role='agent').order_by(Message.created_at.desc()).first()
            if last_agent_msg:
                user_id = interview.user_id if interview else None
                evaluation = ai_service.evaluate_answer(last_agent_msg.content, user_msg.content, user_id)
                logger.info(f"Answer evaluation: {evaluation}")

            # Get context
            job_position = interview.job_position if interview else "General"
            interview_language = _normalize_interview_language(getattr(interview, "language", "zh"))
            messages = Message.query.filter_by(interview_id=interview_id).order_by(Message.created_at).all()
            messages_list = [{'role': m.role, 'content': m.content} for m in messages]
            
            # Generate AI response
            ai_response_content = ai_service.chat_response(
                messages_list,
                user_msg.content,
                job_position,
                language=interview_language,
            )
            
            ai_msg = Message(
                interview_id=interview_id,
                role='agent',
                content=ai_response_content
            )
            db.session.add(ai_msg)
            db.session.commit()
            
            return jsonify({'response': ai_response_content}), 201
        
    else:
        interview = Interview.query.get(interview_id)
        if not interview:
            return jsonify({'message': 'Interview not found'}), 404
        if _is_interview_expired(interview):
            _delete_interview(interview)
            return jsonify({'message': 'Interview expired and has been deleted.'}), 410

        messages = Message.query.filter_by(interview_id=interview_id).order_by(Message.created_at).all()
        return jsonify([{
            'role': m.role,
            'content': m.content,
            'created_at': m.created_at.isoformat()
        } for m in messages]), 200

@api.route('/interview/<int:interview_id>/finish', methods=['POST'])
def finish_interview(interview_id):
    interview = Interview.query.get_or_404(interview_id)
    if _is_interview_expired(interview):
        _delete_interview(interview)
        return jsonify({'message': 'Interview expired and has been deleted.'}), 410

    interview.status = 2 # Ended
    interview.end_time = datetime.utcnow()
    
    # Generate feedback
    feedback = ai_service.generate_feedback(
        interview,
        language=_normalize_interview_language(getattr(interview, "language", "zh")),
    )
    
    # Ensure feedback is stored as JSON string, not dict, for SQLite
    if isinstance(feedback, dict):
        interview.overall_feedback = json.dumps(feedback)
    else:
        interview.overall_feedback = str(feedback)
        
    interview.status = 3 # Reviewed
    
    db.session.commit()
    return jsonify({'message': 'Interview finished', 'feedback': feedback}), 200


@api.route('/user/<int:user_id>/history', methods=['GET'])
def get_interview_history(user_id):
    interviews = Interview.query.filter_by(user_id=user_id).order_by(Interview.created_at.desc()).all()
    expired = []
    result = []
    for interview in interviews:
        if _is_interview_expired(interview):
            expired.append(interview)
            continue
        result.append({
            'id': interview.id,
            'title': interview.title,
            'job_position': interview.job_position,
            'status': interview.status, # 1-ongoing, 2-ended, 3-reviewed
            'language': interview.language or "zh",
            'created_at': interview.created_at.isoformat(),
            'end_time': interview.end_time.isoformat() if interview.end_time else None,
            'overall_feedback': interview.overall_feedback,
            'rtmp_play_url': interview.rtmp_play_url
        })
    for interview in expired:
        _delete_interview(interview)
    return jsonify(result), 200

@api.route('/interview/<int:interview_id>/rejoin', methods=['GET'])
def rejoin_interview(interview_id):
    interview = Interview.query.get_or_404(interview_id)
    if _is_interview_expired(interview):
        _delete_interview(interview)
        return jsonify({'message': 'Interview expired and has been deleted.'}), 410
    if interview.status != 1:
        return jsonify({'message': 'Interview is not active'}), 400
        
    # Get initial or last agent message to display?
    # Actually client just needs rtmp url and maybe last message
    
    last_msg = Message.query.filter_by(interview_id=interview_id, role='agent').order_by(Message.created_at.desc()).first()
    greeting = last_msg.content if last_msg else "Welcome back."
    
    return jsonify({
        'interview_id': interview.id,
        'rtmp_push_url': interview.rtmp_push_url,
        'initial_message': greeting, # Re-use this field to show last message
        'language': interview.language or "zh",
        'rejoin': True
    }), 200


@api.route('/interview/<int:interview_id>/status', methods=['GET'])
def get_interview_status(interview_id):
    interview = Interview.query.get(interview_id)
    if not interview:
        return jsonify({'message': 'Interview not found'}), 404
    if _is_interview_expired(interview):
        _delete_interview(interview)
        return jsonify({'message': 'Interview expired and has been deleted.'}), 410
    return jsonify({'status': interview.status}), 200

@api.route('/invite/create', methods=['POST'])
def create_invite_code():
    data = request.json
    interview_id = data.get('interview_id')
    user_id = data.get('user_id')
    
    code_str = str(uuid.uuid4())[:8] # Simple implementation
    invite = InviteCode(
        code=code_str,
        interview_id=interview_id,
        created_by=user_id
    )
    db.session.add(invite)
    db.session.commit()
    return jsonify({'code': code_str}), 201

@api.route('/invite/join', methods=['POST'])
def join_interview():
    data = request.json
    code_str = data.get('code')
    listener_name = data.get('listener_id', 'Anonymous')
    
    invite = InviteCode.query.filter_by(code=code_str).first()
    if not invite:
        return jsonify({'message': 'Invalid code'}), 400
        
    interview = Interview.query.get(invite.interview_id)
    if interview and _is_interview_expired(interview):
        _delete_interview(interview)
        return jsonify({'message': 'Interview is not live'}), 400
    if not interview or interview.status != 1: # Not ongoing
         return jsonify({'message': 'Interview is not live'}), 400
         
    # Log listener
    import uuid
    listener = Listener(
        interview_id=interview.id,
        invite_code_id=invite.id,
        listener_id=str(uuid.uuid4()),
        listener_name=listener_name
    )
    db.session.add(listener)
    db.session.commit()
    
    return jsonify({
        'interview_id': interview.id, 
        'job_position': interview.job_position,
        'rtmp_play_url': interview.rtmp_play_url,
        'listener_name': listener_name
    }), 200

@api.route('/interview/<int:interview_id>/observers', methods=['GET'])
def get_interview_observers(interview_id):
    interview = Interview.query.get(interview_id)
    if interview and _is_interview_expired(interview):
        _delete_interview(interview)
        return jsonify([]), 200
    listeners = Listener.query.filter_by(interview_id=interview_id).all()
    # Unique by name? Or just list all connections
    seen = set()
    unique_listeners = []
    for l in listeners:
        if l.listener_name not in seen:
            unique_listeners.append({
                'name': l.listener_name,
                'joined_at': l.joined_at.isoformat()
            })
            seen.add(l.listener_name)
    return jsonify(unique_listeners), 200
