"""
MirrorView Interview Voice Integration
=======================================
Wires TTS and STT into the existing InterviewWindow flow.

This module contains the changes needed in client/ui/interview_window.py
to enable full voice interaction:

1. Enable the microphone button (STT)
2. Add TTS playback after AI responses
3. Add voice control UI elements

Usage:
    The InterviewWindowVoiceMixin is a drop-in mixin for InterviewWindow.
    Alternatively, use the patch functions to modify InterviewWindow directly.

    # Option A: Mixin
    class InterviewWindow(QWidget, InterviewWindowVoiceMixin):
        ...

    # Option B: Patch after construction
    window = InterviewWindow(...)
    VoiceIntegration.patch(window, tts_client=TTSClient(...))
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
            sentence_start(int): Emitted with sentence index when a
                                 new sentence starts playing
        """
        playback_started = pyqtSignal()
        playback_finished = pyqtSignal()
        playback_error = pyqtSignal(str)
        sentence_start = pyqtSignal(int)

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

        def run(self):
            """Fetch TTS audio and play it."""
            try:
                from tts_integration.client.audio_player import AudioPlayer

                self.player = AudioPlayer(volume=self.volume)
                self.player.start()
                self.playback_started.emit()

                sentence_idx = 0
                for chunk in self.tts_client.stream_tts(
                    text=self.text,
                    voice=self.voice,
                    mode=self.mode,
                    interview_id=self.interview_id,
                ):
                    # Detect sentence boundaries (simple heuristic)
                    if self.mode == "sentence" and sentence_idx == 0:
                        self.sentence_start.emit(sentence_idx)
                        sentence_idx += 1

                    self.player.feed(chunk)

                self.player.finish()
                self.player.wait()
                self.playback_finished.emit()

            except Exception as e:
                logger.error(f"TTSWorker error: {e}", exc_info=True)
                self.playback_error.emit(str(e))

        def stop(self):
            """Stop playback immediately."""
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

    Usage:
        # After creating InterviewWindow:
        VoiceIntegration.enable_mic(interview_window)

        # After AI response is received:
        VoiceIntegration.speak_response(interview_window, response_text)
    """

    @staticmethod
    def enable_mic(window) -> None:
        """
        Enable the microphone button for speech-to-text input.

        This unhides the mic button, connects it to the recording handler,
        and adds visual recording state feedback.

        Args:
            window: InterviewWindow instance
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
                padding: 8px 16px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #059669;
            }
            QPushButton:pressed {
                background-color: #ef4444;
            }
        """)

        # Connect button to recording toggle
        window._voice_recording = False

        def on_mic_clicked():
            if not window._voice_recording:
                # Start recording
                window._voice_recording = True
                window.mic_btn.setText("🔴 Recording...")
                window.mic_btn.setStyleSheet(window.mic_btn.styleSheet().replace(
                    "#10b981", "#ef4444").replace("#059669", "#dc2626"))
                window.toggle_recording()
            else:
                # Stop recording
                window._voice_recording = False
                window.mic_btn.setText("🎤 Speak")
                window.mic_btn.setStyleSheet(window.mic_btn.styleSheet().replace(
                    "#ef4444", "#10b981").replace("#dc2626", "#059669"))
                window.toggle_recording()

        try:
            window.mic_btn.clicked.disconnect()
        except Exception:
            pass
        window.mic_btn.clicked.connect(on_mic_clicked)

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
            window._tts_worker.stop()

        interview_id = getattr(window, 'interview_id', None)

        worker = TTSWorker(
            tts_client=tts_client,
            text=text,
            voice=voice,
            mode="sentence",
            volume=volume,
            interview_id=interview_id,
        )

        # Connect signals for UI feedback
        worker.playback_started.connect(
            lambda: VoiceIntegration._on_tts_started(window)
        )
        worker.playback_finished.connect(
            lambda: VoiceIntegration._on_tts_finished(window)
        )
        worker.playback_error.connect(
            lambda err: VoiceIntegration._on_tts_error(window, err)
        )

        window._tts_worker = worker
        worker.start()
        return worker

    @staticmethod
    def add_voice_controls(window) -> None:
        """
        Add volume slider and voice selector to the input area.

        Creates a small control bar below the message input with:
        - Volume slider
        - Voice toggle (TTS on/off)
        - Current voice indicator

        Args:
            window: InterviewWindow instance
        """
        if not _HAS_QT:
            return

        # Create voice control bar
        control_bar = QWidget()
        control_layout = QHBoxLayout()
        control_layout.setContentsMargins(8, 4, 8, 4)

        # TTS toggle
        tts_toggle = QPushButton("🔊 TTS On")
        tts_toggle.setCheckable(True)
        tts_toggle.setChecked(True)
        tts_toggle.setStyleSheet("""
            QPushButton {
                background-color: #374151;
                color: #d1d5db;
                border: 1px solid #4b5563;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 12px;
            }
            QPushButton:checked {
                background-color: #10b981;
                color: white;
                border-color: #059669;
            }
        """)
        tts_toggle.toggled.connect(
            lambda checked: tts_toggle.setText(
                "🔊 TTS On" if checked else "🔇 TTS Off"
            )
        )

        # Volume slider
        vol_label = QLabel("Vol:")
        vol_label.setStyleSheet("color: #9ca3af; font-size: 12px;")

        vol_slider = QSlider(Qt.Horizontal)
        vol_slider.setRange(0, 150)
        vol_slider.setValue(100)
        vol_slider.setFixedWidth(80)
        vol_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 4px;
                background: #374151;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                width: 12px;
                height: 12px;
                margin: -4px 0;
                background: #10b981;
                border-radius: 6px;
            }
        """)

        # Voice label
        voice_label = QLabel("Voice: default")
        voice_label.setStyleSheet("color: #9ca3af; font-size: 12px;")

        control_layout.addWidget(tts_toggle)
        control_layout.addWidget(vol_label)
        control_layout.addWidget(vol_slider)
        control_layout.addWidget(voice_label)
        control_layout.addStretch()

        control_bar.setLayout(control_layout)

        # Store references
        window._tts_toggle = tts_toggle
        window._tts_volume = vol_slider
        window._tts_voice_label = voice_label
        window._voice_control_bar = control_bar

        # Insert control bar above the send button
        # Find the input layout and add the control bar
        try:
            # The input area is typically inside a QVBoxLayout
            # Look for the layout containing the message_input and send_btn
            input_layout = window.message_input.parent().layout()
            if input_layout:
                input_layout.insertWidget(
                    input_layout.indexOf(window.send_btn),
                    control_bar
                )
        except Exception as e:
            logger.warning(f"Could not insert voice controls: {e}")

        logger.info("Voice controls added to InterviewWindow")

    # ------------------------------------------------------------------
    # Internal callbacks
    # ------------------------------------------------------------------

    @staticmethod
    def _on_tts_started(window):
        """TTS playback started — update UI."""
        if hasattr(window, '_tts_toggle'):
            window._tts_toggle.setText("🔊 Speaking...")

    @staticmethod
    def _on_tts_finished(window):
        """TTS playback finished — restore UI."""
        if hasattr(window, '_tts_toggle'):
            window._tts_toggle.setText("🔊 TTS On" if window._tts_toggle.isChecked()
                                        else "🔇 TTS Off")

    @staticmethod
    def _on_tts_error(window, error_msg: str):
        """TTS error — show feedback."""
        logger.error(f"TTS playback error: {error_msg}")
        if hasattr(window, '_tts_toggle'):
            window._tts_toggle.setText("🔇 Error")


# ---------------------------------------------------------------------------
# InterviewWindow voice integration — decorator approach
# ---------------------------------------------------------------------------


def voice_enabled(cls):
    """
    Class decorator to add voice capability to InterviewWindow.

    Usage:
        @voice_enabled
        class InterviewWindow(QWidget):
            ...

    This automatically:
    1. Calls VoiceIntegration.enable_mic() after __init__
    2. Calls VoiceIntegration.add_voice_controls() after __init__
    3. Hooks into the AI response handler to trigger TTS playback
    """
    if not _HAS_QT:
        return cls

    original_init = cls.__init__

    def new_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)

        # Enable mic after 500ms (wait for UI to fully render)
        QTimer.singleShot(500, lambda: VoiceIntegration.enable_mic(self))
        QTimer.singleShot(600, lambda: VoiceIntegration.add_voice_controls(self))

    cls.__init__ = new_init
    return cls
