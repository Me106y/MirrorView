from flask import Blueprint, request, jsonify, current_app, Response, stream_with_context
from server.models import db, User, Interview, Message, InviteCode, Listener
from server.services.ai_service import AIService
from server.services.rtmp_service import RTMPService
from utils.logger_handler import logger
from datetime import datetime
import uuid

api = Blueprint('api', __name__)

ai_service = AIService()
rtmp_service = RTMPService("rtmp://116.62.11.13:1935/live") # Hardcoded for now, or from config

@api.route('/auth/register', methods=['POST'])
def register():
    data = request.json
    if User.query.filter_by(username=data.get('username')).first():
        return jsonify({'message': 'Username already exists'}), 400
        
    user = User(
        username=data.get('username'),
        # email=data.get('email'), # Removed
        job_intention=data.get('job_intention'),
        work_experience=data.get('work_experience')
    )
    user.set_password(data.get('password'))
    db.session.add(user)
    db.session.commit()
    return jsonify({'message': 'User registered successfully', 'user_id': user.id}), 201

@api.route('/auth/login', methods=['POST'])
def login():
    data = request.json
    user = User.query.filter_by(username=data.get('username')).first()
    if user and user.check_password(data.get('password')):
        return jsonify({
            'message': 'Login successful', 
            'user_id': user.id,
            'username': user.username,
            'job_intention': user.job_intention
        }), 200
    return jsonify({'message': 'Invalid username or password'}), 401

from server.config import Config
import os
import json

def _is_interview_expired(interview):
    if not interview or not interview.start_time:
        return False
    if interview.status == 3:
        return False
    ttl = getattr(Config, 'INTERVIEW_TTL_SECONDS', 3600)
    return (datetime.utcnow() - interview.start_time).total_seconds() > ttl

def _delete_interview(interview):
    if not interview:
        return
    Message.query.filter_by(interview_id=interview.id).delete(synchronize_session=False)
    InviteCode.query.filter_by(interview_id=interview.id).delete(synchronize_session=False)
    Listener.query.filter_by(interview_id=interview.id).delete(synchronize_session=False)
    db.session.delete(interview)
    db.session.commit()

@api.route('/user/<int:user_id>/upload_resume', methods=['POST'])
def upload_resume(user_id):
    if 'resume' not in request.files:
        return jsonify({'message': 'No file part'}), 400
    file = request.files['resume']
    if file.filename == '':
        return jsonify({'message': 'No selected file'}), 400
    
    if file and file.filename.endswith('.pdf'):
        user = User.query.get_or_404(user_id)
        
        filename = f"resume_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
        file_path = os.path.join(Config.RESUME_UPLOAD_FOLDER, filename)
        file.save(file_path)
        
        user.resume_path = file_path
        user.has_resume = True
        db.session.commit()
        
        # Index resume immediately for RAG
        from server.services.resume_service import ResumeService
        resume_service = ResumeService()
        resume_service.index_resume(user_id, file_path)
        
        return jsonify({'message': 'Resume uploaded successfully'}), 200
    
    return jsonify({'message': 'Invalid file type'}), 400

@api.route('/user/<int:user_id>/update_profile', methods=['POST'])
def update_profile(user_id):
    data = request.json
    user = User.query.get_or_404(user_id)
    
    if 'job_intention' in data:
        user.job_intention = data['job_intention']
    if 'work_experience' in data:
        user.work_experience = data['work_experience']
        
    db.session.commit()
    return jsonify({'message': 'Profile updated successfully'}), 200

