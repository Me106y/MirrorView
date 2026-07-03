from flask import Blueprint, request, jsonify, current_app, Response, stream_with_context
from server.models import db, User, Interview, Message, InviteCode, Listener
from server.services.ai_service import AIService
from server.services.careerforge_command_agent import CareerForgeCommandAgent
from server.services.rtmp_service import RTMPService
from server.services.resume_service import ResumeService
from utils.logger_handler import logger
from datetime import datetime
import uuid
import tempfile

api = Blueprint('api', __name__)

ai_service = AIService()
command_agent = CareerForgeCommandAgent(ai_service)
rtmp_service = RTMPService("rtmp://116.62.11.13:1935/live") # Hardcoded for now, or from config

@api.route('/auth/register', methods=['POST'])
def register():
    data = request.json
    if User.query.filter_by(username=data.get('username')).first():
        return jsonify({'message': 'Username already exists'}), 400

    target_role = (data.get('target_role') or data.get('job_intention') or '').strip()
    user = User(
        username=data.get('username'),
        # email=data.get('email'), # Removed
        job_intention=target_role,
        target_role=target_role,
        target_jd=(data.get('target_jd') or '').strip(),
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
        role = user.target_role or user.job_intention
        return jsonify({
            'message': 'Login successful', 
            'user_id': user.id,
            'username': user.username,
            'job_intention': role,
            'target_role': role,
            'target_jd': user.target_jd,
            'work_experience': user.work_experience,
            'has_resume': bool(user.has_resume),
            'resume_path': user.resume_path,
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


def _extract_resume_text(data):
    """
    Extract resume text from JSON field or uploaded file.
    Supports:
    - data["resume_text"] in JSON/form
    - request.files["resume"] (pdf/txt/md/docx as plain fallback)
    """
    resume_text = (data or {}).get('resume_text', '') or ''
    resume_text = resume_text.strip()
    if resume_text:
        return resume_text

    if 'resume' not in request.files:
        return ""

    file = request.files['resume']
    if not file or not file.filename:
        return ""

    suffix = os.path.splitext(file.filename)[1].lower() or ".txt"
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            file.save(tmp.name)
            temp_path = tmp.name

        if suffix == ".pdf":
            resume_service = ResumeService()
            return (resume_service.parse_resume(temp_path) or "").strip()

        with open(temp_path, "rb") as f:
            return f.read().decode("utf-8", errors="ignore").strip()
    except Exception as e:
        logger.error(f"Failed to parse uploaded resume: {e}")
        return ""
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

@api.route('/user/<int:user_id>/upload_resume', methods=['POST'])
def upload_resume(user_id):
    if 'resume' not in request.files:
        return jsonify({'message': 'No file part'}), 400
    file = request.files['resume']
    if file.filename == '':
        return jsonify({'message': 'No selected file'}), 400
    
    if file and file.filename.endswith('.pdf'):
        user = User.query.get_or_404(user_id)

        # Keep only the latest resume for each user.
        filename = f"resume_{user_id}.pdf"
        file_path = os.path.join(Config.RESUME_UPLOAD_FOLDER, filename)
        file.save(file_path)
        
        user.resume_path = file_path
        user.has_resume = True
        user.resume_uploaded_at = datetime.utcnow()
        db.session.commit()
        
        # Index resume immediately for RAG
        from server.services.resume_service import ResumeService
        resume_service = ResumeService()
        resume_service.index_resume(user_id, file_path)
        
        return jsonify({'message': 'Resume uploaded successfully'}), 200
    
    return jsonify({'message': 'Invalid file type'}), 400


@api.route('/user/<int:user_id>/profile', methods=['GET'])
def get_profile(user_id):
    user = User.query.get_or_404(user_id)
    role = user.target_role or user.job_intention or ''
    return jsonify(
        {
            'user_id': user.id,
            'username': user.username,
            'target_role': role,
            'job_intention': role,
            'target_jd': user.target_jd or '',
            'work_experience': user.work_experience or '',
            'has_resume': bool(user.has_resume),
            'resume_path': user.resume_path,
        }
    ), 200

@api.route('/user/<int:user_id>/update_profile', methods=['POST'])
def update_profile(user_id):
    data = request.json or {}
    user = User.query.get_or_404(user_id)

    target_role = None
    if 'target_role' in data:
        target_role = (data.get('target_role') or '').strip()
    elif 'job_intention' in data:
        target_role = (data.get('job_intention') or '').strip()

    if target_role is not None:
        user.target_role = target_role
        # Keep legacy field in sync for old code paths.
        user.job_intention = target_role

    if 'target_jd' in data:
        user.target_jd = (data.get('target_jd') or '').strip()
    if 'work_experience' in data:
        user.work_experience = data['work_experience']
        
    db.session.commit()
    return jsonify({'message': 'Profile updated successfully'}), 200


@api.route('/careerforge/resume-match', methods=['POST'])
def careerforge_resume_match():
    data = request.get_json(silent=True)
    if data is None:
        data = request.form.to_dict() if request.form else {}

    resume_text = _extract_resume_text(data)
    jd_text = (data.get('jd_text') or '').strip()
    target_role = (data.get('target_role') or '').strip()

    if not resume_text:
        return jsonify({'message': 'Please provide resume_text or upload a resume file.'}), 400
    if not jd_text:
        return jsonify({'message': 'Please provide jd_text.'}), 400

    result = ai_service.run_resume_match(
        {
            "resume_text": resume_text[:20000],
            "jd_text": jd_text[:12000],
            "target_role": target_role,
        }
    )
    return jsonify(
        {
            "skill": "resume-match",
            "result": result,
            "process": [
                "Loaded CareerForge resume-match skill",
                "Parsed resume and JD context",
                "Generated matching report",
            ],
        }
    ), 200


@api.route('/careerforge/resume-craft', methods=['POST'])
def careerforge_resume_craft():
    data = request.get_json(silent=True)
    if data is None:
        data = request.form.to_dict() if request.form else {}

    resume_text = _extract_resume_text(data)
    target_role = (data.get('target_role') or '').strip()
    language = (data.get('language') or 'zh').strip()
    template_name = (data.get('template') or '').strip()
    optimization_goal = (data.get('optimization_goal') or '').strip()

    if not resume_text:
        return jsonify({'message': 'Please provide resume_text or upload a resume file.'}), 400

    result = ai_service.run_resume_craft(
        {
            "resume_text": resume_text[:24000],
            "target_role": target_role,
            "language": language,
            "template": template_name,
            "optimization_goal": optimization_goal,
        }
    )
    return jsonify(
        {
            "skill": "resume-craft",
            "result": result,
            "process": [
                "Loaded CareerForge resume-craft skill",
                "Built optimized resume content",
                "Prepared visual style and next actions",
            ],
        }
    ), 200


@api.route('/careerforge/cover-letter', methods=['POST'])
def careerforge_cover_letter():
    data = request.get_json(silent=True)
    if data is None:
        data = request.form.to_dict() if request.form else {}

    resume_text = _extract_resume_text(data)
    jd_text = (data.get('jd_text') or '').strip()
    scenario = (data.get('scenario') or 'email').strip()
    language = (data.get('language') or 'zh').strip()
    company_name = (data.get('company_name') or '').strip()

    if not jd_text:
        return jsonify({'message': 'Please provide jd_text.'}), 400
    if not resume_text:
        return jsonify({'message': 'Please provide resume_text or upload a resume file.'}), 400

    result = ai_service.run_cover_letter(
        {
            "resume_text": resume_text[:20000],
            "jd_text": jd_text[:12000],
            "scenario": scenario,
            "language": language,
            "company_name": company_name,
        }
    )
    return jsonify(
        {
            "skill": "cover-letter",
            "result": result,
            "process": [
                "Loaded CareerForge cover-letter skill",
                "Matched resume highlights to JD",
                "Generated tailored output",
            ],
        }
    ), 200


@api.route('/careerforge/job-hunt', methods=['POST'])
def careerforge_job_hunt():
    data = request.get_json(silent=True)
    if data is None:
        data = request.form.to_dict() if request.form else {}

    resume_text = _extract_resume_text(data)
    target_role = (data.get('target_role') or data.get('job_intention') or '').strip()
    target_jd = (data.get('target_jd') or data.get('jd_text') or '').strip()
    work_experience = (data.get('work_experience') or '').strip()
    target_regions = data.get('target_regions') or data.get('target_region') or []
    target_cities = data.get('target_cities') or data.get('target_city') or []
    salary_range = (data.get('salary_range') or '').strip()
    hard_requirements = data.get('hard_requirements') or []
    platforms = data.get('platforms') or []

    if isinstance(target_regions, str):
        target_regions = [target_regions]
    if isinstance(target_cities, str):
        target_cities = [target_cities]
    if isinstance(hard_requirements, str):
        hard_requirements = [hard_requirements]
    if isinstance(platforms, str):
        platforms = [platforms]

    if not target_role and not resume_text:
        return jsonify({'message': 'Please provide target_role or resume_text.'}), 400

    result = ai_service.run_job_hunt(
        {
            "resume_text": resume_text[:24000],
            "target_role": target_role,
            "target_jd": target_jd[:12000],
            "work_experience": work_experience,
            "target_regions": target_regions,
            "target_cities": target_cities,
            "salary_range": salary_range,
            "hard_requirements": hard_requirements,
            "platforms": platforms,
        }
    )
    return jsonify(
        {
            "skill": "job-hunt",
            "result": result,
            "process": [
                "Loaded CareerForge job-hunt skill",
                "Built search strategy from profile and constraints",
                "Generated prioritized opportunities",
            ],
        }
    ), 200


@api.route('/careerforge/agent/chat', methods=['POST'])
def careerforge_agent_chat():
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    message = (data.get('message') or '').strip()
    history = data.get('history') or []

    if not message:
        return (
            jsonify(
                {
                    "reply": "请输入消息内容。",
                    "intent": "unknown",
                    "action": "noop",
                    "missing_fields": [],
                    "result": {},
                    "artifacts": [],
                    "error": "empty_message",
                }
            ),
            400,
        )

    if isinstance(user_id, str):
        user_id = user_id.strip() or None
        if user_id is not None:
            try:
                user_id = int(user_id)
            except ValueError:
                user_id = None
    elif user_id is not None:
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            user_id = None

    if not isinstance(history, list):
        history = []

    result = command_agent.handle_chat(
        user_id=user_id,
        message=message,
        history=history,
    )

    status_code = 200
    if result.get("error"):
        status_code = 400
    return jsonify(result), status_code

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

    # Prefer new profile field and keep backward compatibility.
    job_position = user.target_role or user.job_intention
    if not job_position:
        return jsonify({'message': 'Please set your target role in your profile first.'}), 400

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
    
    # Initial greeting from mock-interview skill runtime
    greeting = ai_service.generate_mock_interview_opening(
        job_position=job_position,
        resume_summary=(projects_summary or ""),
    )
    
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
