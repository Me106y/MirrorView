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

    # Legacy DashScope — still configurable if someone has a key
    DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")

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

    # Ensure directories exist
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    Path(RESUME_UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)
    Path(CHROMA_DB_DIR).mkdir(parents=True, exist_ok=True)
