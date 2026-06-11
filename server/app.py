from flask import Flask
from server.config import Config
from server.models import db
from server.routes import api
import os
# import pymysql
from sqlalchemy import inspect, text
from utils.logger_handler import logger


def _ensure_users_table_columns():
    """
    Lightweight compatibility migration for existing SQLite databases.
    """
    inspector = inspect(db.engine)
    if 'users' not in inspector.get_table_names():
        return

    existing = {col['name'] for col in inspector.get_columns('users')}
    alter_sql = []

    if 'target_role' not in existing:
        alter_sql.append("ALTER TABLE users ADD COLUMN target_role VARCHAR(120)")
    if 'target_jd' not in existing:
        alter_sql.append("ALTER TABLE users ADD COLUMN target_jd TEXT")
    if 'resume_uploaded_at' not in existing:
        alter_sql.append("ALTER TABLE users ADD COLUMN resume_uploaded_at DATETIME")

    for statement in alter_sql:
        db.session.execute(text(statement))
    if alter_sql:
        db.session.commit()
        logger.info("Applied users table compatibility migration: %s", ", ".join(alter_sql))


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
            _ensure_users_table_columns()
            logger.info("Database tables created successfully.")


        except Exception as e:
            logger.error(f"Error creating tables: {e}")

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5001, debug=False)
