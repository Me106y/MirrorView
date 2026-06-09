"""
Real-time PCM Audio Player
===========================
Plays raw PCM audio (16-bit, 24kHz, mono) using sounddevice.

Designed for streaming TTS playback — audio chunks are queued and played
as they arrive, enabling "speak-before-done" low-latency interaction.

Features:
- Streaming playback: queue chunks as they arrive from TTS
- Qt integration: emits signals for UI updates
- Buffer management: prevents underrun with configurable watermark
- Graceful interruption: stop current playback immediately
- Volume control

Usage:
    from tts_integration.client.audio_player import AudioPlayer

    player = AudioPlayer()
    player.start()

    # Feed PCM chunks as they arrive
    for pcm_chunk in tts_stream:
        player.feed(pcm_chunk)

    # Wait for playback to finish
    player.wait()
"""

import time
import queue
import threading
import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Audio format constants (matching Higgs Audio v3 PCM output)
# ---------------------------------------------------------------------------
SAMPLE_RATE = 24000        # 24 kHz
SAMPLE_WIDTH = 2           # 16-bit = 2 bytes
NUM_CHANNELS = 1           # mono
DTYPE = np.int16           # NumPy dtype for 16-bit signed int
BLOCKSIZE = 1024           # sounddevice blocksize (latency ≈ blocksize/samplerate)

# ---------------------------------------------------------------------------
# Try importing Qt components (graceful fallback if no Qt)
# ---------------------------------------------------------------------------

try:
    from PyQt5.QtCore import QObject, pyqtSignal
    _HAS_QT = True
except ImportError:
    _HAS_QT = False


class _Signals(QObject if _HAS_QT else object):
    """Qt signals for audio playback state changes."""
    if _HAS_QT:
        playback_started = pyqtSignal()
        playback_finished = pyqtSignal()
        playback_error = pyqtSignal(str)
        buffer_low = pyqtSignal()     # buffer almost empty (potential underrun)
        buffer_ready = pyqtSignal()    # buffer re-filled above watermark


