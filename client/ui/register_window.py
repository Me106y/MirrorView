from PyQt5.QtWidgets import (QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout, 
                             QHBoxLayout, QMessageBox, QFrame, QComboBox, QSpinBox, QDialog)
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QPixmap, QFont
import os

class SuccessDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Success")
        self.setFixedSize(400, 300)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Main container with rounded corners and shadow effect
        container = QFrame()
        container.setObjectName("dialogContainer")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(30, 40, 30, 40)
        container_layout.setSpacing(20)
        container_layout.setAlignment(Qt.AlignCenter)
        
        # Icon (Checkmark)
        icon_label = QLabel("✓")
        icon_label.setObjectName("iconLabel")
        icon_label.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(icon_label)
        
        # Title
        title = QLabel("Registration Successful!")
        title.setObjectName("dialogTitle")
        title.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(title)
        
        # Message
        msg = QLabel("Your account has been created successfully.\nPlease log in to continue.")
        msg.setObjectName("dialogMsg")
        msg.setAlignment(Qt.AlignCenter)
        msg.setWordWrap(True)
        container_layout.addWidget(msg)
        
        # Button
        btn = QPushButton("Go to Login")
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
            QLabel#iconLabel {
                font-size: 60px;
                color: #10b981; /* Green */
                font-weight: bold;
                background-color: #ecfdf5;
                border-radius: 40px; /* Circular background */
                min-width: 80px;
                min-height: 80px;
                max-width: 80px;
                max-height: 80px;
            }
            QLabel#dialogTitle {
                font-size: 24px;
                font-weight: bold;
                color: #111827;
            }
            QLabel#dialogMsg {
                font-size: 16px;
                color: #6b7280;
            }
            QPushButton#dialogButton {
                background-color: #3b82f6;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 24px;
                font-size: 16px;
                font-weight: 600;
                min-width: 150px;
            }
            QPushButton#dialogButton:hover {
                background-color: #2563eb;
            }
        """)

class RegisterWindow(QWidget):
    switch_to_login = pyqtSignal() # Signal to switch back to login

    def __init__(self, api_client):
        super().__init__()
        self.api_client = api_client
        self.setWindowTitle("MirrorView - Register")
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
            self.image_label.setText("MirrorView\nSmart Interview Platform")
            self.image_label.setAlignment(Qt.AlignCenter)
            self.image_label.setStyleSheet("font-size: 24px; color: #555; font-weight: bold;")
        
        left_layout.addWidget(self.image_label)
        main_layout.addWidget(self.left_panel, 1) # Stretch factor 1

        # Right Side - Form
        self.right_panel = QFrame()
        self.right_panel.setObjectName("rightPanel")
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setAlignment(Qt.AlignCenter)
        right_layout.setContentsMargins(50, 50, 50, 50)
        right_layout.setSpacing(20)

        # Title
        title = QLabel("Create Account")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(title)

        # Form Fields
        form_layout = QVBoxLayout()
        form_layout.setSpacing(15)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")
        form_layout.addWidget(self.username_input)

        # self.email_input = QLineEdit()
        # self.email_input.setPlaceholderText("Email Address")
        # form_layout.addWidget(self.email_input)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.Password)
        form_layout.addWidget(self.password_input)

        self.confirm_password_input = QLineEdit()
        self.confirm_password_input.setPlaceholderText("Confirm Password")
        self.confirm_password_input.setEchoMode(QLineEdit.Password)
        form_layout.addWidget(self.confirm_password_input)

        # Job Intention
        self.job_input = QLineEdit()
        self.job_input.setPlaceholderText("Job Intention (e.g. Java Developer)")
        form_layout.addWidget(self.job_input)

        # Work Experience
        self.experience_input = QComboBox()
        self.experience_input.addItems(["No experience", "1-2 years", "3-5 years", "5+ years"])
        # self.years_input = QSpinBox()
        # self.years_input.setRange(0, 50)
        # self.years_input.setPrefix("Experience: ")
        # self.years_input.setSuffix(" years")
        form_layout.addWidget(self.experience_input)

        right_layout.addLayout(form_layout)

        # Buttons
        self.register_btn = QPushButton("Sign Up")
        self.register_btn.setObjectName("primaryButton")
        self.register_btn.setCursor(Qt.PointingHandCursor)
        self.register_btn.clicked.connect(self.handle_register)
        right_layout.addWidget(self.register_btn)

        self.login_link = QPushButton("Already have an account? Log in")
        self.login_link.setObjectName("secondaryButton")
        self.login_link.setCursor(Qt.PointingHandCursor)
        self.login_link.clicked.connect(self.switch_to_login.emit)
        right_layout.addWidget(self.login_link)

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
                font-size: 28px;
                font-weight: bold;
                color: #2c3e50;
                margin-bottom: 10px;
            }
            QLineEdit, QComboBox, QSpinBox {
                padding: 12px;
                border: 1px solid #d1d5db;
                border-radius: 8px;
                font-size: 14px;
                background-color: #f9fafb;
                color: #1f2937; /* Default text color */
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
                border: 1px solid #3b82f6;
                background-color: #ffffff;
            }
            QComboBox QAbstractItemView {
                background-color: #ffffff;
                color: #1f2937;
                selection-background-color: #3b82f6;
                selection-color: #ffffff;
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

    def handle_register(self):
        username = self.username_input.text()
        # email = self.email_input.text()
        password = self.password_input.text()
        confirm_password = self.confirm_password_input.text()
        job = self.job_input.text()
        experience = self.experience_input.currentText()

        if not username or not password:
            QMessageBox.warning(self, "Error", "Please fill in all required fields")
            return
            
        if password != confirm_password:
            QMessageBox.warning(self, "Error", "Passwords do not match")
            return

        success, data = self.api_client.register(username, password, job, experience)
        if success:
            # Show custom success dialog
            dialog = SuccessDialog(self)
            dialog.exec_()
            self.switch_to_login.emit()
        else:
            QMessageBox.critical(self, "Registration Failed", str(data))
