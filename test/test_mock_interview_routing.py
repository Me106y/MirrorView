import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
AI_SERVICE_PATH = REPO_ROOT / "server" / "services" / "ai_service.py"
COMMAND_AGENT_PATH = REPO_ROOT / "server" / "services" / "careerforge_command_agent.py"
ROUTES_PATH = REPO_ROOT / "server" / "routes.py"


def _parse_python(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _find_top_level_function(tree: ast.Module, function_name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return node
    raise AssertionError(f"Function '{function_name}' not found.")


def _find_class_method(
    tree: ast.Module,
    class_name: str,
    method_name: str,
) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return item
    raise AssertionError(f"Method '{class_name}.{method_name}' not found.")


def _collect_call_targets(node: ast.AST) -> list[str]:
    targets = []

    class _Collector(ast.NodeVisitor):
        def visit_Call(self, call_node: ast.Call) -> None:
            func = call_node.func
            if isinstance(func, ast.Attribute):
                targets.append(func.attr)
            elif isinstance(func, ast.Name):
                targets.append(func.id)
            self.generic_visit(call_node)

    _Collector().visit(node)
    return targets

def _collect_calls(node: ast.AST) -> list[ast.Call]:
    calls: list[ast.Call] = []

    class _Collector(ast.NodeVisitor):
        def visit_Call(self, call_node: ast.Call) -> None:
            calls.append(call_node)
            self.generic_visit(call_node)

    _Collector().visit(node)
    return calls

def _get_call_name(call_node: ast.Call) -> str:
    func = call_node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""

def _call_has_keyword(call_node: ast.Call, keyword_name: str) -> bool:
    return any(kw.arg == keyword_name for kw in call_node.keywords if kw.arg)


def test_ai_service_non_streaming_reply_uses_mock_interview_runtime() -> None:
    tree = _parse_python(AI_SERVICE_PATH)
    method = _find_class_method(tree, "AIService", "chat_response")
    calls = _collect_call_targets(method)

    assert "build_mock_interview_reply" in calls, (
        "AIService.chat_response should call CareerForge mock-interview runtime."
    )
    build_calls = [call for call in _collect_calls(method) if _get_call_name(call) == "build_mock_interview_reply"]
    assert build_calls, "Expected build_mock_interview_reply call in AIService.chat_response."
    assert any(_call_has_keyword(call, "language") for call in build_calls), (
        "AIService.chat_response should forward interview language to runtime."
    )


def test_ai_service_streaming_reply_uses_mock_interview_runtime() -> None:
    tree = _parse_python(AI_SERVICE_PATH)
    method = _find_class_method(tree, "AIService", "chat_response_stream")
    calls = _collect_call_targets(method)

    assert "stream_mock_interview_reply" in calls, (
        "AIService.chat_response_stream should call CareerForge mock-interview runtime."
    )
    stream_calls = [call for call in _collect_calls(method) if _get_call_name(call) == "stream_mock_interview_reply"]
    assert stream_calls, "Expected stream_mock_interview_reply call in AIService.chat_response_stream."
    assert any(_call_has_keyword(call, "language") for call in stream_calls), (
        "AIService.chat_response_stream should forward interview language to runtime."
    )


def test_create_interview_opens_with_mock_interview_and_not_legacy_questions() -> None:
    tree = _parse_python(ROUTES_PATH)
    function = _find_top_level_function(tree, "create_interview")
    calls = _collect_call_targets(function)

    assert "generate_mock_interview_opening" in calls, (
        "create_interview should use mock-interview opening path."
    )
    assert "generate_interview_questions" not in calls, (
        "Legacy question-generation call should not be used in create_interview."
    )
    assert "_normalize_interview_language" in calls, (
        "create_interview should normalize requested interview language."
    )

    all_calls = _collect_calls(function)
    interview_ctor_calls = [call for call in all_calls if _get_call_name(call) == "Interview"]
    assert interview_ctor_calls, "Expected Interview(...) constructor in create_interview."
    assert any(_call_has_keyword(call, "language") for call in interview_ctor_calls), (
        "create_interview should persist interview language to Interview.language."
    )

    opening_calls = [call for call in all_calls if _get_call_name(call) == "generate_mock_interview_opening"]
    assert opening_calls, "Expected generate_mock_interview_opening call in create_interview."
    assert any(_call_has_keyword(call, "language") for call in opening_calls), (
        "create_interview should pass language into mock-interview opening generation."
    )


def test_handle_messages_routes_to_stream_and_non_stream_mock_interview_calls() -> None:
    tree = _parse_python(ROUTES_PATH)
    function = _find_top_level_function(tree, "handle_messages")
    calls = _collect_call_targets(function)

    assert "chat_response_stream" in calls, (
        "Streaming path should route through ai_service.chat_response_stream."
    )
    assert "chat_response" in calls, (
        "Non-streaming path should route through ai_service.chat_response."
    )


def test_finish_interview_generates_feedback_with_interview_language() -> None:
    tree = _parse_python(ROUTES_PATH)
    function = _find_top_level_function(tree, "finish_interview")
    all_calls = _collect_calls(function)
    feedback_calls = [call for call in all_calls if _get_call_name(call) == "generate_feedback"]

    assert feedback_calls, "Expected generate_feedback call in finish_interview."
    assert any(_call_has_keyword(call, "language") for call in feedback_calls), (
        "finish_interview should pass interview language when generating feedback."
    )


def test_mock_interview_command_action_includes_language_in_result() -> None:
    source = COMMAND_AGENT_PATH.read_text(encoding="utf-8")
    assert '"language": interview_language' in source or "'language': interview_language" in source, (
        "mock-interview start action should include language in result payload."
    )
