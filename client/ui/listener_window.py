from PyQt5.QtWidgets import (QWidget, QDialog, QLabel, QTextEdit, QVBoxLayout,
                             QHBoxLayout, QFrame, QSplitter, QSizePolicy, QPushButton)
from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtGui import QImage, QPixmap
from client.core.video_thread import VideoThread # We might need a player thread instead
# For now, we reuse VideoThread but it captures camera. We need a PlayerThread.
# Since user said "Video player not implemented", we just show placeholder.
from utils.logger_handler import logger


class InterviewEndedDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Interview Ended")
        self.setFixedSize(400, 250)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        container = QFrame()
        container.setObjectName("dialogContainer")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(30, 30, 30, 30)
        container_layout.setSpacing(20)
        container_layout.setAlignment(Qt.AlignCenter)
        
        # Icon
        icon_label = QLabel("🏁")
        icon_label.setStyleSheet("font-size: 40px;")
        icon_label.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(icon_label)
        
        title = QLabel("Interview Ended")
        title.setObjectName("dialogTitle")
        title.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(title)
        
        desc = QLabel("The candidate has finished the interview session.")
        desc.setObjectName("dialogDesc")
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        container_layout.addWidget(desc)
        
        btn = QPushButton("Close Window")
        btn.setObjectName("primaryButton")
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
                box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
            }
            QLabel#dialogTitle { 
                font-size: 22px; 
                font-weight: 800; 
                color: #111827; 
            }
            QLabel#dialogDesc { 
                font-size: 15px; 
                color: #6b7280; 
            }
            QPushButton#primaryButton { 
                background-color: #3b82f6; 
                color: white; 
                border: none; 
                border-radius: 8px;
                padding: 10px 20px;
                font-weight: 600;
                min-width: 120px;
            }
            QPushButton#primaryButton:hover { 
                background-color: #2563eb; 
            }
        """)


import cv2
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal

class PlayerThread(QThread):
    change_pixmap_signal = pyqtSignal(QImage)

    def __init__(self, url):
        super().__init__()
        self.url = url
        self._run_flag = True

    def run(self):
        # Open the stream
        cap = cv2.VideoCapture(self.url)
        
        while self._run_flag:
            ret, cv_img = cap.read()
            if ret:
                rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb_image.shape
                bytes_per_line = ch * w
                convert_to_Qt_format = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
                p = convert_to_Qt_format.scaled(640, 480, Qt.KeepAspectRatio)
                self.change_pixmap_signal.emit(p)
            else:
                # Retry or wait?
                self.msleep(100)
                # Reconnect if stream dropped?
                # cap.open(self.url)
        cap.release()

    def stop(self):
        self._run_flag = False
        self.wait()


class ListenerWindow(QWidget):
    def __init__(self, api_client, interview_data):
        super().__init__()
        self.api_client = api_client
        self.interview_id = interview_data.get('interview_id')
        self.job_position = interview_data.get('job_position')
        self.listener_name = interview_data.get('listener_name')
        self.rtmp_play_url = interview_data.get('rtmp_play_url')
        
        self.setWindowTitle(f"MirrorView - Observing: {self.job_position}")
        self.resize(1000, 700)
        
        self.last_msg_count = 0
        self.init_ui()
        self.apply_styles()
        
        # Poll for updates
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_updates)
        self.timer.start(2000) # Every 2 seconds
        
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
        
        # Video container
        video_wrapper = QWidget()
        video_wrapper.setStyleSheet("background-color: black; border-radius: 8px;")
        video_wrapper_layout = QVBoxLayout(video_wrapper)
        video_wrapper_layout.setContentsMargins(0,0,0,0)
        
        self.video_label = QLabel("Connecting to stream...")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.video_label.setMinimumSize(640, 480)
        self.video_label.setObjectName("videoLabel")
        video_wrapper_layout.addWidget(self.video_label)
        
        video_layout.addWidget(video_wrapper)
        
        # Info under video
        info_label = QLabel(f"Observing as: {self.listener_name}")
        info_label.setAlignment(Qt.AlignCenter)
        info_label.setStyleSheet("color: #6b7280; font-weight: bold; margin-top: 10px;")
        video_layout.addWidget(info_label)
        
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
        
        # Splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_container)
        splitter.addWidget(right_container)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setHandleWidth(2)
        
        main_layout.addWidget(splitter)
        self.setLayout(main_layout)
        
        # Start Player
        self.start_player()

    def start_player(self):
        # We need the play url. It should be in interview_data or fetched.
        # join_interview returns rtmp_play_url.
        play_url = getattr(self, 'rtmp_play_url', None)
        # Check where we stored it. In __init__:
        # self.interview_id = interview_data.get('interview_id')
        # We need to save the url too.
        
        if play_url:
            self.player_thread = PlayerThread(play_url)
            self.player_thread.change_pixmap_signal.connect(self.update_image)
            self.player_thread.start()
        else:
            self.video_label.setText("No stream URL available")

    @pyqtSlot(QImage)
    def update_image(self, qt_img):
        scaled_pixmap = QPixmap.fromImage(qt_img).scaled(
            self.video_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.video_label.setPixmap(scaled_pixmap)
    
    def closeEvent(self, event):
        if hasattr(self, 'player_thread') and self.player_thread.isRunning():
            self.player_thread.stop()
        super().closeEvent(event)


    def poll_updates(self):
        # 1. Check interview status
        success, status_data = self.api_client.get_interview_status(self.interview_id)
        if success:
            status = status_data.get('status')
            if status not in [0, 1]: # Not pending or ongoing (so it ended)
                self.timer.stop()
                self.show_ended_dialog()
                return

        # 2. Get messages
        success, messages = self.api_client.get_messages(self.interview_id)
        if success and len(messages) > self.last_msg_count:
            new_msgs = messages[self.last_msg_count:]
            for msg in new_msgs:
                role = msg.get('role')
                content = msg.get('content')
                self.append_message(role, content)
            
            self.last_msg_count = len(messages)

    def show_ended_dialog(self):
        dialog = InterviewEndedDialog(self)
        dialog.exec_()
        self.close()

    def append_message(self, role, content):
        color = "blue" if role == "user" else "green"
        sender = "Candidate" if role == "user" else "AI Interviewer"
        self.chat_history.append(f"<b style='color:{color}'>{sender}:</b> {content}<br>")
        
    def apply_styles(self):
        self.setStyleSheet("""
            QWidget { background-color: #f3f4f6; font-family: 'Segoe UI', Arial, sans-serif; }
            QFrame#leftContainer, QFrame#rightContainer { background-color: white; border-radius: 12px; border: 1px solid #e5e7eb; padding: 20px; }
            QLabel#chatHeader { font-size: 18px; font-weight: bold; color: #111827; border-bottom: 1px solid #e5e7eb; padding-bottom: 10px; }
            QTextEdit#chatHistory { border: none; background-color: transparent; font-size: 14px; line-height: 1.5; }
        """)
