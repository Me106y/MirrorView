from PyQt5.QtWidgets import (QWidget, QLabel, QTextEdit, QListWidget, QLineEdit, QPushButton, QVBoxLayout,
                             QHBoxLayout, QMessageBox, QSplitter, QFileDialog, QFrame, QDialog, QSizePolicy,
                             QScrollArea, QApplication, QComboBox)
from PyQt5.QtCore import Qt, pyqtSlot, QTimer, QThread, pyqtSignal, QSize
from PyQt5.QtGui import QImage, QPixmap, QIcon
from client.core.video_thread import VideoThread
from utils.logger_handler import logger
import subprocess
import numpy as np
import shutil
import os
import json
from collections import deque
import sounddevice as sd
import scipy.io.wavfile as wav
import speech_recognition as sr
import tempfile
import time

# --- Voice Integration (TTS + STT) ---
try:
    from client.core.audio_player import AudioPlayer
    from client.core.tts_client import TTSClient
    from client.core.voice_integration import VoiceIntegration, TTSWorker
    _VOICE_AVAILABLE = True
except ImportError as e:
    _VOICE_AVAILABLE = False
    logger.warning(f"Voice integration not available: {e}")
# --- End Voice Integration ---

class AudioRecorderThread(QThread):
    finished_signal = pyqtSignal(str) # Emits path to wav file
    
    def __init__(self):
        super().__init__()
        self.recording = False
        self.frames = []
        self.fs = 44100
        
    def run(self):
        self.recording = True
        self.frames = []
        
        # Use sounddevice InputStream
        # Try to use default input device with robust settings
        try:
            with sd.InputStream(samplerate=self.fs, channels=1, callback=self.callback):
                while self.recording:
                    self.msleep(100)
        except Exception as e:
            logger.error(f"Audio recording error: {e}")
            # Try fallback parameters if default fails (common on some macOS setups)
            try:
                with sd.InputStream(samplerate=16000, channels=1, callback=self.callback): # Lower sample rate
                    while self.recording:
                        self.msleep(100)
            except Exception as e2:
                logger.error(f"Audio recording fallback error: {e2}")
                self.finished_signal.emit("ERROR")
                return
                
        # Save to file
        if self.frames:
            recording = np.concatenate(self.frames, axis=0)
            
            # Convert to int16 for compatibility with SpeechRecognition
            # Assuming recording is float32 in [-1, 1], scale to int16 range
            if recording.dtype != np.int16:
                 recording = (recording * 32767).astype(np.int16)
            
            timestamp = int(time.time())
            filename = os.path.join(tempfile.gettempdir(), f"rec_{timestamp}.wav")
            wav.write(filename, self.fs, recording)
            self.finished_signal.emit(filename)
            
    def callback(self, indata, frames, time, status):
        if status:
            print(status)
        self.frames.append(indata.copy())
        
    def stop(self):
        self.recording = False
        self.wait()

class InviteCodeDialog(QDialog):
    def __init__(self, code, parent=None):
        super().__init__(parent)
        self.code = code
        self.setWindowTitle("Invite Code")
        self.setFixedSize(500, 300)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        container = QFrame()
        container.setObjectName("dialogContainer")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(40, 40, 40, 40)
        container_layout.setSpacing(20)
        container_layout.setAlignment(Qt.AlignCenter)
        
        title = QLabel("Invite Code Generated")
        title.setObjectName("dialogTitle")
        title.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(title)
        
        # Code Display Container
        code_container = QHBoxLayout()
        code_container.setSpacing(10)
        code_container.setAlignment(Qt.AlignCenter)
        
        self.code_label = QLabel(self.code)
        self.code_label.setObjectName("codeLabel")
        self.code_label.setAlignment(Qt.AlignCenter)
        self.code_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        code_container.addWidget(self.code_label)
        
        copy_btn = QPushButton("Copy")
        copy_btn.setObjectName("secondaryButton")
        copy_btn.setCursor(Qt.PointingHandCursor)
        copy_btn.setFixedSize(60, 40)
        copy_btn.clicked.connect(self.copy_to_clipboard)
        code_container.addWidget(copy_btn)
        
        container_layout.addLayout(code_container)
        
        desc = QLabel("Share this code with others to let them watch your interview live. Valid for 24 hours.")
        desc.setObjectName("dialogDesc")
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        container_layout.addWidget(desc)
        
        btn = QPushButton("Close")
        btn.setObjectName("dialogButton")
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(self.accept)
        container_layout.addWidget(btn)
        
        layout.addWidget(container)
        self.setLayout(layout)
        
        self.setStyleSheet("""
            QFrame#dialogContainer {
                background-color: white;
                border-radius: 16px;
                border: 1px solid #e5e7eb;
            }
            QLabel#dialogTitle {
                font-size: 22px;
                font-weight: bold;
                color: #111827;
            }
            QLabel#codeLabel {
                font-size: 36px;
                font-weight: 800;
                color: #3b82f6;
                padding: 15px 25px;
                background-color: #eff6ff;
                border-radius: 8px;
                border: 1px dashed #3b82f6;
            }
            QLabel#dialogDesc {
                font-size: 14px;
                color: #6b7280;
            }
            QPushButton#dialogButton {
                background-color: #3b82f6;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-weight: 600;
                min-width: 100px;
            }
            QPushButton#dialogButton:hover {
                background-color: #2563eb;
            }
            QPushButton#secondaryButton {
                background-color: #ffffff;
                color: #374151;
                border: 1px solid #d1d5db;
                border-radius: 6px;
            }
            QPushButton#secondaryButton:hover {
                background-color: #f9fafb;
                border-color: #9ca3af;
            }
        """)

    def copy_to_clipboard(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.code)
        self.code_label.setStyleSheet("color: #10b981; border-color: #10b981; background-color: #ecfdf5;")
        QTimer.singleShot(1000, lambda: self.code_label.setStyleSheet("color: #3b82f6; border-color: #3b82f6; background-color: #eff6ff;"))

