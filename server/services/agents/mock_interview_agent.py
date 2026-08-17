"""Mock interview runtime agent."""

import os
from datetime import datetime
from html import escape
from typing import Any, Dict, Generator, List

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from server.services.agents.base_skill_agent import BaseSkillAgent
from utils.logger_handler import logger


REPORT_DIMENSIONS = [
    ("professional", "专业能力", "Professional Skill"),
    ("communication", "沟通表达", "Communication"),
    ("logic", "逻辑思维", "Logical Thinking"),
    ("adaptability", "应变能力", "Adaptability"),
    ("culture", "文化匹配", "Culture Fit"),
    ("growth", "成长潜力", "Growth Potential"),
]

ROUND_LABELS = {
    "full": [
        ("hr", "HR 面试", "HR Interview"),
        ("business", "业务主管面试", "Hiring Manager Interview"),
        ("executive", "终面 / 高管面试", "Executive Interview"),
    ],
    "hr": [("hr", "HR 面试", "HR Interview")],
    "business": [("business", "业务主管面试", "Hiring Manager Interview")],
    "executive": [("executive", "终面 / 高管面试", "Executive Interview")],
    "focused": [("focused", "专项训练", "Focused Practice")],
}


class MockInterviewAgent(BaseSkillAgent):
    SKILL_NAME = "mock-interview"

    def _history_messages(self, messages_list: List[dict]) -> List[Any]:
        history_msgs = []
        for msg in messages_list:
            role = str(msg.get("role") or "").strip().lower()
            content = str(msg.get("content") or "")
            if not content:
                continue
            if role == "user":
                history_msgs.append(HumanMessage(content=content))
            elif role in {"assistant", "agent"}:
                history_msgs.append(AIMessage(content=content))
        return history_msgs

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
        history_msgs = self._history_messages(messages_list)

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
        history_msgs = self._history_messages(messages_list)

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

    def generate_mock_interview_report(self, setup: Dict[str, Any], history: List[Dict[str, Any]]) -> Dict[str, Any]:
        normalized_language = self._normalize_language(str(setup.get("language") or "zh"))
        trimmed_history = []
        for item in history or []:
            role = str(item.get("role") or "").strip().lower()
            content = str(item.get("content") or "").strip()
            if role not in {"user", "assistant", "agent"} or not content:
                continue
            trimmed_history.append({"role": "assistant" if role == "agent" else role, "content": content[:4000]})

        scope = str(setup.get("scope") or "full").strip().lower() or "full"
        focus_topic = str(setup.get("focusTopic") or "").strip()
        rounds = ROUND_LABELS.get(scope, ROUND_LABELS["full"])
        schema = {
            "candidateName": "string",
            "targetRole": "string",
            "companyName": "string",
            "language": "zh or en",
            "scope": "full or hr or business or executive or focused",
            "overallScore": 0,
            "hireRecommendation": "string",
            "summary": "string",
            "dimensions": [
                {
                    "key": "string",
                    "label": "string",
                    "score": 0,
                    "comment": "string",
                }
            ],
            "rounds": [
                {
                    "key": "string",
                    "label": "string",
                    "score": 0,
                    "status": "completed or partial or not_started",
                    "summary": "string",
                    "questions": [
                        {
                            "question": "string",
                            "answerSummary": "string",
                            "score": 0,
                            "strength": "string",
                            "gap": "string",
                            "suggestion": "string",
                            "sampleAnswer": "string",
                        }
                    ],
                }
            ],
            "questionBank": [
                {
                    "round": "string",
                    "question": "string",
                    "focus": "string",
                    "score": 0,
                }
            ],
            "actionItems": [
                {
                    "title": "string",
                    "priority": "high or medium or low",
                    "details": "string",
                }
            ],
        }
        payload = {
            "task": "generate_mock_interview_report",
            "setup": {
                "targetRole": str(setup.get("targetRole") or "").strip(),
                "jdText": str(setup.get("jdText") or "").strip()[:12000],
                "resumeText": str(setup.get("resumeText") or "").strip()[:12000],
                "companyName": str(setup.get("companyName") or "").strip(),
                "language": normalized_language,
                "scope": scope,
                "focusTopic": focus_topic,
                "expectedRounds": [{"key": key, "label": zh if normalized_language == "zh" else en} for key, zh, en in rounds],
            },
            "history": trimmed_history,
            "requirements": {
                "scoreBands": {
                    "excellent": "9-10 or 90+",
                    "good": "7-8 or 70-89",
                    "average": "5-6 or 50-69",
                    "weak": "0-4 or below 50",
                },
                "needHtmlReadyContent": True,
                "focusTopic": focus_topic,
            },
        }

        result = self._invoke_json_skill("mock-interview", payload, schema)
        if not isinstance(result, dict) or result.get("error"):
            return self._fallback_report(setup, trimmed_history, normalized_language)

        report = self._normalize_report(result, setup, trimmed_history, normalized_language)
        if not report.get("dimensions") or not report.get("rounds"):
            return self._fallback_report(setup, trimmed_history, normalized_language)
        return report

    def _normalize_report(
        self,
        result: Dict[str, Any],
        setup: Dict[str, Any],
        history: List[Dict[str, Any]],
        language: str,
    ) -> Dict[str, Any]:
        scope = str(result.get("scope") or setup.get("scope") or "full").strip().lower() or "full"
        dimensions = []
        for key, zh_label, en_label in REPORT_DIMENSIONS:
            label = zh_label if language == "zh" else en_label
            matched = None
            for item in result.get("dimensions") or []:
                if str(item.get("key") or "").strip().lower() == key:
                    matched = item
                    break
                if str(item.get("label") or "").strip() in {zh_label, en_label}:
                    matched = item
                    break
            dimensions.append(
                {
                    "key": key,
                    "label": str((matched or {}).get("label") or label),
                    "score": _safe_score((matched or {}).get("score"), default=6),
                    "comment": str((matched or {}).get("comment") or _default_dimension_comment(label, language)),
                }
            )

        normalized_rounds = []
        result_rounds = result.get("rounds") or []
        expected_rounds = ROUND_LABELS.get(scope, ROUND_LABELS["full"])
        for index, (key, zh_label, en_label) in enumerate(expected_rounds):
            label = zh_label if language == "zh" else en_label
            source = result_rounds[index] if index < len(result_rounds) and isinstance(result_rounds[index], dict) else {}
            question_items = []
            for question in source.get("questions") or []:
                if not isinstance(question, dict):
                    continue
                question_items.append(
                    {
                        "question": str(question.get("question") or ("未命名问题" if language == "zh" else "Untitled question")),
                        "answerSummary": str(question.get("answerSummary") or _default_answer_summary(language)),
                        "score": _safe_score(question.get("score"), default=6),
                        "strength": str(question.get("strength") or _default_strength(language)),
                        "gap": str(question.get("gap") or _default_gap(language)),
                        "suggestion": str(question.get("suggestion") or _default_suggestion(language)),
                        "sampleAnswer": str(question.get("sampleAnswer") or _default_sample_answer(language)),
                    }
                )
            normalized_rounds.append(
                {
                    "key": str(source.get("key") or key),
                    "label": str(source.get("label") or label),
                    "score": _safe_score(source.get("score"), default=6),
                    "status": _normalize_round_status(source.get("status"), completed=bool(question_items)),
                    "summary": str(source.get("summary") or _default_round_summary(label, language, bool(question_items))),
                    "questions": question_items,
                }
            )

        question_bank = []
        for item in result.get("questionBank") or []:
            if not isinstance(item, dict):
                continue
            question_bank.append(
                {
                    "round": str(item.get("round") or "-"),
                    "question": str(item.get("question") or "-"),
                    "focus": str(item.get("focus") or ("综合考察" if language == "zh" else "General assessment")),
                    "score": _safe_score(item.get("score"), default=6),
                }
            )
        if not question_bank:
            question_bank = _build_question_bank_from_history(normalized_rounds, language)

        action_items = []
        for item in result.get("actionItems") or []:
            if not isinstance(item, dict):
                continue
            action_items.append(
                {
                    "title": str(item.get("title") or ("重点改进项" if language == "zh" else "Improvement focus")),
                    "priority": _normalize_priority(item.get("priority")),
                    "details": str(item.get("details") or _default_action_detail(language)),
                }
            )
        if not action_items:
            action_items = _default_action_items(language)

        report = {
            "candidateName": str(result.get("candidateName") or ("候选人" if language == "zh" else "Candidate")),
            "targetRole": str(result.get("targetRole") or setup.get("targetRole") or "General"),
            "companyName": str(result.get("companyName") or setup.get("companyName") or ""),
            "language": language,
            "scope": scope,
            "overallScore": _safe_score(result.get("overallScore"), default=_average_score(dimensions, 71)),
            "hireRecommendation": str(result.get("hireRecommendation") or _default_recommendation(language, dimensions)),
            "summary": str(result.get("summary") or _default_report_summary(language, setup, history)),
            "dimensions": dimensions,
            "rounds": normalized_rounds,
            "questionBank": question_bank,
            "actionItems": action_items,
        }
        report["htmlReport"] = build_mock_interview_html_report(report)
        return report

    def _fallback_report(self, setup: Dict[str, Any], history: List[Dict[str, Any]], language: str) -> Dict[str, Any]:
        scope = str(setup.get("scope") or "full").strip().lower() or "full"
        rounds = []
        expected_rounds = ROUND_LABELS.get(scope, ROUND_LABELS["full"])
        qa_pairs = _extract_qa_pairs(history)
        cursor = 0
        for index, (key, zh_label, en_label) in enumerate(expected_rounds):
            label = zh_label if language == "zh" else en_label
            pair_count = 2 if index < len(expected_rounds) - 1 else max(len(qa_pairs) - cursor, 1)
            chunk = qa_pairs[cursor: cursor + pair_count]
            cursor += pair_count
            questions = []
            for pair in chunk:
                question_text = pair.get("question") or ("请做一个简短的自我介绍。" if language == "zh" else "Please give a brief self introduction.")
                answer_summary = pair.get("answer") or _default_answer_summary(language)
                score = _score_from_answer(answer_summary)
                questions.append(
                    {
                        "question": question_text,
                        "answerSummary": answer_summary[:240],
                        "score": score,
                        "strength": _strength_from_answer(answer_summary, language),
                        "gap": _gap_from_answer(answer_summary, language),
                        "suggestion": _suggestion_from_answer(answer_summary, language),
                        "sampleAnswer": _sample_answer_from_question(question_text, setup, language),
                    }
                )
            rounds.append(
                {
                    "key": key,
                    "label": label,
                    "score": _average_score([{"score": item["score"]} for item in questions], 6),
                    "status": "completed" if questions else "not_started",
                    "summary": _default_round_summary(label, language, bool(questions)),
                    "questions": questions,
                }
            )

        dimensions = _fallback_dimensions_from_rounds(rounds, language)
        report = {
            "candidateName": "候选人" if language == "zh" else "Candidate",
            "targetRole": str(setup.get("targetRole") or "General"),
            "companyName": str(setup.get("companyName") or ""),
            "language": language,
            "scope": scope,
            "overallScore": _average_score(dimensions, 71),
            "hireRecommendation": _default_recommendation(language, dimensions),
            "summary": _default_report_summary(language, setup, history),
            "dimensions": dimensions,
            "rounds": rounds,
            "questionBank": _build_question_bank_from_history(rounds, language),
            "actionItems": _default_action_items(language),
        }
        report["htmlReport"] = build_mock_interview_html_report(report)
        return report


