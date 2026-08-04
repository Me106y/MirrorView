from typing import Any, Dict, Optional

from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage

from server.config import Config
from server.factories.llm_factory import ModelFactory
from server.services.agents.cover_letter_agent import CoverLetterAgent
from server.services.agents.job_hunt_agent import JobHuntAgent
from server.services.agents.mock_interview_agent import MockInterviewAgent
from server.services.agents.resume_craft_agent import ResumeCraftAgent
from server.services.agents.resume_match_agent import ResumeMatchAgent
from server.services.resume_service import ResumeService
from utils.logger_handler import logger


class AIService:
    def __init__(self):
        self.resume_service = ResumeService()
        self._platform_llm_error: Optional[str] = None
        try:
            self.llm = self._build_platform_llm()
        except Exception as exc:
            # Keep serverless module import alive. The original configuration
            # error is raised when a request actually needs the model.
            self.llm = None
            self._platform_llm_error = str(exc)
            logger.error("Platform LLM initialization failed: %s", exc)
        self.resume_match_agent = ResumeMatchAgent(
            llm=self.llm,
            llm_error=self._platform_llm_error,
        )
        self.resume_craft_agent = ResumeCraftAgent(llm=self.llm, llm_error=self._platform_llm_error)
        self.cover_letter_agent = CoverLetterAgent(llm=self.llm, llm_error=self._platform_llm_error)
        self.job_hunt_agent = JobHuntAgent(llm=self.llm, llm_error=self._platform_llm_error)
        self.mock_interview_agent = MockInterviewAgent(llm=self.llm, llm_error=self._platform_llm_error)

    @staticmethod
    def _runtime_text(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    def _build_platform_llm(self):
        provider = (Config.PLATFORM_PROVIDER or "deepseek").strip().lower() or "deepseek"
        model_name = (Config.PLATFORM_MODEL or "").strip() or Config.DEEPSEEK_MODEL
        kwargs: Dict[str, Any] = {
            "temperature": 0.7,
            "max_retries": 0,
            "max_tokens": 8000,
            "timeout": 90,
        }

        if provider == "deepseek":
            kwargs["base_url"] = Config.DEEPSEEK_BASE_URL
            kwargs["api_key"] = Config.DEEPSEEK_API_KEY
        elif provider == "openai":
            kwargs["api_key"] = Config.OPENAI_API_KEY
        elif provider == "anthropic":
            kwargs["api_key"] = Config.ANTHROPIC_API_KEY

        return ModelFactory.get_model(provider, model_name, **kwargs)

    def _build_runtime_agent(
        self,
        runtime: Optional[Dict[str, Any]] = None,
        *,
        json_output: bool = True,
        feature: str = "resume_craft",
    ):
        agents = {
            "resume_match": getattr(self, "resume_match_agent", None),
            "resume_craft": getattr(self, "resume_craft_agent", None),
            "cover_letter": getattr(self, "cover_letter_agent", None),
            "job_hunt": getattr(self, "job_hunt_agent", None),
            "mock_interview": getattr(self, "mock_interview_agent", None),
        }
        if feature not in agents:
            raise ValueError(f"Unsupported CareerForge feature: {feature}")
        if not runtime:
            return agents[feature]

        mode = self._runtime_text(runtime.get("mode") or "platform").lower()
        provider = self._runtime_text(runtime.get("provider")).lower()
        model_name = self._runtime_text(runtime.get("model"))
        api_key = self._runtime_text(runtime.get("api_key"))
        base_url = self._runtime_text(runtime.get("base_url"))

        # Platform mode defaults to server-side configured provider/model,
        # but can be overridden by request runtime fields from web settings.
        if mode == "platform":
            default_provider = (Config.PLATFORM_PROVIDER or "deepseek").strip().lower() or "deepseek"
            default_model = (Config.PLATFORM_MODEL or "").strip() or Config.DEEPSEEK_MODEL
            requested_model = self._runtime_text(runtime.get("model"))
            provider = provider or default_provider
            model_name = requested_model or default_model
            has_override = bool(
                api_key
                or base_url
                or (provider != default_provider)
                or (requested_model and requested_model != default_model)
            )
            if not has_override:
                if agents[feature] is None:
                    raise RuntimeError("Feature agent is not initialized")
                return agents[feature]
        else:
            # Backward compatibility for legacy BYOK path.
            provider = provider or "deepseek"
            model_name = model_name or Config.DEEPSEEK_MODEL

        kwargs: Dict[str, Any] = {
            "temperature": 0.2,
            # Chat state and generated resume HTML both need room for structured output.
            "max_tokens": 8000,
            "streaming": False,
            "timeout": 90,
            "max_retries": 0,
        }

        if provider == "deepseek":
            kwargs["api_key"] = api_key or Config.DEEPSEEK_API_KEY
            kwargs["base_url"] = base_url or Config.DEEPSEEK_BASE_URL
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
            if json_output:
                kwargs["response_format"] = {"type": "json_object"}
        elif provider == "openai":
            kwargs["api_key"] = api_key or Config.OPENAI_API_KEY
            if base_url:
                kwargs["base_url"] = base_url
        elif provider == "anthropic":
            kwargs["api_key"] = api_key or Config.ANTHROPIC_API_KEY
            if base_url:
                kwargs["base_url"] = base_url
        else:
            provider = "deepseek"
            kwargs["api_key"] = api_key or Config.DEEPSEEK_API_KEY
            kwargs["base_url"] = base_url or Config.DEEPSEEK_BASE_URL

        llm = ModelFactory.get_model(provider, model_name, **kwargs)
        agent_type = {
            "resume_match": ResumeMatchAgent,
            "resume_craft": ResumeCraftAgent,
            "cover_letter": CoverLetterAgent,
            "job_hunt": JobHuntAgent,
            "mock_interview": MockInterviewAgent,
        }[feature]
        return agent_type(llm=llm)

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

    def test_runtime_connection(self, runtime: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not isinstance(runtime, dict):
            raise RuntimeError("缺少运行时配置。")
        runtime_api_key = self._runtime_text(runtime.get("api_key"))
        if not runtime_api_key:
            raise RuntimeError("请先填写 API Key。")

        provider = self._runtime_text(runtime.get("provider") or Config.PLATFORM_PROVIDER or "deepseek").lower() or "deepseek"
        model_name = self._runtime_text(runtime.get("model") or Config.PLATFORM_MODEL or Config.DEEPSEEK_MODEL)
        base_url = self._runtime_text(runtime.get("base_url"))

        try:
            agent = self._build_runtime_agent(runtime, feature="resume_craft")
            llm = agent.llm
            if llm is None:
                raise RuntimeError(agent.llm_error or "模型初始化失败。")
            _ = llm.invoke([HumanMessage(content='Return a minimal json object like {"ok": true}.')])
            return {
                "ok": True,
                "provider": provider,
                "model": model_name,
                "base_url": base_url,
            }
        except Exception as e:
            raise RuntimeError(str(e) or "模型连通性校验失败。") from e

    def run_resume_match(self, payload, runtime: Optional[Dict[str, Any]] = None):
        runtime_api_key = self._runtime_text((runtime or {}).get("api_key"))
        if not runtime_api_key:
            raise RuntimeError("resume-match 仅支持使用用户提供的 API Key 运行。")

        try:
            agent = self._build_runtime_agent(runtime, feature="resume_match")
            result = agent.run_resume_match(payload)

            if isinstance(result, dict) and result.get("error"):
                error_code = str(result.get("error") or "resume_match_failed").strip()
                error_message = str(result.get("message") or error_code or "模型调用失败").strip()
                raise RuntimeError(f"{error_code}: {error_message}")
            if not isinstance(result, dict):
                raise RuntimeError("模型未返回有效 JSON 对象。")

            return result
        except Exception as e:
            raise RuntimeError(f"分析请求失败: {str(e)}") from e

    def run_resume_craft_chat_turn(self, payload, runtime: Optional[Dict[str, Any]] = None):
        return self._build_runtime_agent(runtime, feature="resume_craft").run_resume_craft_chat_turn(payload)

    def run_resume_craft_html(self, payload, runtime: Optional[Dict[str, Any]] = None):
        return self._build_runtime_agent(runtime, json_output=False, feature="resume_craft").run_resume_craft_html(payload)

    def run_cover_letter(self, payload, runtime: Optional[Dict[str, Any]] = None):
        try:
            return self._build_runtime_agent(runtime, feature="cover_letter").run_cover_letter(payload)
        except Exception as e:
            logger.error("run_cover_letter runtime error: %s", e)
            return {
                "error": "runtime_call_failed",
                "message": "Model runtime call failed.",
            }

    def run_job_hunt(self, payload, runtime: Optional[Dict[str, Any]] = None):
        try:
            return self._build_runtime_agent(runtime, feature="job_hunt").run_job_hunt(payload)
        except Exception as e:
            logger.error("run_job_hunt runtime error: %s", e)
            return {
                "error": "runtime_call_failed",
                "message": "Model runtime call failed.",
            }

    def generate_mock_interview_opening(self, job_position, resume_summary="", language="zh"):
        return self.mock_interview_agent.generate_mock_interview_opening(
            job_position,
            resume_summary,
            language=language,
        )

    def chat_response(self, messages_list, user_input, job_position="General", language="zh"):
        normalized_language = self._normalize_language(language)
        try:
            return self.mock_interview_agent.build_mock_interview_reply(
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
            for chunk in self.mock_interview_agent.stream_mock_interview_reply(
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
