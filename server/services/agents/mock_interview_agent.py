"""Mock interview conversation agent."""

import json
import os
from copy import deepcopy
from typing import Any, Dict, Generator, List, Optional

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from server.services.agents.base_skill_agent import BaseSkillAgent
from utils.logger_handler import logger


class MockInterviewAgent(BaseSkillAgent):
    SKILL_NAME = "mock-interview"

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

