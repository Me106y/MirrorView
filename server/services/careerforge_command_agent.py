import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from client.core.resume_craft_report import build_resume_craft_html_report
from client.core.resume_match_report import build_resume_match_html_report
from client.core.skill_prefill_policy import (
    build_prefill_choice_prompt,
    get_prefill_choice_guidance,
    get_prefill_policy,
    is_prefill_choice_command_only,
    resolve_prefill_choice,
)
from server.config import Config
from server.factories.llm_factory import ModelFactory
from server.models import User
from server.services.resume_service import ResumeService
from utils.logger_handler import logger


class CareerForgeCommandAgent:
    """
    CareerForge command + NL router for TUI chat.

    Routing order (hybrid):
    1) Slash command
    2) Keyword rules
    3) LLM intent classifier
    """

    SKILL_INTENTS = {
        "resume-match",
        "resume-craft",
        "cover-letter",
        "mock-interview",
        "job-hunt",
    }
    PREFILL_CONFIRMED_INTENTS = {
        "resume-match",
        "resume-craft",
        "cover-letter",
        "job-hunt",
    }

    COMMAND_ALIASES = {
        "resume-match": "resume-match",
        "resume_match": "resume-match",
        "match": "resume-match",
        "resume-craft": "resume-craft",
        "resume_craft": "resume-craft",
        "craft": "resume-craft",
        "cover-letter": "cover-letter",
        "cover_letter": "cover-letter",
        "cover": "cover-letter",
        "mock-interview": "mock-interview",
        "mock_interview": "mock-interview",
        "interview": "mock-interview",
        "job-hunt": "job-hunt",
        "job_hunt": "job-hunt",
        "job": "job-hunt",
    }

    KEYWORDS = {
        "resume-match": [
            "简历匹配",
            "匹配度",
            "简历分析",
            "岗位匹配",
            "jd分析",
            "简历评分",
            "简历诊断",
            "简历评估",
            "匹配度分析",
            "简历和jd对比",
            "岗位适配度",
            "resume review",
            "resume scoring",
            "resume match",
            "resume analysis",
            "job fit",
        ],
        "resume-craft": [
            "生成简历",
            "写简历",
            "做简历",
            "简历制作",
            "优化简历",
            "改简历",
            "简历美化",
            "简历排版",
            "简历模板",
            "简历设计",
            "resume template",
            "resume design",
            "resume create",
            "resume build",
            "resume optimize",
        ],
        "cover-letter": [
            "求职信",
            "自荐信",
            "申请信",
            "写一封求职信",
            "帮我写个求职信",
            "投递邮件怎么写",
            "怎么跟hr打招呼",
            "boss直聘打招呼",
            "招呼语",
            "自我介绍信",
            "application letter",
            "cover letter",
            "打招呼",
            "开场白",
        ],
        "mock-interview": [
            "模拟面试",
            "面试准备",
            "面试练习",
            "面试辅导",
            "面试模拟",
            "帮我准备面试",
            "面试训练",
            "练习面试",
            "面试陪练",
            "mock interview",
            "interview prep",
        ],
        "job-hunt": [
            "找工作",
            "岗位推荐",
            "搜岗位",
            "找岗位",
            "招聘信息",
            "求职搜索",
            "看看有什么机会",
            "投递机会",
            "有哪些公司在招",
            "帮我搜一下岗位",
            "有什么合适的岗位",
            "job hunt",
            "job search",
        ],
    }
    PROFILE_EDIT_KEYWORDS = [
        "修改信息",
        "修改资料",
        "编辑信息",
        "编辑资料",
        "更新信息",
        "更新资料",
        "修改求职意向",
        "修改目标岗位",
        "修改profile",
        "编辑profile",
        "update profile",
        "edit profile",
        "update my profile",
    ]

    def __init__(self, ai_service):
        self.ai_service = ai_service
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._resume_service = ResumeService()
        self._output_dir = Path(__file__).resolve().parents[2] / "test-output"

        self._llm = None
        self._llm_error = ""
        try:
            self._llm = ModelFactory.get_model(
                "deepseek",
                "deepseek-chat",
                temperature=0,
                streaming=False,
                max_tokens=256,
            )
        except Exception as e:
            self._llm_error = str(e)
            logger.warning("CareerForgeCommandAgent LLM init failed: %s", e)

    def handle_chat(self, user_id: Optional[int], message: str, history: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        text = (message or "").strip()
        if not text:
            return self._resp(
                reply="请输入内容。可先输入 /help 查看命令。",
                intent="unknown",
                action="noop",
                missing_fields=[],
            )

        session_key = str(user_id) if user_id else "guest"
        session = self._sessions.setdefault(
            session_key,
            {
                "intent": "",
                "slots": {},
                "missing_fields": [],
                "last_result": {},
                "prefill_choice": {},
            },
        )

        cmd = self._parse_command(text)
        if cmd:
            cmd_name, cmd_arg = cmd
            command_response = self._handle_command(user_id=user_id, session=session, command=cmd_name, arg=cmd_arg)
            if command_response is not None:
                return command_response

        intent, source, confidence = self._decide_intent(text=text, session=session, history=history or [])

        if intent == "unknown":
            return self._resp(
                reply=(
                    "我还没识别出你的意图。\n"
                    "可以直接用命令：/resume-match /resume-craft /cover-letter /mock-interview /job-hunt\n"
                    "也可以用自然语言，比如“我想做简历匹配分析”。"
                ),
                intent="unknown",
                action="clarify",
                missing_fields=[],
                result={"source": source, "confidence": confidence},
            )

        if intent == "profile-edit":
            if not user_id:
                return self._resp(
                    reply="请先登录后再修改个人资料。请输入 /login 开始登录。",
                    intent=intent,
                    action="client_auth_login",
                    missing_fields=[],
                    result={"source": source, "confidence": confidence},
                )
            profile = self._profile_payload(user_id)
            return self._resp(
                reply=(
                    "可以，我们来修改资料。\n"
                    f"{self._profile_summary(profile)}\n"
                    "我会在 TUI 里打开编辑流程。"
                ),
                intent=intent,
                action="client_edit_profile",
                missing_fields=[],
                result={"profile": profile, "source": source, "confidence": confidence},
            )

        if intent in self.SKILL_INTENTS and not user_id:
            session["intent"] = intent
            return self._resp(
                reply="请先登录后再使用该功能。请输入 /login 开始登录。",
                intent=intent,
                action="client_auth_login",
                missing_fields=[],
                result={"source": source, "confidence": confidence},
            )

        if intent not in self.SKILL_INTENTS:
            return self._resp(
                reply="暂不支持该指令。请输入 /help 查看可用命令。",
                intent=intent,
                action="noop",
                missing_fields=[],
            )

        # Route to skill flow
        session["intent"] = intent
        slots = dict(session.get("slots") or {})
        prev_missing = list(session.get("missing_fields") or [])

        prefill_resp, use_saved_profile = self._handle_prefill_gate(
            intent=intent,
            text=text,
            user_id=user_id,
            session=session,
        )
        if prefill_resp is not None:
            return prefill_resp

        self._fill_profile_defaults(user_id=user_id, slots=slots, use_saved=use_saved_profile)
        self._extract_slots(intent=intent, text=text, slots=slots, prev_missing=prev_missing)
        if use_saved_profile:
            self._fill_intent_defaults(intent=intent, slots=slots)

        missing_fields = self._missing_fields(intent=intent, slots=slots)
        session["slots"] = slots
        session["missing_fields"] = missing_fields

        if missing_fields:
            ask_fields = missing_fields[:3]
            return self._resp(
                reply=self._build_missing_prompt(intent=intent, missing_fields=ask_fields, slots=slots),
                intent=intent,
                action="collecting",
                missing_fields=missing_fields,
                result={"source": source, "confidence": confidence},
            )

        # Execute skill
        try:
            result, reply, action, artifacts = self._execute_intent(intent=intent, user_id=user_id, slots=slots)
            session["last_result"] = result
            session["intent"] = ""
            session["slots"] = {}
            session["missing_fields"] = []
            self._clear_prefill_choice(session=session, intent=intent)
            return self._resp(
                reply=reply,
                intent=intent,
                action=action,
                missing_fields=[],
                result=result,
                artifacts=artifacts,
            )
        except Exception as e:
            logger.error("CareerForge command execution failed: %s", e)
            return self._resp(
                reply=f"执行失败：{e}",
                intent=intent,
                action="error",
                missing_fields=[],
                error=str(e),
            )

    def _handle_prefill_gate(
        self,
        intent: str,
        text: str,
        user_id: Optional[int],
        session: Dict[str, Any],
    ) -> Tuple[Optional[Dict[str, Any]], bool]:
        """
        Shared prefill decision gate for TUI/Streamlit parity:
        ask user whether to use saved profile info before auto-filling slots.
        """
        if intent not in self.PREFILL_CONFIRMED_INTENTS:
            return None, True
        if not user_id:
            return None, False

        policy = get_prefill_policy(intent)
        if not (policy.get("enabled") and policy.get("ask_before_using_saved")):
            return None, True

        profile = self._profile_payload(user_id)
        has_saved_context = self._has_saved_context(profile)
        if not has_saved_context:
            self._clear_prefill_choice(session=session, intent=intent)
            return None, False

        choice_map = session.setdefault("prefill_choice", {})
        current_choice = str(choice_map.get(intent) or "").strip()
        parsed_choice = resolve_prefill_choice(intent, text)
        command_only_choice = is_prefill_choice_command_only(intent, text)
        if parsed_choice in {"saved", "new"} and (
            current_choice not in {"saved", "new"} or command_only_choice
        ):
            current_choice = parsed_choice
            choice_map[intent] = parsed_choice

        if current_choice not in {"saved", "new"}:
            prompt = build_prefill_choice_prompt(
                intent,
                role=str(profile.get("target_role") or ""),
                jd_text=str(profile.get("target_jd") or ""),
                has_resume=bool(profile.get("has_resume")),
            )
            return (
                self._resp(
                    reply=prompt,
                    intent=intent,
                    action="confirm_prefill_choice",
                    missing_fields=[],
                    result={"profile": profile},
                ),
                False,
            )

        if parsed_choice in {"saved", "new"} and command_only_choice:
            resume_loaded = False
            if current_choice == "saved":
                probe_slots: Dict[str, Any] = {}
                self._fill_profile_defaults(user_id=user_id, slots=probe_slots, use_saved=True)
                resume_loaded = bool((probe_slots.get("resume_text") or "").strip())
            guidance = get_prefill_choice_guidance(intent, current_choice, resume_loaded=resume_loaded)
            return (
                self._resp(
                    reply=guidance,
                    intent=intent,
                    action="collecting",
                    missing_fields=[],
                    result={"profile_choice": current_choice, "profile": profile},
                ),
                current_choice == "saved",
            )

        return None, current_choice == "saved"

    @staticmethod
    def _has_saved_context(profile: Dict[str, Any]) -> bool:
        if not profile:
            return False
        role = str(profile.get("target_role") or "").strip()
        jd_text = str(profile.get("target_jd") or "").strip()
        has_resume = bool(profile.get("has_resume"))
        return bool(role or jd_text or has_resume)

    @staticmethod
    def _clear_prefill_choice(session: Dict[str, Any], intent: Optional[str] = None) -> None:
        choice_map = session.setdefault("prefill_choice", {})
        if not isinstance(choice_map, dict):
            session["prefill_choice"] = {}
            return
        if intent:
            choice_map.pop(intent, None)
        else:
            choice_map.clear()

    def _handle_command(self, user_id: Optional[int], session: Dict[str, Any], command: str, arg: str) -> Optional[Dict[str, Any]]:
        cmd = command.lower().strip()

        if cmd in {"help", "h"}:
            return self._resp(
                reply=self._help_text(),
                intent="help",
                action="show_help",
                missing_fields=[],
            )

        if cmd in {"exit", "quit"}:
            return self._resp(
                reply="好的，正在退出 MirrorView TUI。",
                intent="exit",
                action="exit_app",
                missing_fields=[],
            )

        if cmd == "logout":
            session["intent"] = ""
            session["slots"] = {}
            session["missing_fields"] = []
            self._clear_prefill_choice(session=session)
            return self._resp(
                reply="已退出登录。",
                intent="logout",
                action="client_logout",
                missing_fields=[],
            )

        if cmd == "login":
            return self._resp(
                reply="好的，我们开始登录。",
                intent="login",
                action="client_auth_login",
                missing_fields=[],
            )

        if cmd == "register":
            return self._resp(
                reply="好的，我们开始注册。",
                intent="register",
                action="client_auth_register",
                missing_fields=[],
            )

        if cmd in {"profile", "me"}:
            if not user_id:
                return self._resp(
                    reply="请先登录后再查看个人资料。请输入 /login。",
                    intent="profile",
                    action="client_auth_login",
                    missing_fields=[],
                )
            profile = self._profile_payload(user_id)
            return self._resp(
                reply=self._profile_summary(profile),
                intent="profile",
                action="show_profile",
                missing_fields=[],
                result={"profile": profile},
            )

        if cmd in {"edit-profile", "edit_profile", "update-profile", "update_profile"}:
            if not user_id:
                return self._resp(
                    reply="请先登录后再修改个人资料。请输入 /login。",
                    intent="profile-edit",
                    action="client_auth_login",
                    missing_fields=[],
                )
            profile = self._profile_payload(user_id)
            return self._resp(
                reply=(
                    "好的，我们来修改个人资料。\n"
                    f"{self._profile_summary(profile)}\n"
                    "请按 TUI 提示完成编辑。"
                ),
                intent="profile-edit",
                action="client_edit_profile",
                missing_fields=[],
                result={"profile": profile},
            )

        if cmd == "cancel":
            active_intent = (session.get("intent") or "").strip()
            session["intent"] = ""
            session["slots"] = {}
            session["missing_fields"] = []
            if active_intent:
                self._clear_prefill_choice(session=session, intent=active_intent)
            return self._resp(
                reply="已取消当前收集流程，你可以重新发起新的需求。",
                intent="cancel",
                action="clear_context",
                missing_fields=[],
            )

        if cmd == "skill":
            target = (arg or "").strip().lower()
            if not target:
                return self._resp(
                    reply="用法：/skill <resume-match|resume-craft|cover-letter|mock-interview|job-hunt>",
                    intent="skill",
                    action="clarify",
                    missing_fields=[],
                )
            mapped = self.COMMAND_ALIASES.get(target, target)
            if mapped not in self.SKILL_INTENTS:
                return self._resp(
                    reply=f"不支持的 skill：{target}。请输入 /help 查看支持列表。",
                    intent="skill",
                    action="clarify",
                    missing_fields=[],
                )
            session["intent"] = mapped
            session["slots"] = {}
            session["missing_fields"] = []
            self._clear_prefill_choice(session=session, intent=mapped)
            if not user_id:
                return self._resp(
                    reply="请先登录后再使用该功能。请输入 /login。",
                    intent=mapped,
                    action="client_auth_login",
                    missing_fields=[],
                )
            return self._resp(
                reply=f"已切换到 {mapped}。请继续输入你的需求或材料。",
                intent=mapped,
                action="collecting",
                missing_fields=[],
            )

        mapped = self.COMMAND_ALIASES.get(cmd)
        if mapped:
            session["intent"] = mapped
            session["slots"] = {}
            session["missing_fields"] = []
            self._clear_prefill_choice(session=session, intent=mapped)
            if not user_id:
                return self._resp(
                    reply="请先登录后再使用该功能。请输入 /login。",
                    intent=mapped,
                    action="client_auth_login",
                    missing_fields=[],
                )
            return None

        return self._resp(
            reply=f"未知命令：/{cmd}。请输入 /help 查看可用命令。",
            intent="unknown",
            action="clarify",
            missing_fields=[],
        )

    @staticmethod
    def _parse_command(text: str) -> Optional[Tuple[str, str]]:
        if not text.startswith("/"):
            return None
        body = text[1:].strip()
        if not body:
            return ("help", "")
        parts = body.split(maxsplit=1)
        if len(parts) == 1:
            return (parts[0], "")
        return (parts[0], parts[1])

    def _decide_intent(self, text: str, session: Dict[str, Any], history: List[Dict[str, Any]]) -> Tuple[str, str, float]:
        # Continue active intent during collection.
        active = (session.get("intent") or "").strip()
        if active in self.SKILL_INTENTS:
            return active, "session", 1.0

        lower_text = text.lower()

        for intent, keywords in self.KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in lower_text:
                    return intent, "keyword", 0.9

        for kw in self.PROFILE_EDIT_KEYWORDS:
            if kw.lower() in lower_text:
                return "profile-edit", "keyword", 0.88

        llm_input = text
        history_hint = self._history_hint(history)
        if history_hint:
            llm_input = f"{history_hint}\n\n当前用户输入：{text}"

        llm_intent, llm_conf, _ = self._llm_classify_intent(llm_input)
        if llm_intent in self.SKILL_INTENTS and llm_conf >= 0.5:
            return llm_intent, "llm", llm_conf

        return "unknown", "none", llm_conf

    @staticmethod
    def _history_hint(history: List[Dict[str, Any]]) -> str:
        if not history:
            return ""
        lines: List[str] = []
        for item in history[-8:]:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip().lower()
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            if role not in {"user", "assistant"}:
                role = "user"
            lines.append(f"{role}: {content[:200]}")
        if not lines:
            return ""
        return "历史对话上下文：\n" + "\n".join(lines)

    def _llm_classify_intent(self, text: str) -> Tuple[str, float, List[str]]:
        if self._llm is None:
            return "unknown", 0.0, []

        prompt = ChatPromptTemplate.from_template(
            """
你是 CareerForge 的意图分类器。
只在以下 intent 中选择一个：
- resume-match
- resume-craft
- cover-letter
- mock-interview
- job-hunt
- unknown

输出要求：
- 只输出 JSON，不要输出其他文字。
- JSON 格式固定为：
{{
  "intent": "...",
  "confidence": 0.0,
  "need_fields": ["..."]
}}

用户输入：
{text}
"""
        )
        chain = prompt | self._llm | StrOutputParser()

        try:
            raw = chain.invoke({"text": text[:1200]})
            parsed = self._safe_json(raw)
            if not isinstance(parsed, dict):
                return "unknown", 0.0, []
            intent = str(parsed.get("intent") or "unknown").strip()
            confidence = float(parsed.get("confidence") or 0)
            need_fields = parsed.get("need_fields") or []
            if not isinstance(need_fields, list):
                need_fields = []
            return intent, max(0.0, min(1.0, confidence)), [str(x) for x in need_fields][:5]
        except Exception as e:
            logger.warning("LLM intent classify failed: %s", e)
            return "unknown", 0.0, []

    @staticmethod
    def _safe_json(raw: str) -> Optional[Dict[str, Any]]:
        text = (raw or "").strip()
        if not text:
            return None

        try:
            return json.loads(text)
        except Exception:
            pass

        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                return None
        return None

    def _fill_profile_defaults(self, user_id: Optional[int], slots: Dict[str, Any], use_saved: bool = True) -> None:
        if not user_id:
            return

        user = User.query.get(user_id)
        if not user:
            return

        if not use_saved:
            return

        has_resume_on_file = bool(user.has_resume)
        slots["_resume_file_submitted"] = has_resume_on_file

        if not slots.get("target_role"):
            role = (user.target_role or user.job_intention or "").strip()
            if role:
                slots["target_role"] = role

        if not slots.get("target_jd"):
            target_jd = (user.target_jd or "").strip()
            if target_jd:
                slots["target_jd"] = target_jd

        if not slots.get("work_experience"):
            exp = (user.work_experience or "").strip()
            if exp:
                slots["work_experience"] = exp

        if slots.get("resume_text"):
            return

        if not has_resume_on_file:
            return

        resume_path = self._resolve_resume_path(user_id=user.id, saved_path=user.resume_path)
        if not resume_path:
            slots["_resume_parse_failed"] = True
            return

        try:
            parsed = (self._resume_service.parse_resume(resume_path) or "").strip()
            if parsed:
                slots["resume_text"] = parsed
                slots["_resume_text_source"] = "saved_resume"
            else:
                slots["_resume_parse_failed"] = True
        except Exception as e:
            slots["_resume_parse_failed"] = True
            logger.warning("Failed to parse saved resume for user %s: %s", user_id, e)

    @staticmethod
    def _resolve_resume_path(user_id: int, saved_path: str) -> str:
        raw = (saved_path or "").strip()
        candidates: List[Path] = []

        if raw:
            p = Path(raw).expanduser()
            candidates.append(p)
            if not p.is_absolute():
                root = Path(__file__).resolve().parents[2]
                candidates.append((root / p).resolve())

            basename = p.name
        else:
            basename = ""

        predicted_name = f"resume_{user_id}.pdf"
        roots = [
            Path(Config.RESUME_UPLOAD_FOLDER),
            Path(__file__).resolve().parents[2] / "server" / "uploads" / "resumes",
            Path.home() / ".mirrorview-tui" / "data" / "uploads" / "resumes",
        ]
        for root in roots:
            candidates.append(root / predicted_name)
            if basename:
                candidates.append(root / basename)

        seen = set()
        for cand in candidates:
            key = str(cand)
            if key in seen:
                continue
            seen.add(key)
            if cand.exists() and cand.is_file():
                return str(cand.resolve())
        return ""

    def _extract_slots(self, intent: str, text: str, slots: Dict[str, Any], prev_missing: List[str]) -> None:
        plain = (text or "").strip()
        if not plain:
            return

        # If user is following the previous prompt, map plain text to first missing field.
        if not plain.startswith("/") and prev_missing:
            first_missing = prev_missing[0]
            if first_missing == "target_role_or_resume_text":
                if len(plain) >= 50:
                    slots.setdefault("resume_text", plain)
                else:
                    slots.setdefault("target_role", plain)
            else:
                slots.setdefault(first_missing, plain)

        # Generic explicit KV patterns
        matchers = {
            "resume_text": [r"(?:简历|resume)(?:内容|文本)?\s*[:：]\s*([\s\S]+)"],
            "jd_text": [
                r"(?:jd|jd内容|jd文本|目标jd|岗位jd|岗位jd内容|岗位描述|职位描述|岗位要求)\s*[:：]\s*([\s\S]+)"
            ],
            "target_role": [r"(?:目标岗位|岗位|职位)\s*[:：]\s*([^\n]+)"],
            "target_jd": [r"(?:target_jd|目标jd)\s*[:：]\s*([\s\S]+)"],
            "work_experience": [r"(?:工作经验|经验)\s*[:：]\s*([^\n]+)"],
            "company_name": [r"(?:公司|company)\s*[:：]\s*([^\n]+)"],
            "salary_range": [r"(?:薪资|salary)\s*[:：]\s*([^\n]+)"],
        }

        for field, patterns in matchers.items():
            for pat in patterns:
                m = re.search(pat, plain, re.I)
                if m:
                    val = (m.group(1) or "").strip()
                    if val:
                        slots[field] = val

        # scenario and language (cover-letter)
        low = plain.lower()
        if "邮件" in plain or "email" in low:
            slots["scenario"] = "email"
        if "打招呼" in plain or "chat" in low or "boss" in low:
            slots["scenario"] = "chat"

        if "英文" in plain or re.search(r"\ben\b", low):
            slots["language"] = "en"
        elif "中文" in plain or re.search(r"\bzh\b", low):
            slots["language"] = "zh"

        # resume-craft template
        if intent == "resume-craft":
            tm = re.search(r"(?:模板|模版|template)\s*[:：=]?\s*([A-Za-z0-9\-\s]+)", plain, re.I)
            if tm:
                slots["template"] = tm.group(1).strip()

        # job-hunt list-like fields
        if intent == "job-hunt":
            for key, cn in (
                ("target_regions", "区域"),
                ("target_cities", "城市"),
                ("hard_requirements", "硬性要求"),
                ("platforms", "平台"),
            ):
                mm = re.search(rf"(?:{cn}|{key})\s*[:：]\s*([^\n]+)", plain, re.I)
                if mm:
                    slots[key] = [x.strip() for x in re.split(r"[,，;；]", mm.group(1)) if x.strip()]

    @staticmethod
    def _fill_intent_defaults(intent: str, slots: Dict[str, Any]) -> None:
        if intent in {"resume-match", "cover-letter"}:
            if not (slots.get("jd_text") or "").strip():
                target_jd = (slots.get("target_jd") or "").strip()
                if target_jd:
                    slots["jd_text"] = target_jd
                    slots["_jd_source"] = "profile_target_jd"

    @staticmethod
    def _missing_fields(intent: str, slots: Dict[str, Any]) -> List[str]:
        if intent == "resume-match":
            missing = []
            if not (slots.get("resume_text") or "").strip():
                missing.append("resume_text")
            if not (slots.get("jd_text") or "").strip():
                missing.append("jd_text")
            return missing

        if intent == "resume-craft":
            if not (slots.get("resume_text") or "").strip():
                return ["resume_text"]
            return []

        if intent == "cover-letter":
            missing = []
            if not (slots.get("resume_text") or "").strip():
                missing.append("resume_text")
            if not (slots.get("jd_text") or "").strip():
                missing.append("jd_text")
            return missing

        if intent == "job-hunt":
            has_role = bool((slots.get("target_role") or "").strip())
            has_resume = bool((slots.get("resume_text") or "").strip())
            if not has_role and not has_resume:
                return ["target_role_or_resume_text"]
            return []

        if intent == "mock-interview":
            if not (slots.get("target_role") or "").strip():
                return ["target_role"]
            return []

        return []

    def _execute_intent(self, intent: str, user_id: int, slots: Dict[str, Any]) -> Tuple[Dict[str, Any], str, str, List[Dict[str, str]]]:
        if intent == "resume-match":
            payload = {
                "resume_text": (slots.get("resume_text") or "")[:20000],
                "jd_text": (slots.get("jd_text") or "")[:12000],
                "target_role": (slots.get("target_role") or "").strip(),
            }
            result = self.ai_service.run_resume_match(payload)
            reply = self._summarize_resume_match(result)
            artifacts: List[Dict[str, str]] = []

            if isinstance(result, dict) and not result.get("error"):
                try:
                    report_name, html_doc = build_resume_match_html_report(
                        result,
                        payload["resume_text"],
                        payload["target_role"],
                        payload["jd_text"],
                    )
                    self._output_dir.mkdir(parents=True, exist_ok=True)
                    out_path = self._output_dir / report_name
                    out_path.write_text(html_doc, encoding="utf-8")
                    artifacts.append(
                        {
                            "type": "html",
                            "title": "简历匹配报告",
                            "path": str(out_path),
                        }
                    )
                    reply += "\n\n已生成 HTML 报告，可在 TUI 中点击或按 O 打开浏览器。"
                except Exception as e:
                    logger.warning("Failed to build resume-match html artifact: %s", e)
            return result, reply, "skill_executed", artifacts

        if intent == "resume-craft":
            payload = {
                "resume_text": (slots.get("resume_text") or "")[:24000],
                "target_role": (slots.get("target_role") or "").strip(),
                "language": (slots.get("language") or "zh").strip() or "zh",
                "template": (slots.get("template") or "").strip(),
                "optimization_goal": (slots.get("optimization_goal") or "").strip(),
            }
            result = self.ai_service.run_resume_craft(payload)
            reply = self._summarize_resume_craft(result)
            artifacts: List[Dict[str, str]] = []
            if isinstance(result, dict) and not result.get("error"):
                try:
                    report_name, html_doc = build_resume_craft_html_report(
                        result,
                        target_role=payload["target_role"],
                        language=payload["language"],
                        template=payload["template"],
                    )
                    self._output_dir.mkdir(parents=True, exist_ok=True)
                    out_path = self._output_dir / report_name
                    out_path.write_text(html_doc, encoding="utf-8")
                    artifacts.append(
                        {
                            "type": "html",
                            "title": "简历预览",
                            "path": str(out_path),
                        }
                    )
                    reply += "\n\n已生成 HTML 简历，可在 TUI 中点击或按 O 打开浏览器。"
                except Exception as e:
                    logger.warning("Failed to build resume-craft html artifact: %s", e)
            return result, reply, "skill_executed", artifacts

        if intent == "cover-letter":
            payload = {
                "resume_text": (slots.get("resume_text") or "")[:20000],
                "jd_text": (slots.get("jd_text") or "")[:12000],
                "scenario": (slots.get("scenario") or "email").strip() or "email",
                "language": (slots.get("language") or "zh").strip() or "zh",
                "company_name": (slots.get("company_name") or "").strip(),
            }
            result = self.ai_service.run_cover_letter(payload)
            reply = self._summarize_cover_letter(result)
            return result, reply, "skill_executed", []

        if intent == "job-hunt":
            payload = {
                "resume_text": (slots.get("resume_text") or "")[:24000],
                "target_role": (slots.get("target_role") or "").strip(),
                "target_jd": (slots.get("target_jd") or "")[:12000],
                "work_experience": (slots.get("work_experience") or "").strip(),
                "target_regions": slots.get("target_regions") or [],
                "target_cities": slots.get("target_cities") or [],
                "salary_range": (slots.get("salary_range") or "").strip(),
                "hard_requirements": slots.get("hard_requirements") or [],
                "platforms": slots.get("platforms") or [],
            }
            result = self.ai_service.run_job_hunt(payload)
            reply = self._summarize_job_hunt(result)
            return result, reply, "skill_executed", []

        if intent == "mock-interview":
            interview_language = (slots.get("language") or "zh").strip() or "zh"
            reply = (
                "好的，我们开始模拟面试。\n"
                "我会为你进入文字面试会话（不包含旁听/RTMP 观看）。"
            )
            result = {
                "target_role": (slots.get("target_role") or "").strip(),
                "mode": "text",
                "language": interview_language,
            }
            return result, reply, "start_mock_interview", []

        return {}, "未支持的意图。", "noop", []

    def _build_missing_prompt(self, intent: str, missing_fields: List[str], slots: Dict[str, Any]) -> str:
        field_name = {
            "resume_text": "简历内容（可直接粘贴）",
            "jd_text": "岗位 JD 内容",
            "target_role": "目标岗位",
            "target_role_or_resume_text": "目标岗位，或完整简历文本（二选一）",
        }
        labels = [field_name.get(item, item) for item in missing_fields]
        joined = "；".join(labels)

        has_saved_resume = bool(slots.get("_resume_file_submitted"))
        loaded_saved_resume = (slots.get("_resume_text_source") or "") == "saved_resume"
        resume_parse_failed = bool(slots.get("_resume_parse_failed"))

        resume_prefix = ""
        if loaded_saved_resume:
            resume_prefix = "已自动读取你已上传的简历。"
        elif has_saved_resume and resume_parse_failed:
            resume_prefix = (
                "检测到你已提交简历，但当前无法读取该文件。"
                "请重新上传 PDF 简历，或直接粘贴简历文本。"
            )
        elif has_saved_resume:
            resume_prefix = "检测到你已提交简历。"

        if intent == "resume-match":
            return f"{resume_prefix}\n要进行简历匹配分析，还缺：{joined}。请先补充。".strip()
        if intent == "resume-craft":
            return f"{resume_prefix}\n要生成简历，还缺：{joined}。请先补充。".strip()
        if intent == "cover-letter":
            return f"{resume_prefix}\n要生成求职信，还缺：{joined}。请先补充。".strip()
        if intent == "job-hunt":
            return f"{resume_prefix}\n要进行岗位搜索，还缺：{joined}。请先补充。".strip()
        if intent == "mock-interview":
            return f"{resume_prefix}\n要开始模拟面试，还缺：{joined}。请先补充。".strip()
        return f"还缺少信息：{joined}。"

    @staticmethod
    def _summarize_resume_match(result: Dict[str, Any]) -> str:
        if not isinstance(result, dict):
            return "已完成简历匹配分析，但返回结构异常。"
        if result.get("error"):
            detail = str(result.get("message") or result.get("error") or "")
            return f"简历匹配分析失败：{CareerForgeCommandAgent._humanize_runtime_error(detail)}"
        return (
            f"简历匹配分析完成。\n"
            f"整体匹配度：{result.get('overall_score', '-')}/100\n"
            f"匹配等级：{result.get('match_level', '-') }\n"
            f"总结：{result.get('summary', '')}"
        )

    @staticmethod
    def _summarize_resume_craft(result: Dict[str, Any]) -> str:
        if not isinstance(result, dict):
            return "已完成简历生成，但返回结构异常。"
        if result.get("error"):
            detail = str(result.get("message") or result.get("error") or "")
            return f"简历生成失败：{CareerForgeCommandAgent._humanize_runtime_error(detail)}"
        title = result.get("title", "")
        summary = result.get("profile_summary", "")
        return f"简历生成完成。\n标题：{title}\n概述：{summary}"

    @staticmethod
    def _summarize_cover_letter(result: Dict[str, Any]) -> str:
        if not isinstance(result, dict):
            return "已完成求职信生成，但返回结构异常。"
        if result.get("error"):
            detail = str(result.get("message") or result.get("error") or "")
            return f"求职信生成失败：{CareerForgeCommandAgent._humanize_runtime_error(detail)}"
        letter = (result.get("cover_letter") or "").strip()
        greeting = (result.get("greeting_message") or "").strip()
        return (
            "求职信生成完成。\n\n"
            "【求职信】\n"
            f"{letter}\n\n"
            "【打招呼消息】\n"
            f"{greeting}"
        )

    @staticmethod
    def _summarize_job_hunt(result: Dict[str, Any]) -> str:
        if not isinstance(result, dict):
            return "已完成岗位搜索，但返回结构异常。"
        if result.get("error"):
            detail = str(result.get("message") or result.get("error") or "")
            return f"岗位搜索失败：{CareerForgeCommandAgent._humanize_runtime_error(detail)}"
        summary = (result.get("summary") or "").strip()
        jobs = result.get("top_jobs") or []
        lines = [f"岗位搜索完成。{summary}"]
        for idx, job in enumerate(jobs[:5], start=1):
            title = job.get("title", "未命名岗位")
            company = job.get("company", "未知公司")
            location = job.get("location", "地点未标注")
            lines.append(f"{idx}. {title} - {company} ({location})")
        return "\n".join(lines)

    @staticmethod
    def _profile_payload(user_id: Optional[int]) -> Dict[str, str]:
        if not user_id:
            return {}
        user = User.query.get(user_id)
        if not user:
            return {}
        role = (user.target_role or user.job_intention or "").strip()
        return {
            "username": (user.username or "").strip(),
            "target_role": role,
            "target_jd": (user.target_jd or "").strip(),
            "work_experience": (user.work_experience or "").strip(),
            "has_resume": bool(user.has_resume),
        }

    @staticmethod
    def _profile_summary(profile: Dict[str, Any]) -> str:
        if not profile:
            return "当前未找到你的资料记录。"
        role = (profile.get("target_role") or "").strip() or "未设置"
        jd = (profile.get("target_jd") or "").strip()
        exp = (profile.get("work_experience") or "").strip() or "未设置"
        has_resume = "是" if profile.get("has_resume") else "否"
        jd_preview = (jd[:100] + "...") if len(jd) > 100 else (jd or "未设置")
        return (
            "当前资料：\n"
            f"- 目标岗位: {role}\n"
            f"- 工作经验: {exp}\n"
            f"- 目标 JD: {jd_preview}\n"
            f"- 已上传简历: {has_resume}"
        )

    @staticmethod
    def _humanize_runtime_error(raw_error: str) -> str:
        text = (raw_error or "").strip()
        low = text.lower()

        auth_markers = (
            "authentication fails",
            "invalid api key",
            "incorrect api key",
            "unauthorized",
            "401",
            "governor",
        )
        if any(m in low for m in auth_markers):
            return (
                "DeepSeek 鉴权失败。请确认 DEEPSEEK_API_KEY 为有效密钥（不是示例值），"
                "并确保它已加载到当前后端进程环境中；修改后请重启正在运行的 server。"
            )

        rate_markers = ("429", "rate limit", "too many requests")
        if any(m in low for m in rate_markers):
            return "请求过于频繁触发限流，请稍后重试。"

        model_markers = ("model not found", "does not exist", "not supported")
        if any(m in low for m in model_markers):
            return "模型配置不可用，请检查 DeepSeek 模型名与 base_url 配置。"

        return text or "未知错误"

    @staticmethod
    def _help_text() -> str:
        return (
            "可用命令：\n"
            "/help - 查看帮助\n"
            "/login - 登录\n"
            "/register - 注册\n"
            "/logout - 退出登录\n"
            "/profile - 查看个人资料\n"
            "/edit-profile - 编辑个人资料\n"
            "/exit - 退出程序\n"
            "/resume-match - 简历匹配分析\n"
            "/resume-craft - 简历生成\n"
            "/cover-letter - 求职信撰写\n"
            "/mock-interview - 模拟面试\n"
            "/job-hunt - 寻找工作\n"
            "/skill <name> - 强制切换 skill\n"
            "/cancel - 取消当前收集流程\n\n"
            "你也可以直接说自然语言，例如：\n"
            "“我想进行简历匹配度分析”\n"
            "“帮我写一封针对这个 JD 的求职信”"
        )

    @staticmethod
    def _resp(
        reply: str,
        intent: str,
        action: str,
        missing_fields: List[str],
        result: Optional[Dict[str, Any]] = None,
        artifacts: Optional[List[Dict[str, str]]] = None,
        error: str = "",
    ) -> Dict[str, Any]:
        return {
            "reply": reply,
            "intent": intent,
            "action": action,
            "missing_fields": missing_fields or [],
            "result": result or {},
            "artifacts": artifacts or [],
            "error": error,
        }