@api.route('/interview/create', methods=['POST'])
def create_interview():
    data = request.json
    user_id = data.get('user_id')
    
    user = User.query.get(user_id)
    if not user:
         return jsonify({'message': 'User not found'}), 404
         
    # Check if user has active interview
    active_interview = Interview.query.filter_by(user_id=user_id, status=1).first()
    if active_interview:
        if _is_interview_expired(active_interview):
            _delete_interview(active_interview)
        else:
            return jsonify({'message': 'You have an ongoing interview. Please finish it before starting a new one.'}), 400

    # Use user's job intention directly
    job_position = user.job_intention
    if not job_position:
        return jsonify({'message': 'Please set your job intention in your profile first.'}), 400

    resume_text = None
    projects_summary = None
    
    if user.has_resume and user.resume_path and os.path.exists(user.resume_path):
        from server.services.resume_service import ResumeService
        resume_service = ResumeService()
        resume_text = resume_service.parse_resume(user.resume_path)
        
        if resume_text:
            # Analyze resume only to extract projects, NOT to override job intention
            analysis = ai_service.analyze_resume_and_update_job(user_id, resume_text, job_position)
            projects_summary = analysis.get('projects_summary')

    interview = Interview(
        user_id=user_id,
        title=f"{job_position} Interview - {datetime.now().strftime('%Y-%m-%d')}",
        job_position=job_position,
        questions_count=10,
        status=1, # Ongoing
        start_time=datetime.utcnow()
    )
    
    db.session.add(interview)
    db.session.flush() # Generate ID
    
    interview.rtmp_push_url = rtmp_service.generate_push_url(interview.id, user_id)
    interview.rtmp_play_url = rtmp_service.generate_play_url(interview.rtmp_push_url)
    
    # Generate questions upfront or just first one?
    # Let's generate the full list stored in memory/DB or just generate first question dynamically
    # For now, we'll generate the first greeting.
    # Ideally we should generate the list of 10 questions and store them to ask sequentially.
    # But current architecture seems to be chat-based loop.
    # Let's generate the questions list and store it in a temporary state or message?
    # Simpler: The AI service will maintain the state or we generate them now and system prompts the AI to ask them.
    
    questions = ai_service.generate_interview_questions(job_position, resume_text, projects_summary)
    # We could store these questions in a new table 'InterviewQuestions' or just as a system prompt for the chat context.
    # For simplicity, let's inject them into the system context for the chat model in future turns.
    # Or better: Add a hidden system message with the plan.
    
    system_instruction = f"You are interviewing for {job_position}. Here is your question plan: {json.dumps(questions)}. Ask them one by one. Start with the first one."
    
    # Initial greeting from AI
    greeting = f"你好，我是你的面试官。我们现在开始进行{job_position}岗位的面试。请先做一个简单的自我介绍。"
    
    # Store system instruction as a hidden message or just handle it in AI service state?
    # Stateless API: We need to store it.
    # Let's store the questions plan in a special message or field.
    # For now, we'll just let the chat flow naturally but with the Resume context available in AI service.
    
    initial_msg = Message(
        interview_id=interview.id,
        role='agent',
        content=greeting
    )
    db.session.add(initial_msg)
    
    db.session.commit()
    
    return jsonify({
        'interview_id': interview.id,
        'rtmp_push_url': interview.rtmp_push_url,
        'initial_message': greeting
    }), 201

@api.route('/interview/<int:interview_id>/messages', methods=['GET', 'POST'])
def handle_messages(interview_id):
    if request.method == 'POST':
        interview = Interview.query.get(interview_id)
        if not interview:
            return jsonify({'message': 'Interview not found'}), 404
        if _is_interview_expired(interview):
            _delete_interview(interview)
            return jsonify({'message': 'Interview expired and has been deleted.'}), 410

        data = request.json
        user_msg = Message(
            interview_id=interview_id,
            role='user',
            content=data.get('content'),
            original_content=data.get('original_content'),
            question_type=data.get('question_type')
        )
        db.session.add(user_msg)
        db.session.commit() # Commit user message first
        
        if data.get('stream'):
            # Pre-fetch data to avoid DetachedInstanceError inside generator
            user_content = data.get('content')
            
            def generate():
                with current_app.app_context():
                    interview = Interview.query.get(interview_id)
                    job_position = interview.job_position if interview else "General"
                    
                    messages = Message.query.filter_by(interview_id=interview_id).order_by(Message.created_at).all()
                    messages_list = [{'role': m.role, 'content': m.content} for m in messages]
                    
                    full_response = ""
                    for chunk in ai_service.chat_response_stream(messages_list, user_content, job_position):
                        full_response += chunk
                        yield f"data: {json.dumps({'content': chunk})}\n\n"
                    
                    ai_msg = Message(
                        interview_id=interview_id,
                        role='agent',
                        content=full_response
                    )
                    db.session.add(ai_msg)
                    db.session.commit()
                    
                    yield f"data: {json.dumps({'done': True})}\n\n"

            return Response(stream_with_context(generate()), mimetype='text/event-stream')
        
        else:
            # Existing non-streaming logic
            # Evaluate user's answer
            last_agent_msg = Message.query.filter_by(interview_id=interview_id, role='agent').order_by(Message.created_at.desc()).first()
            if last_agent_msg:
                user_id = interview.user_id if interview else None
                evaluation = ai_service.evaluate_answer(last_agent_msg.content, user_msg.content, user_id)
                logger.info(f"Answer evaluation: {evaluation}")

            # Get context
            job_position = interview.job_position if interview else "General"
            messages = Message.query.filter_by(interview_id=interview_id).order_by(Message.created_at).all()
            messages_list = [{'role': m.role, 'content': m.content} for m in messages]
            
            # Generate AI response
            ai_response_content = ai_service.chat_response(messages_list, user_msg.content, job_position)
            
            ai_msg = Message(
                interview_id=interview_id,
                role='agent',
                content=ai_response_content
            )
            db.session.add(ai_msg)
            db.session.commit()
            
            return jsonify({'response': ai_response_content}), 201
        
    else:
        interview = Interview.query.get(interview_id)
        if not interview:
            return jsonify({'message': 'Interview not found'}), 404
        if _is_interview_expired(interview):
            _delete_interview(interview)
            return jsonify({'message': 'Interview expired and has been deleted.'}), 410

        messages = Message.query.filter_by(interview_id=interview_id).order_by(Message.created_at).all()
        return jsonify([{
            'role': m.role,
            'content': m.content,
            'created_at': m.created_at.isoformat()
        } for m in messages]), 200

