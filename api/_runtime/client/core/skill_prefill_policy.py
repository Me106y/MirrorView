import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict


_DEFAULT_PREFILL_POLICY: Dict[str, Any] = {
    "enabled": True,
    "ask_before_using_saved": True,
    "saved_choice_label": "使用已保存信息",
    "new_choice_label": "使用新提交信息",
    "saved_choice_aliases": [
        "使用已保存信息",
        "使用已保存",
        "已保存",
        "saved",
        "1",
        "选1",
        "选择1",
    ],
    "new_choice_aliases": [
        "使用新提交信息",
        "使用新提交",
        "新提交",
        "重新提交",
        "new",
        "2",
        "选2",
        "选择2",
    ],
    "new_content_markers": [
        "【目标岗位JD】",
        "[目标岗位JD]",
        "JD：",
        "jd：",
        "职位JD：",
        "岗位：",
    ],
    "prompt_template": (
        "检测到您已保存目标岗位和 JD。\n"
        "请选择：\n"
        "1) {saved_choice_label}\n"
        "2) {new_choice_label}\n\n"
        "你可以直接回复“{saved_choice_label}”或“{new_choice_label}”。"
    ),
    "saved_guidance_with_resume": "已切换为“使用已保存信息”，并已读取已保存简历。可继续下一步。",
    "saved_guidance_without_resume": "已切换为“使用已保存信息”。未读取到已保存简历，请补充简历内容或文件路径。",
    "new_guidance": "已切换为“使用新提交信息”。请发送新的目标岗位/JD/简历。",
}


def _resolve_skills_root() -> Path:
    candidates = []
    env_root = (Path().home() / ".codex" / "skills" / "CareerForge" / "skills")
    local_root = Path(__file__).resolve().parents[2] / "skills" / "CareerForge" / "skills"
    candidates.append(local_root)
    candidates.append(env_root)
    for root in candidates:
        if (root / "resume-match" / "SKILL.md").exists():
            return root
    return local_root


def load_skill_frontmatter(skill_name: str) -> Dict[str, Any]:
    path = _resolve_skills_root() / skill_name / "SKILL.md"
    if not path.exists():
        return {}
    try:
        mtime_ns = int(path.stat().st_mtime_ns)
    except Exception:
        mtime_ns = 0
    return _load_skill_frontmatter_cached(str(path), mtime_ns)


@lru_cache(maxsize=64)
def _load_skill_frontmatter_cached(path_str: str, _mtime_ns: int) -> Dict[str, Any]:
    path = Path(path_str)
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="ignore")
    front = _extract_frontmatter(text)
    if not front:
        return {}
    try:
        import yaml  # type: ignore
    except Exception:
        return {}
    try:
        data = yaml.safe_load(front) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _extract_frontmatter(text: str) -> str:
    raw = (text or "").lstrip("\ufeff")
    lines = raw.splitlines()
    if len(lines) < 3:
        return ""
    if lines[0].strip() != "---":
        return ""
    collected = []
    for idx in range(1, len(lines)):
        line = lines[idx]
        if line.strip() == "---":
            return "\n".join(collected)
        collected.append(line)
    return ""


def get_prefill_policy(skill_name: str) -> Dict[str, Any]:
    fm = load_skill_frontmatter(skill_name)
    custom = fm.get("prefill_policy") if isinstance(fm, dict) else None
    policy = dict(_DEFAULT_PREFILL_POLICY)
    if isinstance(custom, dict):
        for k, v in custom.items():
            policy[k] = v
    return policy


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").strip().lower())


def resolve_prefill_choice(skill_name: str, text: str) -> str:
    policy = get_prefill_policy(skill_name)
    norm = _normalize(text)
    saved_aliases = [_normalize(x) for x in (policy.get("saved_choice_aliases") or [])]
    new_aliases = [_normalize(x) for x in (policy.get("new_choice_aliases") or [])]

    if norm and norm in set(saved_aliases):
        return "saved"
    if norm and norm in set(new_aliases):
        return "new"

    # Fuzzy contains (exclude trivial numeric aliases like "1"/"2" to avoid
    # false positives from content such as "模板=02")
    fuzzy_saved_aliases = [x for x in saved_aliases if x and (len(x) > 1) and (not x.isdigit())]
    fuzzy_new_aliases = [x for x in new_aliases if x and (len(x) > 1) and (not x.isdigit())]

    if any(x in norm for x in fuzzy_saved_aliases):
        return "saved"
    if any(x in norm for x in fuzzy_new_aliases):
        return "new"

    # If user is clearly sending new material, treat as "new"
    original = text or ""
    for marker in (policy.get("new_content_markers") or []):
        if marker and marker in original:
            return "new"
    return ""


def is_prefill_choice_command_only(skill_name: str, text: str) -> bool:
    policy = get_prefill_policy(skill_name)
    norm = _normalize(text)
    choices = {
        *(_normalize(x) for x in (policy.get("saved_choice_aliases") or [])),
        *(_normalize(x) for x in (policy.get("new_choice_aliases") or [])),
    }
    return bool(norm and norm in choices)


def build_prefill_choice_prompt(skill_name: str, role: str = "", jd_text: str = "", has_resume: bool = False) -> str:
    policy = get_prefill_policy(skill_name)
    template = str(policy.get("prompt_template") or _DEFAULT_PREFILL_POLICY["prompt_template"])
    role_text = (role or "").strip()
    jd_hint = "有" if (jd_text or "").strip() else "无"
    resume_hint = "有" if has_resume else "无"
    try:
        return template.format(
            saved_choice_label=policy.get("saved_choice_label", "使用已保存信息"),
            new_choice_label=policy.get("new_choice_label", "使用新提交信息"),
            saved_role=role_text,
            has_saved_jd=jd_hint,
            has_saved_resume=resume_hint,
            skill=skill_name,
        )
    except Exception:
        return str(_DEFAULT_PREFILL_POLICY["prompt_template"])


def get_prefill_choice_guidance(skill_name: str, choice: str, resume_loaded: bool) -> str:
    policy = get_prefill_policy(skill_name)
    if choice == "saved":
        key = "saved_guidance_with_resume" if resume_loaded else "saved_guidance_without_resume"
        msg = str(policy.get(key) or "").strip()
        if msg:
            return msg
    if choice == "new":
        msg = str(policy.get("new_guidance") or "").strip()
        if msg:
            return msg
    # fallback
    if choice == "saved":
        return (
            _DEFAULT_PREFILL_POLICY["saved_guidance_with_resume"]
            if resume_loaded
            else _DEFAULT_PREFILL_POLICY["saved_guidance_without_resume"]
        )
    return _DEFAULT_PREFILL_POLICY["new_guidance"]