class AudioPlayer:
    """
    Real-time PCM audio player with streaming buffer.

    Args:
        sample_rate: Audio sample rate in Hz (default: 24000)
        num_channels: Number of audio channels (default: 1)
        blocksize: Audio block size for low-latency playback
        buffer_watermark: Minimum audio duration (seconds) to buffer
                          before starting playback. Lower = less latency
                          but higher risk of underrun.
        volume: Volume multiplier (0.0 to 1.0+)

    Example:
        >>> player = AudioPlayer()
        >>> player.start()
        >>> player.feed(pcm_bytes)
        >>> player.feed(more_pcm_bytes)
        >>> player.finish()  # signal no more data
        >>> player.wait()    # block until playback completes
    """

    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE,
        num_channels: int = NUM_CHANNELS,
        blocksize: int = BLOCKSIZE,
        buffer_watermark: float = 0.3,  # 300ms buffer before playing
        volume: float = 1.0,
    ):
        self.sample_rate = sample_rate
        self.num_channels = num_channels
        self.blocksize = blocksize
        self.buffer_watermark = buffer_watermark
        self.volume = max(0.0, volume)

        # Internal state
        self._stream: Optional["sd.OutputStream"] = None
        self._queue: queue.Queue = queue.Queue()
        self._buffer = bytearray()
        self._lock = threading.Lock()
        self._playing = False
        self._finished = False  # set by finish() — no more data coming
        self._paused = False
        self._error: Optional[str] = None

        # Playback thread
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Qt signals (only if PyQt5 available)
        self.signals = _Signals()

        # Stats
        self._bytes_played = 0
        self._total_bytes = 0
        self._underrun_count = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the audio playback engine."""
        if self._playing:
            logger.warning("AudioPlayer already running")
            return

        self._stop_event.clear()
        self._finished = False
        self._paused = False
        self._error = None
        self._bytes_played = 0
        self._total_bytes = 0
        self._underrun_count = 0
        self._buffer = bytearray()

        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._playing = True
        logger.debug("AudioPlayer started")

    def feed(self, pcm_data: bytes) -> None:
        """
        Queue PCM audio data for playback.

        Thread-safe — can be called from any thread.

        Args:
            pcm_data: Raw 16-bit PCM bytes (24kHz, mono)
        """
        if not pcm_data:
            return
        with self._lock:
            self._buffer.extend(pcm_data)
            self._total_bytes += len(pcm_data)
            # Push to queue to wake the playback thread
            self._queue.put(len(pcm_data))

    def finish(self) -> None:
        """
        Signal that no more audio data will be fed.

        The player will play all remaining buffered audio,
        then stop automatically.
        """
        self._finished = True
        self._queue.put(None)  # sentinel to wake the thread
        logger.debug("AudioPlayer: finish signalled")

    def wait(self, timeout: Optional[float] = None) -> bool:
        """
        Block until all queued audio has been played.

        Args:
            timeout: Maximum wait time in seconds (None = wait forever)

        Returns:
            True if playback completed, False if timed out
        """
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        return not (self._thread and self._thread.is_alive())

    def stop(self) -> None:
        """Stop playback immediately and release resources."""
        self._stop_event.set()
        self._finished = True
        self._queue.put(None)  # wake thread

        # Close the sounddevice stream
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        self._playing = False
        logger.debug("AudioPlayer stopped")

    def pause(self) -> None:
        """Pause playback (keeps buffer)."""
        self._paused = True
        if self._stream:
            try:
                self._stream.stop()
            except Exception:
                pass

    def resume(self) -> None:
        """Resume playback after pause."""
        self._paused = False
        if self._stream:
            try:
                self._stream.start()
            except Exception:
                pass

    def set_volume(self, volume: float) -> None:
        """Set volume multiplier (0.0 = mute, 1.0 = original, >1.0 = amplify)."""
        self.volume = max(0.0, volume)

    @property
    def is_playing(self) -> bool:
        """Whether audio is currently playing."""
        return self._playing and not self._paused

    @property
    def latency_ms(self) -> float:
        """Estimated current buffer latency in milliseconds."""
        with self._lock:
            buffered_bytes = len(self._buffer)
        duration_sec = buffered_bytes / (self.sample_rate * SAMPLE_WIDTH * self.num_channels)
        return duration_sec * 1000.0

    @property
    def progress(self) -> float:
        """Fraction of total audio data played (0.0 — 1.0)."""
        if self._total_bytes == 0:
            return 0.0
        return min(1.0, self._bytes_played / self._total_bytes)

    @property
    def error(self) -> Optional[str]:
        """Last error message, if any."""
        return self._error

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        """Main playback loop running in a dedicated thread."""
        import sounddevice as sd

        try:
            self._stream = sd.OutputStream(
                samplerate=self.sample_rate,
                channels=self.num_channels,
                dtype=DTYPE,
                blocksize=self.blocksize,
                callback=self._audio_callback,
                finished_callback=self._on_stream_finished,
            )
            self._stream.start()
            logger.debug("AudioPlayer: sounddevice stream started")

            if _HAS_QT:
                try:
                    self.signals.playback_started.emit()
                except Exception:
                    pass

            # Wait for stop signal or finish
            while not self._stop_event.is_set():
                # Check if all data has been consumed
                with self._lock:
                    buffer_empty = len(self._buffer) == 0

                if self._finished and buffer_empty:
                    # Give the stream time to finish the last block
                    time.sleep(0.1)
                    with self._lock:
                        if len(self._buffer) == 0:
                            break

                time.sleep(0.05)

        except Exception as e:
            logger.error(f"AudioPlayer error: {e}", exc_info=True)
            self._error = str(e)
            if _HAS_QT:
                try:
                    self.signals.playback_error.emit(str(e))
                except Exception:
                    pass

        finally:
            self._cleanup()

    def _audio_callback(self, outdata, frames, time_info, status):
        """sounddevice callback — fills the output buffer with PCM data."""
        if status:
            logger.debug(f"sounddevice status: {status}")

        if self._paused or self._stop_event.is_set():
            outdata.fill(0)
            return

        needed = frames * SAMPLE_WIDTH * self.num_channels

        with self._lock:
            available = len(self._buffer)
            if available >= needed:
                # Enough data — copy and consume
                raw = bytes(self._buffer[:needed])
                self._buffer = self._buffer[needed:]
            elif available > 0:
                # Partial data — pad with silence
                raw = bytes(self._buffer) + b'\x00' * (needed - available)
                self._buffer = bytearray()
                self._underrun_count += 1
            else:
                # No data — silence
                raw = b'\x00' * needed
                self._underrun_count += 1

        # Convert bytes to numpy array
        audio = np.frombuffer(raw, dtype=DTYPE)

        # Apply volume
        if self.volume != 1.0:
            audio = (audio * self.volume).astype(DTYPE)

        # Reshape for multi-channel (though we use mono)
        if self.num_channels > 1:
            audio = audio.reshape(-1, self.num_channels)

        outdata[:] = audio.reshape(outdata.shape)
        self._bytes_played += needed

        # Emit buffer status signals
        if _HAS_QT and (self._bytes_played % (self.sample_rate * SAMPLE_WIDTH) < needed):
            # Check once per second approximately
            with self._lock:
                buffered_sec = len(self._buffer) / (self.sample_rate * SAMPLE_WIDTH)
            if buffered_sec < self.buffer_watermark / 2:
                try:
                    self.signals.buffer_low.emit()
                except Exception:
                    pass

    def _on_stream_finished(self):
        """Called when the sounddevice stream finishes."""
        logger.debug("AudioPlayer: stream finished")
        if _HAS_QT:
            try:
                self.signals.playback_finished.emit()
            except Exception:
                pass

    def _cleanup(self):
        """Release sounddevice resources."""
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        self._playing = False
        logger.debug(f"AudioPlayer cleaned up (played {self._bytes_played} bytes)")


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


def play_pcm(pcm_data: bytes, volume: float = 1.0) -> None:
    """
    Play PCM audio synchronously (blocking).

    Simple one-shot playback — for streaming, use AudioPlayer directly.

    Args:
        pcm_data: Raw 16-bit PCM bytes
        volume: Volume multiplier
    """
    player = AudioPlayer(volume=volume)
    player.start()
    player.feed(pcm_data)
    player.finish()
    player.wait()
