from PyQt5.QtWidgets import (QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout, 
                             QHBoxLayout, QMessageBox, QFrame)
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QPixmap, QFont
import os

class LoginWindow(QWidget):
    login_success = pyqtSignal(dict) # Emits user data on success
    switch_to_register = pyqtSignal() # Signal to switch to register

    def __init__(self, api_client):
        super().__init__()
        self.api_client = api_client
        self.setWindowTitle("MirrorView - 登录")
        self.setFixedSize(900, 600)
        self.init_ui()
        self.apply_styles()

    def init_ui(self):
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Left Side - Illustration
        self.left_panel = QFrame()
        self.left_panel.setObjectName("leftPanel")
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setAlignment(Qt.AlignCenter)
        
        self.image_label = QLabel()
        image_path = os.path.join(os.path.dirname(__file__), '../static/illustration.png')
        if os.path.exists(image_path):
            pixmap = QPixmap(image_path)
            self.image_label.setPixmap(pixmap.scaled(400, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.image_label.setText("MirrorView\n智能面试平台")
            self.image_label.setAlignment(Qt.AlignCenter)
            self.image_label.setStyleSheet("font-size: 24px; color: #555; font-weight: bold;")
        
        left_layout.addWidget(self.image_label)
        main_layout.addWidget(self.left_panel, 1) # Stretch factor 1

        # Right Side - Form
        self.right_panel = QFrame()
        self.right_panel.setObjectName("rightPanel")
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setAlignment(Qt.AlignCenter)
        right_layout.setContentsMargins(50, 85, 50, 50)
        right_layout.setSpacing(20)

        # Title
        title = QLabel("欢迎回来")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(title)
        
        subtitle = QLabel("请登录后继续")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(subtitle)

        # Form Fields
        form_layout = QVBoxLayout()
        form_layout.setSpacing(15)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("用户名")
        form_layout.addWidget(self.username_input)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("密码")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.returnPressed.connect(self.handle_login)
        form_layout.addWidget(self.password_input)

        right_layout.addLayout(form_layout)

        # Buttons
        self.login_btn = QPushButton("登录")
        self.login_btn.setObjectName("primaryButton")
        self.login_btn.setCursor(Qt.PointingHandCursor)
        self.login_btn.clicked.connect(self.handle_login)
        right_layout.addWidget(self.login_btn)

        self.register_btn = QPushButton("还没有账号？去注册")
        self.register_btn.setObjectName("secondaryButton")
        self.register_btn.setCursor(Qt.PointingHandCursor)
        self.register_btn.clicked.connect(self.switch_to_register.emit)
        right_layout.addWidget(self.register_btn)

        right_layout.addStretch()

        main_layout.addWidget(self.right_panel, 1) # Stretch factor 1

        self.setLayout(main_layout)

    def apply_styles(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #ffffff;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QFrame#leftPanel {
                background-color: #f0f4f8;
                border-right: 1px solid #e1e4e8;
            }
            QLabel#title {
                font-size: 32px;
                font-weight: bold;
                color: #2c3e50;
                margin-bottom: 5px;
            }
            QLabel#subtitle {
                font-size: 16px;
                color: #6b7280;
                margin-bottom: 20px;
            }
            QLineEdit {
                padding: 12px;
                border: 1px solid #d1d5db;
                border-radius: 8px;
                font-size: 14px;
                background-color: #f9fafb;
            }
            QLineEdit:focus {
                border: 1px solid #3b82f6;
                background-color: #ffffff;
            }
            QPushButton#primaryButton {
                background-color: #3b82f6;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px;
                font-size: 16px;
                font-weight: 600;
            }
            QPushButton#primaryButton:hover {
                background-color: #2563eb;
            }
            QPushButton#primaryButton:pressed {
                background-color: #1d4ed8;
            }
            QPushButton#secondaryButton {
                background-color: transparent;
                color: #6b7280;
                border: none;
                font-size: 14px;
            }
            QPushButton#secondaryButton:hover {
                color: #3b82f6;
                text-decoration: underline;
            }
        """)

    def handle_login(self):
        username = self.username_input.text()
        password = self.password_input.text()
        
        if not username or not password:
            QMessageBox.warning(self, "提示", "请填写完整信息")
            return

        success, data = self.api_client.login(username, password)
        if success:
            self.login_success.emit(data)
            self.close()
        else:
            QMessageBox.critical(self, "登录失败", self.localize_login_error(str(data)))

    @staticmethod
    def localize_login_error(message):
        error_map = {
            "Invalid username or password": "用户名或密码错误",
            "Login failed": "登录失败",
        }

        if message in error_map:
            return error_map[message]
        if message.startswith("Server Error"):
            return message.replace("Server Error", "服务器错误")
        return message
