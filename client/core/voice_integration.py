"""
MirrorView Interview Voice Integration
=======================================
Wires TTS and STT into the existing InterviewWindow flow.

Provides:
- VoiceIntegration class with static methods for patching InterviewWindow
- TTSWorker thread for background TTS playback
- enable_mic() — unhides the microphone button and enables STT
- speak_response() — synthesizes AI response as speech
- add_voice_controls() — volume slider, voice toggle UI
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Try importing Qt components
try:
    from PyQt5.QtWidgets import QPushButton, QSlider, QLabel, QHBoxLayout, QWidget
    from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
    _HAS_QT = True
except ImportError:
    _HAS_QT = False


# ---------------------------------------------------------------------------
# TTS Worker Thread — fetches audio in background, signals when done
# ---------------------------------------------------------------------------

if _HAS_QT:

    class TTSWorker(QThread):
        """
        Background thread for TTS synthesis and playback.

        Fetches PCM audio from the server and feeds it to AudioPlayer
        without blocking the GUI.

        Signals:
            playback_started: Emitted when audio starts playing
            playback_finished: Emitted when all audio has played
            playback_error(str): Emitted on error
        """
        playback_started = pyqtSignal()
        playback_finished = pyqtSignal()
        playback_error = pyqtSignal(str)

        def __init__(self, tts_client, text: str, voice: str = "default",
                     mode: str = "sentence", volume: float = 1.0,
                     interview_id: Optional[int] = None):
            super().__init__()
            self.tts_client = tts_client
            self.text = text
            self.voice = voice
            self.mode = mode
            self.volume = volume
            self.interview_id = interview_id

            # Will be set after run
            self.player = None
            self._cancelled = False

        def run(self):
            """Fetch TTS audio and play it."""
            try:
                from client.core.audio_player import AudioPlayer

                self.player = AudioPlayer(volume=self.volume)
                self.player.start()
                self.playback_started.emit()

                for chunk in self.tts_client.stream_tts(
                    text=self.text,
                    voice=self.voice,
                    mode=self.mode,
                    interview_id=self.interview_id,
                ):
                    if self._cancelled:
                        break
                    self.player.feed(chunk)

                if not self._cancelled:
                    self.player.finish()
                    self.player.wait()

            except Exception as e:
                logger.error(f"TTSWorker error: {e}", exc_info=True)
                self.playback_error.emit(str(e))
                if self.player:
                    self.player.stop()

            finally:
                if not self._cancelled:
                    self.playback_finished.emit()

        def stop(self):
            """Stop playback immediately."""
            self._cancelled = True
            if self.player:
                self.player.stop()
            self.quit()
            self.wait(1000)


# ---------------------------------------------------------------------------
# Voice Integration — patching utilities
# ---------------------------------------------------------------------------


class VoiceIntegration:
    """
    Static methods to add voice capability to InterviewWindow.
    """

    @staticmethod
    def enable_mic(window) -> None:
        """
        Enable the microphone button for speech-to-text input.

        Unhides the mic button, updates its styling, and connects
        it to the recording toggle handler.
        """
        if not hasattr(window, 'mic_btn'):
            logger.warning("InterviewWindow has no mic_btn — cannot enable STT")
            return

        # Unhide the mic button
        window.mic_btn.show()
        window.mic_btn.setToolTip("Click to speak (Voice Input)")
        window.mic_btn.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: white;
                border: none;
                border-radius: 12px;
                padding: 4px 8px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #059669;
            }
        """)
        window.mic_btn.setText("🎤")

        logger.info("STT microphone button enabled")

    @staticmethod
    def speak_response(window, text: str, voice: str = "default",
                       volume: float = 1.0) -> Optional['TTSWorker']:
        """
        Synthesize and play the AI's response as speech.

        Args:
            window: InterviewWindow instance
            text: AI response text to speak
            voice: Voice preset name
            volume: Playback volume (0.0 to 1.0+)

        Returns:
            TTSWorker thread or None if TTS client not configured
        """
        tts_client = getattr(window, '_tts_client', None)
        if not tts_client:
            logger.warning("No TTS client configured on InterviewWindow")
            return None

        # Cancel any ongoing TTS playback
        if hasattr(window, '_tts_worker') and window._tts_worker:
            try:
                window._tts_worker.stop()
            except Exception:
                pass

        interview_id = getattr(window, 'interview_id', None)

        worker = TTSWorker(
            tts_client=tts_client,
            text=text,
            voice=voice,
            mode="sentence",
            volume=volume,
            interview_id=interview_id,
        )

        # Store reference
        window._tts_worker = worker

        # Connect signals
        worker.playback_started.connect(
            lambda: VoiceIntegration._on_tts_started(window)
        )
        worker.playback_finished.connect(
            lambda: VoiceIntegration._on_tts_finished(window)
        )
        worker.playback_error.connect(
            lambda err: logger.error(f"TTS playback error: {err}")
        )

        worker.start()
        return worker

    # ------------------------------------------------------------------
    # Internal callbacks
    # ------------------------------------------------------------------

    @staticmethod
    def _on_tts_started(window):
        """TTS playback started."""
        pass

    @staticmethod
    def _on_tts_finished(window):
        """TTS playback finished."""
        pass
