import os


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-mirrorview'

    # Database Configuration
    basedir = os.path.abspath(os.path.dirname(__file__))
    db_path = os.environ.get("MIRRORVIEW_DB_PATH",
                              os.path.join(basedir, 'instance', 'mirrorview.db'))
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{db_path}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # RTMP Configuration
    RTMP_SERVER_URL = "rtmp://116.62.11.13:1935/live"

    # ── AI: DeepSeek (OpenAI-compatible) ──
    # DeepSeek-V3 via OpenAI-compatible API
    # Set env: export DEEPSEEK_API_KEY="sk-xxx"
    _deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")
    DEEPSEEK_API_KEY = _deepseek_key
    DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL = "deepseek-chat"   # DeepSeek-V3

    # Legacy DashScope — still configurable if someone has a key
    _dashscope_key = os.environ.get("DASHSCOPE_API_KEY", "")
    DASHSCOPE_API_KEY = _dashscope_key

    # ── TTS: Boson.ai Higgs Audio v3 ──
    BOSON_API_KEY = os.environ.get("BOSON_API_KEY", "")

    # Resume Configuration
    RESUME_UPLOAD_FOLDER = os.path.join(basedir, 'uploads', 'resumes')
    CHROMA_DB_DIR = os.path.join(basedir, 'instance', 'chroma_db')

    # Ensure directories exist
    os.makedirs(RESUME_UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(CHROMA_DB_DIR, exist_ok=True)
