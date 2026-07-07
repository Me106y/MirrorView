import json
import os
import re
from pathlib import Path
from typing import Dict, Generator, List, Optional

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from server.factories.llm_factory import ModelFactory
from utils.logger_handler import logger


class CareerForgeAgent:
    """
    Runtime skill agent for CareerForge.
    Loads local SKILL.md files and uses them as backend-only execution guides.
    """

    SUPPORTED_SKILLS = {
        "job-hunt",
        "resume-match",
        "resume-craft",
        "cover-letter",
        "mock-interview",
    }

    def __init__(self, skills_root: Optional[str] = None, llm=None):
        base = Path(__file__).resolve().parents[2]
        candidates = []
        if skills_root:
            candidates.append(Path(skills_root))
        env_root = os.environ.get("CAREERFORGE_SKILLS_ROOT")
        if env_root:
            candidates.append(Path(env_root))
        candidates.extend(
            [
                base / "skills" / "CareerForge" / "skills",
                Path.home() / ".codex" / "skills" / "CareerForge" / "skills",
            ]
        )
        chosen = None
        for cand in candidates:
            if (cand / "resume-match" / "SKILL.md").exists():
                chosen = cand
                break
        self.skills_root = chosen or candidates[0]
        self._cache: Dict[str, str] = {}
        self.llm_error: Optional[str] = None
        if llm is not None:
            self.llm = llm
        else:
            try:
                self.llm = ModelFactory.get_model(
                    "deepseek",
                    "deepseek-chat",
                    temperature=0.35,
                )
            except Exception as e:
                self.llm = None
                self.llm_error = str(e)
                logger.warning("CareerForgeAgent LLM init failed: %s", e)

    def _skill_path(self, skill_name: str) -> Path:
        return self.skills_root / skill_name / "SKILL.md"

    def load_skill(self, skill_name: str) -> str:
        if skill_name not in self.SUPPORTED_SKILLS:
            raise ValueError(f"Unsupported skill: {skill_name}")
        if skill_name in self._cache:
            return self._cache[skill_name]

        path = self._skill_path(skill_name)
        if not path.exists():
            raise FileNotFoundError(f"Skill file not found: {path}")

        content = path.read_text(encoding="utf-8", errors="ignore")
        self._cache[skill_name] = content
        return content

    @staticmethod
    def _normalize_language(language: str = "zh") -> str:
        lang = (language or "zh").strip().lower()
        if lang.startswith("en"):
            return "en"
        return "zh"

    @staticmethod
    def _language_label(language: str) -> str:
        return "English" if language == "en" else "Chinese"

    def _safe_json_loads(self, raw: str) -> Optional[dict]:
        raw = (raw or "").strip()
        if not raw:
            return None

        try:
            return json.loads(raw)
        except Exception:
            pass

        block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
        if block:
            try:
                return json.loads(block.group(1))
            except Exception:
                pass

        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(raw[start:end + 1])
            except Exception:
                return None
        return None

    def _invoke_json_skill(self, skill_name: str, payload: dict, schema: dict) -> dict:
        if self.llm is None:
            return {
                "error": "llm_not_ready",
                "message": self.llm_error or "LLM is not initialized",
                "assumptions": ["missing_api_key_or_model_init_failed"],
            }
        skill_spec = self.load_skill(skill_name)
        schema_json = json.dumps(schema, ensure_ascii=False, indent=2)
        payload_json = json.dumps(payload, ensure_ascii=False, indent=2)

        prompt = ChatPromptTemplate.from_template(
            """
You are a backend skill runtime.
You MUST follow the provided Skill specification to process user input.

[Skill Name]
{skill_name}

[Skill Specification]
{skill_spec}

[Runtime Notes]
- Backend execution only, no UI wording.
- Be concise but practical.
- Return STRICT JSON only.
- Do not wrap JSON in markdown code fences.
- If some user fields are missing, still return best-effort output and describe assumptions in "assumptions".

[Input Payload]
{payload_json}

[Required JSON Schema]
{schema_json}
"""
        )
        chain = prompt | self.llm | StrOutputParser()

        try:
            raw = chain.invoke(
                {
                    "skill_name": skill_name,
                    "skill_spec": skill_spec[:14000],
                    "payload_json": payload_json,
                    "schema_json": schema_json,
                }
            )
            parsed = self._safe_json_loads(raw)
            if parsed is None:
                logger.warning("Skill %s returned non-JSON output", skill_name)
                return {
                    "raw_text": raw.strip(),
                    "assumptions": ["model_output_not_json"],
                }
            return parsed
        except Exception as e:
            logger.error("Skill %s invocation failed: %s", skill_name, e)
            return {
                "error": str(e),
                "assumptions": ["model_call_failed"],
            }

    def _stream_json_skill(self, skill_name: str, payload: dict, schema: dict) -> Generator[str, None, None]:
        if self.llm is None:
            yield json.dumps(
                {
                    "error": "llm_not_ready",
                    "message": self.llm_error or "LLM is not initialized",
                    "assumptions": ["missing_api_key_or_model_init_failed"],
                },
                ensure_ascii=False,
            )
            return

        skill_spec = self.load_skill(skill_name)
        schema_json = json.dumps(schema, ensure_ascii=False, indent=2)
        payload_json = json.dumps(payload, ensure_ascii=False, indent=2)

        prompt = ChatPromptTemplate.from_template(
            """
You are a backend skill runtime.
You MUST follow the provided Skill specification to process user input.

[Skill Name]
{skill_name}

[Skill Specification]
{skill_spec}

[Runtime Notes]
- Backend execution only, no UI wording.
- Be concise but practical.
- Return STRICT JSON only.
- Do not wrap JSON in markdown code fences.
- If some user fields are missing, still return best-effort output and describe assumptions in "assumptions".

[Input Payload]
{payload_json}

[Required JSON Schema]
{schema_json}
"""
        )

        chain = prompt | self.llm | StrOutputParser()
        try:
            for chunk in chain.stream(
                {
                    "skill_name": skill_name,
                    "skill_spec": skill_spec[:14000],
                    "payload_json": payload_json,
                    "schema_json": schema_json,
                }
            ):
                yield chunk
        except Exception as e:
            logger.error("Skill %s streaming failed: %s", skill_name, e)
            yield json.dumps(
                {
                    "error": "stream_failed",
                    "message": str(e),
                    "assumptions": ["model_stream_failed"],
                },
                ensure_ascii=False,
            )

    def run_resume_match(self, payload: dict) -> dict:
        schema = {
            "overall_score": 0,
            "match_level": "A|B|C",
            "summary": "string",
            "dimension_scores": [
                {
                    "name": "string",
                    "score": 0,
                    "highlight": "string",
                    "gap": "string",
                    "advice": "string",
                }
            ],
            "critical_missing": ["string"],
            "extra_advantages": ["string"],
            "optimization_suggestions": ["string"],
            "optimized_resume_markdown": "string",
            "assumptions": ["string"],
        }
        return self._invoke_json_skill("resume-match", payload, schema)

    def stream_resume_match(self, payload: dict) -> Generator[str, None, None]:
        schema = {
            "overall_score": 0,
            "match_level": "A|B|C",
            "summary": "string",
            "dimension_scores": [
                {
                    "name": "string",
                    "score": 0,
                    "highlight": "string",
                    "gap": "string",
                    "advice": "string",
                }
            ],
            "critical_missing": ["string"],
            "extra_advantages": ["string"],
            "optimization_suggestions": ["string"],
            "optimized_resume_markdown": "string",
            "assumptions": ["string"],
        }
        for chunk in self._stream_json_skill("resume-match", payload, schema):
            yield chunk

    def parse_json_output(self, raw_text: str) -> Optional[dict]:
        return self._safe_json_loads(raw_text)

    def run_resume_craft(self, payload: dict) -> dict:
        schema = {
            "title": "string",
            "profile_summary": "string",
            "resume_markdown": "string",
            "sections": [{"title": "string", "content_markdown": "string"}],
            "style_advice": ["string"],
            "next_actions": ["string"],
            "assumptions": ["string"],
        }
        return self._invoke_json_skill("resume-craft", payload, schema)

    def run_resume_match_followup(self, analysis_result: dict, question: str) -> str:
        if self.llm is None:
            return "当前模型未就绪，请先配置 API Key 后再进行追问。"
        skill_spec = self.load_skill("resume-match")
        prompt = ChatPromptTemplate.from_template(
            """
You are running CareerForge's resume-match follow-up QA flow.
You MUST follow the provided Skill specification when answering.

[Skill Specification]
{skill_spec}

[Existing Analysis Result JSON]
{analysis_json}

[User Question]
{question}

[Runtime Constraints]
- Answer in Chinese.
- Keep answer concise, practical, and actionable.
- Do not fabricate experiences or facts not supported by analysis.
- If information is insufficient, state uncertainty and provide next-step checks.
- Output plain text only.
"""
        )
        chain = prompt | self.llm | StrOutputParser()
        try:
            return chain.invoke(
                {
                    "skill_spec": skill_spec[:12000],
                    "analysis_json": json.dumps(analysis_result or {}, ensure_ascii=False)[:14000],
                    "question": (question or "").strip()[:1200],
                }
            )
        except Exception as e:
            logger.error("resume-match followup failed: %s", e)
            return "我先给你一个稳妥建议：优先补齐 JD 中高频硬性要求，并用量化结果重写对应经历。"

    def stream_resume_craft_dialog(self, payload: dict) -> Generator[str, None, None]:
        if self.llm is None:
            yield "当前模型未就绪，请先配置 API Key 后重试。"
            return
        skill_spec = self.load_skill("resume-craft")
        prompt = ChatPromptTemplate.from_template(
            """
你正在运行 CareerForge 的 resume-craft 技能（多轮信息收集阶段）。
必须遵循 Skill 规范，并输出给用户可直接阅读的对话文本。

[Skill Specification]
{skill_spec}

[已保存目标信息]
{profile_context}

[最近对话]
{history_text}

[用户最新输入]
{user_input}

[运行约束]
1) 始终围绕简历生成，不跑题。
2) 每轮只追问 1 个字段，禁止一次询问多个字段。
3) 不编造经历，不夸大资历。
4) 模板/语言/照片偏好已在页面第一步确定，禁止再次询问这三项。
5) 不输出 JSON，不输出代码块。
6) 若用户输入看起来是岗位名（如“AI应用开发”“后端工程师”等），必须视为“目标岗位已确认”，下一轮改问教育背景，禁止继续追问目标岗位。
7) 如果 profile_context 明确“Step2 仅收集工作/项目经历”，你只能围绕经历发问（职责、挑战、行动、结果、量化指标），严禁重问目标岗位、教育、技能、联系方式。
"""
        )
        chain = prompt | self.llm | StrOutputParser()
        try:
            for chunk in chain.stream(
                {
                    "skill_spec": skill_spec[:14000],
                    "profile_context": (payload.get("profile_context") or "（无）")[:8000],
                    "history_text": (payload.get("history_text") or "")[:14000],
                    "user_input": (payload.get("user_input") or "").strip()[:3000],
                }
            ):
                yield chunk
        except Exception as e:
            logger.error("resume-craft dialog stream failed: %s", e)
            next_prompt = (payload.get("next_prompt") or "").strip()
            if next_prompt:
                yield f"我已收到你的信息。{next_prompt}"
            else:
                yield "我已收到你的信息。请继续补充下一项字段信息。"

    def run_resume_craft_dialog(self, payload: dict) -> str:
        if self.llm is None:
            return "当前模型未就绪，请先配置 API Key 后重试。"
        chunks = []
        for part in self.stream_resume_craft_dialog(payload):
            chunks.append(part)
        return "".join(chunks).strip()

    def _build_resume_craft_html_prompt(self, payload: dict) -> str:
        skill_spec = self.load_skill("resume-craft")
        template_code = (payload.get("template_code") or "02").strip()[:8]
        template_en = (payload.get("template_en") or "").strip()[:64]
        template_display = (payload.get("template_display") or "").strip()[:120]
        language = (payload.get("language") or "中文").strip()[:40]
        photo_pref = (payload.get("photo_pref") or "未明确").strip()[:40]
        photo_token = (payload.get("photo_token") or "__PHOTO_DATA_URL__").strip()[:120] or "__PHOTO_DATA_URL__"
        base_template = payload.get("base_template") or ""
        preview_snippet = payload.get("preview_snippet") or ""
        profile_context = payload.get("profile_context") or "（无）"
        history_text = payload.get("history_text") or ""
        extra_instruction = (payload.get("extra_instruction") or "").strip()
        photo_rule = (
            f'8) 本次要求放照片：必须输出 <img class="header-photo" src="{photo_token}" ...>，'
            "src 必须是该占位 token，禁止写死 URL 或其他 base64。"
            if photo_pref == "放照片"
            else "8) 本次不放照片：不要输出头像图片标签。"
        )

        return f"""
您是简历 HTML 生成器。请直接输出最终 HTML，不要任何解释文字。

必须严格遵守以下要求：
1) 只输出完整 HTML 文档（从 <!DOCTYPE html> 到 </html>）。
2) 目标模板：{template_code} / {template_en} / {template_display}。
3) 语言要求：{language}。
4) 照片偏好：{photo_pref}。
5) 必须包含导出按钮（window.print）、@page A4、@media print、分页控制。
6) 内容结构与视觉风格遵循 SKILL.md，且不编造事实。
7) 若用户已在早期选定模板，禁止再次确认模板。
{photo_rule}

[SKILL.md 规范全文节选]
{skill_spec[:18000]}

[resume-template.html 参考（Editorial 完整结构）]
{str(base_template)[:22000]}

[CareerForge-模板预览.html 选中模板片段]
{str(preview_snippet)[:5000]}

[已保存目标信息（若用户后续已更新，请以后续最新输入为准）]
{str(profile_context)[:9000]}

[已确认对话事实]
{str(history_text)[:14000]}

[附加约束]
{extra_instruction[:1200] if extra_instruction else "（无）"}
"""

    def stream_resume_craft_html(self, payload: dict) -> Generator[str, None, None]:
        if self.llm is None:
            yield ""
            return
        prompt = ChatPromptTemplate.from_template("{full_prompt}")
        chain = prompt | self.llm | StrOutputParser()
        full_prompt = self._build_resume_craft_html_prompt(payload)
        try:
            for chunk in chain.stream({"full_prompt": full_prompt}):
                yield chunk
        except Exception as e:
            logger.error("resume-craft html stream failed: %s", e)
            yield ""

    def run_resume_craft_html(self, payload: dict) -> str:
        if self.llm is None:
            return ""
        prompt = ChatPromptTemplate.from_template("{full_prompt}")
        chain = prompt | self.llm | StrOutputParser()
        full_prompt = self._build_resume_craft_html_prompt(payload)
        try:
            return chain.invoke({"full_prompt": full_prompt})
        except Exception as e:
            logger.error("resume-craft html invoke failed: %s", e)
            return ""

    def run_cover_letter(self, payload: dict) -> dict:
        schema = {
            "scenario": "email|chat",
            "language": "zh|en",
            "cover_letter": "string",
            "greeting_message": "string",
            "key_points": ["string"],
            "tailoring_notes": ["string"],
            "assumptions": ["string"],
        }
        return self._invoke_json_skill("cover-letter", payload, schema)

    def run_job_hunt(self, payload: dict) -> dict:
        schema = {
            "summary": "string",
            "search_strategy": ["string"],
            "top_jobs": [
                {
                    "title": "string",
                    "company": "string",
                    "location": "string",
                    "salary": "string",
                    "match_level": "green|yellow|orange",
                    "match_reason": "string",
                    "url": "string",
                }
            ],
            "next_actions": ["string"],
            "assumptions": ["string"],
        }
        return self._invoke_json_skill("job-hunt", payload, schema)

    def build_mock_interview_reply(
        self,
        messages_list: List[dict],
        user_input: str,
        job_position: str = "General",
        language: str = "zh",
    ) -> str:
        normalized_language = self._normalize_language(language)
        if self.llm is None:
            if normalized_language == "en":
                return "I cannot reach the interview model right now. Please check your API key and try again."
            return "我暂时无法连接面试模型，请检查 API Key 配置后重试。"
        skill_spec = self.load_skill("mock-interview")
        language_label = self._language_label(normalized_language)
        history_msgs = []
        for msg in messages_list:
            if msg.get("role") == "user":
                history_msgs.append(HumanMessage(content=msg.get("content", "")))
            elif msg.get("role") == "agent":
                history_msgs.append(AIMessage(content=msg.get("content", "")))

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """
You are running CareerForge's mock-interview skill as the interviewer.
Follow the skill behavior and constraints.

[Job Position]
{job_position}

[Output Language]
{language_label}

[Skill Specification]
{skill_spec}

[Runtime Constraints]
- This is interview Q&A runtime, not final report stage.
- Ask only ONE interviewer turn at a time (one main question, optional short follow-up).
- Keep response concise and natural.
- If user asks to end interview, respond with a short confirmation and one-sentence closure.
- The output must be strictly in {language_label}.
- Output plain text only.
""",
                ),
                ("placeholder", "{chat_history}"),
                ("human", "{input}"),
            ]
        )
        chain = prompt | self.llm | StrOutputParser()

        try:
            return chain.invoke(
                {
                    "job_position": job_position,
                    "language_label": language_label,
                    "skill_spec": skill_spec[:12000],
                    "chat_history": history_msgs,
                    "input": user_input,
                }
            )
        except Exception as e:
            logger.error("mock-interview invoke failed: %s", e)
            if normalized_language == "en":
                return "Got it. Let's move to the next question: share one project that best proves your fit for this role."
            return "收到。我们继续下一题：请您分享一个最能体现您岗位胜任力的项目经历。"

    def stream_mock_interview_reply(
        self,
        messages_list: List[dict],
        user_input: str,
        job_position: str = "General",
        language: str = "zh",
    ) -> Generator[str, None, None]:
        normalized_language = self._normalize_language(language)
        if self.llm is None:
            if normalized_language == "en":
                yield "I cannot reach the interview model right now. Please check your API key and try again."
                return
            yield "我暂时无法连接面试模型，请检查 API Key 配置后重试。"
            return
        skill_spec = self.load_skill("mock-interview")
        language_label = self._language_label(normalized_language)
        history_msgs = []
        for msg in messages_list:
            if msg.get("role") == "user":
                history_msgs.append(HumanMessage(content=msg.get("content", "")))
            elif msg.get("role") == "agent":
                history_msgs.append(AIMessage(content=msg.get("content", "")))

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """
You are running CareerForge's mock-interview skill as the interviewer.
Follow the skill behavior and constraints.

[Job Position]
{job_position}

[Output Language]
{language_label}

[Skill Specification]
{skill_spec}

[Runtime Constraints]
- This is interview Q&A runtime, not final report stage.
- Ask only ONE interviewer turn at a time (one main question, optional short follow-up).
- Keep response concise and natural.
- If user asks to end interview, respond with a short confirmation and one-sentence closure.
- The output must be strictly in {language_label}.
- Output plain text only.
""",
                ),
                ("placeholder", "{chat_history}"),
                ("human", "{input}"),
            ]
        )
        chain = prompt | self.llm | StrOutputParser()

        try:
            for chunk in chain.stream(
                {
                    "job_position": job_position,
                    "language_label": language_label,
                    "skill_spec": skill_spec[:12000],
                    "chat_history": history_msgs,
                    "input": user_input,
                }
            ):
                yield chunk
        except Exception as e:
            logger.error("mock-interview stream failed: %s", e)
            if normalized_language == "en":
                yield "Got it, let's continue with the next question: how do you quantify your core contribution in projects?"
                return
            yield "收到，我们继续下一题：您如何量化说明您在项目中的核心贡献？"

    def generate_mock_interview_opening(
        self,
        job_position: str,
        resume_summary: str = "",
        language: str = "zh",
    ) -> str:
        normalized_language = self._normalize_language(language)
        language_label = self._language_label(normalized_language)
        if self.llm is None:
            if normalized_language == "en":
                return f"Hello, I am your interviewer. We are now starting a mock interview for the {job_position} role. Please begin with a brief self-introduction."
            return f"您好，我是您的面试官。我们现在开始进行{job_position}岗位的模拟面试。请先做一个简短自我介绍。"
        if not os.path.exists(str(self._skill_path("mock-interview"))):
            if normalized_language == "en":
                return f"Hello, I am your interviewer. We are now starting a mock interview for the {job_position} role. Please begin with a brief self-introduction."
            return f"您好，我是您的面试官。我们现在开始进行{job_position}岗位的模拟面试。请先做一个简短自我介绍。"
        prompt = ChatPromptTemplate.from_template(
            """
You are initializing a mock interview.
Job: {job_position}
Resume summary: {resume_summary}
Output language: {language_label}

Return one concise opening statement in {language_label}:
- greet candidate
- state interview is starting
- ask first question naturally
Output plain text only.
"""
        )
        chain = prompt | self.llm | StrOutputParser()
        try:
            return chain.invoke(
                {
                    "job_position": job_position,
                    "resume_summary": (resume_summary or "")[:1200],
                    "language_label": language_label,
                }
            )
        except Exception:
            if normalized_language == "en":
                return f"Hello, I am your interviewer. We are now starting a mock interview for the {job_position} role. Please begin with a brief self-introduction."
            return f"您好，我是您的面试官。我们现在开始进行{job_position}岗位的模拟面试。请先做一个简短自我介绍。"
