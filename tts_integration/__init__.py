"""
MirrorView-TTS Integration Module
==================================
Adds real-time Text-to-Speech (TTS) and Speech-to-Text (STT) capabilities
to the MirrorView mock interview platform using Boson.ai Higgs Audio v3.

Modules:
- server/tts_service.py  — Higgs Audio v3 API wrapper (streaming PCM synthesis)
- server/factories/      — LLM & TTS model factories
- client/audio_player.py — Real-time PCM audio playback via sounddevice
- client/tts_client.py   — HTTP client for TTS streaming endpoint
"""

__version__ = "1.0.0"
