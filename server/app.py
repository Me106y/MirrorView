from flask import Flask
from dotenv import load_dotenv
import os

# Load project-level env file before importing modules that read env at import time.
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(ROOT_DIR, ".env_tts"))

from server.config import Config
from server.models import db
from server.routes import api
# import pymysql
from sqlalchemy import text
from utils.logger_handler import logger


def create_app():
    # Ensure database exists before initializing app
    # create_database_if_not_exists()

    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)

    app.register_blueprint(api, url_prefix='/api')

    # --- TTS Integration ---
    # Register TTS API routes (Boson.ai Higgs Audio v3)
    try:
        from server.services.tts_service import HiggsAudioTTS
        from tts_integration.server.routes_tts import tts_bp

        app.config['TTS_SERVICE'] = HiggsAudioTTS(
            voice=os.environ.get('BOSON_TTS_VOICE', 'default'),
        )
        app.register_blueprint(tts_bp)
        logger.info("TTS service registered successfully")
    except ImportError as e:
        logger.warning(f"TTS integration not available: {e}")
    except Exception as e:
        logger.warning(f"TTS service init skipped: {e}")
    # --- End TTS Integration ---

    with app.app_context():
        # Create tables
        try:
            db.create_all()
            logger.info("Database tables created successfully.")


        except Exception as e:
            logger.error(f"Error creating tables: {e}")

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5001, debug=False)
