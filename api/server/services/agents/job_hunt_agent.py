"""Job search and matching agent."""

import json
import os
from copy import deepcopy
from typing import Any, Dict, Generator, List, Optional

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from server.services.agents.base_skill_agent import BaseSkillAgent
from utils.logger_handler import logger


class JobHuntAgent(BaseSkillAgent):
    SKILL_NAME = "job-hunt"

    def run_job_hunt(self, payload: dict) -> dict:
        schema = {
            "summary": "string",
            "search_strategy": ["string"],
            "top_jobs": [
                {
                    "title": "string",
                    "company": "string",
                    "location": "string",
                    "salary": "string",
                    "match_level": "green|yellow|orange",
                    "match_reason": "string",
                    "url": "string",
                }
            ],
            "next_actions": ["string"],
            "assumptions": ["string"],
        }
        return self._invoke_json_skill("job-hunt", payload, schema)


