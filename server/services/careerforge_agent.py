import json
import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from server.services.skill_loader import SkillLoader
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

    def __init__(
        self,
        skills_root: Optional[str] = None,
        llm=None,
        skill_loader: Optional[SkillLoader] = None,
        llm_error: Optional[str] = None,
    ):
        self.skill_loader = skill_loader or SkillLoader(skills_root=skills_root)
        self.llm_error: Optional[str] = llm_error
        self.llm = llm
        if llm is None:
            self.llm_error = self.llm_error or "LLM must be provided by the runtime service"

    def load_skill(self, skill_name: str) -> str:
        if skill_name not in self.SUPPORTED_SKILLS:
            raise ValueError(f"Unsupported skill: {skill_name}")
        return self.skill_loader.load(skill_name)

    @staticmethod
    def _normalize_language(language: str = "zh") -> str:
        lang = (language or "zh").strip().lower()
        if lang.startswith("en"):
            return "en"
        return "zh"

    @staticmethod
    def _language_label(language: str) -> str:
        return "English" if language == "en" else "Chinese"

    @staticmethod
    def _merge_state_patch(existing: Any, patch: Any) -> Any:
        """Merge a model's minimal JSON state patch without losing prior state."""
        if not isinstance(existing, dict) or not isinstance(patch, dict):
            return deepcopy(patch)

        merged = deepcopy(existing)
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = CareerForgeAgent._merge_state_patch(merged[key], value)
            else:
                merged[key] = deepcopy(value)
        return merged

    @staticmethod
    def _normalize_grill_questions(raw: Any) -> List[Dict[str, str]]:
        questions: List[Dict[str, str]] = []
        seen_ids = set()
        if not isinstance(raw, list):
            return questions
        for index, item in enumerate(raw, start=1):
            if not isinstance(item, dict):
                continue
            question_id = str(item.get("id") or f"q-{index}").strip()[:80]
            question_text = str(item.get("text") or "").strip()[:600]
            if not question_id or not question_text or question_id in seen_ids:
                continue
            status = str(item.get("status") or "open").strip().lower()
            if status not in {"open", "answered", "skipped"}:
                status = "open"
            questions.append(
                {
                    "id": question_id,
                    "text": question_text,
                    "dimension": str(item.get("dimension") or "").strip()[:120],
                    "status": status,
                }
            )
            seen_ids.add(question_id)
        return questions

    @classmethod
    def _normalize_grill_state(
        cls,
        previous_wizard_state: Any,
        wizard_state: Any,
        result: dict,
    ) -> dict:
        if not isinstance(wizard_state, dict):
            return result
        step_states = wizard_state.get("step_states")
        step4 = step_states.get("step4") if isinstance(step_states, dict) else None
        active_focus = step4.get("active_focus") if isinstance(step4, dict) else None
        grill = active_focus.get("grill") if isinstance(active_focus, dict) else None
        if not isinstance(grill, dict):
            return result

        previous_step_states = previous_wizard_state.get("step_states") if isinstance(previous_wizard_state, dict) else None
        previous_step4 = previous_step_states.get("step4") if isinstance(previous_step_states, dict) else None
        previous_focus = previous_step4.get("active_focus") if isinstance(previous_step4, dict) else None
        previous_grill = previous_focus.get("grill") if isinstance(previous_focus, dict) else {}
        previous_grill = previous_grill if isinstance(previous_grill, dict) else {}

        previous_questions = cls._normalize_grill_questions(previous_grill.get("pending_questions"))
        questions = cls._normalize_grill_questions(grill.get("pending_questions"))
        questions_by_id = {item["id"]: item for item in questions}
        previous_open = {
            item["id"]: item for item in previous_questions if item["status"] == "open"
        }

        # An open question is never implicitly removed by a model patch. The
        # model must semantically mark it answered or skipped first.
        for question_id, question in previous_open.items():
            current = questions_by_id.get(question_id)
            if current is None:
                restored = dict(question)
                restored["status"] = "open"
                questions.append(restored)
                questions_by_id[question_id] = restored

        def _bounded_count(value: Any, default: int = 0) -> int:
            try:
                return max(0, min(int(value), 3))
            except (TypeError, ValueError):
                return default

        previous_completed = _bounded_count(previous_grill.get("completed_rounds"))
        proposed_completed = _bounded_count(grill.get("completed_rounds"), previous_completed)
        # One user turn can close at most the currently pending question set.
        # This prevents a model response from skipping entire Grill rounds by
        # returning an inflated completed_rounds value.
        proposed_completed = min(proposed_completed, previous_completed + 1)
        remaining_open = [item for item in questions if item["status"] == "open"]
        if previous_open:
            previous_ids_closed = all(
                questions_by_id.get(question_id, {}).get("status") in {"answered", "skipped"}
                for question_id in previous_open
            )
            if previous_ids_closed:
                proposed_completed = max(proposed_completed, previous_completed + 1)
            else:
                proposed_completed = min(proposed_completed, previous_completed)
        else:
            # Once a Grill state exists, a round must be backed by the
            # question set that was open in the prior turn. The initial
            # project description alone is not a completed Grill round.
            proposed_completed = min(proposed_completed, previous_completed)
        completed_rounds = _bounded_count(proposed_completed, previous_completed)

        user_skipped = bool(grill.get("user_skipped"))
        if user_skipped:
            for question in questions:
                if question["status"] == "open":
                    question["status"] = "skipped"
            round_status = "skipped"
            if isinstance(active_focus, dict):
                active_focus["stage"] = "done"
            result["next_step_suggestion"] = "next"
            result["action"] = "advance"
        else:
            requested_status = str(grill.get("round_status") or "").strip().lower()
            if completed_rounds >= 3 and not remaining_open:
                round_status = "project_completed"
                if isinstance(active_focus, dict):
                    active_focus["stage"] = "done"
                result["next_step_suggestion"] = "next"
                result["action"] = "advance"
            elif completed_rounds >= 3 and remaining_open:
                round_status = "awaiting_answers"
                if isinstance(active_focus, dict) and active_focus.get("stage") == "done":
                    active_focus["stage"] = "validation"
                result["next_step_suggestion"] = "stay"
                result["action"] = "collect"
            elif requested_status == "project_completed" and completed_rounds >= 2 and not remaining_open:
                round_status = "project_completed"
                if isinstance(active_focus, dict):
                    active_focus["stage"] = "done"
            elif requested_status == "project_completed" and completed_rounds < 2:
                # A project cannot finish after only one completed Grill round.
                round_status = "round_completed" if not remaining_open else "awaiting_answers"
                if isinstance(active_focus, dict) and active_focus.get("stage") == "done":
                    active_focus["stage"] = "validation"
                result["next_step_suggestion"] = "stay"
                result["action"] = "collect"
            elif remaining_open:
                round_status = "awaiting_answers"
                if isinstance(active_focus, dict) and active_focus.get("stage") == "done":
                    active_focus["stage"] = "validation"
                result["next_step_suggestion"] = "stay"
            else:
                round_status = requested_status if requested_status in {"round_completed", "awaiting_answers"} else "round_completed"

        grill["completed_rounds"] = completed_rounds
        grill["pending_questions"] = questions
        grill["round_status"] = round_status
        grill["user_skipped"] = user_skipped
        return result

    @staticmethod
    def _normalize_render_ready_state(result: dict, current_step: Any = 6) -> dict:
        """Keep the UI confirmation state aligned with the render-ready contract."""
        if str(current_step) != "6":
            wizard_state = result.get("wizard_state")
            premature_confirmation = False
            if isinstance(wizard_state, dict):
                collected = wizard_state.get("collected_by_step")
                if isinstance(collected, dict):
                    premature_confirmation = bool(collected.get("step6_confirmed"))
                    collected["step6_confirmed"] = False
                step_states = wizard_state.get("step_states")
                step6 = step_states.get("step6") if isinstance(step_states, dict) else None
                if isinstance(step6, dict):
                    premature_confirmation = premature_confirmation or bool(step6.get("confirmed"))
                    step6["confirmed"] = False
                    step6["awaiting_confirm"] = False
            if result.get("render_ready") is not True and not premature_confirmation:
                return result
            result["render_ready"] = False
            result["action"] = "advance"
            result["next_step_suggestion"] = "next"
            result["reply"] = "技能与证书信息已记录。接下来请在当前对话中补充最终偏好，随后进行预览确认。"
            return result

        if result.get("render_ready") is not True:
            return result

        wizard_state = result.get("wizard_state")
        if not isinstance(wizard_state, dict):
            result["render_ready"] = False
            return result

        step_states = wizard_state.get("step_states")
        step6 = step_states.get("step6") if isinstance(step_states, dict) else None
        draft_json = step6.get("draft_json") if isinstance(step6, dict) else None
        if not isinstance(draft_json, dict) or not draft_json:
            result["render_ready"] = False
            return result

        collected = wizard_state.setdefault("collected_by_step", {})
        if isinstance(collected, dict):
            collected["step6_confirmed"] = True
        if isinstance(step6, dict):
            step6["confirmed"] = True
            step6["awaiting_confirm"] = False
        guidance = "预览内容已确认，请点击“生成简历”按钮生成 HTML 和 PDF。"
        reply = str(result.get("reply") or "").strip()
        has_generation_guidance = (
            "点击" in reply
            and ("生成" in reply or "导出" in reply)
            and any(token in reply for token in ("简历", "HTML", "PDF", "按钮"))
        )
        if not has_generation_guidance:
            result["reply"] = f"{reply}\n\n{guidance}".strip()
        return result

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

    def _repair_json_output(self, skill_name: str, raw: str, schema_json: str) -> Optional[dict]:
        if self.llm is None:
            return None

        repair_prompt = ChatPromptTemplate.from_template(
            """
You are fixing a model response into STRICT JSON.

[Skill Name]
{skill_name}

[Target JSON Schema]
{schema_json}

[Broken Output]
{raw_output}

[Instructions]
- Convert the broken output into one valid JSON object matching the schema.
- Preserve the original meaning as much as possible.
- Output JSON only.
- Do not add markdown fences or explanations.
"""
        )

        try:
            repaired_raw = (repair_prompt | self.llm | StrOutputParser()).invoke(
                {
                    "skill_name": skill_name,
                    "schema_json": schema_json,
                    "raw_output": (raw or "")[:12000],
                }
            )
        except Exception as e:
            logger.warning("Skill %s JSON repair failed: %s", skill_name, e)
            return None

        repaired = self._safe_json_loads(repaired_raw)
        if isinstance(repaired, dict):
            return repaired
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
            if parsed is None or not isinstance(parsed, dict):
                repaired = self._repair_json_output(skill_name, raw, schema_json)
                if repaired is not None:
                    return repaired
                logger.warning("Skill %s returned non-JSON output", skill_name)
                return {
                    "error": "invalid_skill_output",
                    "message": "Model returned non-JSON output.",
                    "raw_text": raw.strip(),
                    "assumptions": ["model_output_not_json"],
                }
            return parsed
        except Exception as e:
            logger.error("Skill %s invocation failed: %s", skill_name, e)
            return {
                "error": "skill_failed",
                "message": str(e),
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

    def _compact_resume_match_skill_excerpt(self) -> str:
        skill_spec = self.load_skill("resume-match")
        text = str(skill_spec or "").strip()
        if not text:
            return ""
        if text.startswith("---"):
            frontmatter_split = text.split("---", 2)
            if len(frontmatter_split) >= 3:
                text = frontmatter_split[2].strip()

        has_scoring = "六维度评分" in text or "第二步：六维度评分" in text
        has_honesty = "诚实原则" in text or "不要编造" in text
        has_output = "输出格式" in text or "JSON" in text

        summary_lines = ["该 skill 要求：基于简历与 JD 做中文匹配分析，并输出结构化 JSON。"]
        if "简历" in text and "JD" in text:
            summary_lines.append("输入必须围绕当前页提供的简历文本、岗位 JD、目标岗位，不拼接跨页面历史。")
        if has_scoring:
            summary_lines.append(
                "按 6 个维度评分：硬性技能匹配度、工作经验相关度、软性能力匹配度、教育背景匹配度、关键词覆盖率、简历质量。"
            )
            summary_lines.append("根据加权总分输出 A/B/C 匹配等级，并给出总结、关键差距、优势与可执行优化建议。")
        if has_honesty:
            summary_lines.append("不得编造经历；信息不足时只能在 assumptions 中如实说明，不得把已提供内容说成缺失。")
        if has_output:
            summary_lines.append("输出必须是单个 JSON 对象，不加 Markdown 代码块或额外解释。")

        return "\n".join(summary_lines).strip()

    def _looks_like_missing_input_analysis(self, result: dict, payload: dict) -> bool:
        if not isinstance(result, dict):
            return False
        payload_resume = str((payload or {}).get("resume_text") or "").strip()
        payload_jd = str((payload or {}).get("jd_text") or "").strip()
        if not payload_resume or not payload_jd:
            return False

        summary = str(result.get("summary") or "").strip().lower()
        assumptions = " ".join(str(item or "") for item in (result.get("assumptions") or [] if isinstance(result.get("assumptions"), list) else [] )).lower()
        score = result.get("overall_score")
        dims = result.get("dimension_scores")
        no_dims = isinstance(dims, list) and len(dims) == 0
        no_content_markers = (
            "no input content",
            "no resume content",
            "未提供简历",
            "缺少简历",
            "未提供输入",
        )
        text_blob = f"{summary} {assumptions}"
        return (str(score).strip() in {"0", "0.0"} and no_dims and any(marker in text_blob for marker in no_content_markers))

    def _invoke_resume_match_compact(self, payload: dict, schema: dict) -> dict:
        if self.llm is None:
            return {
                "error": "llm_not_ready",
                "message": self.llm_error or "LLM is not initialized",
                "assumptions": ["missing_api_key_or_model_init_failed"],
            }

        prompt = ChatPromptTemplate.from_template(
            """
You are a backend resume-job matching engine.
Follow the loaded resume-match skill guidance and analyze the provided RESUME and JOB DESCRIPTION.

[Resume-Match Skill Excerpt]
{skill_excerpt}

Requirements:
- Language: Chinese.
- Use the provided resume and JD directly; do not claim the input is missing when text is present.
- Output exactly one JSON object matching the target schema.
- Prefer 6 dimension score items whenever the input supports it.
- Each dimension item must include: name, score, highlight, gap, advice.
- Keep every `highlight`, `gap`, and `advice` as a single short sentence, ideally under 30 Chinese characters.
- Keep `summary` within 50 Chinese characters.
- Keep `critical_missing`, `extra_advantages`, and `optimization_suggestions` to at most 2 items each.
- `optimized_resume_markdown` may be an empty string; if provided, keep it under 150 Chinese characters total.
- Keep all content factual and based only on the provided input.
- Do not wrap output in markdown or add explanations outside JSON.

[Input Context]
{{
  "target_role": {target_role_json},
  "resume_text": {resume_text_json},
  "jd_text": {jd_text_json}
}}

[Required JSON Schema]
{schema_json}
"""
        )
        try:
            target_role = str(payload.get("target_role") or "")[:300]
            resume_text = str(payload.get("resume_text") or "")[:12000]
            jd_text = str(payload.get("jd_text") or "")[:8000]
            raw = (prompt | self.llm | StrOutputParser()).invoke(
                {
                    "skill_excerpt": self._compact_resume_match_skill_excerpt()[:4000],
                    "target_role_json": json.dumps(target_role, ensure_ascii=False),
                    "resume_text_json": json.dumps(resume_text[:6000], ensure_ascii=False),
                    "jd_text_json": json.dumps(jd_text[:5000], ensure_ascii=False),
                    "schema_json": json.dumps(schema, ensure_ascii=False, indent=2),
                }
            )
            parsed = self._safe_json_loads(raw)
            if parsed is None or not isinstance(parsed, dict):
                repaired = self._repair_json_output("resume-match", raw, json.dumps(schema, ensure_ascii=False, indent=2))
                if repaired is not None:
                    return repaired
                return {
                    "error": "invalid_skill_output",
                    "message": "Compact resume-match prompt returned non-JSON output.",
                    "raw_text": str(raw or "").strip(),
                    "assumptions": ["compact_model_output_not_json"],
                }
            return parsed
        except Exception as e:
            logger.error("Compact resume-match invocation failed: %s", e)
            return {
                "error": "skill_failed",
                "message": str(e),
                "assumptions": ["compact_model_call_failed"],
            }

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
        result = self._invoke_resume_match_compact(payload, schema)
        if self._looks_like_missing_input_analysis(result, payload):
            logger.warning("resume-match compact prompt still returned missing-input analysis")
        return result

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

    def run_resume_craft_chat_turn(self, payload: dict) -> dict:
        """Run one stateful resume-craft conversation turn through the loaded skill."""
        if self.llm is None:
            raise RuntimeError(self.llm_error or "LLM is not initialized")

        skill_spec = self.load_skill("resume-craft")
        schema = {
            "reply": "string",
            "action": "collect|advance|preview|revise|confirm|render_ready",
            "next_step_suggestion": "stay|next",
            "render_ready": False,
            "missing_fields": ["string"],
            "wizard_state": "minimal JSON patch for ResumeCraftWizardState",
            "step6_preview_markdown": "string",
            "step6_waiting_confirm": False,
            "step6_applied_changes": ["string"],
            "grill_state": {
                "completed_rounds": 0,
                "pending_questions": [
                    {"id": "string", "text": "string", "dimension": "string", "status": "open|answered|skipped"}
                ],
                "round_status": "awaiting_answers|round_completed|project_completed|skipped",
                "user_skipped": False,
            },
        }
        schema_json = json.dumps(schema, ensure_ascii=False, indent=2)
        prompt = ChatPromptTemplate.from_template(
            """
你正在运行 CareerForge 的 resume-craft 对话 Agent。
必须完整阅读并遵循下面的 Skill 规范。Skill 是行为决策的唯一业务依据；当前步骤、表单信息和历史记录只是上下文，不是固定问卷。

[Skill Specification]
{skill_spec}

[当前页面上下文]
{context_json}

[输出要求]
1. 只输出一个 JSON 对象，严格匹配下面的 schema，不要 Markdown 代码块或额外解释。
2. 根据用户最新输入的语义、完整对话历史和当前简历状态，自主决定下一步：该追问、确认、修改、预览，还是允许进入下一阶段。
3. 不要按固定字段顺序或关键词判断推进。先对照完整 history 和当前状态判断哪些问题已经被用户回答；已回答的问题不得重复追问，即使用户没有使用你原问题中的相同措辞。用户表达没有更多补充时，应基于上下文结束当前经历的深挖。
4. 当前页面是 Step3/4/5 的连续对话工作区，但后端阶段必须严格区分：`current_step=4` 只处理工作/项目经历，`current_step=5` 只处理技能与证书，`current_step=6` 才处理确认、预览和生成前状态。前端会在 `next_step_suggestion=next` 后自动切换阶段，并将完整 history 传入下一轮；不要把连续页面理解为跳过阶段，也不要要求用户点击不存在的阶段按钮。
5. Step4 工作/项目经历 Grill 必须维护 `step_states.step4.active_focus.grill`。一次 Agent 输出中的多个问题属于同一轮，必须逐个用 `pending_questions` 的 ID 标记为 answered 或 skipped；仍有 open 问题时不得增加 `completed_rounds`，不得结束项目。每个项目默认至少完成 2 轮、最多 3 轮；第 2 轮完成且事实足够时可以结束，第 3 轮完成后必须结束。只有用户明确表示不想继续回答当前项目时，才设置 `user_skipped=true`、`round_status=skipped` 并结束，不依赖固定关键词。每次生成新问题前，必须依据完整 history 建立已解决事实维度账本，禁止对已回答事实进行同义、上下位或换例子式重复追问。
6. 可以一次询问多个彼此相关的问题，也可以在问题集合全部回答后进入下一轮；问题应该像职业顾问对话，而不是表单提示。每个问题必须绑定仍缺失且影响简历准确性的维度；如果用户已经具体回答过某主题，即使没有使用原问题措辞，也必须将其标记为 answered，不得再次生成等价问题。没有 open 问题且核心事实已齐全时，用户语义表示没有更多补充应直接结束当前经历，不要用宽泛问题延长对话。
7. 严格遵守事实边界，不编造经历、技能、职责或成果。对不清楚的内容先追问或标记为缺失。
8. 只返回本轮必要的 wizard_state 最小 JSON 补丁，不要重复输出完整历史、聊天记录或未变化的经历内容。运行时会把补丁合并到已有状态；本轮确认过的新事实写入对应的 collected_by_step / step_states。
9. 只有当前页面上下文中的 `current_step=6`（连续工作区的“确认与偏好”阶段）才能进行 Step6 预览、修改和确认。`current_step=5` 时只能收集技能、工具、语言能力和证书，不得设置 `step6_confirmed=true`、`step6.confirmed=true` 或 `render_ready=true`，也不得引导用户点击“生成简历”。在 `current_step=6` 时，预览、修改和确认必须由用户语义触发，不要依赖固定按钮或固定关键词。用户表达想查看或生成预览时，基于已确认事实生成结构化 draft_json 和 Markdown 摘要，写入 step_states.step6.preview_markdown，并设置 preview_ready=true、awaiting_confirm=true、confirmed=false、step6_confirmed=false、render_ready=false；reply 必须展示摘要并询问是否需要修改。
10. 用户提出修改时，只修改其明确要求的内容，更新 draft_json 和 preview_markdown，增加 revision_count，并保持 awaiting_confirm=true、confirmed=false、step6_confirmed=false、render_ready=false；修改后再次展示摘要并等待确认。用户可以在连续 history 中修改前一阶段内容，必须同步更新对应的 confirmed state 和后续预览事实。
11. 只有用户明确表示无需修改、确认内容或确认生成时，才设置 step_states.step6.confirmed=true、awaiting_confirm=false、step6_confirmed=true、render_ready=true，并在 reply 中明确提示用户点击“生成简历”生成 HTML 和 PDF。Agent 不得自动调用生成接口。
12. next_step_suggestion=next 只表示你判断当前阶段已完成；连续工作区会据此推进后端语义阶段，不要依赖固定按钮，也不要为了满足固定流程而强行推进。
13. 结束工作/项目经历时，必须在事实边界内写入 step_states.step4.finalized_experiences，设置 step_states.step4.active_focus.stage=done，并记录仍缺失的核心维度（如有）。除非 user_skipped=true 或 Grill 已完成至少 2 轮，否则不得结束。若核心事实已齐全、当前没有 open 问题且用户语义上表示没有更多补充，应完成当前经历并保持 stage=done，不要继续追问。reply 要说明本段经历已完成；若还未达到用户计划的经历数量，邀请用户继续描述下一段，否则自然引导连续工作区进入技能与证书。结束后不得再次提出已经回答过的问题。

[Required JSON Schema]
{schema_json}
"""
        )
        context = {
            "current_step": payload.get("current_step"),
            "step1_profile": payload.get("step1_profile") or {},
            "wizard_state": payload.get("wizard_state") or {},
            "history": payload.get("history") or [],
            "message": str(payload.get("message") or "").strip(),
        }
        raw = (prompt | self.llm | StrOutputParser()).invoke(
            {
                "skill_spec": skill_spec,
                "context_json": json.dumps(context, ensure_ascii=False, indent=2),
                "schema_json": schema_json,
            }
        )
        try:
            parsed = json.loads(str(raw or "").strip())
        except json.JSONDecodeError as exc:
            raise RuntimeError("resume-craft agent returned invalid JSON") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("resume-craft agent returned invalid JSON")
        if not isinstance(parsed.get("wizard_state"), dict):
            raise RuntimeError("resume-craft agent response is missing wizard_state")
        if not str(parsed.get("reply") or "").strip() and not str(parsed.get("step6_preview_markdown") or "").strip():
            raise RuntimeError("resume-craft agent response is missing reply")
        previous_wizard_state = context["wizard_state"]
        parsed["wizard_state"] = self._merge_state_patch(
            previous_wizard_state, parsed["wizard_state"]
        )
        parsed = self._normalize_grill_state(
            previous_wizard_state, parsed["wizard_state"], parsed
        )
        return self._normalize_render_ready_state(parsed, payload.get("current_step"))

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
        history_text = json.dumps(payload.get("history") or [], ensure_ascii=False)
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

[SKILL.md 规范全文]
{skill_spec}

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
            raise RuntimeError(self.llm_error or "LLM is not initialized")
        prompt = ChatPromptTemplate.from_template("{full_prompt}")
        chain = prompt | self.llm | StrOutputParser()
        full_prompt = self._build_resume_craft_html_prompt(payload)
        try:
            for chunk in chain.stream({"full_prompt": full_prompt}):
                yield chunk
        except Exception:
            logger.exception("resume-craft html stream failed")
            raise

    def run_resume_craft_html(self, payload: dict) -> str:
        if self.llm is None:
            raise RuntimeError(self.llm_error or "LLM is not initialized")
        prompt = ChatPromptTemplate.from_template("{full_prompt}")
        chain = prompt | self.llm | StrOutputParser()
        full_prompt = self._build_resume_craft_html_prompt(payload)
        return chain.invoke({"full_prompt": full_prompt})

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
