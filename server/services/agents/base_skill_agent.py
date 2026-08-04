"""Shared SkillLoader-backed runtime for CareerForge feature agents."""

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


class BaseSkillAgent:
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
    SKILL_NAME: Optional[str] = None

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
        if self.SKILL_NAME and skill_name != self.SKILL_NAME:
            raise ValueError(f"{self.__class__.__name__} cannot load skill: {skill_name}")
        return self.skill_loader.load(skill_name)

    def _skill_path(self, skill_name: str) -> Path:
        return self.skill_loader.skill_path(skill_name)

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
                merged[key] = BaseSkillAgent._merge_state_patch(merged[key], value)
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

    @staticmethod
    def _normalize_grill_covered_dimensions(raw: Any) -> List[Dict[str, str]]:
        """Normalize the model-maintained ledger of facts already covered."""
        dimensions: List[Dict[str, str]] = []
        seen = set()
        if not isinstance(raw, list):
            return dimensions
        for item in raw:
            if isinstance(item, str):
                dimension = item.strip()[:80]
                evidence = ""
            elif isinstance(item, dict):
                dimension = str(item.get("dimension") or item.get("id") or "").strip()[:80]
                evidence = str(item.get("evidence") or "").strip()[:800]
            else:
                continue
            if not dimension or dimension in seen:
                continue
            dimensions.append({"dimension": dimension, "evidence": evidence})
            seen.add(dimension)
        return dimensions

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
        previous_covered = cls._normalize_grill_covered_dimensions(
            previous_grill.get("covered_dimensions")
        )
        covered = cls._normalize_grill_covered_dimensions(grill.get("covered_dimensions"))
        covered_by_dimension = {item["dimension"]: item for item in covered}
        for item in previous_covered:
            covered_by_dimension.setdefault(item["dimension"], item)
        # Closing a question also closes its high-level dimension. This keeps
        # old states useful before the model starts returning the ledger.
        for question in questions:
            if question["status"] in {"answered", "skipped"} and question["dimension"]:
                covered_by_dimension.setdefault(
                    question["dimension"],
                    {"dimension": question["dimension"], "evidence": question["text"]},
                )
        covered = list(covered_by_dimension.values())
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
        grill["covered_dimensions"] = covered
        grill["round_status"] = round_status
        grill["user_skipped"] = user_skipped
        return result

    @staticmethod
    def _strip_preview_confirmation_guidance(value: Any) -> str:
        """Keep confirmation guidance in the reply, never in the preview body."""
        text = str(value or "").strip()
        if not text:
            return ""
        guidance = "请确认以上信息是否需要修改？如果没有问题，可以输入“生成简历”来生成您的简历。"
        text = re.sub(re.escape(guidance), "", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _ensure_preview_confirmation_guidance(result: dict) -> dict:
        """Make the single preview-and-preferences confirmation actionable."""
        wizard_state = result.get("wizard_state")
        if not isinstance(wizard_state, dict):
            return result
        step_states = wizard_state.get("step_states")
        step6 = step_states.get("step6") if isinstance(step_states, dict) else None
        if not isinstance(step6, dict):
            return result

        raw_preview = result.get("step6_preview_markdown") or step6.get("preview_markdown") or ""
        preview = BaseSkillAgent._strip_preview_confirmation_guidance(raw_preview)
        if "step6_preview_markdown" in result:
            result["step6_preview_markdown"] = preview
        if "preview_markdown" in step6:
            step6["preview_markdown"] = preview
        awaiting_confirm = (
            result.get("step6_waiting_confirm") is True
            or step6.get("awaiting_confirm") is True
        )
        if not preview or not awaiting_confirm:
            return result

        reply = str(result.get("reply") or "").strip()
        if re.search(r"[\u4e00-\u9fff]", reply) or not reply:
            result["reply"] = "请确认以上信息是否需要修改？如果没有问题，可以输入“生成简历”来生成您的简历。"
        else:
            result["reply"] = 'Please confirm whether the information above needs changes. If everything looks good, type "generate resume" to create your resume.'
        return result

    @staticmethod
    def _normalize_render_ready_state(result: dict, current_step: Any = 6) -> dict:
        """Keep the UI confirmation state aligned with the render-ready contract."""
        if str(current_step) != "6":
            wizard_state = result.get("wizard_state")
            premature_confirmation = False
            step5_preview_transition = False
            if isinstance(wizard_state, dict):
                collected = wizard_state.get("collected_by_step")
                if isinstance(collected, dict):
                    premature_confirmation = bool(collected.get("step6_confirmed"))
                    collected["step6_confirmed"] = False
                step_states = wizard_state.get("step_states")
                step6 = step_states.get("step6") if isinstance(step_states, dict) else None
                if isinstance(step6, dict):
                    step5_preview_transition = (
                        str(current_step) == "5"
                        and result.get("render_ready") is not True
                        and result.get("step6_waiting_confirm") is True
                        and step6.get("preview_ready") is True
                        and step6.get("awaiting_confirm") is True
                    )
                    premature_confirmation = premature_confirmation or bool(step6.get("confirmed"))
                    step6["confirmed"] = False
                    if not step5_preview_transition:
                        step6["awaiting_confirm"] = False
            if (
                result.get("render_ready") is not True
                and not premature_confirmation
                and not step5_preview_transition
            ):
                return BaseSkillAgent._ensure_preview_confirmation_guidance(result)
            result["render_ready"] = False
            result["action"] = "advance"
            result["next_step_suggestion"] = "next"
            return BaseSkillAgent._ensure_preview_confirmation_guidance(result)

        if result.get("render_ready") is not True:
            return BaseSkillAgent._ensure_preview_confirmation_guidance(result)

        wizard_state = result.get("wizard_state")
        if not isinstance(wizard_state, dict):
            result["render_ready"] = False
            return BaseSkillAgent._ensure_preview_confirmation_guidance(result)

        step_states = wizard_state.get("step_states")
        step6 = step_states.get("step6") if isinstance(step_states, dict) else None
        draft_json = step6.get("draft_json") if isinstance(step6, dict) else None
        if not isinstance(draft_json, dict) or not draft_json:
            result["render_ready"] = False
            return BaseSkillAgent._ensure_preview_confirmation_guidance(result)

        collected = wizard_state.get("collected_by_step")
        explicitly_confirmed = (
            isinstance(collected, dict)
            and collected.get("step6_confirmed") is True
            and isinstance(step6, dict)
            and step6.get("confirmed") is True
        )
        if not explicitly_confirmed:
            # Do not turn a malformed model response into a confirmation. The
            # user must have confirmed the preview in the Agent state first.
            result["render_ready"] = False
            return BaseSkillAgent._ensure_preview_confirmation_guidance(result)

        # The previous preview is already visible in the conversation. A
        # generation turn should only report progress, so the frontend does
        # not append the same preview a second time.
        result["step6_preview_markdown"] = ""
        result["step6_waiting_confirm"] = False

        if isinstance(collected, dict):
            collected["step6_confirmed"] = True
        if isinstance(step6, dict):
            step6["confirmed"] = True
            step6["awaiting_confirm"] = False
        reply = str(result.get("reply") or "").strip()
        if "点击" in reply and "生成" in reply:
            reply = re.sub(r"点击[^。！？\n]*生成[^。！？\n]*[。！？]?", "", reply).strip()
        if re.search(r"[\u4e00-\u9fff]", reply) or not reply:
            result["reply"] = "好的，正在为您生成简历的 HTML 和 PDF 版本。请稍候。"
        else:
            result["reply"] = 'Okay, I am generating the HTML and PDF versions of your resume. Please wait.'
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