def _safe_score(value: Any, default: int = 6) -> int:
    try:
        number = float(value)
    except Exception:
        return default
    if number <= 10:
        number = number * 10 if number <= 10 and number % 1 else number
        if number > 10:
            number = number / 10
    if number > 10:
        number = number / 10
    return max(1, min(10, round(number)))


def _average_score(items: List[Dict[str, Any]], fallback: int) -> int:
    scores = [int(item.get("score") or 0) for item in items if int(item.get("score") or 0) > 0]
    if not scores:
        return fallback
    return round(sum(scores) / len(scores) * 10 if max(scores) <= 10 else sum(scores) / len(scores)) if max(scores) <= 10 else round(sum(scores) / len(scores))


def _normalize_round_status(value: Any, completed: bool) -> str:
    status = str(value or "").strip().lower()
    if status in {"completed", "partial", "not_started"}:
        return status
    return "completed" if completed else "not_started"


def _normalize_priority(value: Any) -> str:
    priority = str(value or "").strip().lower()
    if priority in {"high", "medium", "low"}:
        return priority
    return "medium"


def _extract_qa_pairs(history: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    pairs: List[Dict[str, str]] = []
    current_question = ""
    for item in history:
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        if role == "assistant":
            current_question = content
        elif role == "user":
            pairs.append({"question": current_question, "answer": content})
            current_question = ""
    return pairs


def _fallback_dimensions_from_rounds(rounds: List[Dict[str, Any]], language: str) -> List[Dict[str, Any]]:
    round_scores = [int(round_item.get("score") or 6) for round_item in rounds if int(round_item.get("score") or 0) > 0]
    avg = round(sum(round_scores) / len(round_scores)) if round_scores else 7
    labels = REPORT_DIMENSIONS
    adjustments = [1, 0, 0, -1, 1, 0]
    dimensions = []
    for index, (key, zh_label, en_label) in enumerate(labels):
        score = max(4, min(9, avg + adjustments[index]))
        label = zh_label if language == "zh" else en_label
        dimensions.append(
            {
                "key": key,
                "label": label,
                "score": score,
                "comment": _default_dimension_comment(label, language),
            }
        )
    return dimensions


def _build_question_bank_from_history(rounds: List[Dict[str, Any]], language: str) -> List[Dict[str, Any]]:
    bank = []
    for round_item in rounds:
        for question in round_item.get("questions") or []:
            bank.append(
                {
                    "round": str(round_item.get("label") or "-"),
                    "question": str(question.get("question") or "-"),
                    "focus": "项目深挖与表达完整度" if language == "zh" else "Depth, clarity, and role fit",
                    "score": int(question.get("score") or 6),
                }
            )
    return bank


def _score_from_answer(answer: str) -> int:
    length = len(answer.strip())
    if length >= 180:
        return 8
    if length >= 100:
        return 7
    if length >= 45:
        return 6
    return 5


def _strength_from_answer(answer: str, language: str) -> str:
    if language == "en":
        return "The answer gives at least one concrete signal and shows willingness to respond directly."
    return "回答里至少给出了一个具体信息点，且愿意正面回应问题。"


def _gap_from_answer(answer: str, language: str) -> str:
    if language == "en":
        return "The answer still needs clearer structure, stronger metrics, and more explicit ownership."
    return "回答还需要更清晰的结构、更明确的数据支撑，以及更具体的个人贡献。"


def _suggestion_from_answer(answer: str, language: str) -> str:
    if language == "en":
        return "Rework the response with situation-task-action-result, and add one metric plus one decision you personally made."
    return "建议按情境、任务、行动、结果重组回答，并补上一项量化结果与一项您亲自做出的关键决策。"


def _sample_answer_from_question(question: str, setup: Dict[str, Any], language: str) -> str:
    role = str(setup.get("targetRole") or ("the role" if language == "en" else "目标岗位"))
    if language == "en":
        return f"I would answer this around the requirements of {role}, explain my own contribution, and finish with one measurable result that proves fit."
    return f"我会围绕 {role} 的核心要求来回答，先讲清楚自己的职责，再补上一个可量化的结果，证明我与岗位的匹配度。"


def _default_dimension_comment(label: str, language: str) -> str:
    if language == "en":
        return f"{label} shows a usable baseline, but still needs stronger evidence and sharper expression."
    return f"{label} 具备基础表现，但还需要更扎实的证据与更有力的表达。"


def _default_round_summary(label: str, language: str, has_content: bool) -> str:
    if language == "en":
        return f"{label} {'contains enough material for feedback' if has_content else 'was not completed in this session'}."
    return f"{label}{'已有足够内容可供复盘' if has_content else '在本次会话中尚未完整展开'}。"


def _default_answer_summary(language: str) -> str:
    return "该题暂未形成完整回答摘要。" if language == "zh" else "A complete answer summary is not available for this question yet."


def _default_strength(language: str) -> str:
    return "回答意图明确，能够围绕问题作答。" if language == "zh" else "The response stays on topic and shows a clear intent to answer."


def _default_gap(language: str) -> str:
    return "还缺少细节、数据和明确的个人贡献描述。" if language == "zh" else "It still lacks detail, metrics, and a clear statement of personal ownership."


def _default_suggestion(language: str) -> str:
    return "建议用更短的结论先行句开头，再补充具体例子和量化结果。" if language == "zh" else "Start with a shorter conclusion, then add one concrete example and one measurable result."


def _default_sample_answer(language: str) -> str:
    return "参考回答应结合您真实经历，突出职责、动作与结果。" if language == "zh" else "The sample answer should stay grounded in your real experience, with clear action and outcome."


def _default_action_detail(language: str) -> str:
    return "围绕真实项目补充数据、决策过程和复盘结论，再做一次计时练习。" if language == "zh" else "Add metrics, decision rationale, and retrospective detail from real projects, then rehearse it again under time pressure."


def _default_action_items(language: str) -> List[Dict[str, str]]:
    if language == "en":
        return [
            {"title": "Tighten STAR storytelling", "priority": "high", "details": "Rewrite your top 3 stories with a one-line result, one metric, and one explicit decision you made."},
            {"title": "Strengthen evidence", "priority": "medium", "details": "Prepare numbers for user impact, efficiency, or business outcome so each answer can land with proof."},
            {"title": "Practice pressure follow-ups", "priority": "medium", "details": "Rehearse short answers for motivation, gaps, trade-offs, and challenges without over-explaining."},
        ]
    return [
        {"title": "重做 STAR 讲法", "priority": "high", "details": "把最重要的 3 段经历改写成结果先行、含关键数据、含个人决策的回答版本。"},
        {"title": "补齐量化证据", "priority": "medium", "details": "为项目影响、效率提升或业务结果准备数字证据，避免只有定性表述。"},
        {"title": "专项练压力追问", "priority": "medium", "details": "针对动机、短板、取舍和失败经历准备更短更稳的回答，避免解释过长。"},
    ]


def _default_recommendation(language: str, dimensions: List[Dict[str, Any]]) -> str:
    avg = round(sum(int(item.get("score") or 6) for item in dimensions) / max(len(dimensions), 1))
    if language == "en":
        return "Recommended with reservations" if avg >= 7 else "Potential but needs stronger preparation"
    return "推荐录用（有条件）" if avg >= 7 else "待定，需要继续打磨"


def _default_report_summary(language: str, setup: Dict[str, Any], history: List[Dict[str, Any]]) -> str:
    role = str(setup.get("targetRole") or ("this role" if language == "en" else "该岗位"))
    answer_count = len([item for item in history if str(item.get("role") or "") == "user"])
    if language == "en":
        return f"This session collected {answer_count} candidate answers for the {role} interview. The current signal is promising, but the strongest gains will come from clearer structure, stronger metrics, and more explicit ownership in project stories."
    return f"本次 {role} 模拟面试共记录了 {answer_count} 次候选人回答。整体基础不错，但如果想显著提升通过率，最需要加强的是回答结构、量化证据，以及项目经历中的个人主导性表达。"


def _score_tier(score: int) -> str:
    if score >= 8:
        return "good"
    if score >= 6:
        return "mid"
    return "weak"


def build_mock_interview_html_report(report: Dict[str, Any]) -> str:
    language = str(report.get("language") or "zh")
    title = "模拟面试报告" if language == "zh" else "Mock Interview Report"
    subtitle = "三轮仿真面试 · 逐题反馈 · 个性化备考建议" if language == "zh" else "Three-stage interview simulation · detailed feedback · practice plan"
    company_name = str(report.get("companyName") or "")
    company_line = f" · {escape(company_name)}" if company_name else ""
    summary = escape(str(report.get("summary") or ""))
    recommendation = escape(str(report.get("hireRecommendation") or ""))
    candidate_name = escape(str(report.get("candidateName") or "候选人"))
    target_role = escape(str(report.get("targetRole") or "-"))
    report_date = datetime.utcnow().strftime("%Y-%m-%d")
    overall_score = max(1, min(100, int(report.get("overallScore") or 71)))
    ring_offset = round(339.292 - 339.292 * overall_score / 100, 3)

    dimensions_html = "".join(
        f"""
        <article class=\"dimension-card\">
          <div class=\"dimension-head\">
            <h3>{escape(str(item.get('label') or '-'))}</h3>
            <strong class=\"tier-{_score_tier(int(item.get('score') or 0))}\">{int(item.get('score') or 0)}/10</strong>
          </div>
          <div class=\"meter\"><span class=\"tier-{_score_tier(int(item.get('score') or 0))}\" style=\"width: {min(100, int(item.get('score') or 0) * 10)}%\"></span></div>
          <p>{escape(str(item.get('comment') or ''))}</p>
        </article>
        """
        for item in report.get("dimensions") or []
    )

    rounds_html = "".join(_render_round_html(round_item) for round_item in report.get("rounds") or [])
    question_bank_rows = "".join(
        f"<tr><td>{escape(str(item.get('round') or '-'))}</td><td>{escape(str(item.get('question') or '-'))}</td><td>{escape(str(item.get('focus') or '-'))}</td><td>{int(item.get('score') or 0)}/10</td></tr>"
        for item in report.get("questionBank") or []
    )
    action_items_html = "".join(
        f"""
        <article class=\"action-card\">
          <div class=\"action-index\">{index}</div>
          <div>
            <h3>{escape(str(item.get('title') or '-'))}</h3>
            <p>{escape(str(item.get('details') or ''))}</p>
          </div>
        </article>
        """
        for index, item in enumerate(report.get("actionItems") or [], start=1)
    )

    return f"""<!DOCTYPE html>
<html lang=\"{'zh-CN' if language == 'zh' else 'en'}\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{title}</title>
  <style>
    :root {{
      --ink: #1a1f2e;
      --ink-light: #4a5568;
      --ink-muted: #718096;
      --accent: #2d6b5f;
      --accent-light: #e8f4f0;
      --accent-warm: #d4a853;
      --blue: #3b82f6;
      --red: #ef4444;
      --green: #22c55e;
      --orange: #f59e0b;
      --bg: #f8f9fa;
      --card: #ffffff;
      --border: #e5e7eb;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: "Noto Sans SC", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif; background: var(--bg); color: var(--ink); }}
    .page {{ max-width: 860px; margin: 0 auto; padding: 28px 20px 56px; }}
    .hero {{ background: linear-gradient(145deg, #1a1f2e 0%, #2d3748 100%); color: #fff; border-radius: 16px 16px 0 0; padding: 30px 30px 26px; }}
    .hero-badge {{ display: inline-flex; align-items: center; min-height: 34px; padding: 0 14px; border-radius: 999px; border: 1px solid rgba(255,255,255,0.14); color: rgba(255,255,255,0.88); font-size: 12px; letter-spacing: .08em; text-transform: uppercase; }}
    .hero h1 {{ margin: 18px 0 10px; font-family: "Noto Serif SC", Georgia, serif; font-size: 40px; line-height: 1.12; }}
    .hero p {{ margin: 0; color: rgba(255,255,255,0.76); line-height: 1.7; }}
    .hero-meta {{ display: flex; flex-wrap: wrap; gap: 18px; margin-top: 18px; color: rgba(255,255,255,0.86); font-size: 14px; }}
    .sheet {{ background: var(--card); border: 1px solid var(--border); border-top: 0; border-radius: 0 0 16px 16px; overflow: hidden; }}
    .section {{ padding: 30px; border-top: 1px solid var(--border); }}
    .section:first-child {{ border-top: 0; }}
    .section-title {{ display: flex; align-items: center; gap: 12px; margin: 0 0 18px; font-family: "Noto Serif SC", Georgia, serif; font-size: 28px; }}
    .section-title::before {{ content: \"\"; width: 4px; height: 28px; border-radius: 999px; background: var(--accent); }}
    .score-summary {{ display: grid; grid-template-columns: 150px minmax(0, 1fr); gap: 26px; align-items: center; }}
    .score-ring {{ width: 140px; height: 140px; position: relative; margin: 0 auto; }}
    .score-ring svg {{ width: 100%; height: 100%; transform: rotate(-90deg); }}
    .score-ring-value {{ position: absolute; inset: 0; display: grid; place-content: center; text-align: center; }}
    .score-ring-value strong {{ font-size: 42px; line-height: 1; }}
    .score-ring-value span {{ color: var(--ink-muted); font-size: 14px; }}
    .recommendation {{ display: inline-flex; align-items: center; min-height: 38px; padding: 0 14px; border-radius: 10px; background: var(--accent-light); color: var(--accent); font-weight: 700; }}
    .summary-text {{ margin: 14px 0 0; color: var(--ink-light); font-size: 16px; line-height: 1.8; }}
    .dimension-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }}
    .dimension-card {{ border-radius: 16px; border: 1px solid var(--border); background: var(--bg); padding: 18px; }}
    .dimension-head {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }}
    .dimension-head h3 {{ margin: 0; font-size: 18px; }}
    .dimension-head strong {{ font-size: 28px; line-height: 1; }}
    .tier-good {{ color: var(--green); }}
    .tier-mid {{ color: var(--orange); }}
    .tier-weak {{ color: var(--red); }}
    .meter {{ height: 8px; border-radius: 999px; background: #e4e7ec; overflow: hidden; }}
    .meter span {{ display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, currentColor, rgba(45, 107, 95, .7)); }}
    .dimension-card p {{ margin: 14px 0 0; color: var(--ink-light); line-height: 1.7; }}
    .round-card {{ border-radius: 16px; border: 1px solid var(--border); overflow: hidden; background: var(--card); margin-bottom: 18px; }}
    .round-head {{ display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 18px 22px; background: #fafbfc; border-bottom: 1px solid var(--border); }}
    .round-head h3 {{ margin: 0; font-size: 24px; }}
    .round-head p {{ margin: 6px 0 0; color: var(--ink-light); line-height: 1.7; }}
    .round-badge {{ display: inline-flex; align-items: center; min-height: 36px; padding: 0 14px; border-radius: 10px; background: #fff7e6; color: #b7791f; font-weight: 700; }}
    .question-card {{ padding: 22px; border-top: 1px solid var(--border); }}
    .question-index {{ width: 34px; height: 34px; border-radius: 999px; background: var(--accent); color: #fff; display: inline-grid; place-items: center; font-weight: 700; }}
    .question-title {{ margin: 14px 0 14px; font-size: 22px; line-height: 1.5; }}
    .question-summary {{ padding: 14px 16px; border-radius: 14px; background: #f3f7fb; color: var(--ink-light); line-height: 1.8; }}
    .feedback-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin-top: 14px; }}
    .feedback-box {{ border-radius: 14px; padding: 14px 16px; border: 1px solid var(--border); line-height: 1.75; }}
    .feedback-box strong {{ display: block; margin-bottom: 6px; }}
    .feedback-box.good {{ background: #f0fdf4; border-color: #bbf7d0; }}
    .feedback-box.weak {{ background: #fff1f2; border-color: #fecdd3; }}
    .feedback-box.info {{ background: #eff6ff; border-color: #bfdbfe; }}
    .sample-answer {{ margin-top: 14px; padding: 16px 18px; border-radius: 14px; background: #f7f7f7; border-left: 3px solid var(--accent); color: var(--ink-light); line-height: 1.85; }}
    table {{ width: 100%; border-collapse: collapse; border-spacing: 0; overflow: hidden; border-radius: 14px; }}
    thead {{ background: #f8fafc; }}
    th, td {{ padding: 14px 16px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: top; line-height: 1.7; }}
    th {{ color: var(--ink-muted); font-size: 14px; font-weight: 700; }}
    .action-card {{ display: grid; grid-template-columns: 48px minmax(0, 1fr); gap: 16px; padding: 18px; border-radius: 16px; border: 1px solid var(--border); background: #fafafa; margin-bottom: 14px; }}
    .action-index {{ width: 48px; height: 48px; display: grid; place-items: center; border-radius: 999px; background: var(--accent); color: #fff; font-size: 22px; font-weight: 700; }}
    .action-card h3 {{ margin: 0 0 8px; font-size: 22px; }}
    .action-card p {{ margin: 0; color: var(--ink-light); line-height: 1.8; }}
    @media (max-width: 760px) {{
      .hero h1 {{ font-size: 32px; }}
      .section {{ padding: 22px; }}
      .score-summary, .dimension-grid, .feedback-grid {{ grid-template-columns: 1fr; }}
      .hero-meta {{ gap: 12px; }}
    }}
  </style>
</head>
<body>
  <main class=\"page\">
    <header class=\"hero\">
      <span class=\"hero-badge\">Mock Interview Report</span>
      <h1>{title}</h1>
      <p>{subtitle}</p>
      <div class=\"hero-meta\">
        <span>候选人 {candidate_name}</span>
        <span>目标岗位 {target_role}</span>
        <span>面试语言 {'中文' if language == 'zh' else 'English'}</span>
        <span>日期 {report_date}{company_line}</span>
      </div>
    </header>
    <section class=\"sheet\">
      <section class=\"section\">
        <div class=\"score-summary\">
          <div class=\"score-ring\">
            <svg viewBox=\"0 0 120 120\" aria-hidden=\"true\">
              <circle cx=\"60\" cy=\"60\" r=\"54\" fill=\"none\" stroke=\"#e5e7eb\" stroke-width=\"8\"></circle>
              <circle cx=\"60\" cy=\"60\" r=\"54\" fill=\"none\" stroke=\"#2d6b5f\" stroke-width=\"8\" stroke-linecap=\"round\" stroke-dasharray=\"339.292\" stroke-dashoffset=\"{ring_offset}\"></circle>
            </svg>
            <div class=\"score-ring-value\"><strong>{overall_score}</strong><span>/ 100</span></div>
          </div>
          <div>
            <span class=\"recommendation\">{recommendation}</span>
            <p class=\"summary-text\">{summary}</p>
          </div>
        </div>
      </section>
      <section class=\"section\">
        <h2 class=\"section-title\">能力维度评分</h2>
        <div class=\"dimension-grid\">{dimensions_html}</div>
      </section>
      <section class=\"section\">
        <h2 class=\"section-title\">逐轮详细反馈</h2>
        {rounds_html}
      </section>
      <section class=\"section\">
        <h2 class=\"section-title\">面试题目合集</h2>
        <table>
          <thead><tr><th>轮次</th><th>题目</th><th>核心考察点</th><th>评分</th></tr></thead>
          <tbody>{question_bank_rows}</tbody>
        </table>
      </section>
      <section class=\"section\">
        <h2 class=\"section-title\">备考行动清单</h2>
        {action_items_html}
      </section>
    </section>
  </main>
</body>
</html>
"""


def _render_round_html(round_item: Dict[str, Any]) -> str:
    round_title = escape(str(round_item.get("label") or "-"))
    round_summary = escape(str(round_item.get("summary") or ""))
    round_score = int(round_item.get("score") or 0)
    questions_html = ""
    for index, question in enumerate(round_item.get("questions") or [], start=1):
        score = int(question.get("score") or 0)
        questions_html += f"""
        <article class=\"question-card\">
          <div class=\"question-index\">{index}</div>
          <h4 class=\"question-title\">{escape(str(question.get('question') or '-'))} <span class=\"round-badge\">{score}/10</span></h4>
          <div class=\"question-summary\">{escape(str(question.get('answerSummary') or ''))}</div>
          <div class=\"feedback-grid\">
            <section class=\"feedback-box good\"><strong>优点</strong>{escape(str(question.get('strength') or ''))}</section>
            <section class=\"feedback-box weak\"><strong>不足</strong>{escape(str(question.get('gap') or ''))}</section>
            <section class=\"feedback-box info\"><strong>建议</strong>{escape(str(question.get('suggestion') or ''))}</section>
            <section class=\"feedback-box\"><strong>评分</strong>{score}/10</section>
          </div>
          <div class=\"sample-answer\"><strong>参考回答</strong><br />{escape(str(question.get('sampleAnswer') or ''))}</div>
        </article>
        """
    return f"""
    <article class=\"round-card\">
      <header class=\"round-head\">
        <div>
          <h3>{round_title}</h3>
          <p>{round_summary}</p>
        </div>
        <span class=\"round-badge\">该轮 {round_score}/10</span>
      </header>
      {questions_html or '<article class="question-card"><div class="question-summary">该轮在本次会话中尚未进行。</div></article>'}
    </article>
    """
