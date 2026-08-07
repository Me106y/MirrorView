from flask import Blueprint, request, jsonify, current_app, Response, stream_with_context, redirect, make_response
from client.core.resume_match_report import build_resume_match_html_report
from server.models import db, User, Interview, Message, InviteCode, Listener
from server.services.ai_service import AIService
from server.services.careerforge_command_agent import CareerForgeCommandAgent
from server.services.rtmp_service import RTMPService
from server.services.resume_service import ResumeService
from server.runtime_request import build_runtime_meta, parse_runtime_payload
from server.security import enforce_high_cost_guard
from server.config import Config
from utils.logger_handler import logger
from datetime import datetime
import base64
import binascii
import hashlib
import hmac
import secrets
import tempfile
import time
import os
import re
import requests
import subprocess
import sys
from html import unescape
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode, urlsplit, quote, unquote

api = Blueprint('api', __name__)

ai_service = AIService()
command_agent = CareerForgeCommandAgent(ai_service)
rtmp_service = RTMPService(Config.RTMP_SERVER_URL)

HIGH_COST_ENDPOINTS = {
    "resume-match",
    "resume-craft",
    "cover-letter",
    "mock-interview",
}

RESUME_CRAFT_TEMPLATE_MAP: Dict[str, Tuple[str, str]] = {
    "01": ("Editorial", "Editorial 杂志编辑风"),
    "02": ("Minimal", "Minimal 极简主义"),
    "03": ("Sidebar Navy", "Sidebar Navy 深蓝双栏"),
    "04": ("Sidebar Dark", "Sidebar Dark 深灰左栏"),
    "05": ("Dark Header", "Dark Header 深色头部"),
    "06": ("Clean Teal", "Clean Teal 清新青色"),
    "07": ("Elegant", "Elegant 优雅对称"),
}
RESUME_CRAFT_PHOTO_TOKEN = "__PHOTO_DATA_URL__"
RESUME_CRAFT_MAX_PHOTO_DATA_URL_LENGTH = 2_000_000
RESUME_CRAFT_HTML_ARTIFACT_TTL_SECONDS = 30 * 60
RESUME_CRAFT_HTML_ARTIFACT_MAX_ITEMS = 64
_RESUME_CRAFT_HTML_ARTIFACTS: Dict[str, Tuple[float, str]] = {}
@api.route('/health', methods=['GET'])
def health():
    return jsonify(
        {
            "ok": True,
            "service": "mirrorview-api",
            "env": "vercel" if (os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV")) else "local",
        }
    ), 200


@api.route('/debug/oauth', methods=['GET'])
def debug_oauth():
    """Diagnostic endpoint to check OAuth configuration."""
    from server.config import Config
    db_ok = False
    db_error = None
    try:
        User.query.first()
        db_ok = True
    except Exception as e:
        db_error = str(e)

    return jsonify({
        "github_client_id_set": bool(Config.GITHUB_CLIENT_ID),
        "github_client_id_preview": (Config.GITHUB_CLIENT_ID[:4] + "..." if Config.GITHUB_CLIENT_ID else None),
        "github_client_secret_set": bool(Config.GITHUB_CLIENT_SECRET),
        "public_base_url_configured": Config.PUBLIC_BASE_URL or None,
        "public_base_url_resolved": _get_public_base_url(),
        "github_callback_base_url_configured": Config.GITHUB_CALLBACK_BASE_URL or None,
        "github_callback_base_url_resolved": _get_github_callback_base_url(),
        "request_host": request.host,
        "request_url_root": request.url_root,
        "db_uri": Config.SQLALCHEMY_DATABASE_URI,
        "db_ok": db_ok,
        "db_error": db_error,
        "vercel": bool(os.environ.get("VERCEL")),
        "secret_key_set": bool(Config.SECRET_KEY),
    }), 200

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


# ──────────────────────────────────────────────────────
# Session helpers (HMAC-SHA256 signed cookie)
# ──────────────────────────────────────────────────────

def _session_sign(payload: str, secret: str) -> str:
    """HMAC-SHA256 signature for session payload."""
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def _build_session_identity(user: Optional[User] = None, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if payload is not None:
        try:
            uid = int(payload.get("uid") or 0)
        except Exception:
            uid = 0
        return {
            "uid": uid,
            "username": str(payload.get("username") or "").strip(),
            "github_id": str(payload.get("github_id") or "").strip(),
            "avatar_url": str(payload.get("avatar_url") or "").strip(),
        }

    if user is None:
        raise ValueError("user or payload is required")

    return {
        "uid": int(user.id),
        "username": (user.username or "").strip(),
        "github_id": str(user.github_id or "").strip(),
        "avatar_url": str(user.avatar_url or "").strip(),
    }


def _session_create(identity: Dict[str, Any]) -> str:
    """Create a signed session token: base64(json) + '.' + hmac_hex."""
    import json as _json

    session_identity = _build_session_identity(payload=identity)
    payload = _json.dumps({
        **session_identity,
        "exp": int(time.time()) + Config.SESSION_MAX_AGE_SECONDS,
    })
    payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    sig = _session_sign(payload_b64, Config.SECRET_KEY)
    return f"{payload_b64}.{sig}"


def _session_verify(token: str) -> Optional[Dict[str, Any]]:
    """Verify session token and return identity payload, or None."""
    import json as _json
    if not token or "." not in token:
        return None
    payload_b64, sig = token.rsplit(".", 1)
    expected = _session_sign(payload_b64, Config.SECRET_KEY)
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        # Restore base64 padding
        padded = payload_b64 + "=" * (4 - len(payload_b64) % 4)
        data = _json.loads(base64.urlsafe_b64decode(padded))
        if data.get("exp", 0) < time.time():
            return None
        return _build_session_identity(payload=data)
    except Exception:
        return None


def _get_public_base_url() -> str:
    """Build the public-facing base URL, respecting Vercel/proxy headers."""
    configured_base_url = (Config.PUBLIC_BASE_URL or "").strip().rstrip("/")
    if configured_base_url:
        if "://" not in configured_base_url:
            configured_base_url = f"https://{configured_base_url}"
        parsed = urlsplit(configured_base_url)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"

    # On Vercel serverless, request.url_root may report http:// internally.
    # Use X-Forwarded-Proto and Host to reconstruct the correct public URL.
    forwarded_proto = request.headers.get("X-Forwarded-Proto", "").strip()
    host = request.headers.get("Host", "").strip() or request.host
    if forwarded_proto and host:
        return f"{forwarded_proto}://{host}"
    # Fallback: force https for non-localhost, http for localhost
    url_root = request.url_root.rstrip("/")
    if "localhost" in host or "127.0.0.1" in host:
        return url_root
    return url_root.replace("http://", "https://", 1)


def _get_github_callback_base_url() -> str:
    configured_base_url = (Config.GITHUB_CALLBACK_BASE_URL or "").strip().rstrip("/")
    if configured_base_url:
        if "://" not in configured_base_url:
            configured_base_url = f"https://{configured_base_url}"
        parsed = urlsplit(configured_base_url)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    return _get_public_base_url()


def _normalize_absolute_url(url: str) -> str:
    value = (url or "").strip().rstrip("/")
    if not value:
        return ""
    if "://" not in value:
        value = f"https://{value}"
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _get_request_base_url() -> str:
    forwarded_proto = request.headers.get("X-Forwarded-Proto", "").strip()
    host = request.headers.get("Host", "").strip() or request.host
    if forwarded_proto and host:
        return f"{forwarded_proto}://{host}"
    return request.url_root.rstrip("/")


def _is_allowed_return_origin(origin: str) -> bool:
    normalized = _normalize_absolute_url(origin)
    if not normalized:
        return False
    host = urlsplit(normalized).netloc.lower()
    allowed = {
        _normalize_absolute_url(_get_public_base_url()),
        _normalize_absolute_url(_get_github_callback_base_url()),
    }
    if normalized in allowed:
        return True
    return host.endswith(".vercel.app") and host.startswith("mirror-view-")


def _create_login_handoff_token(user: User, return_to: str) -> str:
    import json as _json

    session_identity = _build_session_identity(user=user)
    payload = _json.dumps({
        **session_identity,
        "exp": int(time.time()) + 120,
        "return_to": _normalize_absolute_url(return_to),
        "kind": "oauth_handoff",
    })
    payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    sig = _session_sign(payload_b64, Config.SECRET_KEY)
    return f"{payload_b64}.{sig}"


def _verify_login_handoff_token(token: str) -> Optional[Dict[str, Any]]:
    import json as _json

    if not token or "." not in token:
        return None
    payload_b64, sig = token.rsplit(".", 1)
    expected = _session_sign(payload_b64, Config.SECRET_KEY)
    if not hmac.compare_digest(sig, expected):
        return None

    try:
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        data = _json.loads(base64.urlsafe_b64decode(padded))
    except Exception:
        return None

    if data.get("kind") != "oauth_handoff" or data.get("exp", 0) < time.time():
        return None

    return_to = _normalize_absolute_url(str(data.get("return_to", "")))
    if not _is_allowed_return_origin(return_to):
        return None

    try:
        uid = int(data["uid"])
    except Exception:
        return None

    return {
        "uid": uid,
        "return_to": return_to,
        "username": str(data.get("username") or "").strip(),
        "github_id": str(data.get("github_id") or "").strip(),
        "avatar_url": str(data.get("avatar_url") or "").strip(),
    }


def _redirect_to_canonical_public_origin() -> Optional[Response]:
    configured_base_url = (Config.PUBLIC_BASE_URL or "").strip().rstrip("/")
    if not configured_base_url:
        return None

    public_base_url = _get_public_base_url()
    request_base_url = request.url_root.rstrip("/")
    if urlsplit(public_base_url).netloc.lower() == urlsplit(request_base_url).netloc.lower():
        return None

    query = request.query_string.decode("utf-8", errors="ignore")
    target_url = f"{public_base_url}{request.path}"
    if query:
        target_url = f"{target_url}?{query}"
    return redirect(target_url, code=302)


def _redirect_to_github_callback_origin() -> Optional[Response]:
    callback_base_url = _normalize_absolute_url(_get_github_callback_base_url())
    request_base_url = _normalize_absolute_url(_get_request_base_url())
    if not callback_base_url or callback_base_url == request_base_url:
        return None

    return_to = request.args.get("return_to", "").strip() or request_base_url
    if not _is_allowed_return_origin(return_to):
        return_to = request_base_url

    target_url = f"{callback_base_url}{request.path}?return_to={quote(_normalize_absolute_url(return_to), safe='')}"
    return redirect(target_url, code=302)


def _clear_oauth_flow_cookies(response):
    response.delete_cookie("oauth_state", path="/")
    response.delete_cookie("oauth_return_to", path="/")


def _load_oauth_return_to() -> str:
    return_to = unquote(request.cookies.get("oauth_return_to", "") or "").strip() or _get_request_base_url()
    if not _is_allowed_return_origin(return_to):
        return_to = _get_request_base_url()
    return return_to


def _decode_return_to_token(token: str) -> str:
    raw = (token or "").strip()
    if not raw:
        return ""

    try:
        padded = raw + "=" * (-len(raw) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
    except Exception:
        return ""

    return decoded.strip()


def _exchange_github_code_for_user(code: str):
    base_url = _get_github_callback_base_url()
    logger.info("OAuth callback: exchanging code for token, base_url=%s", base_url)

    try:
        token_resp = requests.post(
            Config.GITHUB_TOKEN_URL,
            data={
                "client_id": Config.GITHUB_CLIENT_ID,
                "client_secret": Config.GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": f"{base_url}/auth/github/callback",
            },
            headers={"Accept": "application/json"},
            timeout=15,
        )
        token_data = token_resp.json()
    except Exception as exc:
        logger.error("GitHub token exchange request failed: %s", exc)
        return jsonify({
            "error": "token_exchange_failed",
            "message": "Failed to reach GitHub token endpoint.",
            "detail": str(exc),
        }), 200

    access_token = token_data.get("access_token")
    if not access_token:
        logger.error("GitHub token exchange failed: %s", token_data)
        return jsonify({
            "error": "token_exchange_failed",
            "message": "Failed to obtain access token.",
            "detail": token_data.get("error_description") or str(token_data),
        }), 200

    try:
        user_resp = requests.get(
            Config.GITHUB_USER_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
            timeout=15,
        )
        gh_user = user_resp.json()
    except Exception as exc:
        logger.error("GitHub user info request failed: %s", exc)
        return jsonify({
            "error": "github_user_failed",
            "message": "Failed to fetch GitHub user info.",
            "detail": str(exc),
        }), 200

    github_id = str(gh_user.get("id", ""))
    if not github_id:
        logger.error("GitHub user info missing id: %s", gh_user)
        return jsonify({"error": "github_user_failed", "message": "GitHub user has no id."}), 200

    logger.info("OAuth login: github_id=%s username=%s", github_id, gh_user.get("login"))

    gh_username = gh_user.get("login", "") or f"github_{github_id}"
    gh_avatar = gh_user.get("avatar_url", "")

    try:
        user = User.query.filter_by(github_id=github_id).first()
        if not user:
            base_name = gh_username
            suffix = 1
            while User.query.filter_by(username=gh_username).first():
                gh_username = f"{base_name}_{suffix}"
                suffix += 1
            user = User(
                username=gh_username,
                github_id=github_id,
                avatar_url=gh_avatar,
            )
            user.set_password(secrets.token_urlsafe(32))
            db.session.add(user)
        else:
            user.avatar_url = gh_avatar
            user.username = gh_username

        user.last_login = datetime.utcnow()
        db.session.commit()
        return user
    except Exception as exc:
        db.session.rollback()
        logger.error("Database error during OAuth login: %s", exc)
        return jsonify({
            "error": "db_error",
            "message": "Failed to save user session.",
            "detail": str(exc),
        }), 200


def _build_oauth_success_response(user: User, return_to: str, response_mode: str = "redirect"):
    callback_origin = _normalize_absolute_url(_get_github_callback_base_url())
    target_origin = _normalize_absolute_url(return_to) or _normalize_absolute_url(_get_public_base_url())

    if callback_origin and target_origin and callback_origin != target_origin:
        handoff_token = _create_login_handoff_token(user, target_origin)
        target_url = f"{target_origin}/auth/finalize?token={quote(handoff_token, safe='')}"
        if response_mode == "json":
            resp = make_response(jsonify({"ok": True, "redirect_to": target_url}))
        else:
            resp = make_response(redirect(target_url))
        _clear_oauth_flow_cookies(resp)
        return resp

    session_token = _session_create(_build_session_identity(user=user))
    if response_mode == "json":
        resp = make_response(jsonify({"ok": True, "redirect_to": "/"}))
    else:
        resp = make_response(redirect("/"))
    _set_session_cookie(resp, session_token)
    _clear_oauth_flow_cookies(resp)
    return resp


def _set_session_cookie(response, token: str):
    """Set httpOnly session cookie on a Flask response."""
    is_secure = not (
        "localhost" in request.host or "127.0.0.1" in request.host
    )
    response.set_cookie(
        Config.SESSION_COOKIE_NAME,
        token,
        max_age=Config.SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=is_secure,
        samesite="lax",
        path="/",
    )


def _clear_session_cookie(response):
    """Clear session cookie."""
    response.delete_cookie(Config.SESSION_COOKIE_NAME, path="/")


def _get_current_user() -> Optional[Dict[str, Any]]:
    """Read session cookie and return current identity, with DB fallback when available."""
    token = request.cookies.get(Config.SESSION_COOKIE_NAME, "")
    identity = _session_verify(token)
    if identity is None:
        return None

    uid = int(identity.get("uid") or 0)
    if uid:
        user = db.session.get(User, uid)
        if user:
            return _build_session_identity(user=user)

    if identity.get("username") or identity.get("github_id") or identity.get("avatar_url"):
        return identity
    return None


# ──────────────────────────────────────────────────────
# GitHub OAuth2 Routes
# ──────────────────────────────────────────────────────

@api.route('/auth/github/start/<path:return_to_token>', methods=['GET'])
def github_oauth_start_path(return_to_token: str):
    if not Config.GITHUB_CLIENT_ID:
        return jsonify({"error": "github_not_configured", "message": "GitHub OAuth not configured."}), 503

    callback_base_url = _normalize_absolute_url(_get_github_callback_base_url())
    request_base_url = _normalize_absolute_url(_get_request_base_url())
    return_to = _decode_return_to_token(return_to_token) or _get_public_base_url()
    if not _is_allowed_return_origin(return_to):
        return_to = _get_public_base_url()

    if callback_base_url and callback_base_url != request_base_url:
        normalized_return_to = _normalize_absolute_url(return_to)
        encoded_return_to = base64.urlsafe_b64encode(normalized_return_to.encode("utf-8")).decode("utf-8").rstrip("=")
        return redirect(f"{callback_base_url}/auth/github/start/{encoded_return_to}", code=302)

    state = secrets.token_urlsafe(32)
    params = urlencode({
        "client_id": Config.GITHUB_CLIENT_ID,
        "redirect_uri": f"{_get_github_callback_base_url()}/auth/github/callback",
        "scope": "read:user user:email",
        "state": state,
    })

    redirect_url = f"{Config.GITHUB_AUTHORIZE_URL}?{params}"
    resp = make_response(redirect(redirect_url))
    is_secure = not ("localhost" in request.host or "127.0.0.1" in request.host)
    resp.set_cookie("oauth_state", state, max_age=600, httponly=True, secure=is_secure, samesite="lax", path="/")
    resp.set_cookie("oauth_return_to", quote(_normalize_absolute_url(return_to), safe=""), max_age=600, httponly=True, secure=is_secure, samesite="lax", path="/")
    return resp

@api.route('/auth/github', methods=['GET'])
def github_oauth_start():
    """Step 1: Redirect user to GitHub authorize page."""
    if not Config.GITHUB_CLIENT_ID:
        return jsonify({"error": "github_not_configured", "message": "GitHub OAuth not configured."}), 503

    callback_redirect = _redirect_to_github_callback_origin()
    if callback_redirect is not None:
        return callback_redirect

    callback_base_url = _normalize_absolute_url(_get_github_callback_base_url())
    request_base_url = _normalize_absolute_url(request.url_root.rstrip("/"))
    if callback_base_url == request_base_url:
        canonical_redirect = _redirect_to_canonical_public_origin()
        if canonical_redirect is not None and callback_base_url == _normalize_absolute_url(_get_public_base_url()):
            return canonical_redirect

    return_to = request.args.get("return_to", "").strip() or _normalize_absolute_url(_get_request_base_url())
    if not _is_allowed_return_origin(return_to):
        return_to = _normalize_absolute_url(_get_request_base_url())

    state = secrets.token_urlsafe(32)
    base_url = _get_github_callback_base_url()
    params = urlencode({
        "client_id": Config.GITHUB_CLIENT_ID,
        "redirect_uri": f"{base_url}/auth/github/callback",
        "scope": "read:user user:email",
        "state": state,
    })

    redirect_url = f"{Config.GITHUB_AUTHORIZE_URL}?{params}"
    resp = make_response(redirect(redirect_url))
    # Store state in a short-lived cookie for CSRF check
    is_secure = not ("localhost" in request.host or "127.0.0.1" in request.host)
    resp.set_cookie("oauth_state", state, max_age=600, httponly=True, secure=is_secure, samesite="lax", path="/")
    resp.set_cookie("oauth_return_to", quote(_normalize_absolute_url(return_to), safe=""), max_age=600, httponly=True, secure=is_secure, samesite="lax", path="/")
    return resp


@api.route('/auth/github/callback', methods=['GET'])
def github_oauth_callback():
    """Step 2: GitHub redirects here after user authorizes."""
    import traceback
    print("[OAUTH] callback started", flush=True)
    try:
        return _github_oauth_callback_inner()
    except Exception as exc:
        tb = traceback.format_exc()
        print(f"[OAUTH] FATAL: {exc}\n{tb}", flush=True)
        logger.error("OAuth callback error: %s\n%s", exc, tb)
        return jsonify({
            "error": "oauth_callback_error",
            "message": str(exc),
            "trace": tb,
        }), 200


def _github_oauth_callback_inner():
    """Inner callback logic wrapped by error handler."""
    # CSRF check
    state = request.args.get("state", "")
    expected_state = request.cookies.get("oauth_state", "")
    if not state or state != expected_state:
        logger.warning("OAuth CSRF: state=%s expected=%s", state[:8] if state else None, expected_state[:8] if expected_state else None)
        return jsonify({"error": "csrf_detected", "message": "Invalid OAuth state."}), 403

    code = request.args.get("code")
    if not code:
        return jsonify({"error": "missing_code", "message": "No authorization code received."}), 400

    return_to = _load_oauth_return_to()
    user = _exchange_github_code_for_user(code)
    if not isinstance(user, User):
        return user
    return _build_oauth_success_response(user, return_to, response_mode="redirect")


@api.route('/auth/github/exchange', methods=['POST'])
def github_oauth_exchange():
    data = request.get_json(silent=True) or {}
    state = str(data.get("state") or "").strip()
    expected_state = request.cookies.get("oauth_state", "")
    if not state or state != expected_state:
        logger.warning("OAuth CSRF(exchange): state=%s expected=%s", state[:8] if state else None, expected_state[:8] if expected_state else None)
        return jsonify({"error": "csrf_detected", "message": "Invalid OAuth state."}), 403

    code = str(data.get("code") or "").strip()
    if not code:
        return jsonify({"error": "missing_code", "message": "No authorization code received."}), 400

    return_to = _load_oauth_return_to()
    user = _exchange_github_code_for_user(code)
    if not isinstance(user, User):
        return user
    return _build_oauth_success_response(user, return_to, response_mode="json")


@api.route('/auth/complete', methods=['GET'])
def auth_complete():
    token = request.args.get("token", "").strip()
    if not token:
        return jsonify({"error": "missing_handoff_token", "message": "Missing login completion token."}), 400
    payload = _verify_login_handoff_token(token)
    if not payload:
        return jsonify({"error": "invalid_handoff_token", "message": "Invalid or expired login completion token."}), 400

    session_token = _session_create(payload)
    resp = make_response(redirect("/"))
    _set_session_cookie(resp, session_token)
    return resp


@api.route('/auth/complete/<path:token>', methods=['GET'])
def auth_complete_path(token: str):
    token = (token or "").strip()
    payload = _verify_login_handoff_token(token)
    if not payload:
        return jsonify({"error": "invalid_handoff_token", "message": "Invalid or expired login completion token."}), 400

    session_token = _session_create(payload)
    resp = make_response(redirect("/"))
    _set_session_cookie(resp, session_token)
    return resp


@api.route('/auth/finalize', methods=['GET'])
def auth_finalize():
    token = request.args.get("token", "").strip()
    if not token:
        return jsonify({"error": "missing_handoff_token", "message": "Missing login completion token."}), 400

    payload = _verify_login_handoff_token(token)
    if not payload:
        return jsonify({"error": "invalid_handoff_token", "message": "Invalid or expired login completion token."}), 400

    session_token = _session_create(payload)
    resp = make_response(redirect("/"))
    _set_session_cookie(resp, session_token)
    return resp


@api.route('/auth/me', methods=['GET'])
def auth_me():
    """Return current logged-in user info, or 401."""
    user = _get_current_user()
    if not user:
        return jsonify({"authenticated": False}), 401
    return jsonify({
        "authenticated": True,
        "user_id": user["uid"],
        "username": user["username"],
        "github_id": user["github_id"] or None,
        "avatar_url": user["avatar_url"] or None,
    }), 200


@api.route('/auth/logout', methods=['GET', 'POST'])
def auth_logout():
    """Clear session and redirect to /."""
    resp = make_response(redirect("/"))
    _clear_session_cookie(resp)
    return resp

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

def _normalize_interview_language(language):
    lang = (language or "zh").strip().lower()
    if lang.startswith("en"):
        return "en"
    return "zh"


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


def _coerce_request_data() -> Dict[str, Any]:
    data = request.get_json(silent=True)
    if data is None:
        data = request.form.to_dict() if request.form else {}
    if not isinstance(data, dict):
        return {}
    return data


def _cover_letter_text_field(data: Dict[str, Any], key: str, default: str = "", limit: Optional[int] = None) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        return default
    value = value.strip()
    return value[:limit] if limit else value


def _resolve_runtime(data: Dict[str, Any]) -> Tuple[Optional[Dict[str, str]], Optional[Tuple[Dict[str, Any], int]], Dict[str, str]]:
    runtime, runtime_error = parse_runtime_payload(data)
    if runtime_error:
        return None, ({"error": "invalid_runtime", "message": runtime_error}, 400), {}
    return runtime, None, build_runtime_meta(runtime or {})


def _require_user_runtime_api_key(runtime: Optional[Dict[str, str]]) -> Optional[Tuple[Dict[str, Any], int]]:
    api_key = str((runtime or {}).get("api_key") or "").strip()
    if api_key:
        return None
    return ({
        "error": "user_runtime_required",
        "message": "请先在模型设置中填写并测试你自己的 API Key。",
    }, 400)


def _to_score_int(value: Any) -> Optional[int]:
    try:
        score = int(round(float(value)))
    except Exception:
        return None
    return max(0, min(100, score))


def _normalize_resume_match_list(value: Any) -> List[str]:
    if isinstance(value, list):
        items = [str(item or "").strip() for item in value]
        return [item for item in items if item]
    if isinstance(value, dict):
        items = []
        for key, item in value.items():
            text = str(item or "").strip()
            if text:
                items.append(f"{key}: {text}" if str(key).strip() else text)
        return items
    if isinstance(value, str):
        items = [line.strip(" -\t") for line in value.splitlines() if line.strip()]
        return [item for item in items if item]
    return []


def _first_text(result: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _normalize_match_level(raw_level: Any, score: int) -> str:
    text = str(raw_level or "").strip()
    upper = text.upper()
    if upper.startswith("A") or "STRONG" in upper or text.startswith("高度匹配"):
        return "A. Strong Fit"
    if upper.startswith("B") or "STRETCH" in upper or text.startswith("部分匹配") or text.startswith("较匹配"):
        return "B. Stretch Fit"
    if upper.startswith("C") or "POOR" in upper or text.startswith("匹配较低") or text.startswith("不匹配"):
        return "C. Poor Fit"
    if score >= 75:
        return "A. Strong Fit"
    if score >= 50:
        return "B. Stretch Fit"
    return "C. Poor Fit"


def _extract_dimension_items(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_dimensions = result.get("dimension_scores")
    if isinstance(raw_dimensions, list):
        return [item for item in raw_dimensions if isinstance(item, dict)]

    for key in ("dimensions", "scores", "dimension_details", "score_breakdown"):
        value = result.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            items = []
            for name, payload in value.items():
                if isinstance(payload, dict):
                    items.append({"name": name, **payload})
                else:
                    items.append({"name": name, "score": payload})
            return items
    return []


def _normalize_dimension_item(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    name = str(item.get("name") or item.get("dimension") or item.get("title") or item.get("label") or "").strip()
    dim_score = _to_score_int(item.get("score") if item.get("score") is not None else item.get("value"))
    highlight = str(item.get("highlight") or item.get("strength") or item.get("matched") or item.get("优势") or item.get("亮点") or "").strip()
    gap = str(item.get("gap") or item.get("weakness") or item.get("missing") or item.get("不足") or item.get("差距") or "").strip()
    advice = str(item.get("advice") or item.get("suggestion") or item.get("recommendation") or item.get("建议") or "").strip()

    details = _normalize_resume_match_list(item.get("details"))
    if not highlight and details:
        highlight = details[0]
    if not gap:
        gap = "暂无明显差距，建议结合 JD 继续补充量化证据。"
    if not advice:
        advice = "结合该维度补充更贴近 JD 的事实描述与成果量化。"

    if not name or dim_score is None:
        return None
    return {
        "name": name,
        "score": dim_score,
        "highlight": highlight or "已识别到相关匹配点。",
        "gap": gap,
        "advice": advice,
    }


def _validate_resume_match_result(result: Any) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not isinstance(result, dict):
        return None, "模型未返回有效 JSON 对象。"

    if result.get("error"):
        return None, str(result.get("message") or result.get("error") or "模型分析失败。")

    score = _to_score_int(result.get("overall_score"))
    if score is None:
        score = _to_score_int(result.get("score"))
    if score is None:
        score = _to_score_int(result.get("total_score"))
    if score is None:
        return None, "匹配分析结果缺少有效的 overall_score。"

    summary = _first_text(result, "summary", "overview", "one_line_summary", "match_summary", "结论", "一句话总结")
    if not summary:
        summary = "已完成简历与岗位 JD 的匹配分析，建议结合下方维度结果继续优化。"

    raw_items = _extract_dimension_items(result)
    normalized_dimensions: List[Dict[str, Any]] = []
    for item in raw_items:
        normalized = _normalize_dimension_item(item)
        if normalized:
            normalized_dimensions.append(normalized)

    if not normalized_dimensions:
        return None, "匹配分析结果缺少可渲染的维度评分内容。"

    match_level = _normalize_match_level(
        result.get("match_level") or result.get("level") or result.get("grade") or result.get("评级"),
        score,
    )

    return {
        "overall_score": score,
        "match_level": match_level,
        "summary": summary,
        "dimension_scores": normalized_dimensions,
        "critical_missing": _normalize_resume_match_list(result.get("critical_missing") or result.get("missing_items") or result.get("gaps")),
        "extra_advantages": _normalize_resume_match_list(result.get("extra_advantages") or result.get("advantages") or result.get("strengths")),
        "optimization_suggestions": _normalize_resume_match_list(result.get("optimization_suggestions") or result.get("suggestions") or result.get("recommendations")),
        "optimized_resume_markdown": str(result.get("optimized_resume_markdown") or result.get("resume_markdown") or result.get("optimized_resume") or "").strip(),
        "assumptions": _normalize_resume_match_list(result.get("assumptions")),
    }, None


def _guard_high_cost_request(endpoint_name: str, data: Dict[str, Any]) -> Optional[Tuple[Dict[str, Any], int]]:
    if endpoint_name not in HIGH_COST_ENDPOINTS:
        return None

    token = str(data.get("turnstile_token") or "").strip()
    allowed, status_code, err = enforce_high_cost_guard(
        endpoint=endpoint_name,
        token=token,
        remote_ip=request.remote_addr or "",
    )
    if allowed:
        return None
    return err, status_code


def _resolve_repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "skills").exists() and (parent / "server").exists():
            return parent
    return current.parents[1]


REPO_ROOT = _resolve_repo_root()
RESUME_CRAFT_DIR = REPO_ROOT / "skills" / "CareerForge" / "skills" / "resume-craft"
RESUME_CRAFT_BASE_TEMPLATE_FILE = RESUME_CRAFT_DIR / "templates" / "resume-template.html"
RESUME_CRAFT_PREVIEW_TEMPLATE_FILE = RESUME_CRAFT_DIR / "templates" / "CareerForge-模板预览.html"
RESUME_CRAFT_GENERATE_PDF_SCRIPT_FILE = RESUME_CRAFT_DIR / "scripts" / "generate_pdf.py"
RESUME_CRAFT_PROCESS_PHOTO_SCRIPT_FILE = RESUME_CRAFT_DIR / "scripts" / "process_photo.py"


@lru_cache(maxsize=1)
def _load_resume_craft_templates() -> Dict[str, str]:
    base_template = ""
    preview_template = ""
    try:
        if RESUME_CRAFT_BASE_TEMPLATE_FILE.exists():
            base_template = RESUME_CRAFT_BASE_TEMPLATE_FILE.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        logger.warning("failed to load resume-craft base template: %s", e)

    try:
        if RESUME_CRAFT_PREVIEW_TEMPLATE_FILE.exists():
            preview_template = RESUME_CRAFT_PREVIEW_TEMPLATE_FILE.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        logger.warning("failed to load resume-craft preview template: %s", e)

    return {"base_template": base_template, "preview_template": preview_template}


def _normalize_resume_craft_template_code(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "02"
    m = re.search(r"([1-7])", text)
    if not m:
        return "02"
    return f"0{m.group(1)}"


def _normalize_resume_craft_language(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"en", "english", "英文"}:
        return "英文"
    if text in {"both", "zh-en", "zh_en", "双语", "中英文", "中英文双版"}:
        return "中英文双版"
    return "中文"


def _normalize_resume_craft_photo_pref(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"with_photo", "with-photo", "photo", "yes", "1", "放照片", "放"}:
        return "放照片"
    return "不放照片"


def _extract_preview_snippet(preview_html: str, template_code: str) -> str:
    if not preview_html:
        return ""
    try:
        idx = int(template_code)
    except Exception:
        idx = 2
    css_marker = f"/* == T{idx}:"
    css_start = preview_html.find(css_marker)
    css_part = preview_html[css_start:css_start + 2500] if css_start != -1 else ""

    card_marker = f"<!-- T{idx}"
    card_start = preview_html.find(card_marker)
    card_part = preview_html[card_start:card_start + 3500] if card_start != -1 else ""
    return (css_part + "\n\n" + card_part).strip()[:5000]


def _ensure_doctype_html(doc: str) -> str:
    text = str(doc or "").strip()
    if not text:
        return ""
    if "<!doctype" in text.lower():
        return text
    return "<!DOCTYPE html>\n" + text


def _extract_html_document_from_candidate(candidate: str) -> str:
    text = str(candidate or "").strip()
    if not text:
        return ""

    matched = re.search(r"(?is)<!doctype\s+html[\s\S]*?</html\s*>", text)
    if matched:
        return matched.group(0).strip()

    matched = re.search(r"(?is)<html\b[^>]*>[\s\S]*?</html\s*>", text)
    if matched:
        return _ensure_doctype_html(matched.group(0).strip())

    html_open = re.search(r"(?is)<html\b[^>]*>", text)
    if html_open:
        fragment = text[html_open.start():]
        body_end = re.search(r"(?is)</body\s*>", fragment)
        if body_end:
            return _ensure_doctype_html((fragment[: body_end.end()] + "\n</html>").strip())

    body = re.search(r"(?is)<body\b[^>]*>[\s\S]*?</body\s*>", text)
    if body:
        head = re.search(r"(?is)<head\b[^>]*>[\s\S]*?</head\s*>", text)
        head_html = head.group(0).strip() if head else "<head><meta charset=\"UTF-8\"></head>"
        return _ensure_doctype_html(f"<html>\n{head_html}\n{body.group(0).strip()}\n</html>")

    return ""


def _extract_html_document(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""

    candidates: List[str] = []

    def _push_candidate(value: str) -> None:
        item = str(value or "").strip()
        if not item:
            return
        if item not in candidates:
            candidates.append(item)

    _push_candidate(raw)
    if "&lt;" in raw and "&gt;" in raw:
        _push_candidate(unescape(raw))

    fenced_blocks = re.findall(r"```(?:[a-zA-Z0-9_-]+)?\s*([\s\S]*?)```", raw)
    for block in fenced_blocks:
        _push_candidate(block)
        if "&lt;" in block and "&gt;" in block:
            _push_candidate(unescape(block))

    def _score(candidate: str) -> int:
        low = candidate.lower()
        score = 0
        if "<!doctype html" in low:
            score += 10
        if "<html" in low:
            score += 8
        if "<body" in low:
            score += 6
        if "</html" in low:
            score += 4
        if "<head" in low:
            score += 2
        return score

    for candidate in sorted(candidates, key=_score, reverse=True):
        doc = _extract_html_document_from_candidate(candidate)
        if doc:
            return doc
    return ""


def _sanitize_resume_filename_component(value: str, fallback: str) -> str:
    text = re.sub(r'[\\/:*?"<>|]+', "", str(value or "").strip())
    text = re.sub(r"\s+", "", text)
    return (text[:40] or fallback).strip() or fallback


def _build_resume_artifact_stem(step1_profile: Dict[str, Any]) -> str:
    personal = step1_profile.get("personal_info") or {}
    name = _sanitize_resume_filename_component(str(personal.get("name") or ""), "候选人")
    role = _sanitize_resume_filename_component(str(step1_profile.get("target_role") or ""), "目标岗位")
    return f"{name}-{role}简历"


def _generate_resume_craft_pdf_artifact(report_html: str, report_name: str) -> Tuple[str, str, str]:
    if not str(report_html or "").strip():
        return "", "", "empty_html"
    if not RESUME_CRAFT_GENERATE_PDF_SCRIPT_FILE.exists():
        return "", "", "pdf_script_missing"

    try:
        with tempfile.TemporaryDirectory(prefix="resume-craft-pdf-") as tmpdir:
            temp_dir = Path(tmpdir)
            html_file = temp_dir / (Path(report_name).name or "resume.html")
            html_file.write_text(report_html, encoding="utf-8")
            pdf_name = html_file.with_suffix(".pdf").name
            pdf_file = temp_dir / pdf_name
            completed = subprocess.run(
                [sys.executable, str(RESUME_CRAFT_GENERATE_PDF_SCRIPT_FILE), str(html_file), str(pdf_file)],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if completed.returncode != 0:
                details = (completed.stderr or completed.stdout or "").strip().replace("\n", " ")
                return "", "", f"pdf_script_failed:{details[:220]}"
            if not pdf_file.exists():
                return "", "", "pdf_not_created"
            pdf_base64 = base64.b64encode(pdf_file.read_bytes()).decode("ascii")
            return pdf_name, pdf_base64, ""
    except Exception as e:
        return "", "", f"pdf_generation_exception:{str(e)[:220]}"


def _store_resume_craft_html_artifact(report_html: str) -> str:
    now = time.time()
    expired = [
        token
        for token, (created_at, _html) in _RESUME_CRAFT_HTML_ARTIFACTS.items()
        if now - created_at > RESUME_CRAFT_HTML_ARTIFACT_TTL_SECONDS
    ]
    for token in expired:
        _RESUME_CRAFT_HTML_ARTIFACTS.pop(token, None)

    while len(_RESUME_CRAFT_HTML_ARTIFACTS) >= RESUME_CRAFT_HTML_ARTIFACT_MAX_ITEMS:
        oldest = min(_RESUME_CRAFT_HTML_ARTIFACTS, key=lambda key: _RESUME_CRAFT_HTML_ARTIFACTS[key][0])
        _RESUME_CRAFT_HTML_ARTIFACTS.pop(oldest, None)

    token = secrets.token_urlsafe(24)
    _RESUME_CRAFT_HTML_ARTIFACTS[token] = (now, report_html)
    return token


@api.route('/careerforge/resume-craft/artifacts/<artifact_token>', methods=['GET'])
def careerforge_resume_craft_artifact(artifact_token: str):
    stored = _RESUME_CRAFT_HTML_ARTIFACTS.get(artifact_token)
    if not stored or time.time() - stored[0] > RESUME_CRAFT_HTML_ARTIFACT_TTL_SECONDS:
        _RESUME_CRAFT_HTML_ARTIFACTS.pop(artifact_token, None)
        return jsonify({"error": "resume_craft_artifact_not_found"}), 404

    return Response(
        stored[1],
        mimetype="text/html",
        headers={"Cache-Control": "no-store"},
    )


def _process_photo_data_url_with_skill(photo_data_url: str) -> Tuple[str, str]:
    value = str(photo_data_url or "").strip()
    if not value:
        return "", "missing_photo"
    if not RESUME_CRAFT_PROCESS_PHOTO_SCRIPT_FILE.exists():
        return value, "photo_script_missing"

    match = re.match(r"^data:image/(png|jpe?g);base64,([a-z0-9+/=\r\n]+)$", value, re.IGNORECASE)
    if not match:
        return value, "invalid_photo_format"

    image_type = match.group(1).lower()
    raw_base64 = re.sub(r"\s+", "", match.group(2))
    try:
        raw_bytes = base64.b64decode(raw_base64, validate=True)
    except (binascii.Error, ValueError):
        return value, "invalid_photo_base64"

    suffix = ".png" if image_type == "png" else ".jpg"
    try:
        with tempfile.TemporaryDirectory(prefix="resume-craft-photo-") as tmpdir:
            temp_dir = Path(tmpdir)
            input_file = temp_dir / f"upload{suffix}"
            input_file.write_bytes(raw_bytes)
            completed = subprocess.run(
                [sys.executable, str(RESUME_CRAFT_PROCESS_PHOTO_SCRIPT_FILE), str(input_file), "160"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if completed.returncode != 0:
                details = (completed.stderr or completed.stdout or "").strip().replace("\n", " ")
                return value, f"photo_process_failed:{details[:220]}"
            processed_base64 = re.sub(r"\s+", "", str(completed.stdout or "").strip())
            if not processed_base64:
                return value, "photo_process_empty"
            return f"data:image/jpeg;base64,{processed_base64}", ""
    except Exception as e:
        return value, f"photo_process_exception:{str(e)[:220]}"


def _normalize_step1_profile(raw: Any) -> Dict[str, Any]:
    profile = raw if isinstance(raw, dict) else {}
    personal = profile.get("personal_info") if isinstance(profile.get("personal_info"), dict) else {}
    education_items = profile.get("education") if isinstance(profile.get("education"), list) else []

    def _clean_list(values: Any, limit: int = 20) -> List[str]:
        if not isinstance(values, list):
            return []
        out: List[str] = []
        for item in values:
            text = str(item or "").strip()
            if text:
                out.append(text[:120])
            if len(out) >= limit:
                break
        return out

    cleaned_education: List[Dict[str, str]] = []
    for item in education_items[:5]:
        if not isinstance(item, dict):
            continue
        school = str(item.get("school") or "").strip()
        major = str(item.get("major") or "").strip()
        degree = str(item.get("degree") or "").strip()
        period = str(item.get("period") or "").strip()
        highlights = str(item.get("highlights") or "").strip()
        if any([school, major, degree, period, highlights]):
            cleaned_education.append(
                {
                    "school": school[:120],
                    "major": major[:120],
                    "degree": degree[:120],
                    "period": period[:60],
                    "highlights": highlights[:240],
                }
            )

    expected_count = profile.get("expected_experience_count")
    try:
        expected = int(expected_count)
    except Exception:
        expected = 1
    expected = max(1, min(expected, 5))

    return {
        "template_code": _normalize_resume_craft_template_code(profile.get("template_code")),
        "language": _normalize_resume_craft_language(profile.get("language")),
        "photo_pref": _normalize_resume_craft_photo_pref(profile.get("photo_pref")),
        "target_role": str(profile.get("target_role") or "").strip()[:120],
        "jd_summary": str(profile.get("jd_summary") or "").strip()[:800],
        "focus_points": str(profile.get("focus_points") or "").strip()[:600],
        "tone_pref": str(profile.get("tone_pref") or "").strip()[:120],
        "expected_experience_count": expected,
        "personal_info": {
            "name": str(personal.get("name") or "").strip()[:80],
            "phone": str(personal.get("phone") or "").strip()[:40],
            "email": str(personal.get("email") or "").strip()[:120],
            "city": str(personal.get("city") or "").strip()[:80],
            "links": _clean_list(personal.get("links"), limit=8),
        },
        "education": cleaned_education,
        "skills": _clean_list(profile.get("skills"), limit=30),
        "certificates": _clean_list(profile.get("certificates"), limit=20),
    }


def _build_step1_profile_context(profile: Dict[str, Any], template_code: str, language: str, photo_pref: str) -> str:
    personal = profile.get("personal_info") or {}
    edu = profile.get("education") or []
    skills = profile.get("skills") or []
    certs = profile.get("certificates") or []
    lines = [
        "【Step1 已定稿信息】",
        f"- 模板编号: {template_code}",
        f"- 语言: {language}",
        f"- 照片偏好: {photo_pref}",
        f"- 目标岗位: {profile.get('target_role') or '未填写'}",
        f"- JD摘要（仅用于方向排序，不是已确认事实）: {profile.get('jd_summary') or '无'}",
        f"- 姓名: {personal.get('name') or '未填写'}",
        f"- 联系方式: 手机={personal.get('phone') or '未填写'} 邮箱={personal.get('email') or '未填写'} 城市={personal.get('city') or '未填写'}",
        f"- 链接: {', '.join(personal.get('links') or []) or '无'}",
        f"- 教育条目数: {len(edu)}",
        f"- 技能: {', '.join(skills) if skills else '无'}",
        f"- 证书: {', '.join(certs) if certs else '无'}",
        f"- 突出偏好: {profile.get('focus_points') or '无'}",
        f"- 语气偏好: {profile.get('tone_pref') or '无'}",
        "- 以上信息来自用户表单；对话 Agent 可根据完整上下文继续收集、追问或确认。",
    ]
    return "\n".join(lines)


def _sanitize_step6_draft_json(raw: Any) -> Dict[str, Any]:
    value = raw if isinstance(raw, dict) else {}
    personal_raw = value.get("personal_info") if isinstance(value.get("personal_info"), dict) else {}
    personal_info = {
        "name": str(personal_raw.get("name") or "").strip()[:80],
        "phone": str(personal_raw.get("phone") or "").strip()[:80],
        "email": str(personal_raw.get("email") or "").strip()[:120],
        "city": str(personal_raw.get("city") or "").strip()[:80],
        "links": [str(item or "").strip()[:240] for item in (personal_raw.get("links") or [])[:8] if str(item or "").strip()],
    }
    return {
        "target_role": str(value.get("target_role") or "").strip()[:160],
        "personal_info": personal_info,
        "education": [str(item or "").strip()[:2400] for item in (value.get("education") or [])[:20] if str(item or "").strip()],
        "experiences": [str(item or "").strip()[:2400] for item in (value.get("experiences") or [])[:20] if str(item or "").strip()],
        "skills_and_certs": [str(item or "").strip()[:2400] for item in (value.get("skills_and_certs") or [])[:30] if str(item or "").strip()],
        "final_preferences": str(value.get("final_preferences") or "").strip()[:2400],
    }


def _build_confirmed_step6_draft_fallback(
    step1_profile: Dict[str, Any],
    wizard_state: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a structural draft from already-confirmed state when the model omits draft_json."""
    collected = wizard_state.get("collected_by_step") if isinstance(wizard_state.get("collected_by_step"), dict) else {}
    step_states = wizard_state.get("step_states") if isinstance(wizard_state.get("step_states"), dict) else {}
    step4 = step_states.get("step4") if isinstance(step_states.get("step4"), dict) else {}
    personal = step1_profile.get("personal_info") if isinstance(step1_profile.get("personal_info"), dict) else {}

    def unique_text(values: Any, limit: int) -> List[str]:
        result: List[str] = []
        for value in values if isinstance(values, list) else []:
            text = str(value or "").strip()
            if text and text not in result:
                result.append(text[:2400])
            if len(result) >= limit:
                break
        return result

    education: List[str] = []
    for item in step1_profile.get("education") if isinstance(step1_profile.get("education"), list) else []:
        if not isinstance(item, dict):
            continue
        value = " | ".join(
            str(item.get(key) or "").strip()
            for key in ("school", "major", "degree", "period", "highlights")
            if str(item.get(key) or "").strip()
        )
        if value:
            education.append(value)

    return {
        "target_role": str(step1_profile.get("target_role") or "").strip(),
        "personal_info": {
            "name": str(personal.get("name") or "").strip(),
            "phone": str(personal.get("phone") or "").strip(),
            "email": str(personal.get("email") or "").strip(),
            "city": str(personal.get("city") or "").strip(),
            "links": unique_text(personal.get("links"), 8),
        },
        "education": unique_text(education + list(collected.get("education") or []), 20),
        "experiences": unique_text(
            list(collected.get("experiences") or []) + list(step4.get("finalized_experiences") or []),
            20,
        ),
        "skills_and_certs": unique_text(
            list(step1_profile.get("skills") or [])
            + list(step1_profile.get("certificates") or [])
            + list(collected.get("skills_and_certs") or []),
            30,
        ),
        "final_preferences": str(
            collected.get("final_preferences") or step1_profile.get("focus_points") or ""
        ).strip(),
    }




def _build_confirmed_facts_context(
    step1_profile: Dict[str, Any],
    draft_json: Dict[str, Any],
    wizard_state: Optional[Dict[str, Any]] = None,
) -> str:
    draft = _sanitize_step6_draft_json(draft_json)
    profile = step1_profile if isinstance(step1_profile, dict) else {}
    profile_personal = profile.get("personal_info") if isinstance(profile.get("personal_info"), dict) else {}
    draft_personal = draft.get("personal_info") or {}
    wizard = wizard_state if isinstance(wizard_state, dict) else {}
    collected = wizard.get("collected_by_step") if isinstance(wizard.get("collected_by_step"), dict) else {}
    step_states = wizard.get("step_states") if isinstance(wizard.get("step_states"), dict) else {}
    step4 = step_states.get("step4") if isinstance(step_states.get("step4"), dict) else {}

    def unique_text(values: Any, limit: int = 30) -> List[str]:
        result: List[str] = []
        if not isinstance(values, list):
            values = [values]
        for value in values:
            text = str(value or "").strip()
            if text and text not in result:
                result.append(text[:2400])
            if len(result) >= limit:
                break
        return result

    def profile_education_items() -> List[str]:
        result: List[str] = []
        for item in profile.get("education") if isinstance(profile.get("education"), list) else []:
            if not isinstance(item, dict):
                continue
            parts = [
                str(item.get("school") or "").strip(),
                str(item.get("major") or "").strip(),
                str(item.get("degree") or "").strip(),
                str(item.get("period") or "").strip(),
                str(item.get("highlights") or "").strip(),
            ]
            value = " | ".join(part for part in parts if part)
            if value:
                result.append(value)
        return result

    personal_name = str(draft_personal.get("name") or profile_personal.get("name") or "").strip()
    personal_phone = str(draft_personal.get("phone") or profile_personal.get("phone") or "").strip()
    personal_email = str(draft_personal.get("email") or profile_personal.get("email") or "").strip()
    personal_city = str(draft_personal.get("city") or profile_personal.get("city") or "").strip()
    links = unique_text(list(draft_personal.get("links") or []) + list(profile_personal.get("links") or []), limit=8)
    education = unique_text(
        list(draft.get("education") or [])
        + profile_education_items()
        + list(collected.get("education") or []),
    )
    experiences = unique_text(
        list(draft.get("experiences") or [])
        + list(collected.get("experiences") or [])
        + list(step4.get("finalized_experiences") or []),
    )
    skills_and_certs = unique_text(
        list(draft.get("skills_and_certs") or [])
        + list(profile.get("skills") or [])
        + list(profile.get("certificates") or [])
        + list(collected.get("skills_and_certs") or []),
    )
    final_preferences = str(
        draft.get("final_preferences") or collected.get("final_preferences") or profile.get("focus_points") or ""
    ).strip()

    lines: List[str] = [
        "【事实白名单（只能使用以下信息）】",
        f"- 目标岗位: {draft.get('target_role') or profile.get('target_role') or '未填写'}",
        f"- 姓名: {personal_name or '未填写'}",
        f"- 手机: {personal_phone or '未填写'}",
        f"- 邮箱: {personal_email or '未填写'}",
        f"- 城市: {personal_city or '未填写'}",
        f"- 链接: {', '.join(links) or '无'}",
        "- 教育背景:",
    ]
    lines.extend(f"  - 教育{idx}: {item}" for idx, item in enumerate(education, start=1))
    if not education:
        lines.append("  - （无）")
    lines.append("- 工作/项目经历:")
    lines.extend(f"  - 经历{idx}: {item}" for idx, item in enumerate(experiences, start=1))
    if not experiences:
        lines.append("  - （无）")
    lines.append("- 技能与证书:")
    lines.extend(f"  - 技能{idx}: {item}" for idx, item in enumerate(skills_and_certs, start=1))
    if not skills_and_certs:
        lines.append("  - （无）")
    lines.append(f"- 生成偏好: {final_preferences or '无'}")
    return "\n".join(lines)


def _build_jd_direction_context(step1_profile: Dict[str, Any]) -> str:
    jd_summary = str(step1_profile.get("jd_summary") or "").strip()
    if not jd_summary:
        return "（无）"
    return (
        "JD 仅用于排序和强调方向，不能当作事实写入简历：\n"
        f"- 方向摘要: {jd_summary[:1600]}"
    )


def _validate_photo_data_url(photo_data_url: str) -> Tuple[bool, str]:
    value = str(photo_data_url or "").strip()
    if not value:
        return False, "missing_photo"
    if len(value) > RESUME_CRAFT_MAX_PHOTO_DATA_URL_LENGTH:
        return False, "photo_too_large"
    pattern = re.compile(r"^data:image/(png|jpe?g);base64,[a-z0-9+/=\r\n]+$", re.IGNORECASE)
    if not pattern.match(value):
        return False, "invalid_photo_format"
    return True, ""


def _inject_photo_data_url_into_html(html_doc: str, photo_data_url: str, token: str) -> str:
    html_text = str(html_doc or "")
    photo_src = str(photo_data_url or "").strip()
    if not html_text or not photo_src:
        return ""

    if token and token in html_text:
        return html_text.replace(token, photo_src)

    with_src = re.sub(
        r'(<img\b[^>]*class=["\'][^"\']*header-photo[^"\']*["\'][^>]*\bsrc=["\'])([^"\']*)(["\'])',
        rf"\1{photo_src}\3",
        html_text,
        count=1,
        flags=re.IGNORECASE,
    )
    if with_src != html_text:
        return with_src

    def _append_src(match: re.Match[str]) -> str:
        tag = match.group(0)
        if re.search(r'\bsrc=["\']', tag, flags=re.IGNORECASE):
            return tag
        return tag[:-1] + f' src="{photo_src}">'

    appended = re.sub(
        r'<img\b[^>]*class=["\'][^"\']*header-photo[^"\']*["\'][^>]*>',
        _append_src,
        html_text,
        count=1,
        flags=re.IGNORECASE,
    )
    if appended != html_text:
        return appended
    return ""

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


@api.route('/careerforge/cover-letter/chat', methods=['POST'])
def careerforge_cover_letter_chat():
    data = _coerce_request_data()
    runtime, runtime_error, meta = _resolve_runtime(data)
    if runtime_error:
        payload, status = runtime_error
        return jsonify(payload), status

    guard_error = _guard_high_cost_request("cover-letter", data)
    if guard_error:
        payload, status = guard_error
        return jsonify(payload), status

    history = data.get("history") or []
    if isinstance(history, str):
        try:
            history = json.loads(history)
        except (TypeError, ValueError):
            history = []
    if isinstance(history, list):
        history = [
            {
                "role": item.get("role"),
                "content": item.get("content", "")[:12000],
                **({"output_text": item["output_text"][:20000]} if isinstance(item.get("output_text"), str) else {}),
            }
            for item in history
            if isinstance(item, dict)
            and item.get("role") in {"user", "assistant"}
            and isinstance(item.get("content"), str)
        ]
    else:
        history = []

    resume_source = _cover_letter_text_field(data, "resume_source")
    if not resume_source:
        resume_source = "pdf" if request.files.get("resume") else "conversation"
    if resume_source not in {"pdf", "conversation"}:
        resume_source = "conversation"

    resume_text = _extract_resume_text(data) if resume_source == "pdf" else ""
    if resume_source == "pdf" and request.files.get("resume") and not resume_text:
        return jsonify({"error": "resume_parse_failed", "message": "PDF 简历无法读取，请更换文件后重试。"}), 400
    payload = {
        "message": _cover_letter_text_field(data, "message"),
        "history": history,
        "resume_text": resume_text[:20000],
        "jd_text": _cover_letter_text_field(data, "jd_text", limit=12000),
        "company_name": _cover_letter_text_field(data, "company_name"),
        "scenario": _cover_letter_text_field(data, "scenario", default="email"),
        "language": _cover_letter_text_field(data, "language", default="zh"),
        "resume_source": resume_source,
    }

    result = ai_service.run_cover_letter_chat(payload, runtime=runtime)
    if not isinstance(result, dict):
        result = {"error": "invalid_skill_output", "message": "模型未返回有效结果。"}

    reply = result.get("reply") if isinstance(result.get("reply"), str) else ""
    output_text = result.get("output_text") if isinstance(result.get("output_text"), str) else ""
    status = 502 if result.get("error") else 200
    return jsonify(
        {
            "skill": "cover-letter",
            "reply": reply,
            "output_text": output_text,
            "result": result,
            "meta": meta,
            "error": str(result.get("error") or ""),
        }
    ), status

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


@api.route('/careerforge/runtime/check', methods=['POST'])
def careerforge_runtime_check():
    data = _coerce_request_data()
    runtime, runtime_error, meta = _resolve_runtime(data)
    if runtime_error:
        payload, status = runtime_error
        return jsonify(payload), status

    runtime_required = _require_user_runtime_api_key(runtime)
    if runtime_required:
        payload, status = runtime_required
        return jsonify({**payload, "meta": meta}), status

    try:
        result = ai_service.test_runtime_connection(runtime=runtime)
    except RuntimeError as e:
        return jsonify({
            "ok": False,
            "error": "runtime_connection_failed",
            "message": str(e),
            "meta": meta,
        }), 200

    return jsonify({
        **result,
        "meta": meta,
    }), 200


@api.route('/careerforge/resume-match', methods=['POST'])
def careerforge_resume_match():
    data = _coerce_request_data()
    runtime, runtime_error, meta = _resolve_runtime(data)
    if runtime_error:
        payload, status = runtime_error
        return jsonify(payload), status

    runtime_required = _require_user_runtime_api_key(runtime)
    if runtime_required:
        payload, status = runtime_required
        return jsonify({
            "skill": "resume-match",
            **payload,
            "report_html": "",
            "report_name": "",
            "result": None,
            "meta": meta,
        }), status

    guard_error = _guard_high_cost_request("resume-match", data)
    if guard_error:
        payload, status = guard_error
        return jsonify(payload), status

    resume_text = _extract_resume_text(data)
    jd_text = (data.get('jd_text') or '').strip()
    target_role = (data.get('target_role') or '').strip()

    if not resume_text:
        return jsonify({'message': 'Please provide resume_text or upload a resume file.'}), 400
    if not jd_text:
        return jsonify({'message': 'Please provide jd_text.'}), 400

    skill_payload = {
        "target_role": target_role,
        "jd_text": jd_text[:12000],
        "resume_text": resume_text[:20000],
        "prefill_context": {
            "target_role": target_role,
            "jd_text": jd_text[:12000],
            "resume_text": resume_text[:20000],
        },
    }

    try:
        raw_result = ai_service.run_resume_match(skill_payload, runtime=runtime)
    except RuntimeError as e:
        message = str(e)
        error_code = "resume_match_failed"
        error_message = message
        if ":" in message:
            maybe_code, maybe_message = message.split(":", 1)
            maybe_code = maybe_code.strip()
            maybe_message = maybe_message.strip()
            if maybe_code:
                error_code = maybe_code
            if maybe_message:
                error_message = maybe_message
        return jsonify(
            {
                "skill": "resume-match",
                "error": error_code,
                "message": error_message,
                "report_html": "",
                "report_name": "",
                "result": None,
                "meta": meta,
            }
        ), 200

    result, validation_error = _validate_resume_match_result(raw_result)
    if validation_error:
        return jsonify(
            {
                "skill": "resume-match",
                "error": "invalid_skill_output",
                "message": validation_error,
                "report_html": "",
                "report_name": "",
                "result": None,
                "meta": meta,
            }
        ), 200

    report_name = ""
    report_html = ""
    try:
        report_name, report_html = build_resume_match_html_report(
            result=result,
            resume_text=resume_text,
            target_role=target_role,
            jd_text=jd_text,
        )
    except Exception as e:
        logger.warning("resume-match html report generation failed: %s", e)
        return jsonify(
            {
                "skill": "resume-match",
                "error": "report_generation_failed",
                "message": "匹配分析已生成，但报告渲染失败，请稍后重试。",
                "report_html": "",
                "report_name": "",
                "result": result,
                "meta": meta,
            }
        ), 200

    return jsonify(
        {
            "skill": "resume-match",
            "result": result,
            "report_name": report_name,
            "report_html": report_html,
            "meta": meta,
            "process": [
                "Loaded CareerForge resume-match skill via SkillLoader",
                "Parsed current resume and JD input as prefill context",
                "Generated matching report from user BYOK runtime",
            ],
        }
    ), 200


@api.route('/careerforge/resume-craft/chat-turn', methods=['POST'])
def careerforge_resume_craft_chat_turn():
    data = _coerce_request_data()
    runtime, runtime_error, meta = _resolve_runtime(data)
    if runtime_error:
        payload, status = runtime_error
        return jsonify(payload), status

    guard_error = _guard_high_cost_request("resume-craft", data)
    if guard_error:
        payload, status = guard_error
        return jsonify(payload), status

    message = str(data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "empty_message", "message": "请先输入消息内容。", "meta": meta}), 400

    step1_profile = data.get("step1_profile")
    if not isinstance(step1_profile, dict):
        step1_profile = {}

    agent_payload = {
        "message": message,
        "history": data.get("history") or [],
        "current_step": data.get("current_step"),
        "step1_profile": step1_profile,
        "wizard_state": data.get("wizard_state") or {},
    }
    try:
        result = ai_service.run_resume_craft_chat_turn(agent_payload, runtime=runtime)
    except Exception as exc:
        logger.exception("resume-craft agent chat turn failed")
        return jsonify(
            {
                "error": "resume_craft_agent_failed",
                "message": str(exc),
                "meta": meta,
            }
        ), 502

    if not isinstance(result, dict):
        return jsonify(
            {
                "error": "invalid_resume_craft_agent_response",
                "message": "resume-craft agent returned an invalid response.",
                "meta": meta,
            }
        ), 502

    chat_step_states = result.get("wizard_state", {}).get("step_states", {}) if isinstance(result.get("wizard_state"), dict) else {}
    chat_step6 = chat_step_states.get("step6", {}) if isinstance(chat_step_states, dict) else {}
    chat_collected = result.get("wizard_state", {}).get("collected_by_step", {}) if isinstance(result.get("wizard_state"), dict) else {}
    logger.info(
        "resume-craft chat response: current_step=%s action=%s suggestion=%s render_ready=%s "
        "step6_confirmed=%s step6_confirmed_state=%s draft_valid=%s preview_chars=%s",
        data.get("current_step"),
        result.get("action"),
        result.get("next_step_suggestion"),
        result.get("render_ready") is True,
        chat_collected.get("step6_confirmed") is True if isinstance(chat_collected, dict) else False,
        chat_step6.get("confirmed") is True if isinstance(chat_step6, dict) else False,
        bool(chat_step6.get("draft_json")) if isinstance(chat_step6, dict) else False,
        len(str(result.get("step6_preview_markdown") or "")),
    )

    return jsonify({"skill": "resume-craft", **result, "meta": meta, "error": ""}), 200


@api.route('/careerforge/resume-craft/render', methods=['POST'])
def careerforge_resume_craft_render():
    data = _coerce_request_data()
    runtime, runtime_error, meta = _resolve_runtime(data)
    if runtime_error:
        payload, status = runtime_error
        return jsonify(payload), status

    guard_error = _guard_high_cost_request("resume-craft", data)
    if guard_error:
        payload, status = guard_error
        return jsonify(payload), status

    step1_profile = _normalize_step1_profile(data.get("step1_profile") or {})
    wizard_state = data.get("wizard_state") if isinstance(data.get("wizard_state"), dict) else {}
    step_states = wizard_state.get("step_states") if isinstance(wizard_state.get("step_states"), dict) else {}
    step6_state = step_states.get("step6") if isinstance(step_states.get("step6"), dict) else {}
    collected_by_step = wizard_state.get("collected_by_step") if isinstance(wizard_state.get("collected_by_step"), dict) else {}
    logger.info(
        "resume-craft render request: current_step=%s render_ready=%s step6_confirmed=%s "
        "step6_confirmed_state=%s draft_valid=%s history_len=%s",
        wizard_state.get("current_step"),
        data.get("render_ready") is True,
        collected_by_step.get("step6_confirmed") is True,
        step6_state.get("confirmed") is True,
        bool(data.get("draft_json") or step6_state.get("draft_json")),
        len(data.get("history") or []) if isinstance(data.get("history"), list) else 0,
    )
    if (
        not wizard_state
        or data.get("render_ready") is not True
        or collected_by_step.get("step6_confirmed") is not True
        or step6_state.get("confirmed") is not True
    ):
        logger.warning(
            "resume-craft render rejected: missing confirmed generation state "
            "wizard_state=%s render_ready=%s step6_confirmed=%s step6_confirmed_state=%s draft_valid=%s",
            bool(wizard_state),
            data.get("render_ready") is True,
            collected_by_step.get("step6_confirmed") is True,
            step6_state.get("confirmed") is True,
            bool(data.get("draft_json") or step6_state.get("draft_json")),
        )
        return jsonify({"error": "not_ready_for_render", "message": "请先完成 Step6 预览确认后再生成简历。", "meta": meta}), 400

    input_draft_json = data.get("draft_json") if isinstance(data.get("draft_json"), dict) else step6_state.get("draft_json")
    if (not isinstance(input_draft_json, dict) or not input_draft_json) and step6_state.get("preview_ready") is True:
        fallback_draft = _build_confirmed_step6_draft_fallback(step1_profile, wizard_state)
        fallback_personal = fallback_draft.get("personal_info") if isinstance(fallback_draft.get("personal_info"), dict) else {}
        if any(
            [
                fallback_draft.get("target_role"),
                fallback_personal.get("name"),
                fallback_personal.get("phone"),
                fallback_personal.get("email"),
                fallback_draft.get("education"),
                fallback_draft.get("experiences"),
                fallback_draft.get("skills_and_certs"),
                fallback_draft.get("final_preferences"),
            ]
        ):
            input_draft_json = fallback_draft
    if not isinstance(input_draft_json, dict) or not input_draft_json:
        return jsonify(
            {
                "error": "missing_resume_craft_draft",
                "message": "请先让 Agent 完成并确认简历草稿。",
                "meta": meta,
            }
        ), 400
    step6_draft_json = _sanitize_step6_draft_json(input_draft_json)

    template_code = _normalize_resume_craft_template_code(data.get("template_code") or step1_profile.get("template_code"))
    template_en, template_display = RESUME_CRAFT_TEMPLATE_MAP.get(template_code, RESUME_CRAFT_TEMPLATE_MAP["02"])
    language = _normalize_resume_craft_language(data.get("language") or step1_profile.get("language"))
    photo_pref = _normalize_resume_craft_photo_pref(data.get("photo_pref") or step1_profile.get("photo_pref"))
    photo_data_url = str(data.get("photo_data_url") or "").strip()
    processed_photo_data_url = photo_data_url
    photo_process_warning = ""
    if photo_pref == "放照片":
        ok, reason = _validate_photo_data_url(photo_data_url)
        if not ok:
            return jsonify({"error": reason, "message": "请上传 PNG/JPG 照片后再生成简历。", "meta": meta}), 400
        processed_photo_data_url, photo_process_warning = _process_photo_data_url_with_skill(photo_data_url)

    templates = _load_resume_craft_templates()
    preview_snippet = _extract_preview_snippet(templates.get("preview_template", ""), template_code)

    step1_context = _build_step1_profile_context(step1_profile, template_code, language, photo_pref)
    confirmed_facts_context = _build_confirmed_facts_context(
        step1_profile,
        step6_draft_json,
        wizard_state,
    )
    jd_direction_context = _build_jd_direction_context(step1_profile)
    html_payload = {
        "template_code": template_code,
        "template_en": template_en,
        "template_display": template_display,
        "language": language,
        "photo_pref": photo_pref,
        "base_template": templates.get("base_template", ""),
        "preview_snippet": preview_snippet,
        "profile_context": step1_context,
        "history": data.get("history") or [],
        "confirmed_facts_context": confirmed_facts_context,
        "jd_direction_context": jd_direction_context,
        "photo_token": RESUME_CRAFT_PHOTO_TOKEN,
    }

    def render_html(payload: Dict[str, Any]) -> str:
        raw_html = ai_service.run_resume_craft_html(payload, runtime=runtime)
        rendered_html = _extract_html_document(raw_html)
        if rendered_html and photo_pref == "放照片":
            rendered_html = _inject_photo_data_url_into_html(
                rendered_html,
                processed_photo_data_url,
                RESUME_CRAFT_PHOTO_TOKEN,
            )
        return rendered_html

    try:
        report_html = render_html(html_payload)
    except Exception as e:
        logger.exception("resume-craft render failed")
        return jsonify(
            {
                "error": "resume_craft_render_failed",
                "message": f"简历生成失败，请稍后重试：{str(e)[:240]}",
                "meta": meta,
            }
        ), 502

    if not report_html:
        return jsonify(
            {
                "error": "resume_craft_render_failed",
                "message": "模型未返回有效 HTML，请稍后重试。",
                "meta": meta,
            }
        ), 502

    report_name = f"{_build_resume_artifact_stem(step1_profile)}.html"
    pdf_name, pdf_base64, pdf_error = _generate_resume_craft_pdf_artifact(report_html, report_name)
    response_meta = {
        **meta,
        "resume_craft_pdf_generated": bool(pdf_base64),
    }
    if pdf_error:
        response_meta["resume_craft_pdf_error"] = pdf_error
    if photo_process_warning:
        response_meta["resume_craft_photo_process_warning"] = photo_process_warning

    artifact_token = _store_resume_craft_html_artifact(report_html)
    report_url = f"/api/careerforge/resume-craft/artifacts/{artifact_token}"
    logger.info(
        "resume-craft render completed: html_chars=%s pdf_generated=%s pdf_error=%s artifact=%s",
        len(report_html),
        bool(pdf_base64),
        bool(pdf_error),
        bool(artifact_token),
    )

    return jsonify(
        {
            "report_name": report_name,
            "report_html": report_html,
            "report_url": report_url,
            "report_pdf_name": pdf_name,
            "report_pdf_base64": pdf_base64,
            "meta": response_meta,
            "error": "",
        }
    ), 200


@api.route('/careerforge/cover-letter', methods=['POST'])
def careerforge_cover_letter():
    data = _coerce_request_data()
    runtime, runtime_error, meta = _resolve_runtime(data)
    if runtime_error:
        payload, status = runtime_error
        return jsonify(payload), status

    guard_error = _guard_high_cost_request("cover-letter", data)
    if guard_error:
        payload, status = guard_error
        return jsonify(payload), status

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
        },
        runtime=runtime,
    )
    return jsonify(
        {
            "skill": "cover-letter",
            "result": result,
            "meta": meta,
            "process": [
                "Loaded CareerForge cover-letter skill",
                "Matched resume highlights to JD",
                "Generated tailored output",
            ],
        }
    ), 200


@api.route('/careerforge/job-hunt', methods=['POST'])
def careerforge_job_hunt():
    data = _coerce_request_data()
    runtime, runtime_error, meta = _resolve_runtime(data)
    if runtime_error:
        payload, status = runtime_error
        return jsonify(payload), status

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
        },
        runtime=runtime,
    )
    return jsonify(
        {
            "skill": "job-hunt",
            "result": result,
            "meta": meta,
            "process": [
                "Loaded CareerForge job-hunt skill",
                "Built search strategy from profile and constraints",
                "Generated prioritized opportunities",
            ],
        }
    ), 200


@api.route('/careerforge/agent/chat', methods=['POST'])
def careerforge_agent_chat():
    data = _coerce_request_data()
    runtime, runtime_error, meta = _resolve_runtime(data)
    if runtime_error:
        payload, status = runtime_error
        return jsonify(payload), status

    guard_error = _guard_high_cost_request("mock-interview", data)
    if guard_error:
        payload, status = guard_error
        return jsonify(payload), status

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
                    "meta": meta,
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
        runtime=runtime,
    )
    if isinstance(result, dict):
        result.setdefault("meta", meta)

    status_code = 200
    if result.get("error"):
        status_code = 400
    return jsonify(result), status_code

@api.route('/interview/create', methods=['POST'])
def create_interview():
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    interview_language = _normalize_interview_language((data or {}).get('language'))
    
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
        language=interview_language,
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
        language=interview_language,
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
        'initial_message': greeting,
        'language': interview.language or "zh",
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
                    interview_language = _normalize_interview_language(getattr(interview, "language", "zh"))
                    
                    messages = Message.query.filter_by(interview_id=interview_id).order_by(Message.created_at).all()
                    messages_list = [{'role': m.role, 'content': m.content} for m in messages]
                    
                    full_response = ""
                    for chunk in ai_service.chat_response_stream(
                        messages_list,
                        user_content,
                        job_position,
                        language=interview_language,
                    ):
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
            interview_language = _normalize_interview_language(getattr(interview, "language", "zh"))
            messages = Message.query.filter_by(interview_id=interview_id).order_by(Message.created_at).all()
            messages_list = [{'role': m.role, 'content': m.content} for m in messages]
            
            # Generate AI response
            ai_response_content = ai_service.chat_response(
                messages_list,
                user_msg.content,
                job_position,
                language=interview_language,
            )
            
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
    feedback = ai_service.generate_feedback(
        interview,
        language=_normalize_interview_language(getattr(interview, "language", "zh")),
    )
    
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
            'language': interview.language or "zh",
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
        'language': interview.language or "zh",
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
