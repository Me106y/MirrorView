# MirrorView Voice Integration — Documentation

## Overview

This directory contains the TTS (Text-to-Speech) and STT (Speech-to-Text) integration for MirrorView, adding **real-time voice interaction** to the mock interview platform.

### What it does

| Component | Before | After |
|-----------|--------|-------|
| AI Response | Text-only display | **Spoken aloud** via Higgs Audio v3 TTS |
| User Input | Typing only | **Voice input** via microphone (STT) |
| Interview Flow | Read/Watch only | **Real-time conversation** with AI interviewer |

### Architecture

```
┌─────────────────────────────────────────────────────┐
│                   MirrorView Client                  │
│  ┌──────────┐  ┌───────────┐  ┌──────────────────┐ │
│  │ Mic (STT)│  │AudioPlayer│  │VoiceIntegration  │ │
│  │sounddevice│  │sounddevice│  │(mixin for        │ │
│  │SpeechRecog│  │24kHz PCM  │  │InterviewWindow)  │ │
│  └────┬─────┘  └─────┬─────┘  └────────┬─────────┘ │
│       │              │                 │            │
└───────┼──────────────┼─────────────────┼────────────┘
        │              │                 │
     Audio          PCM Audio       REST/SSE
        │              │                 │
┌───────┼──────────────┼─────────────────┼────────────┐
│       │         MirrorView Server      │            │
│  ┌────┴─────┐  ┌─────┴──────┐  ┌──────┴──────────┐ │
│  │ STT API  │  │ TTS Routes │  │  AI Service      │ │
│  │(existing)│  │/api/tts/*  │  │  (LangChain)     │ │
│  └──────────┘  └─────┬──────┘  └─────────────────┘ │
│                      │                              │
└──────────────────────┼──────────────────────────────┘
                       │
               ┌───────┴────────┐
               │ Boson.ai       │
               │ Higgs Audio v3 │
               │ 24kHz PCM      │
               └────────────────┘
```

---

## File Structure

```
tts_integration/
├── __init__.py                        # Package info
├── server/
│   ├── __init__.py
│   ├── tts_service.py                 # Higgs Audio v3 API wrapper
│   ├── routes_tts.py                  # Flask TTS API endpoints
│   └── factories/
│       ├── __init__.py
│       └── llm_factory.py             # LLM + TTS model factories
├── client/
│   ├── __init__.py
│   ├── audio_player.py                # PCM audio playback (sounddevice)
│   ├── tts_client.py                  # TTS HTTP client
│   └── voice_integration.py           # InterviewWindow voice integration
├── tests/
│   ├── __init__.py
│   ├── test_tts_service.py            # TTS service unit + live tests
│   ├── test_audio_player.py           # Audio player tests
│   └── test_integration.py            # End-to-end voice pipeline tests
└── docs/
    ├── README.md                      # ← This file
    ├── API.md                         # API reference
    ├── INTEGRATION_GUIDE.md           # Step-by-step integration guide
    └── TEST_PLAN.md                   # Test plan and procedures
```

---

## Quick Start

### 1. Prerequisites

```bash
# Install audio dependencies
pip install sounddevice numpy requests

# Set your Boson.ai API key
export BOSON_API_KEY="bai-xxxxxxxxxxxx"
```

### 2. Test the TTS Service

```bash
# Unit tests (no API key needed)
python tts_integration/tests/test_tts_service.py

# Live tests (needs BOSON_API_KEY)
BOSON_API_KEY="bai-xxx" python tts_integration/tests/test_tts_service.py

# Audio playback tests
python tts_integration/tests/test_audio_player.py

# Integration tests
python tts_integration/tests/test_integration.py
```

### 3. Quick Demo

```python
from tts_integration.server.tts_service import HiggsAudioTTS
from tts_integration.client.audio_player import AudioPlayer

# Synthesize speech
tts = HiggsAudioTTS(voice="default")
player = AudioPlayer()

player.start()
for chunk in tts.synthesize_stream("Hello! Welcome to your mock interview."):
    player.feed(chunk)
player.finish()
player.wait()
```

---

## Integration Steps

See [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) for detailed steps to integrate voice into the existing MirrorView application.

### Summary

1. **Copy** `server/factories/llm_factory.py` → `server/factories/` (fixes missing import)
2. **Copy** `server/tts_service.py` → `server/services/tts_service.py`
3. **Register** TTS routes in `server/app.py`
4. **Copy** `client/audio_player.py` → `client/core/audio_player.py`
5. **Patch** `client/ui/interview_window.py` to enable mic + TTS playback
6. **Set** `BOSON_API_KEY` environment variable

---

## Technology

| Technology | Purpose |
|------------|---------|
| [Boson.ai Higgs Audio v3](https://docs.boson.ai/models/higgs-audio-tts/overview) | TTS synthesis (100+ languages) |
| `sounddevice` | Audio capture (mic) and playback (speakers) |
| `SpeechRecognition` | Google / PocketSphinx STT |
| `numpy` | Audio data processing |
| `requests` | HTTP streaming client |
| PyQt5 | GUI integration (signals/slots) |
| Flask | Server-side TTS API endpoints |