class StreamWorker(QThread):
    chunk_received = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, api_client, interview_id, content):
        super().__init__()
        self.api_client = api_client
        self.interview_id = interview_id
        self.content = content

    def run(self):
        success, result = self.api_client.send_message(
            self.interview_id, 
            self.content, 
            stream=True, 
            callback=self.on_chunk
        )
        if success:
            self.finished.emit()
        else:
            self.error.emit(str(result))

    def on_chunk(self, chunk):
        self.chunk_received.emit(chunk)

class EndInterviewDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("End Interview")
        self.setFixedSize(400, 200)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        container = QFrame()
        container.setObjectName("dialogContainer")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(30, 30, 30, 30)
        container_layout.setSpacing(20)
        container_layout.setAlignment(Qt.AlignCenter)
        
        title = QLabel("End Interview?")
        title.setObjectName("dialogTitle")
        title.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(title)
        
        desc = QLabel("Are you sure you want to end the interview? This action cannot be undone.")
        desc.setObjectName("dialogDesc")
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        container_layout.addWidget(desc)
        
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondaryButton")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        confirm_btn = QPushButton("End Interview")
        confirm_btn.setObjectName("dangerButton")
        confirm_btn.setCursor(Qt.PointingHandCursor)
        confirm_btn.clicked.connect(self.accept)
        btn_layout.addWidget(confirm_btn)
        
        container_layout.addLayout(btn_layout)
        
        layout.addWidget(container)
        self.setLayout(layout)
        
        self.setStyleSheet("""
            QFrame#dialogContainer {
                background-color: white;
                border-radius: 16px;
                border: 1px solid #e5e7eb;
            }
            QLabel#dialogTitle {
                font-size: 22px;
                font-weight: bold;
                color: #111827;
            }
            QLabel#dialogDesc {
                font-size: 15px;
                color: #6b7280;
            }
            QPushButton {
                border-radius: 8px;
                padding: 10px 20px;
                font-weight: 600;
                font-size: 14px;
                min-width: 100px;
            }
            QPushButton#secondaryButton {
                background-color: #f3f4f6;
                color: #374151;
                border: 1px solid #d1d5db;
            }
            QPushButton#secondaryButton:hover {
                background-color: #e5e7eb;
            }
            QPushButton#dangerButton {
                background-color: #ef4444;
                color: white;
                border: none;
            }
            QPushButton#dangerButton:hover {
                background-color: #dc2626;
            }
        """)

class FeedbackDialog(QDialog):
    def __init__(self, feedback, parent=None):
        super().__init__(parent)
        self.feedback = feedback
        self.setWindowTitle("Interview Feedback")
        self.setFixedSize(600, 500)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        container = QFrame()
        container.setObjectName("dialogContainer")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(30, 30, 30, 30)
        container_layout.setSpacing(20)
        
        title = QLabel("Interview Feedback")
        title.setObjectName("dialogTitle")
        title.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(title)
        
        # Feedback Text Area
        feedback_text = QTextEdit()
        feedback_text.setReadOnly(True)
        # Format JSON or dict if needed
        if isinstance(self.feedback, dict):
            formatted_feedback = json.dumps(self.feedback, indent=2, ensure_ascii=False)
        else:
            formatted_feedback = str(self.feedback)
            
        feedback_text.setText(formatted_feedback)
        feedback_text.setObjectName("feedbackText")
        container_layout.addWidget(feedback_text)
        
        btn = QPushButton("Close")
        btn.setObjectName("primaryButton")
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(self.accept)
        container_layout.addWidget(btn, 0, Qt.AlignCenter)
        
        layout.addWidget(container)
        self.setLayout(layout)
        
        self.setStyleSheet("""
            QFrame#dialogContainer {
                background-color: white;
                border-radius: 16px;
                border: 1px solid #e5e7eb;
            }
            QLabel#dialogTitle {
                font-size: 24px;
                font-weight: bold;
                color: #111827;
            }
            QTextEdit#feedbackText {
                border: 1px solid #d1d5db;
                border-radius: 8px;
                background-color: #f9fafb;
                padding: 15px;
                font-size: 14px;
                line-height: 1.6;
                color: #374151;
            }
            QPushButton#primaryButton {
                background-color: #3b82f6;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 30px;
                font-weight: 600;
                font-size: 14px;
            }
            QPushButton#primaryButton:hover {
                background-color: #2563eb;
            }
        """)


