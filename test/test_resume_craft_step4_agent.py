from server.services.agents.resume_craft_agent import ResumeCraftAgent


class _JsonModel:
    def __init__(self, output):
        self.output = output

    def __call__(self, _prompt):
        return self.output


def _agent_payload(message, current_step=5, wizard_state=None):
    return {
        "message": message,
        "current_step": current_step,
        "step1_profile": {"target_role": "AI 应用开发"},
        "wizard_state": wizard_state or {"current_step": current_step},
        "history": [],
    }


def test_resume_craft_agent_returns_skill_driven_state():
    model = _JsonModel(
        '{"reply":"请具体说说你在这段经历中的关键决策。",'
        '"action":"collect","next_step_suggestion":"stay",'
        '"render_ready":false,"missing_fields":["decision"],'
        '"wizard_state":{"current_step":4},"step6_preview_markdown":"",'
        '"step6_waiting_confirm":false,"step6_applied_changes":[]}'
    )
    agent = ResumeCraftAgent(llm=model)

    result = agent.run_resume_craft_chat_turn(
        {
            "message": "我做了一个检索服务。",
            "current_step": 4,
            "step1_profile": {"target_role": "AI 应用开发"},
            "wizard_state": {"current_step": 4},
            "history": [],
        }
    )

    assert result["reply"].startswith("请具体说说")


def test_resume_craft_preserves_skill_decision_to_skip_and_revisit_naturally():
    model = _JsonModel(
        '{"reply":"证书先跳过，之后可以直接补充。",'
        '"action":"advance","next_step_suggestion":"next",'
        '"render_ready":false,"missing_fields":[], '
        '"wizard_state":{"current_step":5,"collected_by_step":{"skills_and_certs":["Python"]},'
        '"step_states":{"step5":{"skipped_dimensions":["certificates"]}}}}'
    )
    agent = ResumeCraftAgent(llm=model)

    result = agent.run_resume_craft_chat_turn(
        _agent_payload("证书暂时没有，先跳过", current_step=5)
    )

    assert result["reply"] == "证书先跳过，之后可以直接补充。"
    assert result["action"] == "advance"
    assert result["next_step_suggestion"] == "next"
    assert result["wizard_state"]["step_states"]["step5"]["skipped_dimensions"] == ["certificates"]


def test_resume_craft_preserves_natural_language_revision_after_skip():
    model = _JsonModel(
        '{"reply":"已补充 AWS 证书，并移除过期证书。",'
        '"action":"revise","next_step_suggestion":"stay",'
        '"render_ready":false,"missing_fields":[], '
        '"wizard_state":{"current_step":5,"collected_by_step":{"skills_and_certs":["Python", "AWS Certified Solutions Architect"]},'
        '"step_states":{"step5":{"certificates":["AWS Certified Solutions Architect"]}}}}'
    )
    agent = ResumeCraftAgent(llm=model)

    result = agent.run_resume_craft_chat_turn(
        _agent_payload(
            "我后来拿到了 AWS 证书，请补上，并删掉之前过期的证书",
            current_step=5,
            wizard_state={
                "current_step": 5,
                "collected_by_step": {"skills_and_certs": ["Python", "旧证书"]},
            },
        )
    )

    assert result["reply"] == "已补充 AWS 证书，并移除过期证书。"
    assert result["action"] == "revise"
    assert result["wizard_state"]["collected_by_step"]["skills_and_certs"] == [
        "Python",
        "AWS Certified Solutions Architect",
    ]
