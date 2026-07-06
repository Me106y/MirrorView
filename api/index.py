"""Vercel Python entrypoint for MirrorView backend API."""

import importlib.util
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_CANDIDATE_ROOTS = [
    _HERE.parent,
    _HERE.parent / "_runtime",
    _HERE.parents[1],
    Path.cwd(),
]


def _load_create_app():
    # Prefer loading server/app.py by file path so we don't depend on package import
    # behavior in serverless bundle layout.
    for _root in _CANDIDATE_ROOTS:
        _server_app = _root / "server" / "app.py"
        if not _server_app.exists():
            continue

        if str(_root) not in sys.path:
            sys.path.insert(0, str(_root))

        try:
            # Fast path when package import works.
            from server.app import create_app as imported_create_app  # type: ignore
            return imported_create_app
        except Exception:
            pass

        spec = importlib.util.spec_from_file_location("mirrorview_server_app", _server_app)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)  # type: ignore[attr-defined]
            if hasattr(module, "create_app"):
                return getattr(module, "create_app")

    looked = ", ".join(str(p / "server" / "app.py") for p in _CANDIDATE_ROOTS)
    raise ModuleNotFoundError(f"Unable to load create_app from server/app.py. looked_in=[{looked}]")


create_app = _load_create_app()

app = create_app()
