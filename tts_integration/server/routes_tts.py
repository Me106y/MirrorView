"""
TTS API Routes for MirrorView Server
=====================================
Add these routes to the existing server/routes.py to enable TTS streaming.

Integration steps:
1. Add the blueprint route below to server/routes.py
2. Import HiggsAudioTTS in server/routes.py
3. Initialize the TTS service in create_app()

Endpoints:
- POST /api/tts/synthesize     — Stream PCM audio for given text
- GET  /api/tts/voices         — List available voice presets
- GET  /api/tts/health         — Check TTS service availability
"""

import json
import logging
from flask import Blueprint, request, Response, jsonify, stream_with_context, current_app

logger = logging.getLogger(__name__)

# This blueprint is designed to be registered alongside the existing API blueprint.
# In server/app.py, add:
#   from server.routes_tts import tts_bp
#   app.register_blueprint(tts_bp, url_prefix='/api/tts')

tts_bp = Blueprint('tts', __name__, url_prefix='/api/tts')


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@tts_bp.route('/synthesize', methods=['POST'])
def synthesize_tts():
    """
    Stream TTS audio as raw PCM bytes.

    Request JSON:
        {
            "text": "Hello, this will be spoken.",
            "voice": "default",           // optional
            "mode": "sentence",           // "full" (default) or "sentence"
            "interview_id": 123           // optional, for context
        }

    Response:
        Content-Type: audio/pcm
        Raw 16-bit, 24kHz, mono PCM byte stream

    Error Responses:
        400 — Missing text
        500 — TTS synthesis failure
        503 — TTS service unavailable
    """
    data = request.get_json(silent=True)
    if not data or not data.get("text"):
        return jsonify({"error": "Missing 'text' field"}), 400

    text = data["text"].strip()
    voice = data.get("voice", "default")
    mode = data.get("mode", "full")

    # Get TTS service from app config
    tts_service = current_app.config.get("TTS_SERVICE")
    if not tts_service:
        return jsonify({"error": "TTS service not configured"}), 503

    def generate():
        try:
            if mode == "sentence":
                # Sentence-level streaming for lower latency
                for chunk in tts_service.synthesize_stream_sentences(text, voice=voice):
                    yield chunk
            else:
                # Full text streaming
                for chunk in tts_service.synthesize_stream(text, voice=voice):
                    yield chunk
        except Exception as e:
            logger.error(f"TTS streaming error: {e}", exc_info=True)
            # Cannot send error mid-stream; log and stop
            return

    return Response(
        stream_with_context(generate()),
        mimetype="audio/pcm",
        headers={
            "X-Audio-Sample-Rate": "24000",
            "X-Audio-Channels": "1",
            "X-Audio-Format": "s16le",
            "X-TTS-Voice": voice,
            "X-TTS-Mode": mode,
            "Cache-Control": "no-cache",
        },
    )


@tts_bp.route('/voices', methods=['GET'])
def list_voices():
    """List available TTS voice presets."""
    from server.services.tts_service import PRESET_VOICES

    tts_service = current_app.config.get("TTS_SERVICE")
    current_voice = getattr(tts_service, 'voice', 'default') if tts_service else 'default'

    return jsonify({
        "voices": PRESET_VOICES,
        "current": current_voice,
        "model": "higgs-audio-v3-tts",
    })


@tts_bp.route('/health', methods=['GET'])
def tts_health():
    """Check TTS service health."""
    tts_service = current_app.config.get("TTS_SERVICE")
    if not tts_service:
        return jsonify({
            "status": "unavailable",
            "reason": "TTS service not configured",
        }), 503

    has_key = bool(tts_service.api_key)
    return jsonify({
        "status": "healthy" if has_key else "no_api_key",
        "model": tts_service.model,
        "voice": tts_service.voice,
        "has_api_key": has_key,
    })


# ---------------------------------------------------------------------------
# Alternative: SSE-based streaming that interleaves text + audio markers
# ---------------------------------------------------------------------------


@tts_bp.route('/synthesize-sse', methods=['POST'])
def synthesize_tts_sse():
    """
    Stream TTS audio with SSE framing for use alongside text streaming.

    Each SSE event is a JSON object:
        {"type": "audio", "data": "<base64-encoded-pcm-chunk>"}
        {"type": "done"}

    This format allows the client to receive text chunks (from the existing
    message SSE endpoint) and audio chunks on separate connections with
    the same parsing logic.

    Request JSON: same as /synthesize
    """
    import base64

    data = request.get_json(silent=True)
    if not data or not data.get("text"):
        return jsonify({"error": "Missing 'text' field"}), 400

    text = data["text"].strip()
    voice = data.get("voice", "default")
    mode = data.get("mode", "sentence")

    tts_service = current_app.config.get("TTS_SERVICE")
    if not tts_service:
        return jsonify({"error": "TTS service not configured"}), 503

    def generate():
        try:
            stream_method = (
                tts_service.synthesize_stream_sentences
                if mode == "sentence"
                else tts_service.synthesize_stream
            )
            for chunk in stream_method(text, voice=voice):
                # Encode PCM bytes as base64 for safe SSE transport
                b64 = base64.b64encode(chunk).decode("ascii")
                yield f"data: {json.dumps({'type': 'audio', 'data': b64})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            logger.error(f"TTS SSE streaming error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
