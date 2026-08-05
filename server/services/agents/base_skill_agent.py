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
 - Backend execution only, no UI wording imposed by the runtime.
 - The loaded Skill owns conversation semantics, progression, omissions,
   skips, revisions, confirmations, and reply style.
 - Preserve the model's valid semantic choices; do not infer intent from
   fixed keywords or repair state based on a hard-coded workflow.
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
 - Backend execution only, no UI wording imposed by the runtime.
 - The loaded Skill owns conversation semantics, progression, omissions,
   skips, revisions, confirmations, and reply style.
 - Preserve the model's valid semantic choices; do not infer intent from
   fixed keywords or repair state based on a hard-coded workflow.
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
