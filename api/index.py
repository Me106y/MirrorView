"""Vercel Python entrypoint for MirrorView backend API."""

import importlib.util
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_CANDIDATE_ROOTS = [
    _HERE.parent,
    _HERE.parent / "api",
    _HERE.parents[1],
    _HERE.parents[1] / "api",
    Path.cwd(),
]

# Ensure imports prefer files colocated with api/index.py.
_PRIMARY_IMPORT_ROOTS = [_HERE.parent]
for _root in reversed(_PRIMARY_IMPORT_ROOTS):
    _path = str(_root)
    if _path in sys.path:
        sys.path.remove(_path)
    sys.path.insert(0, _path)

for _root in _CANDIDATE_ROOTS:
    _path = str(_root)
    if _path not in sys.path:
        sys.path.append(_path)

# Static import first so Vercel packager can trace local dependency files.
try:
    from server.app import create_app as _static_create_app  # type: ignore
    _STATIC_IMPORT_ERROR = None
except Exception as exc:
    _static_create_app = None
    _STATIC_IMPORT_ERROR = repr(exc)


def _candidate_server_app_paths():
    rels = (
        ("server", "app.py"),
        ("api", "server", "app.py"),
        ("_runtime", "server", "app.py"),
    )
    seen = set()
    for root in _CANDIDATE_ROOTS:
        for rel in rels:
            p = root.joinpath(*rel)
            if p in seen:
                continue
            seen.add(p)
            yield p


def _safe_list_dir(path: Path, limit: int = 40) -> str:
    try:
        if not path.exists():
            return "<missing>"
        if not path.is_dir():
            return "<not-dir>"
        items = []
        for child in sorted(path.iterdir(), key=lambda p: p.name)[:limit]:
            suffix = "/" if child.is_dir() else ""
            items.append(f"{child.name}{suffix}")
        return ", ".join(items) if items else "<empty>"
    except Exception as exc:
        return f"<error:{exc}>"


def _load_create_app():
    if _static_create_app is not None:
        return _static_create_app

    # Prefer loading server/app.py by file path so we don't depend on package import
    # behavior in serverless bundle layout.
    for _server_app in _candidate_server_app_paths():
        if not _server_app.exists():
            continue

        spec = importlib.util.spec_from_file_location("mirrorview_server_app", _server_app)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)  # type: ignore[attr-defined]
            if hasattr(module, "create_app"):
                return getattr(module, "create_app")

    looked = ", ".join(str(p) for p in _candidate_server_app_paths())
    api_dir = _HERE.parent
    task_dir = _HERE.parents[1]
    raise ModuleNotFoundError(
        "Unable to load create_app from server/app.py. "
        f"looked_in=[{looked}] "
        f"static_import_error={_STATIC_IMPORT_ERROR} "
        f"dir_api=[{_safe_list_dir(api_dir)}] "
        f"dir_task=[{_safe_list_dir(task_dir)}]"
    )


create_app = _load_create_app()

app = create_app()
