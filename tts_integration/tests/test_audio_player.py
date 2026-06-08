"""
Tests for Audio Player
=======================
Tests the audio_player.py module — PCM audio playback via sounddevice.

Run:
    cd MirrorView-TTS
    python -m pytest tts_integration/tests/test_audio_player.py -v

Or without pytest:
    python tts_integration/tests/test_audio_player.py
"""

import sys
import time
import unittest
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import numpy as np

from tts_integration.client.audio_player import (
    AudioPlayer,
    play_pcm,
    SAMPLE_RATE,
    SAMPLE_WIDTH,
    NUM_CHANNELS,
    BLOCKSIZE,
    DTYPE,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def generate_sine_pcm(
    frequency: float = 440.0,
    duration: float = 0.5,
    sample_rate: int = SAMPLE_RATE,
    amplitude: float = 0.3,
) -> bytes:
    """Generate a simple sine wave as PCM bytes."""
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    wave = (amplitude * 32767 * np.sin(2 * np.pi * frequency * t)).astype(DTYPE)
    return wave.tobytes()


def generate_silence_pcm(duration: float = 0.1) -> bytes:
    """Generate silence PCM bytes."""
    n_samples = int(SAMPLE_RATE * duration)
    return np.zeros(n_samples, dtype=DTYPE).tobytes()


# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------


class TestAudioPlayerInit(unittest.TestCase):
    """Test AudioPlayer initialization."""

    def test_default_init(self):
        """Should create with defaults."""
        player = AudioPlayer()
        self.assertEqual(player.sample_rate, 24000)
        self.assertEqual(player.num_channels, 1)
        self.assertEqual(player.volume, 1.0)
        self.assertFalse(player.is_playing)

    def test_custom_init(self):
        """Should accept custom parameters."""
        player = AudioPlayer(
            sample_rate=44100,
            num_channels=2,
            buffer_watermark=0.5,
            volume=0.8,
        )
        self.assertEqual(player.sample_rate, 44100)
        self.assertEqual(player.num_channels, 2)
        self.assertEqual(player.buffer_watermark, 0.5)
        self.assertEqual(player.volume, 0.8)

    def test_initial_state(self):
        """Should be in correct initial state."""
        player = AudioPlayer()
        self.assertEqual(player.progress, 0.0)
        self.assertIsNone(player.error)
        self.assertFalse(player.is_playing)


class TestAudioPlayerPlayback(unittest.TestCase):
    """Test basic playback functionality."""

    def test_start_stop(self):
        """Should start and stop without error."""
        player = AudioPlayer()
        player.start()
        self.assertTrue(player.is_playing)
        time.sleep(0.1)
        player.stop()
        self.assertFalse(player.is_playing)

    def test_play_silence(self):
        """Should play silence without error (no audible output)."""
        pcm = generate_silence_pcm(0.2)
        player = AudioPlayer()
        player.start()
        player.feed(pcm)
        player.finish()
        result = player.wait(timeout=5.0)
        self.assertTrue(result)
        self.assertGreater(player.progress, 0.9)

    def test_play_sine_wave(self):
        """Should play a sine wave tone."""
        pcm = generate_sine_pcm(frequency=440, duration=0.3)
        player = AudioPlayer(volume=0.1)  # quiet
        player.start()
        player.feed(pcm)
        player.finish()
        result = player.wait(timeout=5.0)
        self.assertTrue(result, "Playback timed out")
        # Should have played most of the data
        self.assertGreater(player.progress, 0.8)

    def test_feed_multiple_chunks(self):
        """Should handle multiple feed() calls."""
        player = AudioPlayer(volume=0.1)
        player.start()

        for _ in range(3):
            chunk = generate_sine_pcm(duration=0.1)
            player.feed(chunk)
            time.sleep(0.02)

        player.finish()
        result = player.wait(timeout=5.0)
        self.assertTrue(result)

    def test_pause_resume(self):
        """Should pause and resume playback."""
        pcm = generate_sine_pcm(duration=1.0)
        player = AudioPlayer(volume=0.1)
        player.start()
        player.feed(pcm)

        # Pause after a short delay
        time.sleep(0.1)
        player.pause()
        self.assertFalse(player.is_playing)

        # Resume
        player.resume()
        self.assertTrue(player.is_playing)

        player.finish()
        result = player.wait(timeout=5.0)
        self.assertTrue(result)

    def test_play_pcm_convenience(self):
        """Should play via the convenience function."""
        pcm = generate_silence_pcm(0.2)
        try:
            play_pcm(pcm, volume=0.1)
        except Exception as e:
            self.fail(f"play_pcm() raised: {e}")


class TestAudioPlayerLatency(unittest.TestCase):
    """Test latency estimation."""

    def test_latency_increases_with_buffer(self):
        """Latency should reflect buffered audio."""
        player = AudioPlayer()

        # Before start, buffer is empty
        self.assertAlmostEqual(player.latency_ms, 0.0, delta=1.0)

        # After feeding data, latency should increase
        pcm = generate_sine_pcm(duration=1.0)
        player.start()
        player.feed(pcm)

        # Give it a moment to measure
        time.sleep(0.05)
        latency = player.latency_ms
        # Should have some buffered data
        self.assertGreater(latency, 0.0)
        # Should be under ~1.5s (1s of audio + buffer)
        self.assertLess(latency, 2000.0)

        player.stop()


class TestAudioPlayerVolume(unittest.TestCase):
    """Test volume control."""

    def test_default_volume(self):
        """Default volume should be 1.0."""
        player = AudioPlayer()
        self.assertEqual(player.volume, 1.0)

    def test_set_volume(self):
        """Should update volume."""
        player = AudioPlayer(volume=0.5)
        self.assertEqual(player.volume, 0.5)
        player.set_volume(0.8)
        self.assertEqual(player.volume, 0.8)

    def test_volume_clamp(self):
        """Should not allow negative volume."""
        player = AudioPlayer(volume=-0.5)
        self.assertEqual(player.volume, 0.0)

    def test_play_at_different_volumes(self):
        """Should play at different volumes."""
        pcm = generate_silence_pcm(0.2)
        for vol in [0.0, 0.5, 1.0]:
            player = AudioPlayer(volume=vol)
            player.start()
            player.feed(pcm)
            player.finish()
            result = player.wait(timeout=5.0)
            self.assertTrue(result, f"Playback failed at volume {vol}")


class TestAudioPlayerEdgeCases(unittest.TestCase):
    """Test edge cases."""

    def test_feed_empty_bytes(self):
        """Should handle empty byte feed gracefully."""
        player = AudioPlayer()
        player.start()
        player.feed(b"")
        player.feed(b"")
        player.finish()
        result = player.wait(timeout=3.0)
        self.assertTrue(result)

    def test_finish_before_start(self):
        """Should handle finish() without start()."""
        player = AudioPlayer()
        player.finish()
        result = player.wait(timeout=1.0)
        self.assertTrue(result)

    def test_stop_before_start(self):
        """Should handle stop() without start()."""
        player = AudioPlayer()
        player.stop()
        self.assertFalse(player.is_playing)

    def test_double_start(self):
        """Should warn but not crash on double start."""
        player = AudioPlayer()
        player.start()
        player.start()  # should log warning
        player.stop()

    def test_progress_at_zero(self):
        """Progress should be 0.0 for empty player."""
        player = AudioPlayer()
        self.assertEqual(player.progress, 0.0)


class TestAudioPlayerConstants(unittest.TestCase):
    """Verify audio format constants match Higgs Audio v3 spec."""

    def test_sample_rate(self):
        """Sample rate should be 24kHz."""
        self.assertEqual(SAMPLE_RATE, 24000)

    def test_sample_width(self):
        """Should be 16-bit."""
        self.assertEqual(SAMPLE_WIDTH, 2)

    def test_mono(self):
        """Should be mono."""
        self.assertEqual(NUM_CHANNELS, 1)

    def test_dtype(self):
        """Should use int16."""
        self.assertEqual(DTYPE, np.int16)


# ---------------------------------------------------------------------------
# Stress Tests
# ---------------------------------------------------------------------------


class TestAudioPlayerStress(unittest.TestCase):
    """Stress test with rapid feed calls."""

    def test_rapid_small_feeds(self):
        """Should handle many small feed() calls."""
        player = AudioPlayer(volume=0.05)

        player.start()
        for _ in range(50):
            chunk = generate_sine_pcm(duration=0.01)
            player.feed(chunk)
            time.sleep(0.001)

        player.finish()
        result = player.wait(timeout=10.0)
        self.assertTrue(result)

    def test_large_single_feed(self):
        """Should handle a large PCM chunk."""
        pcm = generate_sine_pcm(duration=2.0, amplitude=0.1)
        player = AudioPlayer(volume=0.1)
        player.start()
        player.feed(pcm)
        player.finish()
        result = player.wait(timeout=10.0)
        self.assertTrue(result)
        self.assertAlmostEqual(player.progress, 1.0, delta=0.1)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Audio Player Tests")
    print("=" * 60)
    print()
    print("Note: These tests produce audio through your speakers.")
    print("Volume is set low by default.")
    print()
    unittest.main(verbosity=2)
