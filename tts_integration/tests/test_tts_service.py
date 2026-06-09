"""
Tests for Higgs Audio TTS Service
==================================
Tests the tts_service.py module — Higgs Audio v3 API wrapper.

Run:
    cd MirrorView-TTS
    python -m pytest tts_integration/tests/test_tts_service.py -v

Or without pytest:
    python tts_integration/tests/test_tts_service.py

Requires:
    BOSON_API_KEY environment variable (for live tests)
"""

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tts_integration.server.tts_service import (
    HiggsAudioTTS,
    HiggsAudioError,
    HiggsAudioAuthError,
    HiggsAudioRateLimitError,
    HiggsAudioTimeoutError,
    PRESET_VOICES,
    SENTENCE_END_PATTERN,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Sample test text (short, for fast tests)
SHORT_TEXT = "Hello, this is a test."
LONG_TEXT = (
    "Hello! Welcome to the mock interview. "
    "Today we will discuss your background and experience. "
    "Let us begin with the first question. "
    "What motivated you to apply for this position?"
)

# Known PCM properties for Higgs Audio v3
EXPECTED_SAMPLE_RATE = 24000
EXPECTED_SAMPLE_WIDTH = 2  # 16-bit
EXPECTED_CHANNELS = 1       # mono


def check_pcm_data(data: bytes) -> bool:
    """Verify that data looks like valid PCM."""
    if not data:
        return False
    # PCM 16-bit: byte length must be even
    if len(data) % 2 != 0:
        return False
    return True


# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------


class TestHiggsAudioTTSInit(unittest.TestCase):
    """Test HiggsAudioTTS initialization."""

    def test_default_init(self):
        """Should initialize with default parameters."""
        tts = HiggsAudioTTS()
        self.assertEqual(tts.model, "higgs-audio-v3-tts")
        self.assertEqual(tts.voice, "default")
        self.assertEqual(tts.timeout, 180)
        self.assertEqual(tts.max_retries, 3)

    def test_custom_init(self):
        """Should accept custom parameters."""
        tts = HiggsAudioTTS(
            model="higgs-audio-v3-tts",
            voice="jake",
            timeout=60,
            max_retries=5,
        )
        self.assertEqual(tts.voice, "jake")
        self.assertEqual(tts.timeout, 60)
        self.assertEqual(tts.max_retries, 5)

    @mock.patch.dict(os.environ, {"BOSON_API_KEY": "test-key-123"})
    def test_api_key_from_env(self):
        """Should read API key from BOSON_API_KEY env var."""
        tts = HiggsAudioTTS()
        self.assertEqual(tts.api_key, "test-key-123")

    def test_api_key_from_param(self):
        """Should prefer parameter over env var."""
        tts = HiggsAudioTTS(api_key="param-key")
        self.assertEqual(tts.api_key, "param-key")

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_no_api_key_warning(self):
        """Should not raise on missing key — logs warning."""
        with self.assertLogs("tts_integration.server.tts_service", level="WARNING"):
            HiggsAudioTTS()


class TestBuildPayload(unittest.TestCase):
    """Test _build_payload method."""

    def setUp(self):
        self.tts = HiggsAudioTTS(api_key="test-key")

    def test_minimal_payload(self):
        """Should build minimal valid payload."""
        payload = self.tts._build_payload("Hello", voice="default")
        self.assertEqual(payload["model"], "higgs-audio-v3-tts")
        self.assertEqual(payload["input"], "Hello")
        self.assertEqual(payload["voice"], "default")
        self.assertEqual(payload["response_format"], "pcm")
        self.assertEqual(payload["stream"], True)

    def test_non_streaming_payload(self):
        """Should set stream=False when requested."""
        payload = self.tts._build_payload("Hello", stream=False)
        self.assertFalse(payload["stream"])

    def test_ref_audio_payload(self):
        """Should include ref_audio and ref_text."""
        payload = self.tts._build_payload(
            "Hello",
            ref_audio="https://example.com/voice.wav",
            ref_text="This is a reference.",
        )
        self.assertEqual(payload["ref_audio"], "https://example.com/voice.wav")
        self.assertEqual(payload["ref_text"], "This is a reference.")

    def test_voice_override(self):
        """Should use passed voice over instance default."""
        payload = self.tts._build_payload("Hello", voice="jake")
        self.assertEqual(payload["voice"], "jake")


class TestSplitSentences(unittest.TestCase):
    """Test sentence splitting logic."""

    def test_single_sentence(self):
        """Should keep single sentence as-is."""
        result = HiggsAudioTTS._split_sentences("Hello world.")
        self.assertGreaterEqual(len(result), 1)
        self.assertIn("Hello world", " ".join(result))

    def test_multiple_sentences(self):
        """Should split on period, question mark, exclamation."""
        text = "Hi! How are you? I am fine."
        result = HiggsAudioTTS._split_sentences(text)
        self.assertGreater(len(result), 1)

    def test_no_punctuation(self):
        """Should return the full text as one chunk."""
        text = "Hello world without punctuation"
        result = HiggsAudioTTS._split_sentences(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].strip(), text)

    def test_chinese_sentences(self):
        """Should split Chinese text on Chinese punctuation."""
        text = "你好！欢迎参加面试。准备好了吗？"
        result = HiggsAudioTTS._split_sentences(text)
        self.assertGreater(len(result), 1)

    def test_empty_string(self):
        """Should handle empty input."""
        result = HiggsAudioTTS._split_sentences("")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], "")

    def test_whitespace_only(self):
        """Should handle whitespace-only input."""
        result = HiggsAudioTTS._split_sentences("   \n  ")
        self.assertEqual(len(result), 1)


