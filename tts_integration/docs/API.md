# TTS API Reference

## Server Endpoints

### `POST /api/tts/synthesize`

Stream TTS audio as raw PCM bytes.

**Request:**
```json
{
    "text": "Hello, this will be spoken aloud.",
    "voice": "default",
    "mode": "sentence",
    "interview_id": 123
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `text` | string | **Yes** | — | Text to synthesize. Supports inline control tags. |
| `voice` | string | No | `"default"` | Voice preset (see [Voices](#voices)) |
| `mode` | string | No | `"full"` | `"full"` = entire text at once; `"sentence"` = per-sentence streaming for lower latency |
| `interview_id` | integer | No | — | Interview context (for future use) |

**Response:**
- Content-Type: `audio/pcm`
- Raw 16-bit signed integer PCM, 24kHz sample rate, mono, little-endian
- Headers:
  - `X-Audio-Sample-Rate: 24000`
  - `X-Audio-Channels: 1`
  - `X-Audio-Format: s16le`
  - `X-TTS-Voice: <voice_name>`

**Errors:**
| Status | Meaning |
|--------|---------|
| 400 | Missing `text` field |
| 503 | TTS service not configured (no API key) |
| 500 | Synthesis failure |

**Example (curl):**
```bash
curl -X POST http://localhost:5001/api/tts/synthesize \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world!", "voice": "default", "mode": "sentence"}' \
  --output audio.pcm

# Play the PCM audio (macOS/Linux)
# ffplay -f s16le -ar 24000 -ac 1 audio.pcm
```

**Example (Python):**
```python
import requests

with requests.post(
    "http://localhost:5001/api/tts/synthesize",
    json={"text": "Hello world!", "voice": "default", "mode": "sentence"},
    stream=True,
) as r:
    r.raise_for_status()
    for chunk in r.iter_content(chunk_size=4096):
        # Each chunk is raw PCM audio
        play_audio(chunk)
```

---

### `POST /api/tts/synthesize-sse`

Same as `/synthesize` but returns SSE-framed JSON events with base64-encoded audio chunks. Compatible with the existing text SSE streaming format.

**Request:** Same as `/api/tts/synthesize`

**Response:** `text/event-stream`
```
data: {"type": "audio", "data": "<base64-encoded-pcm-chunk>"}
data: {"type": "audio", "data": "<base64-encoded-pcm-chunk>"}
data: {"type": "done"}
```

**Error event:**
```
data: {"type": "error", "message": "TTS synthesis failed"}
```

---

### `GET /api/tts/voices`

List available voice presets.

**Response:**
```json
{
    "voices": ["default", "jake", "emma", "sophia", "liam", "olivia", "noah", "ava", "ethan", "mia"],
    "current": "default",
    "model": "higgs-audio-v3-tts"
}
```

---

### `GET /api/tts/health`

Check TTS service availability.

**Response (healthy):**
```json
{
    "status": "healthy",
    "model": "higgs-audio-v3-tts",
    "voice": "default",
    "has_api_key": true
}
```

**Response (no API key):**
```json
{
    "status": "no_api_key",
    "model": "higgs-audio-v3-tts",
    "voice": "default",
    "has_api_key": false
}
```

**Response (not configured):**
```json
{
    "status": "unavailable",
    "reason": "TTS service not configured"
}
```
Status: 503

---

## Audio Format Specification

All PCM audio follows this specification:

| Parameter | Value |
|-----------|-------|
| Encoding | Signed 16-bit integer (s16le) |
| Sample Rate | 24,000 Hz |
| Channels | 1 (mono) |
| Byte Order | Little-endian |
| Byte Rate | 48,000 bytes/second |

To play with common tools:

```bash
# ffplay
ffplay -f s16le -ar 24000 -ac 1 audio.pcm

# Python sounddevice
import sounddevice as sd
import numpy as np
samples = np.frombuffer(pcm_data, dtype=np.int16)
sd.play(samples, samplerate=24000)
sd.wait()

# PyAudio
import pyaudio
p = pyaudio.PyAudio()
stream = p.open(format=pyaudio.paInt16, channels=1, rate=24000, output=True)
stream.write(pcm_data)
```

---

## Voice Presets

| ID | Description |
|----|-------------|
| `default` | Neutral, balanced voice (default) |
| `jake` | Male, warm and professional |
| `emma` | Female, clear and friendly |
| `sophia` | Female, soft and natural |
| `liam` | Male, confident and articulate |
| `olivia` | Female, warm and engaging |
| `noah` | Male, calm and steady |
| `ava` | Female, bright and energetic |
| `ethan` | Male, deep and authoritative |
| `mia` | Female, gentle and approachable |

For the latest list, check: https://docs.boson.ai/models/higgs-audio-tts/voices

---

## Control Tags

Higgs Audio v3 supports inline control tags embedded in the text:

### Emotion
```
<|emotion:enthusiasm|>Welcome to the interview!
<|emotion:calm|>Take your time to answer.
<|emotion:concern|>Are you sure about that?
```

### Prosody
```
Let me think<|prosody:pause|>about your answer.
This is important<|prosody:slow|>so listen carefully.
```

### Style
```
<|style:whisper|>This is confidential.
<|style:professional|>Let's begin the technical assessment.
```

### Sound Effects
```
Correct! <|sfx:ding|>
Time's up. <|sfx:bell|>
```

Full reference: https://docs.boson.ai/models/higgs-audio-tts/tags

---

## Streaming Modes

### Full Mode (`mode: "full"`)

The entire text is sent to the TTS API in one request. Audio chunks are streamed as they are generated. **Higher latency** (wait for full TTS before playback starts) but **simpler**.

Best for: Short responses, non-interactive scenarios.

### Sentence Mode (`mode: "sentence"`)

Text is split into sentences. Each sentence is sent to the TTS API separately. Audio for sentence N can play while sentence N+1 is being synthesized. **Lower perceived latency** — playback begins after the first sentence.

Best for: Long AI responses, interactive conversation.

---

## Voice Cloning

To clone a voice, provide a reference audio clip:

```json
{
    "text": "Hello world",
    "ref_audio": "https://example.com/voice-sample.wav",
    "ref_text": "This is the transcript of the reference audio."
}
```

- `ref_audio`: URL, base64 data URI, or file path to a short audio clip
- `ref_text`: Transcript of the reference clip (improves quality)

⚠️ **Important**: You must own the rights to clone the voice.

Reference: https://docs.boson.ai/models/higgs-audio-tts/voices#reference-voice
