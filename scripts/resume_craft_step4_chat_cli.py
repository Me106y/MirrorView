#!/usr/bin/env python3
"""
Step4 (工作/项目经历 Grill) interactive CLI for resume-craft.

Usage examples:
  python3 scripts/resume_craft_step4_chat_cli.py
  python3 scripts/resume_craft_step4_chat_cli.py --target-role "AI应用开发" --expected-experience-count 2
  python3 scripts/resume_craft_step4_chat_cli.py --mock-step4
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Flask

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import routes
from server.config import Config


INITIAL_ASSISTANT_PROMPT = "我们进入 Step4（工作/项目经历）。请描述第一段经历的场景、职责、行动和结果。"


def _build_client():
    app = Flask(__name__)
    app.register_blueprint(routes.api, url_prefix="/api")
    app.config["TESTING"] = True
    return app.test_client()


def _default_step1_profile(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "template_code": args.template_code,
        "language": args.language,
        "photo_pref": args.photo_pref,
        "target_role": args.target_role,
        "jd_summary": args.jd_summary,
        "expected_experience_count": args.expected_experience_count,
        "personal_info": {
            "name": args.name,
            "phone": args.phone,
            "email": args.email,
            "city": args.city,
            "links": [x.strip() for x in (args.links or "").split(",") if x.strip()],
        },
        "education": [
            {
                "school": args.school,
                "major": args.major,
                "degree": args.degree,
                "period": args.edu_period,
                "highlights": "",
            }
        ],
        "skills": [x.strip() for x in (args.skills or "").split(",") if x.strip()],
        "certificates": [x.strip() for x in (args.certificates or "").split(",") if x.strip()],
    }


def _safe_json(raw: str) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _enable_mock_step4():
    def _detect_focus_topic(text: str, previous_topic: str) -> str:
        if previous_topic:
            return previous_topic
        lower = text.lower()
        if "langchain" in lower or "rag" in lower:
            return "LangChain 检索链路"
        if "k8s" in lower or "kubernetes" in lower:
            return "Kubernetes 服务治理"
        if "flask" in lower or "fastapi" in lower:
            return "后端服务链路"
        return "该项目核心技术点"

    def _merge_evidence(base: Dict[str, bool], text: str) -> Dict[str, bool]:
        lower = text.lower()
        patch = {
            "implementation": any(token in lower for token in ["实现", "模块", "链路", "流程", "接口", "构建", "搭建", "重构"]),
            "tradeoff": any(token in lower for token in ["取舍", "选型", "为什么", "而不是", "相比", "权衡"]),
            "validation": any(token in lower for token in ["p95", "qps", "%", "ms", "压测", "监控", "线上", "错误率"]),
        }
        return {
            "implementation": bool(base.get("implementation")) or patch["implementation"],
            "tradeoff": bool(base.get("tradeoff")) or patch["tradeoff"],
            "validation": bool(base.get("validation")) or patch["validation"],
        }

    def _next_stage(evidence: Dict[str, bool]) -> str:
        if not evidence.get("implementation"):
            return "implementation"
        if not evidence.get("tradeoff"):
            return "tradeoff"
        if not evidence.get("validation"):
            return "validation"
        return "done"

    def _probe(topic: str, stage: str) -> str:
        if stage == "implementation":
            return f"围绕“{topic}”，请具体说明一个核心功能的实现链路（输入→处理→输出）。"
        if stage == "tradeoff":
            return f"围绕“{topic}”，请说明一次关键技术取舍：为什么这样选，而不是备选方案？"
        if stage == "validation":
            return f"围绕“{topic}”，请给验证口径与结果（如 P95/QPS/错误率/收益指标）。"
        return "是否还有要补充的经历"

    def _mock_step4_decision(payload, runtime=None):
        user_input = str(payload.get("user_input") or "")
        if any(token in user_input for token in ["没有更多项目", "没有更多经历", "没了", "没有了"]):
            return {
                "reply": "已收到。你目前没有更多项目/经历需要补充，我将进入下一阶段。",
                "resume_ready_draft": {
                    "title": "项目经历",
                    "role": "核心开发",
                    "period": "时间待补",
                    "bullets": [],
                },
                "missing_points": [],
                "current_experience_completed": True,
                "ask_more_experience": False,
                "reasoning_focus": [],
                "active_focus_topic": "",
                "next_probe_dimension": "more_experience",
                "evidence_coverage": {"implementation": True, "tradeoff": True, "validation": True},
            }

        active_focus = payload.get("active_focus") if isinstance(payload.get("active_focus"), dict) else {}
        topic = _detect_focus_topic(user_input, str(active_focus.get("topic") or "").strip())
        base_evidence = active_focus.get("evidence") if isinstance(active_focus.get("evidence"), dict) else {}
        evidence = _merge_evidence(
            {
                "implementation": bool(base_evidence.get("implementation", False)),
                "tradeoff": bool(base_evidence.get("tradeoff", False)),
                "validation": bool(base_evidence.get("validation", False)),
            },
            user_input,
        )
        stage = _next_stage(evidence)
        done = stage == "done"
        probe_question = _probe(topic, stage)
        first_round = bool(payload.get("is_first_round", False))
        if first_round:
            return {
                "reply": (
                    "我先按你给的信息整理成可上简历版本（待你确认）：\n"
                    f"{topic}（草稿）\n"
                    "本轮只问一个关键点：\n"
                    f"{probe_question}"
                ),
                "resume_ready_draft": {
                    "title": topic,
                    "role": "核心开发",
                    "period": "时间待补",
                    "bullets": ["请确认并补充细节。"],
                },
                "missing_points": [probe_question] if not done else ["是否还有要补充的经历"],
                "current_experience_completed": done,
                "ask_more_experience": True,
                "reasoning_focus": [topic],
                "active_focus_topic": topic,
                "next_probe_dimension": "more_experience" if done else stage,
                "evidence_coverage": evidence,
            }

        if done:
            return {
                "reply": "这一段经历已完成深挖。是否还有要补充的经历？",
                "resume_ready_draft": {
                    "title": topic,
                    "role": "核心开发",
                    "period": "时间待补",
                    "bullets": [],
                },
                "missing_points": ["是否还有要补充的经历"],
                "current_experience_completed": True,
                "ask_more_experience": True,
                "reasoning_focus": [topic],
                "active_focus_topic": topic,
                "next_probe_dimension": "more_experience",
                "evidence_coverage": evidence,
            }
        return {
            "reply": f"继续围绕“{topic}”深挖：{probe_question}",
            "resume_ready_draft": {
                "title": topic,
                "role": "核心开发",
                "period": "时间待补",
                "bullets": [],
            },
            "missing_points": [probe_question],
            "current_experience_completed": False,
            "ask_more_experience": True,
            "reasoning_focus": [topic],
            "active_focus_topic": topic,
            "next_probe_dimension": stage,
            "evidence_coverage": evidence,
        }

    routes.ai_service.run_resume_craft_step4_decision = _mock_step4_decision


def _print_turn_result(body: Dict[str, Any]) -> None:
    reply = str(body.get("reply") or "").strip()
    action = body.get("action")
    next_step = body.get("next_step_suggestion")
    missing = body.get("missing_fields") or []
    meta = body.get("meta") or {}
    step4_missing = meta.get("step4_missing_points") or []
    step4_raw_missing = meta.get("step4_raw_missing_points") or []
    step4_focus = meta.get("step4_reasoning_focus") or []
    step4_focus_topic = meta.get("step4_focus_topic") or ""
    step4_focus_stage = meta.get("step4_focus_stage") or ""
    step4_evidence = meta.get("step4_evidence_coverage") or {}

    print("\nAI:")
    print(reply or "(empty)")
    print("\n[状态]")
    print(f"- action: {action}")
    print(f"- next_step_suggestion: {next_step}")
    print(f"- missing_fields: {missing}")
    print(f"- step4_mode: {meta.get('step4_mode')}")
    print(f"- step4_missing_points: {step4_missing}")
    print(f"- step4_raw_missing_points: {step4_raw_missing}")
    print(f"- step4_reasoning_focus: {step4_focus}")
    print(f"- step4_focus_topic: {step4_focus_topic}")
    print(f"- step4_focus_stage: {step4_focus_stage}")
    print(f"- step4_evidence_coverage: {step4_evidence}")

    experience_state = body.get("experience_state") or {}
    finalized = experience_state.get("finalized_experiences") or []
    print(f"- finalized_experiences_count: {len(finalized)}")


def main():
    parser = argparse.ArgumentParser(description="Interactive Step4 chat tester for /api/careerforge/resume-craft/chat-turn")
    parser.add_argument("--template-code", default="02")
    parser.add_argument("--language", default="中文")
    parser.add_argument("--photo-pref", default="不放照片", choices=["放照片", "不放照片"])
    parser.add_argument("--target-role", default="AI应用开发")
    parser.add_argument("--jd-summary", default="AI应用开发岗位，关注工程化与可量化结果。")
    parser.add_argument("--expected-experience-count", type=int, default=2)
    parser.add_argument("--name", default="张三")
    parser.add_argument("--phone", default="13800000000")
    parser.add_argument("--email", default="zhangsan@example.com")
    parser.add_argument("--city", default="杭州")
    parser.add_argument("--links", default="https://github.com/example")
    parser.add_argument("--school", default="某大学")
    parser.add_argument("--major", default="计算机科学")
    parser.add_argument("--degree", default="硕士")
    parser.add_argument("--edu-period", default="2020-2023")
    parser.add_argument("--skills", default="Python,LangChain,Flask")
    parser.add_argument("--certificates", default="")
    parser.add_argument("--runtime-json", default="", help="Optional runtime JSON string, e.g. '{\"mode\":\"platform\"}'")
    parser.add_argument("--once", default="", help="Run single turn with this message and exit.")
    parser.add_argument("--mock-step4", action="store_true", help="Use local mock Step4 decision (no model call).")
    args = parser.parse_args()

    if args.mock_step4:
        _enable_mock_step4()

    # Keep local CLI testing deterministic (avoid captcha/rate-limit blockers).
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    runtime_payload = _safe_json(args.runtime_json)
    client = _build_client()

    step1_profile = _default_step1_profile(args)
    wizard_state: Optional[Dict[str, Any]] = None
    experience_state: Optional[Dict[str, Any]] = None
    history: List[Dict[str, str]] = [{"role": "assistant", "content": INITIAL_ASSISTANT_PROMPT}]

    print("=== Resume Craft Step4 CLI ===")
    print("支持多行输入：连续输入多行内容，输入空行后一次性发送本轮。")
    print("命令：/state 查看状态，/cancel 清空当前草稿，/exit 退出。")
    print(f"初始提示: {INITIAL_ASSISTANT_PROMPT}\n")

    def do_turn(user_message: str) -> bool:
        nonlocal wizard_state, experience_state, history

        payload: Dict[str, Any] = {
            "message": user_message,
            "current_step": 4,
            "history": history,
            "step1_profile": step1_profile,
            "wizard_state": wizard_state,
            "experience_state": experience_state,
            "template_code": step1_profile["template_code"],
            "language": step1_profile["language"],
            "photo_pref": step1_profile["photo_pref"],
            "photo_uploaded": step1_profile["photo_pref"] == "放照片",
        }
        if runtime_payload is not None:
            payload["runtime"] = runtime_payload

        resp = client.post("/api/careerforge/resume-craft/chat-turn", json=payload)
        body = resp.get_json() if resp.is_json else {"error": "non_json_response", "raw": resp.data.decode("utf-8", errors="ignore")}
        if resp.status_code != 200:
            print(f"\n[ERROR] status={resp.status_code}")
            print(json.dumps(body, ensure_ascii=False, indent=2))
            return False

        _print_turn_result(body)
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": str(body.get("reply") or "")})
        wizard_state = body.get("wizard_state") if isinstance(body.get("wizard_state"), dict) else wizard_state
        experience_state = body.get("experience_state") if isinstance(body.get("experience_state"), dict) else experience_state
        return True

    if args.once:
        do_turn(args.once.strip())
        return

    draft_lines: List[str] = []

    while True:
        try:
            prompt = "\nYou> " if not draft_lines else "... "
            line = input(prompt)
        except (EOFError, KeyboardInterrupt):
            print("\n退出。")
            break

        stripped = line.strip()
        if not draft_lines and stripped in {"/exit", "exit", "quit"}:
            print("退出。")
            break
        if not draft_lines and stripped == "/state":
            print(
                json.dumps(
                    {
                        "wizard_state": wizard_state,
                        "experience_state": experience_state,
                        "history_size": len(history),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            continue
        if not draft_lines and stripped == "/cancel":
            print("当前草稿为空。")
            continue

        if stripped == "/cancel":
            draft_lines = []
            print("已清空当前草稿。")
            continue

        if line == "":
            if not draft_lines:
                continue
            user_message = "\n".join(draft_lines).strip()
            draft_lines = []
            if user_message:
                do_turn(user_message)
            continue

        draft_lines.append(line)


if __name__ == "__main__":
    main()
