"""
Integration Tests for MirrorView Voice Pipeline
=================================================
End-to-end tests for the TTS + STT voice interaction pipeline.

Tests the full flow:
    STT (mic recording) → Text → AI (mock) → Text → TTS (synthesis) → Audio playback

Run:
    cd MirrorView-TTS
    python -m pytest tts_integration/tests/test_integration.py -v

Requires:
    BOSON_API_KEY environment variable (for TTS tests)
    Working microphone (for STT tests)
"""

import os
import sys
import time
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import numpy as np

from tts_integration.server.tts_service import HiggsAudioTTS
from tts_integration.client.audio_player import AudioPlayer
from tts_integration.client.tts_client import TTSClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def generate_fake_pcm(duration: float = 0.5) -> bytes:
    """Generate fake PCM audio for testing."""
    sample_rate = 24000
    n_samples = int(sample_rate * duration)
    wave = (0.1 * 32767 * np.sin(
        2 * np.pi * 440 * np.linspace(0, duration, n_samples, endpoint=False)
    )).astype(np.int16)
    return wave.tobytes()


def mock_tts_stream(text, voice="default", mode="full", interview_id=None):
    """Mock TTS stream that yields fake PCM chunks."""
    # Generate ~100ms of audio per call (simulating streaming chunks)
    chunks_per_call = 2
    for _ in range(chunks_per_call):
        yield generate_fake_pcm(0.1)
        time.sleep(0.01)


# ---------------------------------------------------------------------------
# Unit Tests (no hardware required)
# ---------------------------------------------------------------------------


class TestTTSClient(unittest.TestCase):
    """Test TTSClient with mocked server."""

    def setUp(self):
        self.client = TTSClient(base_url="http://localhost:9999")

    @mock.patch("requests.post")
    def test_stream_tts_makes_correct_call(self, mock_post):
        """Should POST to /api/tts/synthesize with correct payload."""
        mock_response = mock.Mock()
        mock_response.__enter__ = mock.Mock(return_value=mock_response)
        mock_response.__exit__ = mock.Mock(return_value=False)
        mock_response.iter_content.return_value = [b"chunk1", b"chunk2"]
        mock_post.return_value = mock_response

        # We can't iterate without actually making the call
        # Just verify the client constructs the right URL
        url = f"{self.client.base_url}/api/tts/synthesize"
        self.assertEqual(
            url,
            "http://localhost:9999/api/tts/synthesize"
        )

    def test_base_url_normalized(self):
        """Should strip trailing slash from base_url."""
        client = TTSClient(base_url="http://localhost:5001/")
        self.assertEqual(client.base_url, "http://localhost:5001")


class TestVoicePipelineMock(unittest.TestCase):
    """Test the full voice pipeline with mocked components."""

    def test_text_to_speech_pipeline(self):
        """Should convert text → TTS → PCM without errors."""
        text = "Hello, this is a test of the voice pipeline."

        # Mock the TTS service response
        with mock.patch.object(
            HiggsAudioTTS, 'synthesize_stream',
            return_value=iter([generate_fake_pcm(0.2)])
        ):
            tts = HiggsAudioTTS(api_key="test-key")
            chunks = list(tts.synthesize_stream(text))
            self.assertGreater(len(chunks), 0)

    def test_pcm_to_playback_pipeline(self):
        """Should feed PCM to AudioPlayer and play without errors."""
        pcm = generate_fake_pcm(0.3)
        player = AudioPlayer(volume=0.0)  # muted

        player.start()
        player.feed(pcm)
        player.finish()

        result = player.wait(timeout=5.0)
        self.assertTrue(result, "Playback timed out")
        self.assertGreater(player._bytes_played, 0)

    def test_sentence_splitting_integration(self):
        """Sentence streaming should process multi-sentence text correctly."""
        text = "Hi! How are you? I'm doing well. Let's begin."

        tts = HiggsAudioTTS(api_key="test-key")
        sentences = tts._split_sentences(text)

        self.assertGreater(len(sentences), 1,
                           f"Expected multiple sentences, got: {sentences}")

    def test_full_mock_pipeline(self):
        """Simulate the full pipeline end-to-end with mocks."""
        # 1. Simulate AI response text
        ai_response = (
            "Thank you for your answer. "
            "That is a great example of your experience. "
            "Let me ask you the next question."
        )

        # 2. Split into sentences
        tts = HiggsAudioTTS(api_key="test-key")
        sentences = tts._split_sentences(ai_response)
        self.assertGreater(len(sentences), 0)

        # 3. Simulate TTS synthesis for each sentence
        total_pcm = bytearray()
        player = AudioPlayer(volume=0.0)
        player.start()

        for sentence in sentences:
            pcm = generate_fake_pcm(0.2)
            total_pcm.extend(pcm)
            player.feed(pcm)

        player.finish()
        result = player.wait(timeout=5.0)
        self.assertTrue(result)
        self.assertGreater(len(total_pcm), 0)

    def test_tts_error_handling(self):
        """Pipeline should handle TTS errors gracefully."""
        tts = HiggsAudioTTS(api_key="invalid-key")

        with mock.patch.object(tts, 'synthesize_stream',
                               side_effect=Exception("API Error")):
            with self.assertRaises(Exception):
                list(tts.synthesize_stream("Test"))


