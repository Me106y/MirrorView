"""Vercel Python entrypoint for MirrorView backend API."""

import importlib.util
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_CANDIDATE_ROOTS = [
    _HERE.parent,
    _HERE.parents[1],
    Path.cwd(),
]
for _root in _CANDIDATE_ROOTS:
    if (_root / "server" / "app.py").exists() and str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

try:
    from server.app import create_app  # type: ignore
except Exception:
    create_app = None
    for _root in _CANDIDATE_ROOTS:
        _server_app = _root / "server" / "app.py"
        if not _server_app.exists():
            continue
        spec = importlib.util.spec_from_file_location("mirrorview_server_app", _server_app)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)  # type: ignore[attr-defined]
            if hasattr(module, "create_app"):
                create_app = getattr(module, "create_app")
                break
    if create_app is None:
        raise ModuleNotFoundError("Unable to load create_app from server/app.py")

app = create_app()