@api.route('/interview/<int:interview_id>/finish', methods=['POST'])
def finish_interview(interview_id):
    interview = Interview.query.get_or_404(interview_id)
    if _is_interview_expired(interview):
        _delete_interview(interview)
        return jsonify({'message': 'Interview expired and has been deleted.'}), 410

    interview.status = 2 # Ended
    interview.end_time = datetime.utcnow()
    
    # Generate feedback
    feedback = ai_service.generate_feedback(interview)
    
    # Ensure feedback is stored as JSON string, not dict, for SQLite
    if isinstance(feedback, dict):
        interview.overall_feedback = json.dumps(feedback)
    else:
        interview.overall_feedback = str(feedback)
        
    interview.status = 3 # Reviewed
    
    db.session.commit()
    return jsonify({'message': 'Interview finished', 'feedback': feedback}), 200


@api.route('/user/<int:user_id>/history', methods=['GET'])
def get_interview_history(user_id):
    interviews = Interview.query.filter_by(user_id=user_id).order_by(Interview.created_at.desc()).all()
    expired = []
    result = []
    for interview in interviews:
        if _is_interview_expired(interview):
            expired.append(interview)
            continue
        result.append({
            'id': interview.id,
            'title': interview.title,
            'job_position': interview.job_position,
            'status': interview.status, # 1-ongoing, 2-ended, 3-reviewed
            'created_at': interview.created_at.isoformat(),
            'end_time': interview.end_time.isoformat() if interview.end_time else None,
            'overall_feedback': interview.overall_feedback,
            'rtmp_play_url': interview.rtmp_play_url
        })
    for interview in expired:
        _delete_interview(interview)
    return jsonify(result), 200

@api.route('/interview/<int:interview_id>/rejoin', methods=['GET'])
def rejoin_interview(interview_id):
    interview = Interview.query.get_or_404(interview_id)
    if _is_interview_expired(interview):
        _delete_interview(interview)
        return jsonify({'message': 'Interview expired and has been deleted.'}), 410
    if interview.status != 1:
        return jsonify({'message': 'Interview is not active'}), 400
        
    # Get initial or last agent message to display?
    # Actually client just needs rtmp url and maybe last message
    
    last_msg = Message.query.filter_by(interview_id=interview_id, role='agent').order_by(Message.created_at.desc()).first()
    greeting = last_msg.content if last_msg else "Welcome back."
    
    return jsonify({
        'interview_id': interview.id,
        'rtmp_push_url': interview.rtmp_push_url,
        'initial_message': greeting, # Re-use this field to show last message
        'rejoin': True
    }), 200


@api.route('/interview/<int:interview_id>/status', methods=['GET'])
def get_interview_status(interview_id):
    interview = Interview.query.get(interview_id)
    if not interview:
        return jsonify({'message': 'Interview not found'}), 404
    if _is_interview_expired(interview):
        _delete_interview(interview)
        return jsonify({'message': 'Interview expired and has been deleted.'}), 410
    return jsonify({'status': interview.status}), 200

@api.route('/invite/create', methods=['POST'])
def create_invite_code():
    data = request.json
    interview_id = data.get('interview_id')
    user_id = data.get('user_id')
    
    code_str = str(uuid.uuid4())[:8] # Simple implementation
    invite = InviteCode(
        code=code_str,
        interview_id=interview_id,
        created_by=user_id
    )
    db.session.add(invite)
    db.session.commit()
    return jsonify({'code': code_str}), 201

@api.route('/invite/join', methods=['POST'])
def join_interview():
    data = request.json
    code_str = data.get('code')
    listener_name = data.get('listener_id', 'Anonymous')
    
    invite = InviteCode.query.filter_by(code=code_str).first()
    if not invite:
        return jsonify({'message': 'Invalid code'}), 400
        
    interview = Interview.query.get(invite.interview_id)
    if interview and _is_interview_expired(interview):
        _delete_interview(interview)
        return jsonify({'message': 'Interview is not live'}), 400
    if not interview or interview.status != 1: # Not ongoing
         return jsonify({'message': 'Interview is not live'}), 400
         
    # Log listener
    import uuid
    listener = Listener(
        interview_id=interview.id,
        invite_code_id=invite.id,
        listener_id=str(uuid.uuid4()),
        listener_name=listener_name
    )
    db.session.add(listener)
    db.session.commit()
    
    return jsonify({
        'interview_id': interview.id, 
        'job_position': interview.job_position,
        'rtmp_play_url': interview.rtmp_play_url,
        'listener_name': listener_name
    }), 200

@api.route('/interview/<int:interview_id>/observers', methods=['GET'])
def get_interview_observers(interview_id):
    interview = Interview.query.get(interview_id)
    if interview and _is_interview_expired(interview):
        _delete_interview(interview)
        return jsonify([]), 200
    listeners = Listener.query.filter_by(interview_id=interview_id).all()
    # Unique by name? Or just list all connections
    seen = set()
    unique_listeners = []
    for l in listeners:
        if l.listener_name not in seen:
            unique_listeners.append({
                'name': l.listener_name,
                'joined_at': l.joined_at.isoformat()
            })
            seen.add(l.listener_name)
    return jsonify(unique_listeners), 200
