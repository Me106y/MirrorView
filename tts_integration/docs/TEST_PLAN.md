# Test Plan — MirrorView Voice Integration

## Overview

This document describes the test strategy for verifying the TTS/STT voice integration works correctly in MirrorView.

---

## Test Levels

### Level 1: Unit Tests (no hardware/API)
- **TTS Service**: Payload construction, sentence splitting, response error handling, control tags
- **Audio Player**: Init state, volume control, buffer management, edge cases
- **TTS Client**: URL construction, base URL normalization

### Level 2: Component Tests (needs API key)
- **TTS Live**: Synthesize short/long text, stream chunks, voice presets, emotion tags
- **Audio Playback**: Play silence, sine wave, multiple chunks, pause/resume

### Level 3: Integration Tests (needs API key + audio hardware)
- **End-to-end pipeline**: Text → TTS → PCM → play
- **Streaming pipeline**: Sentence-level streaming → real-time playback
- **Interview scenario**: Realistic multi-sentence interview interaction
- **Multi-language**: Chinese, English, mixed language TTS
- **Latency measurement**: Time-to-first-audio for streaming mode

### Level 4: System Tests (needs full MirrorView running)
- **Server endpoint test**: POST `/api/tts/synthesize` → valid PCM
- **Client-server integration**: Client GUI → send message → hear spoken response
- **Full interview flow**: Login → create interview → voice Q&A → receive spoken feedback

---

## Test Cases

### TC-01: TTS Service — Basic Synthesis
| Field | Detail |
|-------|--------|
| **ID** | TC-01 |
| **Level** | 2 |
| **Precondition** | `BOSON_API_KEY` set |
| **Steps** | 1. Create `HiggsAudioTTS()` with API key<br>2. Call `synthesize("Hello world.")` |
| **Expected** | Returns non-empty bytes. PCM format valid (16-bit LE). |

### TC-02: TTS Service — Streaming
| Field | Detail |
|-------|--------|
| **ID** | TC-02 |
| **Level** | 2 |
| **Precondition** | `BOSON_API_KEY` set |
| **Steps** | 1. Call `synthesize_stream("Test 1. Test 2. Test 3.")`<br>2. Collect all chunks |
| **Expected** | Multiple chunks yielded. Total bytes > 0. |

### TC-03: TTS Service — Sentence Streaming
| Field | Detail |
|-------|--------|
| **ID** | TC-03 |
| **Level** | 2 |
| **Precondition** | `BOSON_API_KEY` set |
| **Steps** | 1. Call `synthesize_stream_sentences("A. B. C. D.")`<br>2. Count chunks |
| **Expected** | Audio produced for all sentences. Lower TTFA than full mode. |

### TC-04: Audio Player — Play/Pause/Resume
| Field | Detail |
|-------|--------|
| **ID** | TC-04 |
| **Level** | 2 |
| **Precondition** | Working audio output |
| **Steps** | 1. Start player, feed sine wave<br>2. Pause after 100ms<br>3. Resume after 100ms<br>4. Finish and wait |
| **Expected** | Playback completes without error. State toggles correctly. |

### TC-05: Audio Player — Volume Control
| Field | Detail |
|-------|--------|
| **ID** | TC-05 |
| **Level** | 2 |
| **Steps** | 1. Create player with volume=0.0 (muted)<br>2. Play test audio<br>3. Repeat with volume=0.5, 1.0 |
| **Expected** | All complete without crash. Higher volume = higher amplitude. |

### TC-06: Audio Player — Buffer Underrun
| Field | Detail |
|-------|--------|
| **ID** | TC-06 |
| **Level** | 2 |
| **Steps** | 1. Start player<br>2. Feed very small chunks with delays<br>3. Monitor underrun count |
| **Expected** | Playback continues (silence fills gaps). No crash. |

### TC-07: Voice Pipeline E2E
| Field | Detail |
|-------|--------|
| **ID** | TC-07 |
| **Level** | 3 |
| **Precondition** | `BOSON_API_KEY` + audio output |
| **Steps** | 1. TTS service synthesizes text<br>2. Audio player plays PCM<br>3. Verify progress reaches 1.0 |
| **Expected** | Full pipeline succeeds. Audio heard from speakers. |

### TC-08: Chinese Language TTS
| Field | Detail |
|-------|--------|
| **ID** | TC-08 |
| **Level** | 3 |
| **Precondition** | `BOSON_API_KEY` |
| **Steps** | 1. Synthesize Chinese text: "您好，欢迎参加面试"<br>2. Play audio |
| **Expected** | Audio produced and plays correctly. Natural Chinese pronunciation. |

### TC-09: Latency — Time to First Audio
| Field | Detail |
|-------|--------|
| **ID** | TC-09 |
| **Level** | 3 |
| **Precondition** | `BOSON_API_KEY` |
| **Steps** | 1. Record start time<br>2. Start streaming TTS<br>3. Record time of first non-empty chunk<br>4. Calculate TTFA |
| **Expected** | TTFA < 10s for short text (network + model dependent). Logged for monitoring. |

### TC-10: Server TTS Endpoint
| Field | Detail |
|-------|--------|
| **ID** | TC-10 |
| **Level** | 4 |
| **Precondition** | MirrorView server running with TTS configured |
| **Steps** | 1. `curl -X POST /api/tts/synthesize -d '{"text":"Test."}' -o test.pcm`<br>2. Check `test.pcm` size<br>3. Play with ffplay |
| **Expected** | HTTP 200. Non-empty PCM file. Audio plays correctly. |

---

## Running Tests

### Quick test (unit tests only, no API needed)
```bash
cd MirrorView-TTS
python -m pytest tts_integration/tests/test_tts_service.py -v -k "Unit"
python -m pytest tts_integration/tests/test_audio_player.py -v
python -m pytest tts_integration/tests/test_integration.py -v -k "Mock"
```

### Full test suite (needs API key)
```bash
export BOSON_API_KEY="bai-xxx"
python -m pytest tts_integration/tests/ -v
```

### Specific test
```bash
# Run only live TTS tests
python -m pytest tts_integration/tests/test_tts_service.py -v -k "Live"

# Run only audio player stress tests
python -m pytest tts_integration/tests/test_audio_player.py -v -k "Stress"

# Run integration pipeline test
python -m pytest tts_integration/tests/test_integration.py -v -k "Mock"
```

---

## Expected Results

### Unit tests (no API key)
✅ All unit tests should pass without any external dependencies.

### Live tests (with API key)
✅ TTS synthesis returns valid PCM  
✅ Streaming produces multiple chunks  
✅ Audio playback completes without error  
✅ Chinese text synthesizes correctly  
✅ TTFA (time-to-first-audio) is reasonable (<10s typical)

---

## Known Limitations

1. **STT tests require microphone** — automated STT tests are limited to simulated audio buffers
2. **TTS latency varies** — network conditions and API load affect TTFA
3. **Voice quality is subjective** — automated tests only verify format, not naturalness
4. **PocketSphinx accuracy is low** — the offline STT fallback may produce inaccurate transcriptions for Chinese
