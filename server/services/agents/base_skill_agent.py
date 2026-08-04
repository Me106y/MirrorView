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

    @staticmethod
    def _canonical_grill_dimension(dimension: Any) -> str:
        """Collapse question labels to the high-level dimensions used for de-duplication."""
        value = str(dimension or "").strip().lower()
        if not value:
            return ""
        compact = re.sub(r"[\s_\-./:：]+", "", value)
        aliases = {
            "result": {"result", "results", "outcome", "impact", "metric", "metrics", "achievement", "businessimpact", "businessvalue", "quantitativeresult", "quantifiedperformance", "userscale", "deploymenteffect", "成果", "结果", "效果", "影响", "量化成果", "业务影响", "用户规模", "部署效果"},
            "collaboration": {"collaboration", "collaborations", "teamwork", "team", "communication", "coordination", "stakeholderalignment", "cross-team", "cross-teamcommunication", "teamcollaboration", "协作", "团队", "团队协作", "沟通", "跨团队", "需求变更"},
            "challenge": {"challenge", "challenges", "technicalchallenge", "technicalproblem", "technicaldifficulty", "difficulty", "stability", "concurrency", "reliability", "maintenance", "modelstability", "modelrobustness", "knowledgebasemaintenance", "技术挑战", "挑战", "难点", "稳定性", "并发", "可靠性", "知识库维护"},
        }
        for canonical, candidates in aliases.items():
            compact_candidates = {re.sub(r"[\s_\-./:：]+", "", item) for item in candidates}
            if value in candidates or compact in compact_candidates:
                return canonical
            # Models may return a composite label such as "业务成果/用户规模"
            # or "技术挑战与稳定性". Those are still the same parent
            # dimension for de-duplication purposes.
            if any(len(candidate) >= 2 and candidate in compact for candidate in compact_candidates):
                return canonical
        return value[:80]

    @staticmethod
    def _grill_question_signature(text: Any) -> str:
        """Create a conservative signature for exact or near-exact repeated questions."""
        value = str(text or "").strip().lower()
        return re.sub(r"[\s\u3000，。！？、；：,.!?;:（）()“”\"'‘’]+", "", value)

    @classmethod
    def _infer_grill_dimension_from_text(cls, text: Any) -> str:
        """Map a historical question to a broad fact dimension when possible."""
        value = str(text or "").strip().lower()
        patterns = {
            "result": (
                "成果", "结果", "效果", "影响", "指标", "效率", "响应", "用户", "部署", "上线",
                "价值", "业务影响", "使用场景", "提升", "提高", "降低", "减少", "增长", "百分比", "%", "ms", "规模",
            ),
            "collaboration": (
                "协作", "团队", "小组", "产品经理", "工程师", "算法", "沟通", "对齐", "分工",
                "带领", "配合", "跨职能", "跨团队", "需求变更", "成员", "角色",
            ),
            "challenge": (
                "挑战", "难点", "问题", "根因", "解决", "稳定", "并发", "维护", "死循环",
                "难题", "技术难题", "故障", "排查", "修复", "可靠", "权限控制",
            ),
        }
        for dimension, candidates in patterns.items():
            if any(candidate.lower() in value for candidate in candidates):
                return dimension
        return ""

    @classmethod
    def _infer_grill_dimensions_from_text(cls, text: Any) -> set:
        """Collect every broad dimension evidenced by a user answer."""
        value = str(text or "").strip().lower()
        patterns = {
            "result": (
                "成果", "结果", "效果", "影响", "指标", "效率", "响应", "用户", "部署", "上线",
                "价值", "业务影响", "使用场景", "提升", "提高", "降低", "减少", "增长", "百分比", "%", "ms", "规模",
            ),
            "collaboration": (
                "协作", "团队", "小组", "产品经理", "工程师", "算法", "沟通", "对齐", "分工",
                "带领", "配合", "跨职能", "跨团队", "需求变更", "成员", "角色",
            ),
            "challenge": (
                "挑战", "难点", "问题", "根因", "解决", "稳定", "并发", "维护", "死循环",
                "难题", "技术难题", "故障", "排查", "修复", "可靠",
            ),
        }
        labels = {
            "result": ("成果", "结果", "效果", "业务影响", "用户规模", "量化指标"),
            "collaboration": ("协作", "团队协作", "跨团队", "沟通", "对齐", "分工", "合作"),
            "challenge": ("挑战", "技术挑战", "难点", "技术难题", "模型稳定性", "并发处理", "知识库维护"),
        }
        negative_markers = (
            "还没回答", "尚未回答", "不知道", "不清楚", "不记得", "还需要补充", "需要补充",
            "还需要确认", "需要确认", "仍需", "待补充", "待确认", "没有补充", "没有其他",
        )
        dimensions = set()
        for dimension, candidates in patterns.items():
            if not any(candidate.lower() in value for candidate in candidates):
                continue
            explicitly_unanswered = any(
                marker in value[max(0, index - 12): index + len(label) + 12]
                for label in labels[dimension]
                for index in [value.find(label)]
                if index >= 0
                for marker in negative_markers
            )
            if not explicitly_unanswered:
                dimensions.add(dimension)
        return dimensions

    @classmethod
    def _infer_grill_dimensions_from_user_history(cls, history: Any) -> set:
        """Recover fact dimensions stated before the Agent asked about them."""
        if not isinstance(history, list):
            return set()
        dimensions = set()
        for item in history:
            if not isinstance(item, dict) or item.get("role") != "user":
                continue
            dimensions.update(cls._infer_grill_dimensions_from_text(item.get("content")))
        return dimensions

    @classmethod
    def _infer_historical_completed_rounds(cls, history: Any) -> int:
        """Recover completed Grill rounds when a model drops its state patch.

        Each assistant turn is one question set. Count only sets whose
        recognizable questions were answered, and de-duplicate sets that have
        the same parent dimensions so an already repeated group cannot inflate
        the round count.
        """
        historical_questions = cls._extract_historical_grill_questions(history)
        if not historical_questions:
            return 0

        grouped: Dict[str, List[Dict[str, str]]] = {}
        for question in historical_questions:
            match = re.match(r"history-q-(\d+)-", question.get("id", ""))
            if not match:
                continue
            grouped.setdefault(match.group(1), []).append(question)

        completed_groups = []
        seen_dimensions = set()
        for questions in grouped.values():
            if not questions or any(item["status"] == "open" for item in questions):
                continue
            dimensions = tuple(sorted(
                dimension
                for dimension in {
                    cls._canonical_grill_dimension(item.get("dimension"))
                    for item in questions
                }
                if dimension
            ))
            if not dimensions or dimensions in seen_dimensions:
                continue
            seen_dimensions.add(dimensions)
            completed_groups.append(questions)
        return min(len(completed_groups), 3)

    @classmethod
    def _extract_historical_grill_questions(cls, history: Any) -> List[Dict[str, str]]:
        """Recover question-level Grill context when a model omitted its ledger.

        The conversation history is an audit trail, not a replacement for the
        structured state. This fallback only recovers recognizable technical
        Grill questions and uses the user messages immediately following each
        assistant turn to determine whether their parent dimension was answered.
        """
        if not isinstance(history, list):
            return []

        questions: List[Dict[str, str]] = []
        seen_signatures = set()
        for assistant_index, message in enumerate(history):
            if not isinstance(message, dict) or message.get("role") != "assistant":
                continue
            content = str(message.get("content") or "").strip()
            if not content or not re.search(r"[？?]", content):
                continue

            answer_parts: List[str] = []
            for following in history[assistant_index + 1:]:
                if not isinstance(following, dict):
                    continue
                if following.get("role") == "assistant":
                    break
                if following.get("role") == "user":
                    answer_parts.append(str(following.get("content") or ""))
            answer_text = " ".join(answer_parts).strip()

            for question_index, chunk in enumerate(re.split(r"(?<=[？?])", content), start=1):
                question_text = re.sub(r"\s+", " ", chunk).strip()
                if not question_text or not re.search(r"[？?]", question_text):
                    continue
                dimension = cls._infer_grill_dimension_from_text(question_text)
                if not dimension:
                    continue
                signature = cls._grill_question_signature(question_text)
                if not signature or signature in seen_signatures:
                    continue
                question = {
                    "id": f"history-q-{assistant_index + 1}-{question_index}",
                    "text": question_text[:600],
                    "dimension": dimension,
                    "status": "open",
                }
                if answer_text and dimension in cls._infer_grill_answered_dimensions(answer_text, [question]):
                    question["status"] = "answered"
                questions.append(question)
                seen_signatures.add(signature)
        return questions

    @classmethod
    def _infer_grill_answered_dimensions(
        cls,
        message: Any,
        questions: List[Dict[str, str]],
    ) -> set:
        """Infer obvious answer coverage only for duplicate-question recovery.

        The LLM remains responsible for normal semantic question-to-answer
        mapping. This conservative fallback is used when it emits a new open
        copy of a question that was pending in the previous turn, so a model
        failure cannot create an endless loop. Partial answers leave the
        unmatched dimensions open.
        """
        text = str(message or "").strip().lower()
        if not text:
            return set()

        evidence_patterns = {
            "result": (
                "成果", "结果", "效果", "影响", "指标", "效率", "响应", "用户", "部署", "上线",
                "价值", "业务影响", "使用场景", "提升", "提高", "降低", "减少", "增长", "从", "到", "%", "ms", "万", "人次",
            ),
            "collaboration": (
                "协作", "团队", "小组", "产品经理", "工程师", "算法", "沟通", "对齐", "分工",
                "带领", "负责与", "配合", "跨职能", "跨团队", "成员", "角色",
            ),
            "challenge": (
                "挑战", "难点", "问题", "根因", "解决", "通过", "优化", "稳定", "并发", "维护",
                "死循环", "难题", "技术难题", "故障", "排查", "修复", "可靠",
            ),
        }
        label_patterns = {
            "result": ("成果", "结果", "效果", "业务影响", "用户规模", "量化指标"),
            "collaboration": ("协作", "团队协作", "跨团队", "沟通", "对齐", "分工", "合作"),
            "challenge": ("挑战", "技术挑战", "难点", "技术难题", "模型稳定性", "并发处理", "知识库维护"),
        }
        negative_markers = ("还没回答", "尚未回答", "不知道", "不清楚", "不记得", "还需要补充", "需要补充", "还需要确认", "需要确认", "仍需", "待补充", "待确认", "没有补充", "没有其他")
        answered = set()
        for question in questions:
            dimension = cls._canonical_grill_dimension(question.get("dimension"))
            if not dimension:
                question_text = str(question.get("text") or "").lower()
                dimension = next(
                    (
                        canonical
                        for canonical, patterns in evidence_patterns.items()
                        if any(pattern in question_text for pattern in patterns)
                    ),
                    "",
                )
            if dimension not in evidence_patterns or not any(pattern in text for pattern in evidence_patterns[dimension]):
                continue
            is_explicitly_unanswered = any(
                marker in text[max(0, index - 12): index + len(label) + 12]
                for label in label_patterns.get(dimension, ())
                for index in [text.find(label)]
                if index >= 0
                for marker in negative_markers
            )
            if not is_explicitly_unanswered:
                answered.add(dimension)
        return answered

    @classmethod
    def _normalize_grill_state(
        cls,
        previous_wizard_state: Any,
        wizard_state: Any,
        result: dict,
        user_message: Any = "",
        history: Any = None,
        current_step: Any = None,
    ) -> dict:
        if not isinstance(wizard_state, dict):
            return result
        step_states = wizard_state.get("step_states")
        request_is_step4 = str(current_step) == "4"
        if not isinstance(step_states, dict):
            if not request_is_step4:
                return result
            step_states = {}
            wizard_state["step_states"] = step_states
        step4 = step_states.get("step4")
        if not isinstance(step4, dict):
            if not request_is_step4:
                return result
            step4 = {}
            step_states["step4"] = step4
        active_focus = step4.get("active_focus")
        if not isinstance(active_focus, dict):
            if not request_is_step4:
                return result
            active_focus = {}
            step4["active_focus"] = active_focus
        if not isinstance(active_focus, dict):
            return result
        grill = active_focus.get("grill")
        if not isinstance(grill, dict):
            grill = {}
            active_focus["grill"] = grill

        previous_step_states = previous_wizard_state.get("step_states") if isinstance(previous_wizard_state, dict) else None
        previous_step4 = previous_step_states.get("step4") if isinstance(previous_step_states, dict) else None
        previous_focus = previous_step4.get("active_focus") if isinstance(previous_step4, dict) else None
        previous_grill = previous_focus.get("grill") if isinstance(previous_focus, dict) else {}
        previous_grill = previous_grill if isinstance(previous_grill, dict) else {}

        def _bounded_count(value: Any, default: int = 0) -> int:
            try:
                return max(0, min(int(value), 3))
            except (TypeError, ValueError):
                return default

        previous_questions = cls._normalize_grill_questions(previous_grill.get("pending_questions"))
        questions = cls._normalize_grill_questions(grill.get("pending_questions"))
        previous_completed = _bounded_count(previous_grill.get("completed_rounds"))
        historical_questions = cls._extract_historical_grill_questions(history)
        if not previous_questions and not previous_grill.get("covered_dimensions"):
            previous_completed = max(
                previous_completed,
                cls._infer_historical_completed_rounds(history),
            )
        historical_answered_dimensions = {
            cls._canonical_grill_dimension(item["dimension"])
            for item in historical_questions
            if item["status"] == "answered"
        }
        historical_user_answered_dimensions = {
            cls._canonical_grill_dimension(item)
            for item in cls._infer_grill_dimensions_from_user_history(history)
            if cls._canonical_grill_dimension(item)
        }
        answered_dimensions = cls._infer_grill_answered_dimensions(
            user_message,
            previous_questions + [item for item in historical_questions if item["status"] == "open"],
        )
        if previous_completed >= 2:
            answered_dimensions.update(cls._infer_grill_dimensions_from_text(user_message))
        answered_dimensions.update(item for item in historical_answered_dimensions if item)
        answered_dimensions.update(historical_user_answered_dimensions)
        previous_questions_by_signature = {
            cls._grill_question_signature(item["text"]): item
            for item in previous_questions
            if cls._grill_question_signature(item["text"])
        }
        previous_open_by_dimension = {}
        for item in previous_questions:
            if item["status"] != "open":
                continue
            dimension = cls._canonical_grill_dimension(item["dimension"])
            if dimension:
                previous_open_by_dimension.setdefault(dimension, item)
        previous_covered = cls._normalize_grill_covered_dimensions(
            previous_grill.get("covered_dimensions")
        )
        covered = cls._normalize_grill_covered_dimensions(grill.get("covered_dimensions"))
        covered_by_dimension = {}
        for item in covered:
            canonical = cls._canonical_grill_dimension(item["dimension"])
            if canonical:
                item["dimension"] = canonical
                covered_by_dimension.setdefault(canonical, item)
        for item in previous_covered:
            canonical = cls._canonical_grill_dimension(item["dimension"])
            if canonical:
                item["dimension"] = canonical
                covered_by_dimension.setdefault(canonical, item)
        # A user answer must close the matching dimensions from an existing
        # question set before the model's replacement questions are examined.
        # This is important at the end of round 1: waiting until round 2 would
        # let the model reopen the just-answered result/team/challenge group.
        # With no previous questions, this remains a project description and
        # must not be treated as a completed Grill answer set.
        if previous_questions or previous_completed >= 2:
            previous_question_evidence = {
                cls._canonical_grill_dimension(item["dimension"]): item["text"]
                for item in previous_questions
                if item.get("dimension")
            }
            for dimension in answered_dimensions:
                covered_by_dimension.setdefault(
                    dimension,
                    {
                        "dimension": dimension,
                        "evidence": previous_question_evidence.get(dimension)
                        or str(user_message or "").strip()[:800]
                        or "本轮用户回答已覆盖该事实维度",
                    },
                )
        for item in historical_questions:
            if item["status"] == "answered" and item["dimension"]:
                canonical = cls._canonical_grill_dimension(item["dimension"])
                if canonical:
                    covered_by_dimension.setdefault(
                        canonical,
                        {"dimension": canonical, "evidence": "已在对话历史中回答该问题"},
                    )
        # Closing a question also closes its high-level dimension. This keeps
        # old states useful before the model starts returning the ledger.
        for question in questions:
            if question["status"] in {"answered", "skipped"} and question["dimension"]:
                question["dimension"] = cls._canonical_grill_dimension(question["dimension"])
                covered_by_dimension.setdefault(
                    question["dimension"],
                    {"dimension": question["dimension"], "evidence": question["text"]},
                )
        for question in previous_questions:
            if question["status"] in {"answered", "skipped"} and question["dimension"]:
                canonical = cls._canonical_grill_dimension(question["dimension"])
                if canonical:
                    covered_by_dimension.setdefault(
                        canonical,
                        {"dimension": canonical, "evidence": question["text"]},
                    )
        for dimension in historical_user_answered_dimensions:
            covered_by_dimension.setdefault(
                dimension,
                {"dimension": dimension, "evidence": "用户已在更早的对话中提供该事实"},
            )

        # Coalesce a model-generated replacement question with the pending
        # question from the previous turn. New IDs must not create a second
        # copy of the same prompt. If the user's latest answer clearly covers
        # the parent dimension, close the old question; otherwise retain it as
        # open and restore the original wording below.
        coalesced_open_question = False
        coalesced_question = False
        previous_question_ids = {item["id"] for item in previous_questions}
        has_new_question = False
        for question in questions:
            question["dimension"] = cls._canonical_grill_dimension(question["dimension"])
            signature = cls._grill_question_signature(question["text"])
            previous_match = previous_questions_by_signature.get(signature)
            if previous_match is None:
                previous_match = previous_open_by_dimension.get(question["dimension"])
            if previous_match is None or previous_match["status"] != "open":
                has_new_question = has_new_question or question["id"] not in previous_question_ids
                continue
            coalesced_question = True
            question["id"] = previous_match["id"]
            question["text"] = previous_match["text"]
            question["dimension"] = cls._canonical_grill_dimension(previous_match["dimension"])
            if question["status"] in {"answered", "skipped"} or question["dimension"] in answered_dimensions:
                question["status"] = "skipped" if question["status"] == "skipped" else "answered"
            else:
                question["status"] = "open"
                coalesced_open_question = True

        covered = list(covered_by_dimension.values())
        questions_by_id = {item["id"]: item for item in questions}
        previous_open = {
            item["id"]: item for item in previous_questions if item["status"] == "open"
        }

        # A new model turn must not reopen a dimension that was already closed
        # in the preceding turn. This is the runtime guard for a common loop:
        # the model acknowledges a user's answers, then emits the same result,
        # collaboration, and challenge questions with new IDs.
        covered_dimensions = set(covered_by_dimension)
        previous_question_signatures = {
            cls._grill_question_signature(item["text"]): item
            for item in previous_questions
            if item["status"] in {"answered", "skipped"}
        }
        historical_answered_signatures = {
            cls._grill_question_signature(item["text"]): item
            for item in historical_questions
            if item["status"] in {"answered", "skipped"}
        }
        previous_question_signatures.update(historical_answered_signatures)
        historical_covered_dimensions = set(historical_answered_dimensions)
        filtered_questions: List[Dict[str, str]] = []
        filtered_duplicate_questions = False
        historical_reply_questions = cls._extract_historical_grill_questions(
            [{"role": "assistant", "content": str(result.get("reply") or "")}]
        )
        covered_parent_dimensions = covered_dimensions | historical_covered_dimensions
        reply_question_dimensions = {
            cls._canonical_grill_dimension(item["dimension"])
            for item in historical_reply_questions
            if cls._canonical_grill_dimension(item["dimension"])
        }
        # A model can rename a question's structured dimension on every turn,
        # while the prose still asks the same covered parent fact. Treat the
        # whole reply as a duplicate when every recognizable question belongs
        # to an already covered parent dimension. This reply-level guard keeps
        # a new question ID or label from leaking the old question group back
        # into the chat.
        historical_duplicate_questions = bool(reply_question_dimensions) and reply_question_dimensions.issubset(
            covered_parent_dimensions
        )
        if historical_duplicate_questions:
            filtered_duplicate_questions = True
        seen_signatures = set()
        for question in questions:
            canonical_dimension = cls._canonical_grill_dimension(question["dimension"])
            if canonical_dimension not in covered_parent_dimensions:
                inferred_dimension = cls._infer_grill_dimension_from_text(question["text"])
                if inferred_dimension in covered_parent_dimensions:
                    canonical_dimension = inferred_dimension
            question["dimension"] = canonical_dimension
            signature = cls._grill_question_signature(question["text"])
            is_previous_open = question["id"] in previous_open
            is_repeated_closed_question = (
                not is_previous_open
                and signature
                and signature in previous_question_signatures
            )
            is_covered_dimension = (
                not is_previous_open
                and question["status"] == "open"
                and canonical_dimension
                and canonical_dimension in covered_dimensions
            )
            is_historical_duplicate = (
                not is_previous_open
                and (
                    (signature and signature in historical_answered_signatures)
                    or canonical_dimension in historical_covered_dimensions
                )
            )
            if is_repeated_closed_question or is_covered_dimension or (
                signature and signature in seen_signatures
            ):
                filtered_duplicate_questions = True
                historical_duplicate_questions = historical_duplicate_questions or is_historical_duplicate
                continue
            filtered_questions.append(question)
            if signature:
                seen_signatures.add(signature)
        questions = filtered_questions
        questions_by_id = {item["id"]: item for item in questions}

        # The model may omit a pending question after the user answered it.
        # Keep a closed copy so the round can be counted, while unmatched
        # questions continue through the normal open-question restoration.
        for previous_question in previous_questions:
            if previous_question["status"] != "open":
                continue
            if previous_question["id"] in questions_by_id:
                continue
            dimension = cls._canonical_grill_dimension(previous_question["dimension"])
            if dimension in answered_dimensions:
                closed = dict(previous_question)
                closed["dimension"] = dimension
                closed["status"] = "answered"
                questions.append(closed)
                questions_by_id[closed["id"]] = closed

        for question in questions:
            if question["status"] in {"answered", "skipped"} and question["dimension"]:
                dimension = cls._canonical_grill_dimension(question["dimension"])
                if dimension:
                    question["dimension"] = dimension
                    covered_by_dimension.setdefault(
                        dimension,
                        {"dimension": dimension, "evidence": question["text"]},
                    )
        covered = list(covered_by_dimension.values())

        # An open question is never implicitly removed by a model patch. The
        # model must semantically mark it answered or skipped first.
        for question_id, question in previous_open.items():
            current = questions_by_id.get(question_id)
            if current is None:
                restored = dict(question)
                restored["status"] = "open"
                questions.append(restored)
                questions_by_id[question_id] = restored

        if coalesced_open_question:
            filtered_duplicate_questions = True

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
            if filtered_duplicate_questions and not remaining_open and completed_rounds >= 2:
                # The model tried to start another round using only dimensions
                # that are already covered. Finish the project instead of
                # showing the same question group again.
                round_status = "project_completed"
                if isinstance(active_focus, dict):
                    active_focus["stage"] = "done"
                result["next_step_suggestion"] = "next"
                result["action"] = "advance"
                result["reply"] = "感谢补充，相关项目事实已经记录完整。本段经历已完成；如果还有其他经历，可以继续描述。"
            elif filtered_duplicate_questions and not remaining_open and completed_rounds < 2:
                # Do not manufacture a repeated question to satisfy the
                # minimum-round rule. Ask the model for an uncovered dimension
                # on the next turn while keeping the current round open.
                round_status = "round_completed"
                result["next_step_suggestion"] = "stay"
                result["action"] = "collect"
                result["reply"] = "这部分信息已记录，本轮已完成。请补充一个尚未提到的技术实现、个人决策或项目结果细节。"
            elif completed_rounds >= 3 and not remaining_open:
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

        # Do not expose the model's repeated wording after the state has been
        # coalesced. A short state-aware reply keeps the conversation moving
        # without asking the same question group again.
        if historical_duplicate_questions:
            if remaining_open:
                open_text = "\n".join(
                    f"{position}. {item['text']}"
                    for position, item in enumerate(remaining_open, start=1)
                )
                result["reply"] = f"已记录已回答的项目事实。请继续补充尚未确认的内容：\n{open_text}"
            elif result.get("action") == "advance" or round_status == "project_completed":
                result["reply"] = "感谢补充，相关项目事实已经记录完整。本段经历已完成；如果还有其他经历，可以继续描述。"
            else:
                result["reply"] = "这部分信息已记录，本轮已完成。请补充一个尚未提到的技术实现、个人决策或项目结果细节。"
        elif coalesced_question and not has_new_question:
            if result.get("action") == "advance" or round_status == "project_completed":
                result["reply"] = "感谢补充，相关项目事实已经记录完整。本段经历已完成；如果还有其他经历，可以继续描述。"
            elif remaining_open:
                result["reply"] = "已记录本轮信息，请继续补充尚未回答的项目事实。"

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

        if (
            result.get("render_ready") is not True
            and result.get("action") not in {"confirm", "render_ready"}
        ):
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

        # The action and confirmed state are authoritative when a model omits
        # the redundant top-level boolean from an otherwise valid response.
        result["render_ready"] = True

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
            result["reply"] = "简历已确认。"
        else:
            result["reply"] = "Resume confirmed; opening the generator."
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
