import json
import os
from pathlib import Path


def _load_json_config():
    base_path = Path(__file__).resolve().parent
    candidates = [
        base_path / "config.json",
        base_path / "config.json.example",
    ]

    for config_path in candidates:
        if not config_path.exists():
            continue
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError(f"{config_path.name} must be a JSON object.")
        return data

    raise FileNotFoundError(
        f"Missing config files. Expected one of: {', '.join(str(p) for p in candidates)}"
    )


def _to_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _to_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


_JSON_CONFIG = _load_json_config()
_PATH_CONFIG = _JSON_CONFIG.get("paths", {})
if not isinstance(_PATH_CONFIG, dict):
    _PATH_CONFIG = {}


class Config:
    basedir = Path(__file__).resolve().parent

    SECRET_KEY = os.environ.get("SECRET_KEY") or str(
        _JSON_CONFIG.get("SECRET_KEY", "dev-key-mirrorview")
    )

    # Database Configuration
    _default_data_dir = basedir / str(_PATH_CONFIG.get("data_dir", "instance"))
    # Vercel Serverless file system is read-only except /tmp.
    if os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"):
        _default_data_dir = Path("/tmp/mirrorview-data")
    data_dir = Path(
        os.environ.get("MIRRORVIEW_DATA_DIR", str(_default_data_dir))
    ).expanduser()
    _default_db_filename = str(_PATH_CONFIG.get("db_filename", "mirrorview.db"))
    _default_db_path = data_dir / _default_db_filename
    db_path = Path(
        os.environ.get("MIRRORVIEW_DB_PATH", str(_default_db_path))
    ).expanduser()

    SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path}"
    SQLALCHEMY_TRACK_MODIFICATIONS = _to_bool(
        _JSON_CONFIG.get("SQLALCHEMY_TRACK_MODIFICATIONS", False),
        default=False,
    )

    # RTMP Configuration
    RTMP_SERVER_URL = str(
        _JSON_CONFIG.get("RTMP_SERVER_URL", "rtmp://116.62.11.13:1935/live")
    )
    INTERVIEW_TTL_SECONDS = _to_int(
        _JSON_CONFIG.get("INTERVIEW_TTL_SECONDS", 3600),
        default=3600,
    )

    # ── AI: DeepSeek (OpenAI-compatible) ──
    # DeepSeek-V3 via OpenAI-compatible API
    # Priority: env var > config.json
    DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY") or str(
        _JSON_CONFIG.get("DEEPSEEK_API_KEY", "")
    )
    DEEPSEEK_BASE_URL = str(
        _JSON_CONFIG.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    )
    DEEPSEEK_MODEL = str(
        _JSON_CONFIG.get("DEEPSEEK_MODEL", "deepseek-chat")
    )

    # Platform default model route (used when runtime.mode == "platform")
    PLATFORM_PROVIDER = str(
        os.environ.get("PLATFORM_PROVIDER")
        or _JSON_CONFIG.get("PLATFORM_PROVIDER", "deepseek")
    ).strip().lower() or "deepseek"
    PLATFORM_MODEL = str(
        os.environ.get("PLATFORM_MODEL")
        or _JSON_CONFIG.get("PLATFORM_MODEL", DEEPSEEK_MODEL)
    ).strip() or DEEPSEEK_MODEL

    # Legacy DashScope — still configurable if someone has a key
    DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")

    # Optional provider keys for BYOK routing
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

    # Cloudflare Turnstile
    TURNSTILE_SITE_KEY = str(
        os.environ.get("TURNSTILE_SITE_KEY")
        or _JSON_CONFIG.get("TURNSTILE_SITE_KEY", "")
    )
    TURNSTILE_SECRET_KEY = str(
        os.environ.get("TURNSTILE_SECRET_KEY")
        or _JSON_CONFIG.get("TURNSTILE_SECRET_KEY", "")
    )
    TURNSTILE_VERIFY_URL = str(
        os.environ.get("TURNSTILE_VERIFY_URL")
        or _JSON_CONFIG.get(
            "TURNSTILE_VERIFY_URL",
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        )
    )
    TURNSTILE_ENFORCE = _to_bool(
        os.environ.get("TURNSTILE_ENFORCE", _JSON_CONFIG.get("TURNSTILE_ENFORCE", False)),
        default=False,
    )

    # Lightweight API guardrails (in-memory)
    RATE_LIMIT_ENFORCE = _to_bool(
        os.environ.get("RATE_LIMIT_ENFORCE", _JSON_CONFIG.get("RATE_LIMIT_ENFORCE", False)),
        default=False,
    )
    RATE_LIMIT_REQUESTS = _to_int(
        os.environ.get("RATE_LIMIT_REQUESTS", _JSON_CONFIG.get("RATE_LIMIT_REQUESTS", 30)),
        default=30,
    )
    RATE_LIMIT_WINDOW_SECONDS = _to_int(
        os.environ.get("RATE_LIMIT_WINDOW_SECONDS", _JSON_CONFIG.get("RATE_LIMIT_WINDOW_SECONDS", 60)),
        default=60,
    )

    # ── TTS: Boson.ai Higgs Audio v3 ──
    BOSON_API_KEY = os.environ.get("BOSON_API_KEY", "")

    # Resume Configuration
    _default_resume_folder = data_dir / str(
        _PATH_CONFIG.get("resume_upload_folder", "uploads/resumes")
    )
    RESUME_UPLOAD_FOLDER = os.environ.get(
        "MIRRORVIEW_RESUME_UPLOAD_FOLDER",
        str(_default_resume_folder),
    )
    _default_chroma_dir = data_dir / str(
        _PATH_CONFIG.get("chroma_db_dir", "chroma_db")
    )
    CHROMA_DB_DIR = os.environ.get(
        "MIRRORVIEW_CHROMA_DB_DIR",
        str(_default_chroma_dir),
    )

    # Ensure directories exist. Fallback to /tmp if current target is not writable.
    try:
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        Path(RESUME_UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)
        Path(CHROMA_DB_DIR).mkdir(parents=True, exist_ok=True)
    except Exception:
        _tmp_root = Path("/tmp/mirrorview-data")
        _tmp_resume = _tmp_root / "uploads" / "resumes"
        _tmp_chroma = _tmp_root / "chroma_db"

        _tmp_root.mkdir(parents=True, exist_ok=True)
        _tmp_resume.mkdir(parents=True, exist_ok=True)
        _tmp_chroma.mkdir(parents=True, exist_ok=True)

        data_dir = _tmp_root
        db_path = _tmp_root / _default_db_filename
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path}"
        RESUME_UPLOAD_FOLDER = str(_tmp_resume)
        CHROMA_DB_DIR = str(_tmp_chroma)
