from flask import Flask
from server.config import Config
from server.models import db
from server.routes import api
import os
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
    app.run(host='0.0.0.0', port=5001, debug=True)
