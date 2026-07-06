import json
from typing import Any, Dict, Optional

from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from server.config import Config
from server.factories.llm_factory import ModelFactory
from server.services.careerforge_agent import CareerForgeAgent
from server.services.resume_service import ResumeService
from utils.logger_handler import logger


class AIService:
    def __init__(self):
        self.resume_service = ResumeService()
        self.llm = self._build_platform_llm()
        if self.llm is None:
            logger.warning("Platform LLM unavailable at startup; running in degraded mode.")
        self.careerforge_agent = CareerForgeAgent(llm=self.llm)

    @staticmethod
    def _runtime_text(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    def _build_platform_llm(self):
        provider = (Config.PLATFORM_PROVIDER or "deepseek").strip().lower() or "deepseek"
        model_name = (Config.PLATFORM_MODEL or "").strip() or Config.DEEPSEEK_MODEL
        kwargs: Dict[str, Any] = {"temperature": 0.7}

        if provider == "deepseek":
            kwargs["base_url"] = Config.DEEPSEEK_BASE_URL
            kwargs["api_key"] = Config.DEEPSEEK_API_KEY
        elif provider == "openai":
            kwargs["api_key"] = Config.OPENAI_API_KEY
        elif provider == "anthropic":
            kwargs["api_key"] = Config.ANTHROPIC_API_KEY

        try:
            return ModelFactory.get_model(provider, model_name, **kwargs)
        except Exception as e:
            logger.warning("Platform model init fallback to deepseek: %s", e)
            try:
                return ModelFactory.get_model(
                    "deepseek",
                    Config.DEEPSEEK_MODEL,
                    temperature=0.7,
                    base_url=Config.DEEPSEEK_BASE_URL,
                    api_key=Config.DEEPSEEK_API_KEY,
                )
            except Exception as fallback_e:
                logger.warning("Platform deepseek fallback init failed: %s", fallback_e)
                return None

    def _build_runtime_agent(self, runtime: Optional[Dict[str, Any]] = None) -> CareerForgeAgent:
        if not runtime:
            return self.careerforge_agent

        mode = self._runtime_text(runtime.get("mode") or "platform").lower()
        if mode != "byok":
            return self.careerforge_agent

        provider = self._runtime_text(runtime.get("provider")).lower()
        model_name = self._runtime_text(runtime.get("model"))
        api_key = self._runtime_text(runtime.get("api_key"))
        base_url = self._runtime_text(runtime.get("base_url"))

        kwargs: Dict[str, Any] = {
            "temperature": 0.35,
        }
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url

        llm = ModelFactory.get_model(provider, model_name, **kwargs)
        return CareerForgeAgent(llm=llm)

    @staticmethod
    def _normalize_language(language):
        lang = (language or "zh").strip().lower()
        if lang.startswith("en"):
            return "en"
        return "zh"

    def analyze_resume_and_update_job(self, user_id, resume_text, current_job_intention):
        """
        Analyze resume to extract job intention and key projects.
        Returns updated job intention and project summary.
        """
        if self.llm is None:
            return {"suggested_position": current_job_intention, "projects_summary": ""}

        prompt = ChatPromptTemplate.from_template(
            """
            You are an expert HR and Technical Interviewer.
            Analyze the following resume content and the user's stated job intention.

            User's stated intention: {current_job}

            Resume Content:
            {resume_text}

            Task:
            1. Determine the most suitable job position based on the resume and stated intention.
               If the resume strongly suggests a different specific role, suggest that, otherwise stick to the stated intention but refine it.
            2. Extract 2-3 key projects or experiences that are most relevant to this role.

            Output JSON format:
            {{
                "suggested_position": "string",
                "projects_summary": "string (concise summary of key projects)"
            }}
            """
        )

        chain = prompt | self.llm | JsonOutputParser()

        try:
            result = chain.invoke(
                {
                    "current_job": current_job_intention,
                    "resume_text": resume_text[:10000],
                }
            )
            return result
        except Exception as e:
            logger.error(f"Error analyzing resume: {e}")
            return {"suggested_position": current_job_intention, "projects_summary": ""}

    def generate_interview_questions(self, job_position, resume_text=None, projects_summary=None):
        """
        Generate 10 interview questions.
        If resume/projects provided, include 2 project-specific questions.
        """
        if self.llm is None:
            return [
                f"Tell me about yourself and why you want to be a {job_position}.",
                "What are your greatest strengths and weaknesses?",
                "Describe a challenging technical problem you solved.",
                "Where do you see yourself in 5 years?",
                "Why should we hire you?",
                "How do you handle conflict in a team?",
                "What is your preferred working style?",
                "Tell me about a time you failed.",
                "What technologies are you most proficient in?",
                "Do you have any questions for us?",
            ]

        if resume_text and projects_summary:
            template = """
            You are an expert Interviewer. Generate 10 interview questions for a {job_position} role.

            Candidate's Key Projects/Experience:
            {projects_summary}

            Requirements:
            1. Questions 1-8: General technical and behavioral questions relevant to {job_position}.
            2. Questions 9-10: Specific questions probing the candidate's projects/experience mentioned above.
            3. Questions should be challenging but fair.
            4. Output ONLY a JSON array of strings.

            Example:
            ["Question 1", "Question 2", ...]
            """
            input_vars = {"job_position": job_position, "projects_summary": projects_summary}
        else:
            template = """
            You are an expert Interviewer. Generate 10 interview questions for a {job_position} role.

            Requirements:
            1. Mix of technical and behavioral questions.
            2. Output ONLY a JSON array of strings.

            Example:
            ["Question 1", "Question 2", ...]
            """
            input_vars = {"job_position": job_position}

        prompt = ChatPromptTemplate.from_template(template)
        chain = prompt | self.llm | JsonOutputParser()

        try:
            questions = chain.invoke(input_vars)
            return [str(q) for q in questions]
        except Exception as e:
            logger.error(f"Error generating questions: {e}")
            return [
                f"Tell me about yourself and why you want to be a {job_position}.",
                "What are your greatest strengths and weaknesses?",
                "Describe a challenging technical problem you solved.",
                "Where do you see yourself in 5 years?",
                "Why should we hire you?",
                "How do you handle conflict in a team?",
                "What is your preferred working style?",
                "Tell me about a time you failed.",
                "What technologies are you most proficient in?",
                "Do you have any questions for us?",
            ]

    def evaluate_answer(self, question, answer, user_id=None):
        """
        Evaluate user's answer. Use RAG if user_id is provided (to access resume context).
        """
        if self.llm is None:
            return {
                "score": 5.0,
                "feedback": "Could not evaluate answer because model is not configured.",
                "improved_answer_suggestion": "",
            }

        context = ""
        if user_id:
            try:
                vectorstore = self.resume_service.get_vector_store(user_id)
                docs = vectorstore.similarity_search(question + " " + answer, k=2)
                context = "\n".join([d.page_content for d in docs])
            except Exception as e:
                logger.warning(f"RAG lookup failed: {e}")

        prompt = ChatPromptTemplate.from_template(
            """
            You are an expert Interviewer evaluating a candidate's answer.

            Question: {question}
            Candidate's Answer: {answer}

            Context from Resume (if any):
            {context}

            Task:
            Evaluate the answer. Consider if it matches their resume context (if provided).
            Provide a dynamic score (0-10) based on the quality, depth, and relevance of the answer.
            - 9-10: Excellent, deep understanding, relevant examples.
            - 7-8: Good, covers basics, some examples.
            - 5-6: Average, correct but shallow.
            - 3-4: Below average, missed key points.
            - 0-2: Poor or irrelevant.

            Give a brief constructive feedback and a score.

            Output JSON:
            {{
                "score": float,
                "feedback": "string",
                "improved_answer_suggestion": "string"
            }}
            """
        )

        chain = prompt | self.llm | JsonOutputParser()

        try:
            return chain.invoke({"question": question, "answer": answer, "context": context})
        except Exception as e:
            logger.error(f"Error evaluating answer: {e}")
            return {
                "score": 5.0,
                "feedback": "Could not evaluate answer due to error.",
                "improved_answer_suggestion": "",
            }

    def generate_feedback(self, interview, language="zh"):
        """
        Generate overall feedback for the interview.
        """
        from server.models import Message

        normalized_language = self._normalize_language(language)
        if self.llm is None:
            if normalized_language == "en":
                return "Feedback generation is unavailable because model runtime is not configured."
            return "当前未配置可用模型，暂时无法生成面试反馈。"

        output_language = "English" if normalized_language == "en" else "Chinese"
        messages = Message.query.filter_by(interview_id=interview.id).order_by(Message.created_at).all()
        conversation = "\n".join([f"{m.role}: {m.content}" for m in messages])

        prompt = ChatPromptTemplate.from_template(
            """
            You are an expert Interview Coach.
            Review the following interview transcript for a {job_position} role.

            Transcript:
            {conversation}

            Task:
            Provide a comprehensive summary and feedback in a single, well-structured paragraph or a few paragraphs.
            Include an overall score (0-100), key strengths, areas for improvement, and a final verdict (Hire/No Hire).
            IMPORTANT: Write the response strictly in {output_language}.
            Do NOT return JSON. Return plain text only.

            Format:
            Start with the score and verdict, then provide the detailed feedback.
            """
        )

        chain = prompt | self.llm | StrOutputParser()

        try:
            return chain.invoke(
                {
                    "job_position": interview.job_position,
                    "conversation": conversation,
                    "output_language": output_language,
                }
            )
        except Exception as e:
            logger.error(f"Error generating feedback: {e}")
            if normalized_language == "en":
                return "Could not generate feedback due to an error."
            return "生成面试反馈时出现异常，请稍后重试。"

    def run_resume_match(self, payload, runtime: Optional[Dict[str, Any]] = None):
        try:
            return self._build_runtime_agent(runtime).run_resume_match(payload)
        except Exception as e:
            logger.error("run_resume_match runtime error: %s", e)
            return {
                "error": "runtime_call_failed",
                "message": "Model runtime call failed.",
            }

    def run_resume_craft(self, payload, runtime: Optional[Dict[str, Any]] = None):
        try:
            return self._build_runtime_agent(runtime).run_resume_craft(payload)
        except Exception as e:
            logger.error("run_resume_craft runtime error: %s", e)
            return {
                "error": "runtime_call_failed",
                "message": "Model runtime call failed.",
            }

    def run_cover_letter(self, payload, runtime: Optional[Dict[str, Any]] = None):
        try:
            return self._build_runtime_agent(runtime).run_cover_letter(payload)
        except Exception as e:
            logger.error("run_cover_letter runtime error: %s", e)
            return {
                "error": "runtime_call_failed",
                "message": "Model runtime call failed.",
            }

    def run_job_hunt(self, payload, runtime: Optional[Dict[str, Any]] = None):
        try:
            return self._build_runtime_agent(runtime).run_job_hunt(payload)
        except Exception as e:
            logger.error("run_job_hunt runtime error: %s", e)
            return {
                "error": "runtime_call_failed",
                "message": "Model runtime call failed.",
            }

    def generate_mock_interview_opening(self, job_position, resume_summary="", language="zh"):
        return self.careerforge_agent.generate_mock_interview_opening(
            job_position,
            resume_summary,
            language=language,
        )

    def chat_response(self, messages_list, user_input, job_position="General", language="zh"):
        normalized_language = self._normalize_language(language)
        try:
            return self.careerforge_agent.build_mock_interview_reply(
                messages_list=messages_list,
                user_input=user_input,
                job_position=job_position,
                language=normalized_language,
            )
        except Exception as e:
            logger.error(f"Error generating chat response: {e}")
            if normalized_language == "en":
                return "Got it. Let's move on: how would you prove you're a strong fit for this role?"
            return "收到，我们继续下一题：您如何证明自己能胜任这个岗位？"

    def chat_response_stream(self, messages_list, user_input, job_position="General", language="zh"):
        """
        Interview streaming response now uses CareerForge mock-interview skill runtime.
        """
        normalized_language = self._normalize_language(language)
        try:
            for chunk in self.careerforge_agent.stream_mock_interview_reply(
                messages_list=messages_list,
                user_input=user_input,
                job_position=job_position,
                language=normalized_language,
            ):
                yield chunk
        except Exception as e:
            logger.error(f"Error generating chat response stream: {e}")
            if normalized_language == "en":
                yield "I hit a temporary issue. Let's continue: tell me about your most representative project."
            else:
                yield "我遇到了一点问题，我们继续：请您讲一个最有代表性的项目经历。"
