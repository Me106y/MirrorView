import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

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
7) 必须严格遵循 profile_context 里声明的“当前步骤”字段白名单：
   - Step3 只能问教育背景；
   - Step4 只能问工作/项目经历（Grill）；
   - Step5 只能问技能与证书；
   - Step6 只能做确认与偏好，不回退前面字段。
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

    def run_resume_craft_step4_decision(self, payload: dict) -> dict:
        """
        Agent-led Step4 decision maker.
        Returns structured decision for route state machine consumption.
        """
        fallback = self._build_step4_heuristic_decision(payload)
        fallback["model_connection_ok"] = False
        fallback["model_connection_error"] = self.llm_error or "llm_not_ready_or_connection_failed"

        if self.llm is None:
            return fallback

        skill_spec = self.load_skill("resume-craft")
        schema = {
            "reply": "string",
            "resume_ready_draft": {
                "title": "string",
                "role": "string",
                "period": "string",
                "bullets": ["string"],
            },
            "missing_points": ["string"],
            "current_experience_completed": False,
            "ask_more_experience": True,
            "reasoning_focus": ["string"],
            "active_focus_topic": "string",
            "next_probe_dimension": "implementation|more_experience",
            "evidence_coverage": {
                "implementation": False,
                "tradeoff": False,
                "validation": False,
            },
        }
        schema_json = json.dumps(schema, ensure_ascii=False, indent=2)
        prompt = ChatPromptTemplate.from_template(
            """
你正在运行 CareerForge 的 resume-craft Step4（工作/项目经历 Grill）决策器。
请严格遵循 Skill 规范，输出结构化 JSON（不要代码块）。

[Skill Specification]
{skill_spec}

[Step1 已定稿上下文]
{profile_context}

[最近对话]
{history_text}

[当前经历状态]
- is_first_round: {is_first_round}
- followup_count: {followup_count}
- current_index: {current_index}
- expected_experience_count: {expected_experience_count}
- active_focus: {active_focus_json}

[用户最新输入]
{user_input}

[硬性约束]
1) 必须事实忠实：不编造、不夸大。
2) 路由层是状态机，本次只负责 Step4 问答决策。
3) Step4 采用固定三轮实现链路式深挖：Round1/2/3 都只问“实现链路与落地细节”，禁止改成取舍比较题。
4) 优先深挖“功能与技术实现细节”，角色/时间/背景只能作为可选补充，不可抢占主路径。
5) 第二、三轮要围绕同一个 active_focus_topic，不允许跳主题。
6) 若你生成了“取舍/权衡/备选方案”措辞，路由会改写为实现链路问题；请直接输出实现链路问题。
7) 若当前经历已可定稿，使用“是否还有要补充的经历”作为转场问题。
8) current_experience_completed=true 仅当当前这段信息已可定稿；ask_more_experience=true 表示继续询问是否还有经历。
9) 需维护 active_focus_topic / next_probe_dimension / evidence_coverage 供状态机追踪。

[输出 JSON Schema]
{schema_json}
"""
        )
        chain = prompt | self.llm | StrOutputParser()
        try:
            raw = chain.invoke(
                {
                    "skill_spec": skill_spec[:14000],
                    "profile_context": (payload.get("profile_context") or "（无）")[:9000],
                    "history_text": (payload.get("history_text") or "")[:14000],
                    "user_input": (payload.get("user_input") or "").strip()[:3600],
                    "is_first_round": str(bool(payload.get("is_first_round", False))).lower(),
                    "followup_count": int(payload.get("followup_count", 0)),
                    "current_index": int(payload.get("current_index", 1)),
                    "expected_experience_count": int(payload.get("expected_experience_count", 1)),
                    "active_focus_json": json.dumps(payload.get("active_focus") or {}, ensure_ascii=False),
                    "schema_json": schema_json,
                }
            )
            parsed = self._safe_json_loads(raw)
            if not isinstance(parsed, dict):
                return fallback

            normalized = self._coerce_step4_single_focus_decision(
                payload=payload,
                candidate=parsed,
                fallback=fallback,
            )
            normalized["model_connection_ok"] = True
            normalized["model_connection_error"] = ""
            return normalized
        except Exception as e:
            logger.error("resume-craft step4 decision invoke failed: %s", e)
            fallback["model_connection_ok"] = False
            fallback["model_connection_error"] = str(e)
            return fallback

    @staticmethod
    def _is_generic_step4_reply(reply: str) -> bool:
        text = str(reply or "").strip().lower()
        if not text:
            return True
        generic_markers = [
            "请继续补充",
            "关键信息",
            "挑战/难点",
            "挑战和行动",
            "收到你的信息",
            "这段经历很关键",
        ]
        return any(marker in text for marker in generic_markers)

    @staticmethod
    def _normalize_step4_evidence(raw: Any) -> Dict[str, bool]:
        value = raw if isinstance(raw, dict) else {}
        return {
            "implementation": bool(value.get("implementation", False)),
            "tradeoff": bool(value.get("tradeoff", False)),
            "validation": bool(value.get("validation", False)),
        }

    @classmethod
    def _default_step4_active_focus(cls) -> Dict[str, Any]:
        return {
            "topic": "",
            "stage": "implementation",
            "evidence": cls._normalize_step4_evidence({}),
            "turn_count": 0,
        }

    @classmethod
    def _normalize_step4_active_focus(cls, raw: Any) -> Dict[str, Any]:
        value = raw if isinstance(raw, dict) else {}
        topic = str(value.get("topic") or "").strip()[:120]
        stage = str(value.get("stage") or "").strip().lower()
        if stage not in {"implementation", "tradeoff", "validation", "done"}:
            stage = "implementation"
        try:
            turn_count = int(value.get("turn_count", 0))
        except Exception:
            turn_count = 0
        evidence = cls._normalize_step4_evidence(value.get("evidence"))
        if all(evidence.values()):
            stage = "done"
        return {
            "topic": topic,
            "stage": stage,
            "evidence": evidence,
            "turn_count": max(0, min(turn_count, 20)),
        }

    @staticmethod
    def _merge_step4_evidence(base: Dict[str, bool], patch: Dict[str, bool]) -> Dict[str, bool]:
        return {
            "implementation": bool(base.get("implementation")) or bool(patch.get("implementation")),
            "tradeoff": bool(base.get("tradeoff")) or bool(patch.get("tradeoff")),
            "validation": bool(base.get("validation")) or bool(patch.get("validation")),
        }

    @staticmethod
    def _detect_step4_evidence_from_text(text: str) -> Dict[str, bool]:
        lower = str(text or "").lower()
        implementation = any(
            token in lower
            for token in ["实现", "搭建", "重构", "改造", "开发", "模块", "链路", "流程", "接口", "服务", "引擎", "pipeline"]
        )
        tradeoff = any(
            token in lower
            for token in [
                "选型",
                "取舍",
                "权衡",
                "为什么",
                "因为",
                "由于",
                "因此",
                "相比",
                "相比之下",
                "而不是",
                "而非",
                "备选",
                "最终选择",
                "选择",
                "成本",
                "稳定性",
                "扩展性",
                "兼容",
                "方案",
            ]
        )
        validation = any(
            token in lower
            for token in [
                "压测",
                "监控",
                "告警",
                "线上",
                "验证",
                "观测",
                "slo",
                "sla",
                "p95",
                "p99",
                "qps",
                "错误率",
                "时延",
                "响应",
                "%",
                "ms",
            ]
        )
        return {
            "implementation": implementation,
            "tradeoff": tradeoff,
            "validation": validation,
        }

    @staticmethod
    def _next_step4_stage(evidence: Dict[str, bool]) -> str:
        if not evidence.get("implementation"):
            return "implementation"
        if not evidence.get("tradeoff"):
            return "tradeoff"
        if not evidence.get("validation"):
            return "validation"
        return "done"

    @staticmethod
    def _next_stage_label(stage: str) -> str:
        s = str(stage or "").strip().lower()
        if s == "implementation":
            return "tradeoff"
        if s == "tradeoff":
            return "validation"
        if s == "validation":
            return "done"
        return "implementation"

    @staticmethod
    def _step4_stage_rank(stage: str) -> int:
        s = str(stage or "").strip().lower()
        if s == "implementation":
            return 1
        if s == "tradeoff":
            return 2
        if s == "validation":
            return 3
        if s == "done":
            return 4
        return 0

    @staticmethod
    def _normalize_step4_probe_dimension(value: Any) -> str:
        text = str(value or "").strip().lower()
        if text in {"implementation", "tradeoff", "validation", "more_experience"}:
            return text
        return ""

    @staticmethod
    def _build_step4_single_probe(topic: str, round_idx: int, text: str = "") -> str:
        focus = topic or "该项目核心能力点"
        lower = str(text or "").lower()
        is_rag_stack = any(
            token in lower
            for token in [
                "langchain",
                "agentic rag",
                "rag",
                "prompt",
                "temperature",
                "deepseek",
                "gpt-4",
                "gpt4",
                "llama",
                "embedding",
                "memory",
                "检索",
                "记忆",
            ]
        )
        is_vision_stack = any(
            token in lower
            for token in ["pyqt", "yolov8", "ffmpeg", "rtmp", "kmz", "无人机", "百度地图", "航迹", "大疆"]
        )
        round_num = max(1, min(int(round_idx or 1), 3))

        if round_num == 1:
            if is_rag_stack:
                return (
                    f"围绕“{focus}”，请展开一个最关键功能：检索、记忆与提示词编排是如何串成一条可运行链路的？"
                )
            if is_vision_stack:
                return (
                    f"围绕“{focus}”，请拆解一个核心功能的实现链路（如航迹规划或实时检测）：输入、处理、输出分别怎么落地？"
                )
            return f"围绕“{focus}”，请具体说明一个核心功能从输入到输出的实现链路是怎么搭起来的？"

        if round_num == 2:
            if is_rag_stack:
                return (
                    f"围绕“{focus}”，请继续拆解一个关键子模块（如检索召回、会话记忆更新或提示词编排）：它在整条链路中的输入、处理、输出分别是什么？"
                )
            if is_vision_stack:
                return (
                    f"围绕“{focus}”，请继续拆解一个关键子模块（如航迹规划、目标检测或推流管道）：它在整条链路中的输入、处理、输出分别是什么？"
                )
            return f"围绕“{focus}”，请继续拆解一个关键子模块：它在整条链路中的输入、处理、输出分别是什么？"

        if is_rag_stack:
            return f"围绕“{focus}”，请补充落地闭环：这条链路在接口调用、异常处理与监控验证上是如何串联并稳定运行的？"
        if is_vision_stack:
            return f"围绕“{focus}”，请补充落地闭环：这条链路在实时推理、异常处理与监控告警上是如何串联并稳定运行的？"
        return f"围绕“{focus}”，请补充落地闭环：这条链路在接口调用、异常处理与监控验证上是如何串联并稳定运行的？"

    def _choose_step4_focus_topic(self, text: str, previous_topic: str = "") -> str:
        prior = str(previous_topic or "").strip()
        if prior:
            return prior
        raw = str(text or "")
        title = self._extract_step4_title(raw)
        if title and title not in {"项目经历"} and any(token in title for token in ["系统", "平台", "项目", "链路"]):
            return title[:24]
        patterns = [
            r"(?:基于|围绕|通过)([^，。；;\n]{2,24})(?:实现|构建|搭建|重构|优化)",
            r"([^，。；;\n]{2,24})(?:模块|链路|服务|系统|平台|引擎)",
        ]
        for pattern in patterns:
            match = re.search(pattern, raw, flags=re.IGNORECASE)
            if match:
                topic = match.group(1).strip(" ：:，。；;")
                if topic:
                    return topic[:24]
        focus_terms = self._extract_step4_focus_terms(raw)
        if focus_terms:
            return focus_terms[0]
        return "该项目核心技术点"

    def _coerce_step4_single_focus_decision(self, payload: Dict[str, Any], candidate: Any, fallback: Dict[str, Any]) -> Dict[str, Any]:
        parsed = candidate if isinstance(candidate, dict) else {}
        is_first_round = bool(payload.get("is_first_round", False))
        try:
            followup_count = int(payload.get("followup_count", 0))
        except Exception:
            followup_count = 0
        user_input = str(payload.get("user_input") or "").strip()
        source_focus = self._normalize_step4_active_focus(payload.get("active_focus"))
        fallback_focus = self._normalize_step4_active_focus(fallback.get("active_focus"))

        topic = str(parsed.get("active_focus_topic") or "").strip()
        topic = topic or fallback_focus.get("topic") or source_focus.get("topic") or self._choose_step4_focus_topic(user_input)
        topic = self._choose_step4_focus_topic(user_input, topic)

        evidence = self._merge_step4_evidence(source_focus.get("evidence", {}), fallback_focus.get("evidence", {}))
        evidence = self._merge_step4_evidence(evidence, self._normalize_step4_evidence(parsed.get("evidence_coverage")))
        evidence = self._merge_step4_evidence(evidence, self._detect_step4_evidence_from_text(user_input))
        safe_followup_count = max(1, followup_count)
        probe_round = min(safe_followup_count, 3)
        close_after_three_rounds = safe_followup_count > 3
        current_experience_completed = close_after_three_rounds
        stage = "done" if current_experience_completed else "implementation"
        ask_more_experience = bool(parsed.get("ask_more_experience", True))

        draft = parsed.get("resume_ready_draft") if isinstance(parsed.get("resume_ready_draft"), dict) else {}
        fallback_draft = fallback.get("resume_ready_draft") if isinstance(fallback.get("resume_ready_draft"), dict) else {}
        bullets = draft.get("bullets") if isinstance(draft.get("bullets"), list) else []
        safe_bullets = [str(item or "").strip()[:220] for item in bullets if str(item or "").strip()][:5]
        if not safe_bullets:
            safe_bullets = [str(item or "").strip()[:220] for item in (fallback_draft.get("bullets") or []) if str(item or "").strip()][:5]

        missing_raw = parsed.get("missing_points") if isinstance(parsed.get("missing_points"), list) else []
        missing_points = [str(item or "").strip()[:120] for item in missing_raw if str(item or "").strip()][:5]

        canonical_probe = self._build_step4_single_probe(topic, probe_round, user_input)

        if current_experience_completed:
            missing_points = ["是否还有要补充的经历"] if ask_more_experience else []
            next_probe_dimension = "more_experience"
            candidate_reply = str(parsed.get("reply") or "").strip()
            if ask_more_experience and "还有要补充的经历" not in candidate_reply:
                reply = "这一段经历已完成深挖。是否还有要补充的经历？"
            else:
                reply = candidate_reply or ("这一段经历已完成深挖。是否还有要补充的经历？" if ask_more_experience else "这一段经历已完成深挖。")
        else:
            next_probe_dimension = "implementation"
            missing_points = [canonical_probe]

            if is_first_round:
                title = str(draft.get("title") or fallback_draft.get("title") or self._extract_step4_title(user_input) or "项目经历").strip()[:80]
                preview_lines = safe_bullets[:3] or self._extract_step4_bullets(user_input)[:3]
                preview = "\n".join(f"- {line}" for line in preview_lines if str(line or "").strip())
                reply = (
                    "我先按你给的信息整理一个可上简历版本（待确认）：\n"
                    f"{title}\n"
                    f"{preview}\n"
                    f"接下来我先围绕“{topic or '该项目核心技术点'}”追问一个最关键问题：{canonical_probe}"
                ).strip()
            else:
                reply = f"继续围绕“{topic or '该项目核心技术点'}”深入一层：{canonical_probe}"

        reasoning_raw = parsed.get("reasoning_focus") if isinstance(parsed.get("reasoning_focus"), list) else []
        reasoning_focus = [str(item or "").strip()[:80] for item in reasoning_raw if str(item or "").strip()][:6]
        if topic and topic not in reasoning_focus:
            reasoning_focus.insert(0, topic)
        if not reasoning_focus:
            reasoning_focus = [topic] if topic else []

        active_focus = {
            "topic": topic,
            "stage": stage,
            "evidence": evidence,
            "turn_count": max(
                source_focus.get("turn_count", 0),
                fallback_focus.get("turn_count", 0),
            )
            + 1,
        }

        return {
            "reply": reply,
            "resume_ready_draft": {
                "title": str(draft.get("title") or fallback_draft.get("title") or "项目经历").strip()[:80],
                "role": str(draft.get("role") or fallback_draft.get("role") or "核心开发").strip()[:80],
                "period": str(draft.get("period") or fallback_draft.get("period") or "时间待补").strip()[:80],
                "bullets": safe_bullets,
            },
            "missing_points": missing_points,
            "current_experience_completed": current_experience_completed,
            "ask_more_experience": ask_more_experience,
            "reasoning_focus": reasoning_focus,
            "active_focus_topic": topic,
            "next_probe_dimension": next_probe_dimension,
            "evidence_coverage": evidence,
            "active_focus": active_focus,
        }

    @staticmethod
    def _extract_step4_focus_terms(text: str) -> List[str]:
        lower = str(text or "").lower()
        catalog = [
            ("LangChain", ["langchain"]),
            ("Agentic RAG", ["agentic rag", "rag"]),
            ("Prompt", ["prompt", "few-shot", "few shot", "temperature"]),
            ("Flask", ["flask"]),
            ("FastAPI", ["fastapi"]),
            ("SQLAlchemy", ["sqlalchemy"]),
            ("PostgreSQL", ["postgresql", "postgres"]),
            ("MySQL", ["mysql"]),
            ("Redis", ["redis"]),
            ("Kafka", ["kafka"]),
            ("Kubernetes", ["kubernetes", "k8s"]),
            ("微服务治理", ["微服务"]),
            ("WebSocket", ["websocket"]),
            ("JWT", ["jwt"]),
            ("SLO", ["slo", "sla"]),
            ("性能优化", ["性能", "时延", "延迟", "响应"]),
        ]
        focus: List[str] = []
        for label, tokens in catalog:
            if any(token in lower for token in tokens) and label not in focus:
                focus.append(label)
        return focus[:6]

    @staticmethod
    def _extract_step4_period(text: str) -> str:
        raw = str(text or "")
        patterns = [
            r"(20\d{2}[./-](?:0?[1-9]|1[0-2])\s*(?:[-~到至]\s*20\d{2}[./-](?:0?[1-9]|1[0-2]))?)",
            r"(20\d{2}年(?:0?[1-9]|1[0-2])月\s*(?:[-~到至]\s*20\d{2}年(?:0?[1-9]|1[0-2])月)?)",
        ]
        for pattern in patterns:
            m = re.search(pattern, raw)
            if m:
                return m.group(1).strip()
        return "时间待补"

    @staticmethod
    def _extract_step4_title(text: str) -> str:
        raw = str(text or "").strip()
        lines = [line.strip(" \t-•") for line in raw.splitlines() if line.strip()]
        if not lines:
            return "项目经历"
        first = lines[0]
        labeled = re.search(r"(?:项目|平台|系统|产品)\s*[:：]\s*([^\n，。；;]{2,40})", first)
        if labeled:
            return labeled.group(1).strip()[:40]
        head = re.split(r"[，。；;:：]", first)[0].strip()
        if 2 <= len(head) <= 40:
            return head
        return "项目经历"

    @staticmethod
    def _extract_step4_role(text: str) -> str:
        raw = str(text or "")
        if any(token in raw for token in ["独立开发", "独立完成", "独立负责"]):
            return "独立开发"
        if "主导" in raw:
            return "主导开发"
        if "负责人" in raw:
            return "项目负责人"
        if "负责" in raw:
            return "核心开发"
        return "核心开发"

    @staticmethod
    def _extract_step4_bullets(text: str) -> List[str]:
        raw = str(text or "").strip()
        if not raw:
            return ["待补充项目职责与结果细节。"]
        parts = [p.strip() for p in re.split(r"[。；;\n]+", raw) if p.strip()]
        bullets: List[str] = []
        for part in parts:
            if len(part) < 8:
                continue
            item = part[:220]
            if item not in bullets:
                bullets.append(item)
        return bullets[:5] or ["请补充项目职责、关键动作与可验证结果。"]

    def _build_step4_heuristic_decision(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        text = str(payload.get("user_input") or "").strip()
        is_first_round = bool(payload.get("is_first_round", False))
        try:
            followup_count = int(payload.get("followup_count", 0))
        except Exception:
            followup_count = 0
        source_focus = self._normalize_step4_active_focus(payload.get("active_focus"))
        topic = self._choose_step4_focus_topic(text, source_focus.get("topic", ""))
        evidence = self._merge_step4_evidence(source_focus.get("evidence", {}), self._detect_step4_evidence_from_text(text))
        safe_followup_count = max(1, followup_count)
        probe_round = min(safe_followup_count, 3)
        current_experience_completed = safe_followup_count > 3
        ask_more_experience = True
        next_probe_dimension = "more_experience" if current_experience_completed else "implementation"
        probe = self._build_step4_single_probe(topic, probe_round, text)
        missing_points = ["是否还有要补充的经历"] if current_experience_completed else [probe]
        if current_experience_completed:
            reply = "这一段经历已完成深挖。是否还有要补充的经历？"
        elif is_first_round:
            preview_lines = self._extract_step4_bullets(text)
            preview = "\n".join(f"- {line}" for line in preview_lines[:3])
            reply = (
                "我先按你给的信息整理一个可上简历版本（待确认）：\n"
                f"{self._extract_step4_title(text)}\n"
                f"{preview}\n"
                f"接下来我先围绕“{topic}”追问一个最关键问题：{probe}"
            )
        else:
            reply = f"继续围绕“{topic}”深入一层：{probe}"

        return {
            "reply": reply,
            "resume_ready_draft": {
                "title": self._extract_step4_title(text),
                "role": self._extract_step4_role(text),
                "period": self._extract_step4_period(text),
                "bullets": self._extract_step4_bullets(text),
            },
            "missing_points": missing_points,
            "current_experience_completed": current_experience_completed,
            "ask_more_experience": ask_more_experience,
            "reasoning_focus": [topic] + [x for x in self._extract_step4_focus_terms(text) if x != topic],
            "active_focus_topic": topic,
            "next_probe_dimension": next_probe_dimension,
            "evidence_coverage": evidence,
            "active_focus": {
                "topic": topic,
                "stage": "done" if current_experience_completed else "implementation",
                "evidence": evidence,
                "turn_count": source_focus.get("turn_count", 0) + 1,
            },
        }

    def _build_step6_heuristic_revision(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        current = payload.get("current_draft_json") if isinstance(payload.get("current_draft_json"), dict) else {}
        instruction = str(payload.get("user_edit_instruction") or "").strip()
        updated = json.loads(json.dumps(current or {}, ensure_ascii=False))
        applied_changes: List[str] = []

        if instruction:
            lowered = instruction.lower()
            no_change_markers = ["没有补充", "没有偏好", "先看草稿", "preview", "草稿", "先这样"]
            if not any(marker in lowered for marker in no_change_markers):
                old_pref = str(updated.get("final_preferences") or "").strip()
                merged = instruction if not old_pref else f"{old_pref}；{instruction}"
                updated["final_preferences"] = merged[:2400]
                applied_changes.append("更新了最终偏好说明")

        preview_markdown = ""
        if isinstance(updated, dict):
            target_role = str(updated.get("target_role") or "").strip() or "待补充"
            experiences = updated.get("experiences") if isinstance(updated.get("experiences"), list) else []
            skills = updated.get("skills_and_certs") if isinstance(updated.get("skills_and_certs"), list) else []
            preview_markdown = (
                "### 待生成内容预览（请确认）\n\n"
                f"- 目标岗位：{target_role}\n"
                f"- 项目经历条目：{len(experiences)}\n"
                f"- 技能证书条目：{len(skills)}\n"
            )

        return {
            "updated_draft_json": updated,
            "updated_preview_markdown": preview_markdown,
            "applied_changes": applied_changes,
            "needs_clarification": False,
            "clarification_question": "",
        }

    def run_resume_craft_step6_revise(self, payload: dict) -> dict:
        fallback = self._build_step6_heuristic_revision(payload if isinstance(payload, dict) else {})
        if self.llm is None:
            return fallback

        skill_spec = self.load_skill("resume-craft")
        schema = {
            "updated_draft_json": {
                "target_role": "string",
                "personal_info": {
                    "name": "string",
                    "phone": "string",
                    "email": "string",
                    "city": "string",
                    "links": ["string"],
                },
                "education": ["string"],
                "experiences": ["string"],
                "skills_and_certs": ["string"],
                "final_preferences": "string",
            },
            "updated_preview_markdown": "string",
            "applied_changes": ["string"],
            "needs_clarification": False,
            "clarification_question": "string",
        }
        prompt = ChatPromptTemplate.from_template(
            """
你正在运行 CareerForge 的 resume-craft Step6 修订器。
输出严格 JSON（不要代码块）。

[Skill Specification]
{skill_spec}

[当前草稿 JSON]
{current_draft_json}

[用户本轮修改指令]
{user_edit_instruction}

[事实白名单（只能使用）]
{confirmed_facts_context}

[JD方向上下文（仅用于强调方向，不能新增事实）]
{jd_direction_context}

[硬性约束]
1) 只能在“当前草稿 + 用户本轮明确补充”范围内修改。
2) 不得从 JD 上下文补充用户未提及的事实。
3) 若用户信息不足，needs_clarification=true 并给出一个澄清问题。
4) 输出必须匹配 schema。

[Schema]
{schema_json}
"""
        )
        chain = prompt | self.llm | StrOutputParser()
        try:
            raw = chain.invoke(
                {
                    "skill_spec": skill_spec[:14000],
                    "current_draft_json": json.dumps(payload.get("current_draft_json") or {}, ensure_ascii=False)[:16000],
                    "user_edit_instruction": str(payload.get("user_edit_instruction") or "").strip()[:3000],
                    "confirmed_facts_context": str(payload.get("confirmed_facts_context") or "（无）")[:18000],
                    "jd_direction_context": str(payload.get("jd_direction_context") or "（无）")[:6000],
                    "schema_json": json.dumps(schema, ensure_ascii=False, indent=2),
                }
            )
            parsed = self._safe_json_loads(raw)
            if not isinstance(parsed, dict):
                return fallback
            return {
                "updated_draft_json": parsed.get("updated_draft_json") if isinstance(parsed.get("updated_draft_json"), dict) else fallback.get("updated_draft_json"),
                "updated_preview_markdown": str(parsed.get("updated_preview_markdown") or "").strip()[:12000],
                "applied_changes": [str(item or "").strip()[:160] for item in (parsed.get("applied_changes") or []) if str(item or "").strip()][:10],
                "needs_clarification": bool(parsed.get("needs_clarification", False)),
                "clarification_question": str(parsed.get("clarification_question") or "").strip()[:600],
            }
        except Exception as e:
            logger.error("resume-craft step6 revise invoke failed: %s", e)
            return fallback

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
        confirmed_facts_context = payload.get("confirmed_facts_context") or history_text or "（无）"
        jd_direction_context = payload.get("jd_direction_context") or "（无）"
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
8) 只能使用“事实白名单”中已经确认的信息；不得从 JD 摘要中新增任何未被用户确认的事实。
{photo_rule}

[SKILL.md 规范全文节选]
{skill_spec[:18000]}

[resume-template.html 参考（Editorial 完整结构）]
{str(base_template)[:22000]}

[CareerForge-模板预览.html 选中模板片段]
{str(preview_snippet)[:5000]}

[已保存目标信息（若用户后续已更新，请以后续最新输入为准）]
{str(profile_context)[:9000]}

[事实白名单（可写入简历）]
{str(confirmed_facts_context)[:18000]}

[JD 方向上下文（仅用于排序/强调，不可当作事实）]
{str(jd_direction_context)[:6000]}

[对话摘要（仅供参考）]
{str(history_text)[:5000]}

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
