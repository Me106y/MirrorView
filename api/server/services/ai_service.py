import json
import re
from collections import Counter
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
                return self.careerforge_agent
        else:
            # Backward compatibility for legacy BYOK path.
            provider = provider or "deepseek"
            model_name = model_name or Config.DEEPSEEK_MODEL

        kwargs: Dict[str, Any] = {"temperature": 0.35}

        if provider == "deepseek":
            kwargs["api_key"] = api_key or Config.DEEPSEEK_API_KEY
            kwargs["base_url"] = base_url or Config.DEEPSEEK_BASE_URL
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
        return CareerForgeAgent(llm=llm)

    @staticmethod
    def _normalize_language(language):
        lang = (language or "zh").strip().lower()
        if lang.startswith("en"):
            return "en"
        return "zh"

    @staticmethod
    def _tokenize_keywords(text: Any) -> list:
        raw = str(text or "")
        lowered = raw.lower()
        english = re.findall(r"[a-z][a-z0-9+._-]{1,}", lowered)
        chinese = re.findall(r"[\u4e00-\u9fff]{2,8}", raw)
        tokens = english + chinese
        stop = {
            "and",
            "the",
            "for",
            "with",
            "from",
            "that",
            "this",
            "you",
            "your",
            "will",
            "have",
            "are",
            "job",
            "岗位",
            "负责",
            "具有",
            "相关",
            "能力",
            "经验",
            "以及",
            "熟悉",
            "能够",
            "优先",
            "要求",
            "我们",
            "公司",
            "以上",
            "以下",
        }
        clean = []
        for token in tokens:
            t = token.strip().lower()
            if len(t) < 2 or t in stop:
                continue
            clean.append(t)
        return clean

    def _extract_top_keywords(self, text: Any, limit: int = 24) -> list:
        tokens = self._tokenize_keywords(text)
        if not tokens:
            return []
        counts = Counter(tokens)
        ranked = sorted(counts.items(), key=lambda item: (-item[1], -len(item[0]), item[0]))
        return [k for k, _ in ranked[:limit]]

    @staticmethod
    def _should_fallback_resume_match(result: Any) -> bool:
        if not isinstance(result, dict):
            return True
        if result.get("error"):
            return True

        assumptions = result.get("assumptions")
        if not isinstance(assumptions, list):
            return False
        markers = {
            "model_call_failed",
            "missing_api_key_or_model_init_failed",
            "model_output_not_json",
            "model_stream_failed",
        }
        return any(str(item).strip().lower() in markers for item in assumptions)

    @staticmethod
    def _extract_runtime_error_text(result: Any) -> str:
        if not isinstance(result, dict):
            return str(result or "")
        return str(result.get("error") or result.get("message") or result.get("assumptions") or "")

    @staticmethod
    def _looks_like_auth_failure(text: str) -> bool:
        lower = (text or "").lower()
        markers = (
            "authentication fails",
            "authentication_error",
            "invalid api key",
            "api key is invalid",
            "invalid_request_error",
            "unauthorized",
            "error code: 401",
            "401",
        )
        return any(marker in lower for marker in markers)

    @staticmethod
    def _normalize_fallback_reason(reason: str) -> str:
        lower = (reason or "").lower()
        if AIService._looks_like_auth_failure(lower):
            return "platform_model_auth_failed"
        if "timeout" in lower or "timed out" in lower:
            return "platform_model_timeout"
        if "llm_not_ready" in lower or "missing_api_key_or_model_init_failed" in lower:
            return "platform_model_not_ready"
        if "model_output_not_json" in lower:
            return "platform_model_non_json"
        if "model_call_failed" in lower:
            return "platform_model_call_failed"
        if "runtime_exception" in lower:
            return "platform_runtime_exception"
        return "platform_model_unavailable"

    @staticmethod
    def _can_retry_with_server_platform_key(runtime: Optional[Dict[str, Any]], reason: str) -> bool:
        if not isinstance(runtime, dict):
            return False
        mode = str(runtime.get("mode") or "platform").strip().lower()
        if mode != "platform":
            return False
        runtime_key = str(runtime.get("api_key") or "").strip()
        if not runtime_key:
            return False
        return AIService._looks_like_auth_failure(reason)

    @staticmethod
    def _runtime_without_api_key(runtime: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        clean = dict(runtime or {})
        clean["mode"] = "platform"
        clean["api_key"] = ""
        return clean

    @staticmethod
    def _extract_step4_runtime_error(decision: Any) -> str:
        if not isinstance(decision, dict):
            return str(decision or "")
        return str(
            decision.get("model_connection_error")
            or decision.get("error")
            or decision.get("message")
            or ""
        ).strip()

    def _fallback_resume_match(self, payload: Dict[str, Any], reason: str) -> Dict[str, Any]:
        resume_text = str(payload.get("resume_text") or "")
        jd_text = str(payload.get("jd_text") or "")
        target_role = str(payload.get("target_role") or "目标岗位").strip() or "目标岗位"

        resume_keywords = self._extract_top_keywords(resume_text, limit=36)
        jd_keywords = self._extract_top_keywords(jd_text, limit=36)
        role_keywords = self._extract_top_keywords(target_role, limit=8)

        resume_set = set(resume_keywords)
        overlap = [kw for kw in jd_keywords if kw in resume_set]
        missing = [kw for kw in jd_keywords if kw not in resume_set]
        role_hits = [kw for kw in role_keywords if kw in resume_set]

        skill_ratio = len(overlap) / max(1, len(jd_keywords))
        skill_score = int(round(45 + 55 * skill_ratio))
        role_score = 90 if role_hits else (68 if not role_keywords else 58)

        evidence_hits = re.findall(
            r"\d+(?:\.\d+)?[%万千kK]?|负责|主导|优化|提升|增长|上线|交付|落地|管理|协作",
            resume_text,
        )
        evidence_score = min(95, 54 + len(evidence_hits) * 4)
        expression_score = min(92, 58 + int(len(resume_text) / 220))
        overall = int(round(skill_score * 0.4 + role_score * 0.25 + evidence_score * 0.2 + expression_score * 0.15))
        overall = max(45, min(96, overall))

        if overall >= 82:
            match_level = "A"
        elif overall >= 63:
            match_level = "B"
        else:
            match_level = "C"

        critical_missing = missing[:8] or ["建议补充与 JD 直接对应的核心技能关键词"]
        advantages = overlap[:8] or resume_keywords[:6]

        summary = (
            f"当前为降级分析模式：你的简历与“{target_role}”存在 {len(overlap)} 项关键词重合，"
            f"整体匹配度评估为 {match_level}（{overall}/100）。优先补齐 JD 中未覆盖的高频关键词，可显著提升通过率。"
        )

        dimension_scores = [
            {
                "name": "岗位方向一致性",
                "score": role_score,
                "highlight": "简历内容与目标岗位关键词一致" if role_hits else "岗位方向可判断但关键词锚点不足",
                "gap": "目标岗位关键词在经历中出现偏少" if not role_hits else "可进一步强化岗位专属术语",
                "advice": "在最近两段经历中明确写出与目标岗位对应的职责与结果。",
            },
            {
                "name": "技能匹配度",
                "score": skill_score,
                "highlight": f"已覆盖 {len(overlap)} 项 JD 关键词",
                "gap": "部分 JD 高频要求未在简历中出现",
                "advice": "把缺失关键词映射到真实项目经历，按“场景-动作-结果”补充。",
            },
            {
                "name": "经历证据强度",
                "score": evidence_score,
                "highlight": "简历中存在可量化表达" if evidence_hits else "已有项目描述基础",
                "gap": "量化指标或业务结果仍可增强",
                "advice": "每段经历至少补 1 个量化结果（效率、成本、转化、时长等）。",
            },
            {
                "name": "表达清晰度",
                "score": expression_score,
                "highlight": "简历内容具备可读性",
                "gap": "结构层次仍可进一步聚焦到 JD 核心诉求",
                "advice": "将最相关项目前置，并把次要描述压缩为 1-2 行。",
            },
        ]

        optimization = [
            "优先补齐“关键缺口”中的前 3 个词，并绑定到真实项目成果。",
            "简历开头新增“目标岗位 + 3 项核心能力”摘要，提升首屏命中率。",
            "每段经历保留 1 条动作描述 + 1 条量化结果，减少泛化表述。",
        ]

        optimized_resume_markdown = "\n".join(
            [
                f"## 目标岗位",
                f"{target_role}",
                "",
                "## 核心匹配能力",
                *[f"- {kw}" for kw in (advantages[:5] or ["请补充与你目标岗位直接对应的技能关键词"])],
                "",
                "## 优先补齐关键词",
                *[f"- {kw}" for kw in critical_missing[:5]],
                "",
                "## 写作建议",
                "- 使用 STAR/项目成果格式：场景 -> 行动 -> 可量化结果。",
                "- 与 JD 关联较弱的内容放到靠后位置，核心匹配内容前置。",
            ]
        )

        normalized_reason = self._normalize_fallback_reason(reason)
        return {
            "overall_score": overall,
            "match_level": match_level,
            "summary": summary,
            "dimension_scores": dimension_scores,
            "critical_missing": critical_missing,
            "extra_advantages": advantages,
            "optimization_suggestions": optimization,
            "optimized_resume_markdown": optimized_resume_markdown,
            "assumptions": [
                "platform_model_unavailable_fallback_used",
                "keyword_based_heuristic_analysis",
                f"fallback_reason:{normalized_reason}",
            ],
        }

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
            result = self._build_runtime_agent(runtime).run_resume_match(payload)
            if self._should_fallback_resume_match(result):
                reason = self._extract_runtime_error_text(result)
                if self._can_retry_with_server_platform_key(runtime, reason):
                    try:
                        retry_runtime = self._runtime_without_api_key(runtime)
                        retried = self._build_runtime_agent(retry_runtime).run_resume_match(payload)
                        if not self._should_fallback_resume_match(retried):
                            return retried
                        reason = self._extract_runtime_error_text(retried) or reason
                    except Exception as retry_error:
                        logger.warning("run_resume_match platform retry failed: %s", retry_error)
                        reason = f"runtime_exception:{retry_error}"
                return self._fallback_resume_match(payload, reason or "resume_match_runtime_unavailable")
            return result
        except Exception as e:
            logger.error("run_resume_match runtime error: %s", e)
            return self._fallback_resume_match(payload, f"runtime_exception:{e}")

    def run_resume_craft(self, payload, runtime: Optional[Dict[str, Any]] = None):
        try:
            return self._build_runtime_agent(runtime).run_resume_craft(payload)
        except Exception as e:
            logger.error("run_resume_craft runtime error: %s", e)
            return {
                "error": "runtime_call_failed",
                "message": "Model runtime call failed.",
            }

    def run_resume_craft_dialog(self, payload, runtime: Optional[Dict[str, Any]] = None):
        try:
            return self._build_runtime_agent(runtime).run_resume_craft_dialog(payload)
        except Exception as e:
            logger.error("run_resume_craft_dialog runtime error: %s", e)
            return "简历助手暂时不可用，请稍后重试。"

    def run_resume_craft_step4_decision(self, payload, runtime: Optional[Dict[str, Any]] = None):
        try:
            decision = self._build_runtime_agent(runtime).run_resume_craft_step4_decision(payload)
            reason = self._extract_step4_runtime_error(decision)
            if self._can_retry_with_server_platform_key(runtime, reason):
                try:
                    retry_runtime = self._runtime_without_api_key(runtime)
                    retried = self._build_runtime_agent(retry_runtime).run_resume_craft_step4_decision(payload)
                    if bool(retried.get("model_connection_ok")):
                        return retried
                    retried_reason = self._extract_step4_runtime_error(retried)
                    if retried_reason and self._looks_like_auth_failure(reason):
                        return retried
                except Exception as retry_error:
                    logger.warning("run_resume_craft_step4_decision platform retry failed: %s", retry_error)
            return decision
        except Exception as e:
            logger.error("run_resume_craft_step4_decision runtime error: %s", e)
            fallback_builder = getattr(self.careerforge_agent, "_build_step4_heuristic_decision", None)
            if callable(fallback_builder):
                try:
                    decision = fallback_builder(payload if isinstance(payload, dict) else {})
                    if isinstance(decision, dict):
                        decision["model_connection_ok"] = False
                        decision["model_connection_error"] = str(e)
                        return decision
                except Exception as fallback_error:
                    logger.warning("run_resume_craft_step4_decision heuristic fallback failed: %s", fallback_error)
            return {
                "reply": str((payload or {}).get("fallback_reply") or "请继续补充这一段项目的关键信息。"),
                "resume_ready_draft": {"title": "项目经历", "role": "核心开发", "period": "时间待补", "bullets": []},
                "missing_points": ["请继续补充该项目里一个最关键的技术实现或功能细节。"],
                "current_experience_completed": False,
                "ask_more_experience": True,
                "reasoning_focus": [],
                "model_connection_ok": False,
                "model_connection_error": str(e),
            }

    def run_resume_craft_html(self, payload, runtime: Optional[Dict[str, Any]] = None):
        try:
            result = self._build_runtime_agent(runtime).run_resume_craft_html(payload)
            if str(result or "").strip():
                return result
            if isinstance(runtime, dict):
                mode = str(runtime.get("mode") or "platform").strip().lower()
                runtime_key = str(runtime.get("api_key") or "").strip()
                if mode == "platform" and runtime_key:
                    try:
                        retry_runtime = self._runtime_without_api_key(runtime)
                        retry_result = self._build_runtime_agent(retry_runtime).run_resume_craft_html(payload)
                        if str(retry_result or "").strip():
                            return retry_result
                    except Exception as retry_error:
                        logger.warning("run_resume_craft_html platform retry failed: %s", retry_error)
            return ""
        except Exception as e:
            logger.error("run_resume_craft_html runtime error: %s", e)
            if self._can_retry_with_server_platform_key(runtime, str(e)):
                try:
                    retry_runtime = self._runtime_without_api_key(runtime)
                    retry_result = self._build_runtime_agent(retry_runtime).run_resume_craft_html(payload)
                    if str(retry_result or "").strip():
                        return retry_result
                except Exception as retry_error:
                    logger.warning("run_resume_craft_html platform retry after exception failed: %s", retry_error)
            return ""

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
