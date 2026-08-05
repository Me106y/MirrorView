"""Resume conversation and HTML generation agent."""

import json
import os
import re
from copy import deepcopy
from typing import Any, Dict, Generator, List, Optional

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from server.services.agents.base_skill_agent import BaseSkillAgent
from utils.logger_handler import logger


class ResumeCraftAgent(BaseSkillAgent):
    SKILL_NAME = "resume-craft"

    def run_resume_craft_chat_turn(self, payload: dict) -> dict:
        """Run one stateful resume-craft conversation turn through the loaded skill."""
        if self.llm is None:
            raise RuntimeError(self.llm_error or "LLM is not initialized")

        skill_spec = self.load_skill("resume-craft")
        schema = {
            "reply": "string",
            "action": "collect|advance|preview|revise|confirm|render_ready",
            "next_step_suggestion": "stay|next",
            "render_ready": False,
            "missing_fields": ["string"],
            "wizard_state": "minimal JSON patch for ResumeCraftWizardState",
            "step6_preview_markdown": "string",
            "step6_waiting_confirm": False,
            "step6_applied_changes": ["string"],
            "grill_state": {
                "completed_rounds": 0,
                "pending_questions": [
                    {"id": "string", "text": "string", "dimension": "string", "status": "open|answered|skipped"}
                ],
                "covered_dimensions": [
                    {"dimension": "canonical high-level fact dimension", "evidence": "confirmed user evidence"}
                ],
                "round_status": "awaiting_answers|round_completed|project_completed|skipped",
                "user_skipped": False,
            },
        }
        schema_json = json.dumps(schema, ensure_ascii=False, indent=2)
        prompt = ChatPromptTemplate.from_template(
            """
你正在运行 CareerForge 的 resume-craft 对话 Agent。
必须完整阅读并遵循下面的 Skill 规范。Skill 是行为决策的唯一业务依据；当前步骤、表单信息和历史记录只是上下文，不是固定问卷。

[Skill Specification]
{skill_spec}

[当前页面上下文]
{context_json}

[输出要求]
1. 只输出一个 JSON 对象，严格匹配下面的 schema，不要 Markdown 代码块或额外解释。
2. 使用完整 history、wizard_state、step1_profile 和用户消息理解语义，依据 Skill 自主决定追问、记录、跳过、修改、预览、确认或推进。
3. 只返回本轮必要的 wizard_state 最小 JSON 补丁，不要重复输出历史、聊天记录或未变化的数据。
[Required JSON Schema]
{schema_json}
"""
        )
        context = {
            "current_step": payload.get("current_step"),
            "step1_profile": payload.get("step1_profile") or {},
            "wizard_state": payload.get("wizard_state") or {},
            "history": payload.get("history") or [],
            "message": str(payload.get("message") or "").strip(),
        }
        raw = (prompt | self.llm | StrOutputParser()).invoke(
            {
                "skill_spec": skill_spec,
                "context_json": json.dumps(context, ensure_ascii=False, indent=2),
                "schema_json": schema_json,
            }
        )
        previous_wizard_state = context["wizard_state"]
        raw_text = str(raw or "").strip()
        parsed = self._safe_json_loads(raw_text)
        if parsed is None or not isinstance(parsed, dict):
            parsed = self._repair_json_output("resume-craft", raw_text, schema_json)
        if parsed is None or not isinstance(parsed, dict):
            logger.warning("resume-craft agent returned an unusable structured response; using a safe state-preserving reply")
            parsed = {}

        # A model can return valid JSON while omitting one or more contract
        # fields. Preserve the conversation instead of turning that response
        # into a route-level 502; the next turn can continue from this state.
        if not isinstance(parsed.get("wizard_state"), dict):
            fallback_state = deepcopy(previous_wizard_state) if isinstance(previous_wizard_state, dict) else {}
            if not fallback_state:
                fallback_state = {"current_step": payload.get("current_step") or 4}
            parsed["wizard_state"] = fallback_state
        if not str(parsed.get("reply") or "").strip() and not str(parsed.get("step6_preview_markdown") or "").strip():
            parsed["reply"] = "我已收到这段信息。请继续补充与项目相关的职责、关键行动和结果；如果已经没有更多内容，也可以直接告诉我。"
        if parsed.get("action") not in {"collect", "advance", "preview", "revise", "confirm", "render_ready"}:
            parsed["action"] = "collect"
        if parsed.get("next_step_suggestion") not in {"stay", "next"}:
            parsed["next_step_suggestion"] = "stay"
        if not isinstance(parsed.get("missing_fields"), list):
            parsed["missing_fields"] = []
        parsed["wizard_state"] = self._merge_state_patch(
            previous_wizard_state, parsed["wizard_state"]
        )
        # Semantic progression is owned by resume-craft/SKILL.md. The runtime
        # only preserves the model patch and the prior state; render safety is
        # enforced by the render route.
        parsed["wizard_state"] = self._merge_state_patch(
            previous_wizard_state,
            parsed["wizard_state"],
        )
        return parsed

    def _build_resume_craft_html_prompt(self, payload: dict) -> str:
        skill_spec = self.load_skill("resume-craft")
        template_code = (payload.get("template_code") or "02").strip()[:8]
        template_en = (payload.get("template_en") or "").strip()[:64]
        template_display = (payload.get("template_display") or "").strip()[:120]
        language = (payload.get("language") or "中文").strip()[:40]
        photo_pref = (payload.get("photo_pref") or "未明确").strip()[:40]
        photo_token = (payload.get("photo_token") or "__PHOTO_DATA_URL__").strip()[:120] or "__PHOTO_DATA_URL__"
        base_template = payload.get("base_template") or ""
        preview_snippet = payload.get("preview_snippet") or ""
        profile_context = payload.get("profile_context") or "（无）"
        history_text = json.dumps(payload.get("history") or [], ensure_ascii=False)
        confirmed_facts_context = payload.get("confirmed_facts_context") or history_text or "（无）"
        jd_direction_context = payload.get("jd_direction_context") or "（无）"
        extra_instruction = (payload.get("extra_instruction") or "").strip()
        photo_rule = (
            f'8) 本次要求放照片：必须输出 <img class="header-photo" src="{photo_token}" ...>，'
            "src 必须是该占位 token，禁止写死 URL 或其他 base64。"
            if photo_pref == "放照片"
            else "8) 本次不放照片：不要输出头像图片标签。"
        )

        return f"""
您是简历 HTML 生成器。请直接输出最终 HTML，不要任何解释文字。

必须严格遵守以下要求：
1) 只输出完整 HTML 文档（从 <!DOCTYPE html> 到 </html>）。
2) 目标模板：{template_code} / {template_en} / {template_display}。
3) 语言要求：{language}。
4) 照片偏好：{photo_pref}。
5) 必须包含导出按钮（window.print）、@page A4、@media print、分页控制。
6) 内容结构与视觉风格遵循 SKILL.md，且不编造事实。
7) 若用户已在早期选定模板，禁止再次确认模板。
8) 只能使用“事实白名单”中已经确认的信息；不得从 JD 摘要中新增任何未被用户确认的事实。
{photo_rule}
9) 事实白名单是唯一可写入简历的事实来源；目标 JD、职位要求、JD 中的示例技术和候选方案都不是事实。若某个技术、协议、数据库、云服务、证书、雇主、指标或职责没有在事实白名单中明确出现，必须完全省略，不能作为对比项、备选项或技能列表补充。尤其不要把 Pinecone、Chroma、Qdrant、AWS、GCP、Azure、Java 等 JD 示例写入简历，除非它们已在白名单中被用户确认。
10) 生成内容必须以事实白名单为准，即使 JD 或参考模板建议了更丰富的技术栈，也只能使用白名单中明确确认的内容；不确定时删去，不要猜测或补全。

[SKILL.md 规范全文]
{skill_spec}

[resume-template.html 参考（Editorial 完整结构）]
{str(base_template)[:22000]}

[CareerForge-模板预览.html 选中模板片段]
{str(preview_snippet)[:5000]}

[已保存目标信息（若用户后续已更新，请以后续最新输入为准）]
{str(profile_context)[:9000]}

[事实白名单（可写入简历）]
{str(confirmed_facts_context)[:18000]}

[JD 方向上下文（仅用于排序/强调，不可当作事实）]
{str(jd_direction_context)[:6000]}

[对话摘要（仅供参考）]
{str(history_text)[:5000]}

[附加约束]
{extra_instruction[:1200] if extra_instruction else "（无）"}
"""

    def stream_resume_craft_html(self, payload: dict) -> Generator[str, None, None]:
        if self.llm is None:
            raise RuntimeError(self.llm_error or "LLM is not initialized")
        prompt = ChatPromptTemplate.from_template("{full_prompt}")
        chain = prompt | self.llm | StrOutputParser()
        full_prompt = self._build_resume_craft_html_prompt(payload)
        try:
            for chunk in chain.stream({"full_prompt": full_prompt}):
                yield chunk
        except Exception:
            logger.exception("resume-craft html stream failed")
            raise

    def run_resume_craft_html(self, payload: dict) -> str:
        if self.llm is None:
            raise RuntimeError(self.llm_error or "LLM is not initialized")
        prompt = ChatPromptTemplate.from_template("{full_prompt}")
        chain = prompt | self.llm | StrOutputParser()
        full_prompt = self._build_resume_craft_html_prompt(payload)
        return chain.invoke({"full_prompt": full_prompt})
