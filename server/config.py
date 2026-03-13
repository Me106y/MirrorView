import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-mirrorview'
    
    # Database Configuration
    # Use SQLite for easier local setup
    basedir = os.path.abspath(os.path.dirname(__file__))
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'instance', 'mirrorview.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # RTMP Configuration
    RTMP_SERVER_URL = "rtmp://116.62.11.13:1935/live"
    
    # AI Configuration
    DASHSCOPE_API_KEY = "sk-8729b18340b84faa97760edd5ad2f0d2"
    
    # Resume Configuration
    RESUME_UPLOAD_FOLDER = os.path.join(basedir, 'uploads', 'resumes')
    CHROMA_DB_DIR = os.path.join(basedir, 'instance', 'chroma_db')
    
    # Ensure directories exist
    os.makedirs(RESUME_UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(CHROMA_DB_DIR, exist_ok=True)