class ErrorDialog(QDialog):
    def __init__(self, title, message, details=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedSize(450, 250)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        container = QFrame()
        container.setObjectName("dialogContainer")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(30, 30, 30, 30)
        container_layout.setSpacing(15)
        
        # Icon (Optional, just use text for now or emoji)
        icon_label = QLabel("⚠️")
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("font-size: 32px;")
        container_layout.addWidget(icon_label)
        
        title_label = QLabel(title)
        title_label.setObjectName("dialogTitle")
        title_label.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(title_label)
        
        msg_label = QLabel(message)
        msg_label.setObjectName("dialogDesc")
        msg_label.setAlignment(Qt.AlignCenter)
        msg_label.setWordWrap(True)
        container_layout.addWidget(msg_label)
        
        if details:
            details_label = QLabel(f"Details: {details}")
            details_label.setObjectName("dialogDetails")
            details_label.setAlignment(Qt.AlignCenter)
            details_label.setWordWrap(True)
            container_layout.addWidget(details_label)
            
        btn = QPushButton("Close")
        btn.setObjectName("primaryButton")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedWidth(120)
        btn.clicked.connect(self.accept)
        container_layout.addWidget(btn, 0, Qt.AlignCenter)
        
        layout.addWidget(container)
        self.setLayout(layout)
        
        self.setStyleSheet("""
            QFrame#dialogContainer { 
                background-color: white; 
                border-radius: 16px; 
                border: 1px solid #e5e7eb;
                
            }
            QLabel#dialogTitle { 
                font-size: 20px; 
                font-weight: 800; 
                color: #991b1b; 
            }
            QLabel#dialogDesc { 
                font-size: 15px; 
                color: #374151; 
                font-weight: 500;
            }
            QLabel#dialogDetails { 
                font-size: 12px; 
                color: #6b7280; 
                font-family: monospace;
                background-color: #f3f4f6;
                padding: 8px;
                border-radius: 6px;
            }
            QPushButton#primaryButton { 
                background-color: #ef4444; 
                color: white; 
                border: none; 
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: 600;
                margin-top: 10px;
            }
            QPushButton#primaryButton:hover { 
                background-color: #dc2626; 
            }
        """)

class InterviewWindow(QWidget):
    def __init__(self, api_client, interview_data):
        super().__init__()
        self.api_client = api_client
        self.interview_id = interview_data.get('interview_id')
        self.rtmp_push_url = interview_data.get('rtmp_push_url')
        self.initial_message = interview_data.get('initial_message')

        self._stream_config = self._load_stream_config()
        self._preview_mode = self._normalize_preview_mode(
            self._stream_config.get('preview_mode', 'fit')
        )
        self._selected_resolution = self._normalize_resolution(
            self._stream_config.get('stream_resolution', '720p')
        )
        self._resolution_profiles = {
            "360p": {"size": (640, 360), "bitrate": "800k", "maxrate": "1000k"},
            "480p": {"size": (854, 480), "bitrate": "1200k", "maxrate": "1600k"},
            "720p": {"size": (1280, 720), "bitrate": "2200k", "maxrate": "3000k"},
            "1080p": {"size": (1920, 1080), "bitrate": "3500k", "maxrate": "5000k"},
        }
        self._resolution_order = ["360p", "480p", "720p", "1080p"]
        self._auto_resolution_index = len(self._resolution_order) - 1
        self._rtmp_ladder = [
            (1920, 1080),
            (1600, 900),
            (1280, 720),
            (1152, 648),
            (1024, 576),
            (960, 540),
            (854, 480),
            (768, 432),
            (640, 360),
            (512, 288),
            (426, 240),
            (320, 180),
        ]
        self._ffmpeg_path = None
        self._streaming_requested = False
        self._current_frame_size = None
        self._last_launch_ts = 0.0
        self._log_throttle_ts = {}
        self._ffmpeg_failures = deque()
        self._backoff_steps = [1, 2, 4, 8, 15, 30]
        self._backoff_index = 0
        self._downgrade_window_sec = 60
        self._downgrade_trigger = 2
        self._restart_reason = "startup"
        self._shutdown_requested = False

        self.push_process = None
        self.recorder_thread = None
        self.stream_worker = None
        self._restart_timer = QTimer(self)
        self._restart_timer.setSingleShot(True)
        self._restart_timer.timeout.connect(self._restart_ffmpeg_after_delay)
        
        self.setWindowTitle("MirrorView - Interview")
        self.resize(1100, 750)
        self.apply_styles()
        
        self.init_ui()
        self.start_video()
        # Delay start_pushing slightly to ensure UI is ready
        QTimer.singleShot(100, self.start_pushing)
        
        self.obs_timer = QTimer(self)
        self.obs_timer.timeout.connect(self.poll_observers)
        self.obs_timer.start(5000)

        if self.initial_message:
            self.append_message("AI", self.initial_message)

    def _stream_config_path(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ffmpeg_config.json')

    def _load_stream_config(self):
        config_path = self._stream_config_path()
        if not os.path.exists(config_path):
            return {}
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.error(f"Error reading ffmpeg config: {e}")
            return {}

    def _save_stream_config(self):
        payload = dict(self._stream_config)
        payload['preview_mode'] = self._preview_mode
        payload['stream_resolution'] = self._selected_resolution
        if self._ffmpeg_path:
            payload['ffmpeg_path'] = self._ffmpeg_path
        try:
            with open(self._stream_config_path(), 'w', encoding='utf-8') as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            self._stream_config = payload
        except Exception as e:
            logger.error(f"Error saving ffmpeg config: {e}")

    def _normalize_preview_mode(self, mode):
        normalized = (mode or "").strip().lower()
        if normalized not in {"fit", "fill"}:
            return "fit"
        return normalized

    def _normalize_resolution(self, label):
        text = (label or "").strip().lower()
        for candidate in ("auto", "360p", "480p", "720p", "1080p"):
            if text == candidate:
                return candidate
        return "720p"

    def _is_auto_resolution_mode(self):
        return self._selected_resolution == "auto"

    def _current_auto_cap(self):
        return self._resolution_order[self._auto_resolution_index]

    def _resolution_label_for_status(self):
        if self._is_auto_resolution_mode():
            return f"AUTO (cap {self._current_auto_cap()})"
        return self._selected_resolution

    def _capture_profile_key(self):
        if self._is_auto_resolution_mode():
            return self._current_auto_cap()
        return self._selected_resolution

    def get_ffmpeg_path(self):
        # 1. Check system PATH
        path = shutil.which('ffmpeg')
        if path:
            return path

        # 2. Check config file
        saved_path = self._stream_config.get('ffmpeg_path')
        if saved_path and os.path.exists(saved_path) and os.access(saved_path, os.X_OK):
            return saved_path

        # 3. Check common paths
        common_paths = [
            '/usr/local/bin/ffmpeg',
            '/opt/homebrew/bin/ffmpeg',
            '/usr/bin/ffmpeg',
            '/bin/ffmpeg',
            'C:\\ffmpeg\\bin\\ffmpeg.exe',
            'C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe'
        ]
        for p in common_paths:
            if os.path.exists(p) and os.access(p, os.X_OK):
                return p

        # 4. Ask user
        reply = QMessageBox.question(
            self,
            "FFmpeg Missing",
            "FFmpeg was not found automatically.\n"
            "Would you like to locate the 'ffmpeg' executable manually to enable video streaming?\n"
            "(If you choose No, video streaming will be disabled)",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            path, _ = QFileDialog.getOpenFileName(self, "Locate FFmpeg Executable")
            if path and os.path.exists(path):
                self._ffmpeg_path = path
                self._stream_config['ffmpeg_path'] = path
                self._save_stream_config()
                return path

        return None

    def init_ui(self):
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)
        
        # Left side: Video
        left_container = QFrame()
        left_container.setObjectName("leftContainer")
        video_layout = QVBoxLayout(left_container)
        video_layout.setContentsMargins(0, 0, 0, 0)
        video_layout.setSpacing(15)

        # Video container to center the video and remove black bars if aspect ratio differs
        video_wrapper = QWidget()
        video_wrapper.setStyleSheet("background-color: black; border-radius: 8px;")
        video_wrapper_layout = QVBoxLayout(video_wrapper)
        video_wrapper_layout.setContentsMargins(0,0,0,0)
        
        self.video_label = QLabel("Camera Loading...")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.video_label.setMinimumSize(640, 480)
        self.video_label.setObjectName("videoLabel")
        video_wrapper_layout.addWidget(self.video_label)
        
        video_layout.addWidget(video_wrapper)

        stream_controls_layout = QHBoxLayout()
        stream_controls_layout.setSpacing(10)

        quality_label = QLabel("Resolution")
        quality_label.setObjectName("streamControlLabel")
        stream_controls_layout.addWidget(quality_label)

        self.resolution_combo = QComboBox()
        self.resolution_combo.setObjectName("streamCombo")
        self.resolution_combo.addItem("Auto", "auto")
        for item in self._resolution_order:
            self.resolution_combo.addItem(item, item)
        current_index = self.resolution_combo.findData(self._selected_resolution)
        if current_index < 0:
            current_index = self.resolution_combo.findData("720p")
        self.resolution_combo.setCurrentIndex(current_index)
        self.resolution_combo.currentIndexChanged.connect(self.on_resolution_changed)
        stream_controls_layout.addWidget(self.resolution_combo)

        mode_label = QLabel("Preview")
        mode_label.setObjectName("streamControlLabel")
        stream_controls_layout.addWidget(mode_label)

        self.preview_mode_combo = QComboBox()
        self.preview_mode_combo.setObjectName("streamCombo")
        self.preview_mode_combo.addItem("Fit (Center)", "fit")
        self.preview_mode_combo.addItem("Fill (Crop)", "fill")
        mode_index = 0 if self._preview_mode == "fit" else 1
        self.preview_mode_combo.setCurrentIndex(mode_index)
        self.preview_mode_combo.currentIndexChanged.connect(self.on_preview_mode_changed)
        stream_controls_layout.addWidget(self.preview_mode_combo)

        stream_controls_layout.addStretch()
        video_layout.addLayout(stream_controls_layout)

        self.stream_status_label = QLabel("")
        self.stream_status_label.setObjectName("streamStatus")
        video_layout.addWidget(self.stream_status_label)
        
        # Controls under video
        controls_layout = QHBoxLayout()
        
        self.invite_btn = QPushButton("Generate Invite Code")
        self.invite_btn.setObjectName("secondaryButton")
        self.invite_btn.setCursor(Qt.PointingHandCursor)
        self.invite_btn.clicked.connect(self.generate_invite_code)
        controls_layout.addWidget(self.invite_btn)
        
        controls_layout.addStretch()
        
        self.end_btn = QPushButton("End Interview")
        self.end_btn.setObjectName("dangerButton")
        self.end_btn.setCursor(Qt.PointingHandCursor)
        self.end_btn.clicked.connect(self.end_interview)
        controls_layout.addWidget(self.end_btn)
        
        video_layout.addLayout(controls_layout)
        # Observers Section
        observers_label = QLabel("Observers")
        observers_label.setObjectName("sectionHeader")
        observers_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        video_layout.addWidget(observers_label)
        
        self.observers_list = QListWidget()
        self.observers_list.setObjectName("observersList")
        self.observers_list.setFixedHeight(100)
        self.observers_list.setStyleSheet("border: 1px solid #e5e7eb; border-radius: 8px; background: #f9fafb;")
        video_layout.addWidget(self.observers_list)
        
        
        # Right side: Chat
        right_container = QFrame()
        right_container.setObjectName("rightContainer")
        chat_layout = QVBoxLayout(right_container)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(10)
        
        chat_header = QLabel("Interview Chat")
        chat_header.setObjectName("chatHeader")
        chat_layout.addWidget(chat_header)

        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        self.chat_history.setObjectName("chatHistory")
        chat_layout.addWidget(self.chat_history)
        
        # Custom Input Area
        self.input_container = QFrame()
        self.input_container.setObjectName("customInputContainer")
        self.input_container.setFixedHeight(120)
        
        input_stack = QVBoxLayout(self.input_container)
        input_stack.setContentsMargins(1, 1, 1, 1)
        input_stack.setSpacing(0)
        
        # The text edit fills the container
        self.message_input = QTextEdit()
        self.message_input.setPlaceholderText("Type your answer here...")
        self.message_input.setObjectName("transparentInput")
        self.message_input.setFrameShape(QFrame.NoFrame)
        input_stack.addWidget(self.message_input)
        
        # Buttons overlay area (bottom right)
        btn_overlay_layout = QHBoxLayout()
        btn_overlay_layout.setContentsMargins(0, 0, 10, 10)
        btn_overlay_layout.addStretch()
        
        # Voice Button (Icon only)
        # Voice Input (Hidden for now due to issues)
        self.mic_btn = QPushButton("🎤")
        self.mic_btn.setObjectName("iconButton")
        self.mic_btn.setCursor(Qt.PointingHandCursor)
        self.mic_btn.setFixedSize(32, 32)
        self.mic_btn.setToolTip("Voice Input (Disabled)")
        self.mic_btn.clicked.connect(self.toggle_recording)
        # Enable voice input with STT via microphone
        if _VOICE_AVAILABLE:
            VoiceIntegration.enable_mic(self)
        else:
            self.mic_btn.hide()  # Voice integration not available
        btn_overlay_layout.addWidget(self.mic_btn)
        
        # Send Button
        self.send_btn = QPushButton("Send")
        self.send_btn.setObjectName("sendButtonSmall")
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.setFixedSize(60, 32)
        self.send_btn.clicked.connect(self.send_message)
        btn_overlay_layout.addWidget(self.send_btn)
        
        # We need to overlay buttons on top of text edit, or put them in layout below?
        # Requirement: "buttons inside the text area at bottom right"
        # Since QTextEdit is scrollable, we can't easily put widgets *inside* the scroll area at a fixed position without overlay.
        # So we use a layout that puts the text edit on top, and buttons at the bottom, but visually it looks like one box.
        # Actually, let's put buttons in the layout below the text edit but inside the border of container
        
        input_stack.addLayout(btn_overlay_layout)
        
        chat_layout.addWidget(self.input_container)
        
        # Combine using Splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_container)
        splitter.addWidget(right_container)
        splitter.setStretchFactor(0, 3) # Video takes more space
        splitter.setStretchFactor(1, 2)
        splitter.setHandleWidth(2)
        
        main_layout.addWidget(splitter)
        self.setLayout(main_layout)
        self._update_stream_status(
            f"Streaming profile: {self._resolution_label_for_status()}, preview mode: {self._preview_mode.upper()}."
        )

    def apply_styles(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #f3f4f6;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QFrame#leftContainer, QFrame#rightContainer {
                background-color: #ffffff;
                border-radius: 12px;
                border: 1px solid #e5e7eb;
                padding: 20px;
            }
            QLabel#videoLabel {
                background-color: #000000;
                color: #ffffff;
                border-radius: 8px;
            }
            QLabel#streamControlLabel {
                color: #374151;
                font-size: 12px;
                font-weight: 600;
                padding: 0 2px;
            }
            QLabel#streamStatus {
                color: #4b5563;
                font-size: 12px;
                padding: 2px 4px 4px 2px;
            }
            QComboBox#streamCombo {
                border: 1px solid #d1d5db;
                border-radius: 6px;
                padding: 4px 8px;
                min-width: 110px;
                background: #ffffff;
                font-size: 12px;
            }
            QComboBox#streamCombo::drop-down {
                border: none;
            }
            QLabel#chatHeader {
                font-size: 18px;
                font-weight: bold;
                color: #111827;
                padding-bottom: 10px;
                border-bottom: 1px solid #e5e7eb;
            }
            QTextEdit#chatHistory {
                border: 1px solid #d1d5db;
                border-radius: 8px;
                background-color: #f9fafb;
                padding: 10px;
                font-size: 14px;
                line-height: 1.5;
            }
            QFrame#customInputContainer {
                border: 1px solid #d1d5db;
                border-radius: 8px;
                background-color: #ffffff;
            }
            QFrame#customInputContainer:focus-within {
                border: 1px solid #3b82f6;
            }
            QTextEdit#transparentInput {
                background-color: transparent;
                border: none;
                padding: 10px;
                font-size: 14px;
            }
            QPushButton {
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton#sendButtonSmall {
                background-color: #3b82f6;
                color: white;
                border: none;
                border-radius: 6px;
            }
            QPushButton#sendButtonSmall:hover {
                background-color: #2563eb;
            }
            QPushButton#iconButton {
                background-color: #f3f4f6;
                border: 1px solid #e5e7eb;
                border-radius: 16px; /* Circle */
                font-size: 16px;
                padding: 0;
            }
            QPushButton#iconButton:hover {
                background-color: #e5e7eb;
            }
            QPushButton#iconButton:checked {
                background-color: #fee2e2;
                border-color: #fca5a5;
            }
            QPushButton#secondaryButton {
                background-color: #ffffff;
                color: #374151;
                border: 1px solid #d1d5db;
            }
            QPushButton#secondaryButton:hover {
                background-color: #f9fafb;
                border-color: #9ca3af;
            }
            QPushButton#dangerButton {
                background-color: #ef4444;
                color: white;
                border: none;
            }
            QPushButton#dangerButton:hover {
                background-color: #dc2626;
            }
            QSplitter::handle {
                background-color: #e5e7eb;
            }
        """)

    def start_video(self):
        capture_key = self._capture_profile_key()
        target_size = self._resolution_profiles[capture_key]["size"]
        self.thread = VideoThread(capture_width=target_size[0], capture_height=target_size[1])
        self.thread.change_pixmap_signal.connect(self.update_image)
        self.thread.frame_signal.connect(self.push_frame)
        self.thread.start()

    def on_resolution_changed(self, index):
        normalized = self._normalize_resolution(self.resolution_combo.itemData(index))
        if normalized == self._selected_resolution:
            return

        self._selected_resolution = normalized
        if self._is_auto_resolution_mode():
            self._auto_resolution_index = len(self._resolution_order) - 1
        self._save_stream_config()
        self._update_stream_status(
            f"Resolution switched to {self._resolution_label_for_status()}. Reconfiguring stream..."
        )

        if self._streaming_requested and self._ffmpeg_path:
            self._backoff_index = 0
            self._ffmpeg_failures.clear()
            self._restart_timer.stop()
            self._close_push_process()
            self._restart_reason = "manual resolution switch"
            self._restart_timer.start(0)

    def on_preview_mode_changed(self, index):
        mode = self.preview_mode_combo.itemData(index)
        normalized = self._normalize_preview_mode(mode)
        if normalized == self._preview_mode:
            return
        self._preview_mode = normalized
        self._save_stream_config()
        self._update_stream_status(
            f"Preview mode switched to {normalized.upper()}."
        )

    def _update_stream_status(self, message):
        if hasattr(self, "stream_status_label"):
            self.stream_status_label.setText(message)

    def _log_with_throttle(self, key, message, level="error", interval_sec=30):
        now = time.time()
        last_ts = self._log_throttle_ts.get(key, 0.0)
        if now - last_ts < interval_sec:
            return
        self._log_throttle_ts[key] = now
        log_fn = getattr(logger, level, logger.error)
        log_fn(message)

    def _fit_aspect(self, max_width, max_height, aspect_w=16, aspect_h=9):
        max_width = max(2, int(max_width))
        max_height = max(2, int(max_height))
        if max_width * aspect_h <= max_height * aspect_w:
            width = max_width
            height = int(max_width * aspect_h / aspect_w)
        else:
            height = max_height
            width = int(max_height * aspect_w / aspect_h)
        width = max(2, width - (width % 2))
        height = max(2, height - (height % 2))
        return width, height

    def _choose_stream_output_size(self):
        if not self._is_auto_resolution_mode():
            return self._resolution_profiles[self._selected_resolution]["size"]

        cap_key = self._current_auto_cap()
        profile_w, profile_h = self._resolution_profiles[cap_key]["size"]
        area_w = max(self.video_label.width(), 640)
        area_h = max(self.video_label.height(), 360)

        fit_w, fit_h = self._fit_aspect(area_w, area_h, 16, 9)
        max_w = min(profile_w, fit_w)
        max_h = min(profile_h, fit_h)

        for candidate_w, candidate_h in self._rtmp_ladder:
            if candidate_w <= max_w and candidate_h <= max_h:
                return candidate_w, candidate_h

        return self._fit_aspect(max_w, max_h, 16, 9)

    def _profile_key_for_output(self, output_size):
        if not self._is_auto_resolution_mode():
            return self._selected_resolution

        _, output_h = output_size
        if output_h >= 1080:
            return "1080p"
        if output_h >= 720:
            return "720p"
        if output_h >= 480:
            return "480p"
        return "360p"

    def _calc_bufsize(self, maxrate):
        # maxrate is formatted like "3000k"
        if not maxrate.endswith("k"):
            return maxrate
        try:
            numeric = int(maxrate[:-1])
            return f"{numeric * 2}k"
        except ValueError:
            return maxrate

    def _build_ffmpeg_command(self, input_size, output_size):
        input_w, input_h = input_size
        output_w, output_h = output_size
        profile_key = self._profile_key_for_output(output_size)
        profile = self._resolution_profiles[profile_key]
        scale_filter = (
            f"scale={output_w}:{output_h}:force_original_aspect_ratio=decrease,"
            f"pad={output_w}:{output_h}:(ow-iw)/2:(oh-ih)/2:black"
        )
        return [
            self._ffmpeg_path,
            '-loglevel', 'error',
            '-y',
            '-f', 'rawvideo',
            '-pixel_format', 'bgr24',
            '-video_size', f'{input_w}x{input_h}',
            '-framerate', '15',
            '-i', '-',
            '-vf', scale_filter,
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-tune', 'zerolatency',
            '-pix_fmt', 'yuv420p',
            '-r', '15',
            '-g', '30',
            '-b:v', profile['bitrate'],
            '-maxrate', profile['maxrate'],
            '-bufsize', self._calc_bufsize(profile['maxrate']),
            '-f', 'flv',
            self.rtmp_push_url
        ]

    def _close_push_process(self):
        if not self.push_process:
            return
        try:
            if self.push_process.stdin:
                try:
                    self.push_process.stdin.close()
                except Exception:
                    pass
            if self.push_process.poll() is None:
                self.push_process.terminate()
                try:
                    self.push_process.wait(timeout=2)
                except Exception:
                    self.push_process.kill()
        except Exception as e:
            logger.debug(f"Error closing FFmpeg process: {e}")
        finally:
            self.push_process = None

    def _start_ffmpeg_process(self, reason):
        if not self._streaming_requested or self._shutdown_requested:
            return False
        if not self._current_frame_size:
            return False
        if self.push_process and self.push_process.poll() is None:
            return True
        if not self._ffmpeg_path:
            return False

        input_size = self._current_frame_size
        output_size = self._choose_stream_output_size()
        command = self._build_ffmpeg_command(input_size, output_size)

        try:
            self.push_process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                bufsize=0
            )
            self._last_launch_ts = time.time()
            self._update_stream_status(
                f"Streaming at {output_size[0]}x{output_size[1]} ({self._resolution_label_for_status()}, {self._preview_mode.upper()})."
            )
            logger.info(
                "FFmpeg started (%s): input=%sx%s output=%sx%s profile=%s",
                reason,
                input_size[0],
                input_size[1],
                output_size[0],
                output_size[1],
                self._resolution_label_for_status(),
            )
            return True
        except Exception as e:
            self.push_process = None
            self._log_with_throttle(
                "ffmpeg_start_failure",
                f"Failed to start FFmpeg: {e}",
                level="error",
                interval_sec=30,
            )
            return False

    def _record_ffmpeg_failure(self, reason):
        now = time.time()
        self._ffmpeg_failures.append(now)
        while self._ffmpeg_failures and now - self._ffmpeg_failures[0] > self._downgrade_window_sec:
            self._ffmpeg_failures.popleft()

        if len(self._ffmpeg_failures) >= self._downgrade_trigger:
            self._maybe_auto_downgrade_resolution()

        if now - self._last_launch_ts >= 20:
            self._backoff_index = 0

        delay = self._backoff_steps[self._backoff_index]
        self._backoff_index = min(self._backoff_index + 1, len(self._backoff_steps) - 1)

        self._restart_reason = reason
        if not self._restart_timer.isActive():
            self._update_stream_status(
                f"FFmpeg will retry in {delay}s ({reason})."
            )
            self._restart_timer.start(int(delay * 1000))

    def _maybe_auto_downgrade_resolution(self):
        if not self._is_auto_resolution_mode():
            return

        if self._auto_resolution_index == 0:
            self._update_stream_status(
                "Auto fallback reached minimum profile (360p). Continuing retries."
            )
            return

        self._auto_resolution_index -= 1
        downgraded = self._current_auto_cap()
        self._save_stream_config()
        self._ffmpeg_failures.clear()
        self._update_stream_status(
            f"Auto mode downgraded stream cap to {downgraded} after repeated FFmpeg exits."
        )
        logger.warning(
            "Auto mode downgraded stream cap to %s after repeated FFmpeg exits.",
            downgraded,
        )

    def _handle_ffmpeg_exit(self, reason):
        if self._shutdown_requested:
            return
        self._close_push_process()
        self._log_with_throttle(
            "ffmpeg_exit",
            f"FFmpeg process has exited unexpectedly ({reason}).",
            level="error",
            interval_sec=30,
        )
        self._record_ffmpeg_failure(reason)

    def _restart_ffmpeg_after_delay(self):
        if not self._streaming_requested or self._shutdown_requested:
            return
        if not self._current_frame_size:
            # Wait for first camera frame before launching FFmpeg.
            self._restart_timer.start(1000)
            return
        if not self._start_ffmpeg_process(self._restart_reason):
            self._record_ffmpeg_failure("restart failed")

    def start_pushing(self):
        """
        Start RTMP pushing using ffmpeg via pipe.
        """
        if not self.rtmp_push_url:
            logger.warning("No RTMP URL provided, skipping push.")
            self._update_stream_status("No RTMP URL available. Streaming disabled.")
            return

        ffmpeg_path = self.get_ffmpeg_path()
        if not ffmpeg_path:
            logger.warning("FFmpeg not found or selected. Streaming disabled.")
            self._update_stream_status("FFmpeg unavailable. Streaming disabled.")
            return

        self._ffmpeg_path = ffmpeg_path
        self._streaming_requested = True
        self._shutdown_requested = False
        self._stream_config['ffmpeg_path'] = ffmpeg_path
        self._save_stream_config()

        logger.info(f"Starting push to: {self.rtmp_push_url} using {ffmpeg_path}")
        if self._current_frame_size:
            self._start_ffmpeg_process("initial start")
        else:
            self._update_stream_status(
                "Waiting for camera frames before starting RTMP push..."
            )

    @pyqtSlot(np.ndarray)
    def push_frame(self, frame):
        """
        Receive raw frame from VideoThread and write to FFmpeg stdin
        """
        if frame is None:
            return

        frame_h, frame_w = frame.shape[:2]
        if frame_w > 0 and frame_h > 0:
            self._current_frame_size = (frame_w, frame_h)

        if not self._streaming_requested:
            return

        if not self.push_process and not self._restart_timer.isActive():
            if not self._start_ffmpeg_process("frame-driven launch"):
                self._record_ffmpeg_failure("frame-driven launch failed")
                return

        if not self.push_process or not self.push_process.stdin:
            return

        if self.push_process.poll() is not None:
            self._handle_ffmpeg_exit("poll() returned exited process")
            return

        if not hasattr(self, '_frame_count'):
            self._frame_count = 0
        self._frame_count += 1
        # Keep 15fps push rate while local preview can stay smoother.
        if self._frame_count % 2 != 0:
            return

        try:
            self.push_process.stdin.write(frame.tobytes())
            if self._backoff_index > 0 and time.time() - self._last_launch_ts >= 20:
                self._backoff_index = 0
        except (BrokenPipeError, OSError, ValueError) as e:
            self._handle_ffmpeg_exit(f"stdin write failed: {e}")
        except Exception as e:
            self._log_with_throttle(
                "ffmpeg_write_error",
                f"Error pushing frame: {e}",
                level="error",
                interval_sec=30,
            )
            self._handle_ffmpeg_exit("unknown write failure")

    @pyqtSlot(QImage)
    def update_image(self, qt_img):
        pixmap = QPixmap.fromImage(qt_img)
        target_size = self.video_label.size()
        if target_size.width() <= 0 or target_size.height() <= 0:
            self.video_label.setPixmap(pixmap)
            return

        if self._preview_mode == "fill":
            scaled = pixmap.scaled(
                target_size,
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
            x = max(0, (scaled.width() - target_size.width()) // 2)
            y = max(0, (scaled.height() - target_size.height()) // 2)
            cropped = scaled.copy(x, y, target_size.width(), target_size.height())
            self.video_label.setPixmap(cropped)
            return

        scaled = pixmap.scaled(
            target_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.video_label.setPixmap(scaled)

    def append_message(self, sender, content):
        color = "blue" if sender == "You" else "green"
        self.chat_history.append(f"<b style='color:{color}'>{sender}:</b> {content}<br>")

    def send_message(self):
        text = self.message_input.toPlainText().strip()
        if not text:
            return

        self.append_message("You", text)
        self.message_input.clear()

        # Disable send button
        self.send_btn.setEnabled(False)

        # Reset full response accumulator for TTS
        self._full_response = ""

        # Start AI message block
        # Use HTML to style the sender name
        self.chat_history.append(f"<b style='color:green'>AI:</b> ")

        # Start streaming
        self.stream_worker = StreamWorker(self.api_client, self.interview_id, text)
        self.stream_worker.chunk_received.connect(self.handle_stream_chunk)
        self.stream_worker.finished.connect(self.handle_stream_finished)
        self.stream_worker.error.connect(self.handle_stream_error)
        self.stream_worker.start()

    def handle_stream_chunk(self, chunk):
        # Insert chunk at end of document
        cursor = self.chat_history.textCursor()
        cursor.movePosition(cursor.End)
        # Check if we need a space? usually chunks are raw text.
        cursor.insertText(chunk)
        self.chat_history.setTextCursor(cursor)
        self.chat_history.ensureCursorVisible()
        # Accumulate for TTS playback
        if not hasattr(self, '_full_response'):
            self._full_response = ""
        self._full_response += chunk

    def handle_stream_finished(self):
        self.send_btn.setEnabled(True)
        # Add a newline for spacing after message is done
        self.chat_history.append("")

        # === Voice Integration: Speak the AI's response ===
        if _VOICE_AVAILABLE and hasattr(self, '_full_response') and self._full_response.strip():
            tts_enabled = getattr(self, '_tts_enabled', True)
            if tts_enabled:
                try:
                    # Initialize TTS client on first use
                    if not hasattr(self, '_tts_client') or self._tts_client is None:
                        self._tts_client = TTSClient(
                            base_url=self.api_client.base_url.replace('/api', ''),
                            timeout=60,
                        )

                    voice = getattr(self, '_selected_voice', 'default')
                    volume = (getattr(self, '_tts_volume_ref', None)
                              and self._tts_volume_ref.value() / 100.0) or 1.0

                    VoiceIntegration.speak_response(
                        self,
                        self._full_response,
                        voice=voice,
                        volume=volume,
                    )
                except Exception as e:
                    logger.warning(f"TTS playback skipped: {e}")
        # === End Voice Integration ===
        
    def handle_stream_error(self, error_msg):
        self.send_btn.setEnabled(True)
        self.chat_history.append(f"<br><span style='color:red'>Error: {error_msg}</span><br>")
        logger.error(f"Stream error: {error_msg}")

    def generate_invite_code(self):
        success, response = self.api_client.create_invite_code(self.interview_id)
        if success:
            code = response.get('code')
            dialog = InviteCodeDialog(code, self)
            dialog.exec_()
        else:
            QMessageBox.warning(self, "Error", "Failed to generate invite code")

    def end_interview(self):
        dialog = EndInterviewDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            success, response = self.api_client.finish_interview(self.interview_id)
            if success:
                feedback = response.get('feedback')
                fb_dialog = FeedbackDialog(feedback, self)
                fb_dialog.exec_()
                self.close()
            else:
                QMessageBox.warning(self, "Error", "Failed to end interview properly")

    def toggle_recording(self):
        if not self.recorder_thread or not self.recorder_thread.isRunning():
            # Start recording
            self.mic_btn.setText("🛑") # Stop icon
            self.mic_btn.setStyleSheet("background-color: #fee2e2; border-color: #fca5a5; color: #dc2626;")
            self.recorder_thread = AudioRecorderThread()
            self.recorder_thread.finished_signal.connect(self.handle_recording_finished)
            self.recorder_thread.start()
        else:
            # Stop recording
            self.recorder_thread.stop()
            self.mic_btn.setText("🎤")
            self.mic_btn.setStyleSheet("")

    def handle_recording_finished(self, filename):
        if filename == "ERROR":
            QMessageBox.warning(self, "Audio Error", "Could not access microphone. Please check permissions.")
            return

        # Process the WAV file
        try:
            r = sr.Recognizer()
            with sr.AudioFile(filename) as source:
                audio = r.record(source)
            
            try:
                # Try Google Speech Recognition first (default language is English, let's set to auto or Chinese if needed?)
                # User used Chinese in previous prompts, maybe we should set language='zh-CN'
                text = r.recognize_google(audio, language='zh-CN')
            except sr.RequestError:
                # Fallback to Sphinx (Offline) if available
                try:
                    logger.info("Google Speech failed, trying Sphinx...")
                    text = r.recognize_sphinx(audio, language='zh-CN')
                except:
                    # If Sphinx fails or not installed, re-raise original error
                    raise
            
            # Set input directly
            logger.info(f"Speech recognized: {text}")
            self.message_input.setText(text)
            
        except sr.UnknownValueError:
            # QMessageBox.information(self, "Speech Recognition", "No speech detected.")
            pass
        except sr.RequestError as e:
            logger.error(f"Speech Recognition Error: {e}")
            
            # Check if it's a missing module error for offline fallback
            error_msg = str(e)
            user_msg = "Connection to speech service failed."
            
            if "PocketSphinx" in error_msg:
                user_msg = "Offline speech recognition is not available."
                error_msg = "PocketSphinx module is missing. Please install it or check your internet connection for online recognition."
            
            dlg = ErrorDialog("Speech Recognition Failed", user_msg, error_msg, self)
            dlg.exec_()
        except Exception as e:
            logger.error(f"Error processing audio: {e}")
            dlg = ErrorDialog("Processing Error", "Failed to process audio.", str(e), self)
            dlg.exec_()
        finally:
            # Cleanup
            if os.path.exists(filename):
                os.remove(filename)

    def closeEvent(self, event):
        # Attempt to finish interview on close
        try:
            logger.info("Closing window, finishing interview...")
            self.api_client.finish_interview(self.interview_id)
        except Exception as e:
            logger.error(f"Error finishing interview on close: {e}")

        if self.recorder_thread and self.recorder_thread.isRunning():
            self.recorder_thread.stop()
        if self.stream_worker and self.stream_worker.isRunning():
            self.stream_worker.quit()
            self.stream_worker.wait()
        if hasattr(self, "obs_timer") and self.obs_timer.isActive():
            self.obs_timer.stop()
        self._shutdown_requested = True
        self._streaming_requested = False
        if self._restart_timer.isActive():
            self._restart_timer.stop()
        self.thread.stop()
        self._close_push_process()
        event.accept()

    def poll_observers(self):
        success, observers = self.api_client.get_observers(self.interview_id)
        if success:
            self.observers_list.clear()
            if not observers:
                self.observers_list.addItem("No observers yet")
            else:
                for obs in observers:
                    self.observers_list.addItem(f"👤 {obs.get('name')}")