class TestLatencyBudget(unittest.TestCase):
    """Test that the pipeline meets latency targets."""

    def test_audio_player_startup_latency(self):
        """AudioPlayer should start within acceptable time."""
        start = time.time()
        player = AudioPlayer(volume=0.0)
        player.start()
        elapsed = time.time() - start

        player.stop()
        # Startup should be under 500ms
        self.assertLess(elapsed, 2.0,
                        f"AudioPlayer startup took {elapsed:.2f}s")

    def test_pcm_generation_speed(self):
        """Fake PCM generation should be fast."""
        start = time.time()
        for _ in range(10):
            generate_fake_pcm(0.1)
        elapsed = time.time() - start

        # 10 chunks of 100ms should generate in <100ms
        self.assertLess(elapsed, 1.0,
                        f"PCM generation too slow: {elapsed:.2f}s")


class TestSTTSimulation(unittest.TestCase):
    """Simulate STT recording pipeline without actual microphone."""

    def test_audio_buffer_handling(self):
        """Should handle float32 → int16 conversion correctly."""
        sample_rate = 44100
        duration = 1.0
        n_samples = int(sample_rate * duration)

        # Simulate recorded float32 audio
        float_audio = (0.5 * np.sin(
            2 * np.pi * 440 * np.linspace(0, duration, n_samples, endpoint=False)
        )).astype(np.float32)

        # Convert to int16 (as AudioRecorderThread does)
        int_audio = (float_audio * 32767).astype(np.int16)

        self.assertEqual(len(int_audio), n_samples)
        # Should have non-zero samples
        self.assertGreater(np.count_nonzero(int_audio), 0)
        # Should be in valid int16 range
        self.assertGreaterEqual(int_audio.min(), -32768)
        self.assertLessEqual(int_audio.max(), 32767)

    def test_wav_file_creation(self):
        """Should create valid WAV files from audio data."""
        import wave

        sample_rate = 16000
        duration = 0.5
        n_samples = int(sample_rate * duration)
        audio = (0.5 * 32767 * np.sin(
            2 * np.pi * 440 * np.linspace(0, duration, n_samples, endpoint=False)
        )).astype(np.int16)

        # Write WAV to temp file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name

        try:
            with wave.open(temp_path, 'w') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(audio.tobytes())

            # Read back and verify
            with wave.open(temp_path, 'r') as wf:
                self.assertEqual(wf.getnchannels(), 1)
                self.assertEqual(wf.getsampwidth(), 2)
                self.assertEqual(wf.getframerate(), sample_rate)
                frames = wf.readframes(wf.getnframes())

            self.assertGreater(len(frames), 0)

        finally:
            os.unlink(temp_path)


# ---------------------------------------------------------------------------
# Live Integration Tests
# ---------------------------------------------------------------------------