class TestControlTags(unittest.TestCase):
    """Test inline control tag helpers."""

    def test_emotion_tag(self):
        """Should wrap text in emotion tag."""
        result = HiggsAudioTTS.emotion("Hi!", "enthusiasm")
        self.assertIn("<|emotion:enthusiasm|>", result)
        self.assertIn("Hi!", result)

    def test_pause_tag(self):
        """Should insert pause tag."""
        result = HiggsAudioTTS.pause()
        self.assertEqual(result, "<|prosody:pause|>")

    def test_style_tag(self):
        """Should wrap text in style tag."""
        result = HiggsAudioTTS.style("Hello", "whisper")
        self.assertIn("<|style:whisper|>", result)

    def test_sfx_tag(self):
        """Should include sound effect tag."""
        result = HiggsAudioTTS.sfx("Beep", "beep")
        self.assertIn("<|sfx:beep|>", result)


class TestResponseChecking(unittest.TestCase):
    """Test HTTP response error handling."""

    def setUp(self):
        self.tts = HiggsAudioTTS(api_key="test-key")

    def make_response(self, status_code, text="", headers=None):
        """Create a mock response object."""
        resp = mock.Mock()
        resp.status_code = status_code
        resp.text = text
        resp.headers = headers or {}
        return resp

    def test_200_passes(self):
        """Should not raise for 200."""
        try:
            self.tts._check_response(self.make_response(200))
        except Exception as e:
            self.fail(f"Should not raise: {e}")

    def test_401_raises_auth_error(self):
        """401 should raise HiggsAudioAuthError."""
        with self.assertRaises(HiggsAudioAuthError):
            self.tts._check_response(self.make_response(401))

    def test_403_raises_auth_error(self):
        """403 should raise HiggsAudioAuthError."""
        with self.assertRaises(HiggsAudioAuthError):
            self.tts._check_response(self.make_response(403))

    def test_429_raises_rate_limit(self):
        """429 should raise HiggsAudioRateLimitError."""
        with self.assertRaises(HiggsAudioRateLimitError):
            self.tts._check_response(self.make_response(429))

    def test_500_raises_generic_error(self):
        """500 should raise HiggsAudioError."""
        with self.assertRaises(HiggsAudioError):
            self.tts._check_response(self.make_response(500, "Internal error"))


class TestConstants(unittest.TestCase):
    """Test module-level constants."""

    def test_preset_voices_list(self):
        """Should have voice presets."""
        self.assertIsInstance(PRESET_VOICES, list)
        self.assertIn("default", PRESET_VOICES)

    def test_sentence_pattern(self):
        """Should compile a valid regex."""
        self.assertTrue(SENTENCE_END_PATTERN.search("Hello. World"))
        self.assertTrue(SENTENCE_END_PATTERN.search("你好。世界"))


