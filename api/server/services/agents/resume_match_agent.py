"""Resume-to-JD matching agent."""

import json
import os
from copy import deepcopy
from typing import Any, Dict, Generator, List, Optional

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from server.services.agents.base_skill_agent import BaseSkillAgent
from utils.logger_handler import logger


class ResumeMatchAgent(BaseSkillAgent):
    SKILL_NAME = "resume-match"

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


