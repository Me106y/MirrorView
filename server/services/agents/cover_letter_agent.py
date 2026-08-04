"""Cover letter generation agent."""

import json
import os
from copy import deepcopy
from typing import Any, Dict, Generator, List, Optional

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from server.services.agents.base_skill_agent import BaseSkillAgent
from utils.logger_handler import logger


class CoverLetterAgent(BaseSkillAgent):
    SKILL_NAME = "cover-letter"

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