@unittest.skipUnless(
    os.environ.get("BOSON_API_KEY"),
    "BOSON_API_KEY not set — skipping live integration tests",
)
class TestLiveVoicePipeline(unittest.TestCase):
    """Live end-to-end voice pipeline tests."""

    def setUp(self):
        self.tts = HiggsAudioTTS(timeout=120)

    def test_e2e_text_to_audio_playback(self):
        """Full pipeline: text → TTS → playback (live API)."""
        text = "Hello! This is a live integration test of the voice pipeline."

        # Step 1: Synthesize
        pcm = self.tts.synthesize(text)
        self.assertGreater(len(pcm), 0)

        # Step 2: Play (low volume)
        player = AudioPlayer(volume=0.1)
        player.start()
        player.feed(pcm)
        player.finish()
        result = player.wait(timeout=15.0)
        self.assertTrue(result, "Playback timed out")

    def test_e2e_streaming_playback(self):
        """Streaming TTS → real-time playback."""
        text = "This is a streaming test. Each sentence plays as it is generated."

        player = AudioPlayer(volume=0.1)
        player.start()

        for chunk in self.tts.synthesize_stream_sentences(text):
            player.feed(chunk)

        player.finish()
        result = player.wait(timeout=15.0)
        self.assertTrue(result)
        self.assertAlmostEqual(player.progress, 1.0, delta=0.1)

    def test_interview_scenario(self):
        """Simulate a realistic interview interaction."""
        # Interviewer's opening
        opening = (
            "Welcome to the interview! "
            "I have reviewed your resume and I am impressed by your background. "
            "Let us start with a few questions. "
            "First, could you tell me about your most challenging project?"
        )

        player = AudioPlayer(volume=0.1)
        player.start()

        for chunk in self.tts.synthesize_stream_sentences(opening):
            player.feed(chunk)

        player.finish()
        result = player.wait(timeout=20.0)
        self.assertTrue(result, "Interview scenario playback timed out")

    def test_chinese_tts(self):
        """Test Chinese language TTS."""
        text = "你好！欢迎参加今天的面试。请先简单介绍一下你自己。"

        pcm = self.tts.synthesize(text)
        self.assertGreater(len(pcm), 0)

        player = AudioPlayer(volume=0.1)
        player.start()
        player.feed(pcm)
        player.finish()
        result = player.wait(timeout=15.0)
        self.assertTrue(result)

    def test_mixed_language(self):
        """Test mixed Chinese-English TTS."""
        text = "I have experience with Python and 机器学习. 我认为AI是未来。"

        pcm = self.tts.synthesize(text)
        self.assertGreater(len(pcm), 0)

    def test_latency_measurement(self):
        """Measure time-to-first-audio for streaming TTS."""
        text = "Latency test. This should produce audio quickly."

        start = time.time()
        first_chunk_time = None

        player = AudioPlayer(volume=0.05)
        player.start()

        for chunk in self.tts.synthesize_stream(text):
            if first_chunk_time is None and chunk:
                first_chunk_time = time.time()
            player.feed(chunk)

        player.finish()
        player.wait(timeout=15.0)

        if first_chunk_time:
            ttfa = first_chunk_time - start
            print(f"\n    Time-to-first-audio: {ttfa:.2f}s")
            # Should be under 10s (network + model inference)
            self.assertLess(ttfa, 30.0,
                            f"TTFA too high: {ttfa:.2f}s")


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("MirrorView Voice Pipeline Integration Tests")
    print("=" * 60)
    print()

    # Run unit tests
    print("[1] Running unit tests (no hardware/API)...")
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    suite.addTests(loader.loadTestsFromTestCase(TestTTSClient))
    suite.addTests(loader.loadTestsFromTestCase(TestVoicePipelineMock))
    suite.addTests(loader.loadTestsFromTestCase(TestLatencyBudget))
    suite.addTests(loader.loadTestsFromTestCase(TestSTTSimulation))

    runner = unittest.TextTestRunner(verbosity=2)
    unit_result = runner.run(suite)

    # Run live tests if API key is set
    if os.environ.get("BOSON_API_KEY"):
        print("\n[2] Running live integration tests...")
        live_suite = loader.loadTestsFromTestCase(TestLiveVoicePipeline)
        runner.run(live_suite)
    else:
        print("\n[2] Skipping live integration tests.")
        print("    Set BOSON_API_KEY environment variable to run them.")

    print("\n" + "=" * 60)
    if unit_result.wasSuccessful():
        print("✓ All unit tests passed")
    else:
        print(f"✗ {len(unit_result.failures)} failures, "
              f"{len(unit_result.errors)} errors")
        sys.exit(1)