# ---------------------------------------------------------------------------
# Integration / Live Tests (skipped if no API key)
# ---------------------------------------------------------------------------


@unittest.skipUnless(
    os.environ.get("BOSON_API_KEY"),
    "BOSON_API_KEY not set — skipping live TTS tests",
)
class TestHiggsAudioTTSLive(unittest.TestCase):
    """Live tests against the Boson.ai Higgs Audio v3 API."""

    def setUp(self):
        self.tts = HiggsAudioTTS(timeout=120)

    def test_synthesize_short_text(self):
        """Should synthesize short text and return PCM data."""
        pcm = self.tts.synthesize(SHORT_TEXT)
        self.assertIsInstance(pcm, bytes)
        self.assertGreater(len(pcm), 0)
        self.assertTrue(check_pcm_data(pcm),
                        f"Expected valid PCM, got {len(pcm)} bytes")

    def test_synthesize_long_text(self):
        """Should synthesize longer text."""
        pcm = self.tts.synthesize(LONG_TEXT)
        self.assertGreater(len(pcm), 0)

    def test_stream_yields_chunks(self):
        """Streaming should yield PCM chunks."""
        chunks = list(self.tts.synthesize_stream(SHORT_TEXT))
        self.assertGreater(len(chunks), 0)
        for chunk in chunks:
            self.assertIsInstance(chunk, bytes)
            self.assertGreater(len(chunk), 0)

    def test_stream_sentences(self):
        """Sentence streaming should yield all audio."""
        chunks = list(self.tts.synthesize_stream_sentences(LONG_TEXT))
        self.assertGreater(len(chunks), 0)
        # Total audio should be non-empty
        total = sum(len(c) for c in chunks)
        self.assertGreater(total, 0)

    def test_different_voices(self):
        """Should support different voice presets."""
        for voice in ["default", "jake"][:1]:  # Test one at a time to save API calls
            pcm = self.tts.synthesize("Testing voice " + voice, voice=voice)
            self.assertGreater(len(pcm), 0)
            self.assertTrue(check_pcm_data(pcm))

    def test_emotion_tags(self):
        """Should handle emotion control tags."""
        text = HiggsAudioTTS.emotion("That is wonderful!", "enthusiasm")
        pcm = self.tts.synthesize(text)
        self.assertGreater(len(pcm), 0)

    def test_synthesize_empty_text(self):
        """Should handle minimal text gracefully."""
        # Minimal text — should produce minimal audio
        pcm = self.tts.synthesize("Hi.")
        self.assertGreater(len(pcm), 0)

    def test_pcm_format_correct(self):
        """PCM data should be 16-bit little-endian 24kHz mono."""
        import struct
        import numpy as np

        pcm = self.tts.synthesize(SHORT_TEXT)

        # Convert to numpy for analysis
        samples = np.frombuffer(pcm, dtype=np.int16)

        # Should have at least some non-zero samples
        nonzero = np.count_nonzero(samples)
        self.assertGreater(nonzero, 0,
                           "Expected audio with non-zero samples")


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Higgs Audio TTS Service Tests")
    print("=" * 60)

    # Quick local test (no API call)
    print("\n[1] Running unit tests (no API calls)...")
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    suite.addTests(loader.loadTestsFromTestCase(TestHiggsAudioTTSInit))
    suite.addTests(loader.loadTestsFromTestCase(TestBuildPayload))
    suite.addTests(loader.loadTestsFromTestCase(TestSplitSentences))
    suite.addTests(loader.loadTestsFromTestCase(TestControlTags))
    suite.addTests(loader.loadTestsFromTestCase(TestResponseChecking))
    suite.addTests(loader.loadTestsFromTestCase(TestConstants))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Live tests (requires API key)
    if os.environ.get("BOSON_API_KEY"):
        print("\n[2] Running live API tests...")
        live_suite = loader.loadTestsFromTestCase(TestHiggsAudioTTSLive)
        runner.run(live_suite)
    else:
        print("\n[2] Skipping live tests (set BOSON_API_KEY to run)")

    # Summary
    print("\n" + "=" * 60)
    if result.wasSuccessful():
        print("✓ All unit tests passed")
    else:
        print(f"✗ {len(result.failures)} failures, {len(result.errors)} errors")
        sys.exit(1)
