import os
import requests
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, QPushButton, QFileDialog, 
                             QMessageBox, QHBoxLayout, QFrame, QProgressBar)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

class UploadThread(QThread):
    finished = pyqtSignal(bool, str) # success, message

    def __init__(self, api_client, file_path):
        super().__init__()
        self.api_client = api_client
        self.file_path = file_path

    def run(self):
        try:
            # Prepare file for upload
            files = {'resume': open(self.file_path, 'rb')}
            # We need to send user_id as well, but api_client handles that via endpoint usually?
            # Let's assume api_client has a method for this
            
            # Using requests directly here since api_client method might not exist yet or needs to handle multipart
            url = f"{self.api_client.base_url}/user/{self.api_client.user_id}/upload_resume"
            response = requests.post(url, files=files)
            
            if response.status_code == 200:
                self.finished.emit(True, "Resume uploaded successfully!")
            else:
                try:
                    msg = response.json().get('message', 'Upload failed')
                except:
                    msg = f"Error {response.status_code}"
                self.finished.emit(False, msg)
        except Exception as e:
            self.finished.emit(False, str(e))

class ResumeUploadDialog(QDialog):
    def __init__(self, api_client, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self.selected_file = None
        
        self.setWindowTitle("Upload Resume")
        self.setFixedSize(500, 350)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        container = QFrame()
        container.setObjectName("dialogContainer")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(30, 20, 30, 30)
        container_layout.setSpacing(15)
        
        # Header Row (Title + Close Button)
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        title = QLabel("Enhance Your Interview")
        title.setObjectName("dialogTitle")
        # title.setAlignment(Qt.AlignCenter) # Align left looks better with close button on right
        
        close_btn = QPushButton("✕")
        close_btn.setObjectName("closeButton")
        close_btn.setFixedSize(30, 30)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.reject)
        
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(close_btn)
        
        container_layout.addLayout(header_layout)
        
        # Description
        desc = QLabel("Would you like to upload your resume? This allows our AI to tailor questions specifically to your experience and projects.")
        desc.setObjectName("dialogDesc")
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        container_layout.addWidget(desc)
        
        # File Selection Area
        self.file_label = QLabel("No file selected")
        self.file_label.setObjectName("fileLabel")
        self.file_label.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(self.file_label)
        
        select_btn = QPushButton("Select PDF Resume")
        select_btn.setObjectName("secondaryButton")
        select_btn.setCursor(Qt.PointingHandCursor)
        select_btn.clicked.connect(self.select_file)
        container_layout.addWidget(select_btn)
        
        # Progress Bar (Hidden by default)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        container_layout.addWidget(self.progress)
        
        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)
        
        skip_btn = QPushButton("Skip")
        skip_btn.setObjectName("textButton")
        skip_btn.setCursor(Qt.PointingHandCursor)
        skip_btn.clicked.connect(self.skip_upload)
        btn_layout.addWidget(skip_btn)
        
        self.upload_btn = QPushButton("Upload & Start")
        self.upload_btn.setObjectName("primaryButton")
        self.upload_btn.setCursor(Qt.PointingHandCursor)
        self.upload_btn.setEnabled(False) # Disabled until file selected
        self.upload_btn.clicked.connect(self.upload_resume)
        btn_layout.addWidget(self.upload_btn)
        
        container_layout.addLayout(btn_layout)
        
        layout.addWidget(container)
        self.setLayout(layout)
        
        self.apply_styles()

    def apply_styles(self):
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
                font-size: 14px;
                color: #6b7280;
                margin-bottom: 10px;
            }
            QLabel#fileLabel {
                background-color: #f9fafb;
                border: 1px dashed #d1d5db;
                border-radius: 8px;
                padding: 15px;
                color: #6b7280;
                font-size: 13px;
            }
            QPushButton {
                border-radius: 8px;
                padding: 10px 20px;
                font-weight: 600;
                font-size: 14px;
            }
            QPushButton#primaryButton {
                background-color: #3b82f6;
                color: white;
                border: none;
            }
            QPushButton#primaryButton:hover {
                background-color: #2563eb;
            }
            QPushButton#primaryButton:disabled {
                background-color: #93c5fd;
            }
            QPushButton#secondaryButton {
                background-color: #ffffff;
                color: #374151;
                border: 1px solid #d1d5db;
            }
            QPushButton#secondaryButton:hover {
                background-color: #f9fafb;
            }
            QPushButton#textButton {
                background-color: transparent;
                color: #6b7280;
                border: none;
            }
            QPushButton#textButton:hover {
                color: #374151;
                text-decoration: underline;
            }
            QProgressBar {
                border: none;
                background-color: #e5e7eb;
                border-radius: 4px;
                height: 6px;
            }
            QProgressBar::chunk {
                background-color: #3b82f6;
                border-radius: 4px;
            }
            QPushButton#closeButton {
                background-color: transparent;
                color: #9ca3af;
                font-size: 16px;
                border: none;
                padding: 0;
            }
            QPushButton#closeButton:hover {
                color: #111827;
                background-color: #f3f4f6;
                border-radius: 15px;
            }
        """)

    def select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Resume", "", "PDF Files (*.pdf)")
        if file_path:
            self.selected_file = file_path
            filename = os.path.basename(file_path)
            self.file_label.setText(f"Selected: {filename}")
            self.file_label.setStyleSheet("""
                background-color: #eff6ff;
                border: 1px solid #bfdbfe;
                color: #1e40af;
                border-radius: 8px;
                padding: 15px;
            """)
            self.upload_btn.setEnabled(True)

    def skip_upload(self):
        # User wants to skip upload but proceed with interview
        self.accept()

    def upload_resume(self):
        if not self.selected_file:
            return
            
        self.progress.setVisible(True)
        self.progress.setRange(0, 0) # Indeterminate
        self.upload_btn.setEnabled(False)
        self.upload_btn.setText("Uploading...")
        
        self.thread = UploadThread(self.api_client, self.selected_file)
        self.thread.finished.connect(self.on_upload_finished)
        self.thread.start()

    def on_upload_finished(self, success, message):
        self.progress.setVisible(False)
        self.upload_btn.setEnabled(True)
        self.upload_btn.setText("Upload & Start")
        
        if success:
            self.accept() # Close dialog with accepted result
        else:
            QMessageBox.warning(self, "Upload Failed", message)
