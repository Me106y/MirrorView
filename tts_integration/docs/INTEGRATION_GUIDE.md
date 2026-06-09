# Integration Guide — Adding Voice to MirrorView

This guide walks through integrating the TTS/STT voice pipeline into the existing MirrorView application.

---

## Step 1: Fix the Missing LLM Factory

The existing `server/services/ai_service.py` imports from `server.factories.llm_factory`, which **does not exist** in the repository. This blocks the entire AI service.

```bash
# Copy the factory module
cp tts_integration/server/factories/llm_factory.py server/factories/llm_factory.py
```

Verify:
```python
from server.factories.llm_factory import ModelFactory, TTSFactory
llm = ModelFactory.get_model("dashscope", "qwen3-max", temperature=0.7)
print("LLM factory works:", type(llm).__name__)
```

---

## Step 2: Add TTS Service to Server

### 2.1 Copy TTS service

```bash
cp tts_integration/server/tts_service.py server/services/tts_service.py
```

### 2.2 Register TTS routes in `server/app.py`

Add these lines to `server/app.py`:

```python
# In create_app():
from server.services.tts_service import HiggsAudioTTS
from tts_integration.server.routes_tts import tts_bp

app.config['TTS_SERVICE'] = HiggsAudioTTS(voice='default')
app.register_blueprint(tts_bp)
```

### 2.3 Update `server/__init__.py` if needed

Ensure the `services` package is importable.

---

## Step 3: Add Audio Player to Client

### 3.1 Copy audio player

```bash
cp tts_integration/client/audio_player.py client/core/audio_player.py
```

### 3.2 Add TTS client

```bash
cp tts_integration/client/tts_client.py client/core/tts_client.py
```

---

## Step 4: Enable Voice in InterviewWindow

This is the main integration point. Edit `client/ui/interview_window.py`:

### 4.1 Add imports at the top of `interview_window.py`

```python
# Add near other imports
from client.core.audio_player import AudioPlayer
from client.core.tts_client import TTSClient
from client.core.voice_integration import VoiceIntegration, TTSWorker
```

### 4.2 Initialize TTS client in InterviewWindow.__init__

Add after `self.api_client = api_client` (around line 630):

```python
# TTS client for voice output
self._tts_client = TTSClient(
    base_url=api_client.base_url.replace('/api', ''),
    timeout=60,
)
self._tts_enabled = True  # Toggle for voice on/off
self._tts_worker = None
```

### 4.3 Enable the microphone button

Find `self.mic_btn.hide()` (around line 660) and replace with:

```python
# Enable voice input (STT)
VoiceIntegration.enable_mic(self)
```

### 4.4 Add voice controls

After the input area setup, add:

```python
# Add TTS volume + voice controls
VoiceIntegration.add_voice_controls(self)
```

### 4.5 Trigger TTS after AI response

Find `handle_stream_finished()` (the method called when SSE text streaming completes) and add TTS playback:

```python
def handle_stream_finished(self):
    """Called when AI finishes responding."""
    self.send_btn.setEnabled(True)

    # === ADD THIS BLOCK ===
    # Speak the AI's response
    if self._tts_enabled and hasattr(self, '_full_response'):
        voice = getattr(self, '_selected_voice', 'default')
        volume = self._tts_volume.value() / 100.0 if hasattr(self, '_tts_volume') else 1.0
        VoiceIntegration.speak_response(
            self,
            self._full_response,
            voice=voice,
            volume=volume,
        )
    # === END ADD ===
```

### 4.6 Track full response during streaming

In the `handle_chunk_received(chunk)` method, accumulate the full response:

```python
def handle_chunk_received(self, chunk):
    """Handle a text chunk from the streaming AI response."""
    # Existing display logic...
    cursor = self.chat_display.textCursor()
    cursor.movePosition(cursor.End)
    cursor.insertText(chunk)
    self.chat_display.setTextCursor(cursor)
    self.chat_display.ensureCursorVisible()

    # === ADD THIS LINE ===
    # Accumulate for TTS playback
    if not hasattr(self, '_full_response'):
        self._full_response = ""
    self._full_response += chunk
```

