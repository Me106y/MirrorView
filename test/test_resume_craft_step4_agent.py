from server.services.agents.resume_craft_agent import ResumeCraftAgent


class _JsonModel:
    def __init__(self, output):
        self.output = output

    def __call__(self, _prompt):
        return self.output


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
