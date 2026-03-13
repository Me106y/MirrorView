from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import json

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    job_intention = db.Column(db.String(100))
    work_experience = db.Column(db.String(50), default='No experience') # Changed from integer work_years
    resume_path = db.Column(db.String(200))
    has_resume = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    last_login = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    interviews = db.relationship('Interview', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Interview(db.Model):
    __tablename__ = 'interviews'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200))
    job_position = db.Column(db.String(100), nullable=False)
    questions_count = db.Column(db.Integer, default=10)
    # difficulty = db.Column(db.String(20), default='medium') # Removed
    # duration = db.Column(db.Integer) # in minutes # Removed
    status = db.Column(db.Integer, default=0) # 0-pending, 1-ongoing, 2-ended, 3-reviewed
    rtmp_push_url = db.Column(db.String(200))
    rtmp_play_url = db.Column(db.String(200))
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    total_score = db.Column(db.Float)
    overall_feedback = db.Column(db.Text) # JSON string
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    messages = db.relationship('Message', backref='interview', lazy=True)
    invite_codes = db.relationship('InviteCode', backref='interview', lazy=True)
    listeners = db.relationship('Listener', backref='interview', lazy=True)

class Message(db.Model):
    __tablename__ = 'messages'
    
    id = db.Column(db.Integer, primary_key=True)
    interview_id = db.Column(db.Integer, db.ForeignKey('interviews.id'), nullable=False)
    role = db.Column(db.String(10), nullable=False) # 'user' or 'agent'
    content = db.Column(db.Text, nullable=False)
    original_content = db.Column(db.Text)
    asr_confidence = db.Column(db.Float)
    response_time = db.Column(db.Integer)
    question_type = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class InviteCode(db.Model):
    __tablename__ = 'invite_codes'
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    interview_id = db.Column(db.Integer, db.ForeignKey('interviews.id'), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    max_uses = db.Column(db.Integer, default=10)
    current_uses = db.Column(db.Integer, default=0)
    expires_at = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Listener(db.Model):
    __tablename__ = 'listeners'
    
    id = db.Column(db.Integer, primary_key=True)
    interview_id = db.Column(db.Integer, db.ForeignKey('interviews.id'), nullable=False)
    invite_code_id = db.Column(db.Integer, db.ForeignKey('invite_codes.id'))
    listener_id = db.Column(db.String(100))
    listener_name = db.Column(db.String(50))
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    left_at = db.Column(db.DateTime)
    watch_duration = db.Column(db.Integer)