Reset `_full_response` when sending a new message:

```python
# In the send button handler, before starting the stream:
self._full_response = ""
```

---

## Step 5: Configure Environment

```bash
# Required for TTS
export BOSON_API_KEY="bai-your-api-key-here"

# Already required for AI (was hardcoded in config.py — move to env)
export DASHSCOPE_API_KEY="sk-your-key-here"

# Optional
export BOSON_TTS_VOICE="default"  # Override default voice
```

---

## Step 6: Update server/config.py (Security)

Move the hardcoded API key to environment variable:

```python
# server/config.py
import os

class Config:
    # BEFORE (insecure):
    # DASHSCOPE_API_KEY = "sk-8729b18340b84faa97760edd5ad2f0d2"

    # AFTER (secure):
    DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
```

---

## Step 7: Test

```bash
# 1. Test TTS service independently
python tts_integration/tests/test_tts_service.py

# 2. Test audio playback
python tts_integration/tests/test_audio_player.py

# 3. Test full pipeline
python tts_integration/tests/test_integration.py

# 4. Start the server and test endpoint
python server/app.py &
sleep 2
curl -X POST http://localhost:5001/api/tts/synthesize \
  -H "Content-Type: application/json" \
  -d '{"text": "Integration test successful.", "mode": "full"}' \
  -o test.pcm

# 5. Play the output
ffplay -f s16le -ar 24000 -ac 1 test.pcm
```

---

## Troubleshooting

### "No module named 'server.factories.llm_factory'"
→ Complete Step 1 above.

### "BOSON_API_KEY not set"
→ Set the environment variable or pass `api_key` parameter directly.

### "No audio output"
- Check speakers are connected and not muted
- Verify `sounddevice` is installed: `python -c "import sounddevice; print(sounddevice.query_devices())"`
- On Linux: install `libportaudio2` and `pulseaudio`

### "sounddevice.PortAudioError: Invalid sample rate"
→ Check that your audio hardware supports 24kHz output. Most modern hardware does, but some may need 44.1kHz or 48kHz. Adjust `SAMPLE_RATE` in `audio_player.py`.

### "TTS playback is delayed"
→ Switch to `mode: "sentence"` for lower latency. This starts playing audio after the first sentence instead of waiting for the full response.

### "Microphone recording does not transcribe correctly"
→ The existing system uses Google STT (requires internet) with PocketSphinx fallback (offline, lower accuracy). For Chinese, ensure `language='zh-CN'`.

---

## Complete File Change Summary

| File | Action | Purpose |
|------|--------|---------|
| `server/factories/llm_factory.py` | **New** | Fix missing LLM factory + add TTS factory |
| `server/services/tts_service.py` | **New** | Higgs Audio v3 TTS wrapper |
| `server/routes_tts.py` | **New** | TTS API endpoints |
| `server/app.py` | **Edit** | Register TTS blueprint + initialize TTS service |
| `server/config.py` | **Edit** | Move API keys to environment variables |
| `client/core/audio_player.py` | **New** | PCM audio playback |
| `client/core/tts_client.py` | **New** | HTTP client for TTS endpoint |
| `client/ui/interview_window.py` | **Edit** | Enable mic, add TTS playback triggers, voice controls |
| `.env` or shell | **New** | `BOSON_API_KEY` environment variable |

---

## Next Steps

1. **Voice cloning**: Record a professional interviewer voice and use `ref_audio` for more realistic interactions
2. **Emotion-aware TTS**: Add emotion tags based on AI feedback tone (encouraging vs. critical)
3. **Streaming sentence TTS**: Interleave TTS audio chunks with text SSE chunks for true real-time speech
4. **Multi-voice**: Use different voices for different interviewers
5. **ElevenLabs / other TTS**: Extend `TTSFactory` to support alternative providers
