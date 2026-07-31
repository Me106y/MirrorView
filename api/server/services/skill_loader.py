from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional


class SkillLoader:
    """Loads CareerForge SKILL.md files from known roots with simple caching."""

    def __init__(self, skills_root: Optional[str] = None):
        self._root = self._resolve_root(skills_root)
        self._cache: Dict[str, str] = {}

    @property
    def skills_root(self) -> Path:
        return self._root

    def _candidate_roots(self, skills_root: Optional[str] = None) -> List[Path]:
        base = Path(__file__).resolve().parents[2]
        candidates: List[Path] = []
        if skills_root:
            candidates.append(Path(skills_root))
        env_root = os.environ.get("CAREERFORGE_SKILLS_ROOT")
        if env_root:
            candidates.append(Path(env_root))
        candidates.extend(
            [
                base / "skills" / "CareerForge" / "skills",
                Path.home() / ".codex" / "skills" / "CareerForge" / "skills",
            ]
        )
        return candidates

    def _resolve_root(self, skills_root: Optional[str] = None) -> Path:
        candidates = self._candidate_roots(skills_root)
        for candidate in candidates:
            path = candidate.expanduser().resolve()
            if (path / "resume-match" / "SKILL.md").exists():
                return path
        fallback = candidates[0].expanduser().resolve()
        return fallback

    def skill_path(self, skill_name: str) -> Path:
        safe_name = str(skill_name or "").strip()
        if not safe_name or safe_name in {".", ".."} or "/" in safe_name or "\\" in safe_name:
            raise ValueError(f"Invalid skill name: {skill_name!r}")
        return self.skills_root / safe_name / "SKILL.md"

    def load(self, skill_name: str) -> str:
        key = str(skill_name or "").strip()
        if key in self._cache:
            return self._cache[key]

        path = self.skill_path(key)
        if not path.exists():
            raise FileNotFoundError(f"Skill file not found: {path}")

        content = path.read_text(encoding="utf-8", errors="ignore").strip()
        if not content:
            raise ValueError(f"Skill file is empty: {path}")

        self._cache[key] = content
        return content
