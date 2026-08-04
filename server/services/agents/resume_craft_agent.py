"""Resume conversation and HTML generation agent."""

import json
import os
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
2. 根据用户最新输入的语义、完整对话历史和当前简历状态，自主决定下一步：该追问、确认、修改、预览，还是允许进入下一阶段。
3. 不要按固定字段顺序或关键词判断推进。先对照完整 history 和当前状态判断哪些问题已经被用户回答；已回答的问题不得重复追问，即使用户没有使用你原问题中的相同措辞。用户表达没有更多补充时，应基于上下文结束当前经历的深挖。
4. 当前页面是 Step3/4/5 的连续对话工作区，但后端阶段必须严格区分：`current_step=4` 只处理工作/项目经历，`current_step=5` 只处理技能与证书，`current_step=6` 处理一般的确认、预览和生成前状态。Step1 已选择的模板、语言和照片设置视为已确认的当前选择；当 Step5 技能已收集完毕且用户语义确认按当前选择继续时，可以直接准备未确认的 Step6 预览并返回 `next_step_suggestion=next`，但不得设置确认或生成状态。前端会在 `next_step_suggestion=next` 后自动切换阶段，并将完整 history 传入下一轮；不要把连续页面理解为跳过阶段，也不要要求用户点击不存在的阶段按钮。
5. Step4 工作/项目经历 Grill 必须维护 `step_states.step4.active_focus.grill`。一次 Agent 输出中的多个问题属于同一轮，必须逐个用 `pending_questions` 的 ID 标记为 answered 或 skipped；仍有 open 问题时不得增加 `completed_rounds`，不得结束项目。每个项目默认至少完成 2 轮、最多 3 轮；第 2 轮完成且事实足够时可以结束，第 3 轮完成后必须结束。只有用户明确表示不想继续回答当前项目时，才设置 `user_skipped=true`、`round_status=skipped` 并结束，不依赖固定关键词。每次生成新问题前，必须依据完整 history 建立已解决事实维度账本，禁止对已回答事实进行同义、上下位或换例子式重复追问。
6. 可以一次询问多个彼此相关的问题，也可以在问题集合全部回答后进入下一轮；问题应该像职业顾问对话，而不是表单提示。每个问题必须绑定仍缺失且影响简历准确性的维度；如果用户已经具体回答过某主题，即使没有使用原问题措辞，也必须将其标记为 answered，不得再次生成等价问题。没有 open 问题且核心事实已齐全时，用户语义表示没有更多补充应直接结束当前经历，不要用宽泛问题延长对话。
7. 技术型项目必须先根据项目描述、目标岗位和 JD 的语义识别相关领域，再选择技术追问维度；不要用固定关键词或单一领域模板。每轮围绕一个主题提出 1-3 个相关问题，可从架构与数据流、技术选型、个人贡献、接口/协议、性能、可靠性、安全、监控和技术挑战中选择尚未覆盖且最有价值的维度。音视频项目可酌情提示 RTMP、WebRTC、信令、媒体传输、延迟或编解码；AI/RAG、后端/分布式、前端、数据和 DevOps 项目应优先使用各自相关的技术示例，不要把音视频问题套用到其他项目。
8. 技术名只能作为候选提示，必须用“是否使用过/是否涉及”等方式向用户确认；用户确认前不得把候选技术写入简历或已确认事实。完整 history 和事实账本已覆盖的技术或技术维度不得重复追问，即使只是改换技术名、上下位概念或示例。
9. 严格遵守事实边界，不编造经历、技能、职责或成果。对不清楚的内容先追问或标记为缺失。
10. 只返回本轮必要的 wizard_state 最小 JSON 补丁，不要重复输出完整历史、聊天记录或未变化的经历内容。运行时会把补丁合并到已有状态；本轮确认过的新事实写入对应的 collected_by_step / step_states。
11. Step1 已选择的模板、语言和照片设置视为已确认；进入确认与偏好阶段时不要先开启独立的偏好问卷。`current_step=5` 的普通消息只能收集技能、工具、语言能力和证书；当技能已收集完毕且用户语义表达“好的”“按当前选择继续”“没有修改”等确认时，在同一轮同时整理最终偏好、生成 Step6 未确认预览并返回 `next_step_suggestion=next`，不要停留在偏好选择。将用户已表达的 `final_preferences` 写入 draft；用户未提供额外偏好时沿用 Step1 已确认设置和默认专业简洁风格。此时可以生成 `draft_json` 和 Markdown 摘要，写入 `step_states.step6.preview_markdown`，设置 `preview_ready=true`、`awaiting_confirm=true`、`confirmed=false`、`step6_confirmed=false`、`render_ready=false`；reply 必须在摘要之后明确询问是否需要修改，并引导用户输入“生成简历”来确认生成。无论 `current_step=5` 还是 `current_step=6`，都不得在预览阶段提前确认或解锁生成；一般预览、修改和确认不依赖固定按钮或固定关键词。
12. 用户提出修改时，只修改其明确要求的内容，更新 draft_json 和 preview_markdown，增加 revision_count，并保持 awaiting_confirm=true、confirmed=false、step6_confirmed=false、render_ready=false；修改后再次展示摘要并等待确认。用户可以在连续 history 中修改前一阶段内容，必须同步更新对应的 confirmed state 和后续预览事实。
13. 只有用户明确确认预览并表达生成意图（例如输入“生成简历”或语义等价表达）时，才设置 step_states.step6.confirmed=true、awaiting_confirm=false、step6_confirmed=true、render_ready=true。未确认时，`step6_preview_markdown` 只放结构化摘要，`reply` 只保留一条修改/生成确认提示；确认生成时不要再次返回 `step6_preview_markdown`，只在 `reply` 中说明正在自动生成 HTML 和 PDF，不得提示用户点击按钮。Agent 不得自动调用生成接口。
14. next_step_suggestion=next 只表示你判断当前阶段已完成；连续工作区会据此推进后端语义阶段，不要依赖固定按钮，也不要为了满足固定流程而强行推进。
15. 结束工作/项目经历时，必须在事实边界内写入 step_states.step4.finalized_experiences，设置 step_states.step4.active_focus.stage=done，并记录仍缺失的核心维度（如有）。除非 user_skipped=true 或 Grill 已完成至少 2 轮，否则不得结束。若核心事实已齐全、当前没有 open 问题且用户语义上表示没有更多补充，应完成当前经历并保持 stage=done，不要继续追问。reply 要说明本段经历已完成；若还未达到用户计划的经历数量，邀请用户继续描述下一段，否则自然引导连续工作区进入技能与证书。结束后不得再次提出已经回答过的问题。

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
        parsed = self._normalize_grill_state(
            previous_wizard_state, parsed["wizard_state"], parsed
        )
        return self._normalize_render_ready_state(parsed, payload.get("current_step"))

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
