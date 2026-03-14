from PyQt5.QtWidgets import (QWidget, QLabel, QPushButton, QVBoxLayout, QScrollArea,
                             QMessageBox, QInputDialog, QMainWindow, QFrame, QHBoxLayout, QDialog, QLineEdit, QComboBox,
                             QTextEdit)
from PyQt5.QtCore import Qt
from client.ui.interview_window import InterviewWindow
from client.ui.resume_dialog import ResumeUploadDialog


class ProfileDialog(QDialog):
    def __init__(self, api_client, current_job, current_exp, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self.setWindowTitle("Edit Profile")
        self.setFixedSize(450, 350)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.job_intention = current_job
        self.work_experience = current_exp
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        container = QFrame()
        container.setObjectName("dialogContainer")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(30, 30, 30, 30)
        container_layout.setSpacing(20)
        
        title = QLabel("Edit Profile")
        title.setObjectName("dialogTitle")
        title.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(title)
        
        # Form Layout
        form_layout = QVBoxLayout()
        form_layout.setSpacing(15)
        
        # Job Intention
        job_label = QLabel("Job Intention")
        job_label.setObjectName("inputLabel")
        form_layout.addWidget(job_label)
        
        self.job_input = QLineEdit(self.job_intention)
        self.job_input.setPlaceholderText("e.g. Java Developer, Product Manager")
        self.job_input.setObjectName("inputField")
        form_layout.addWidget(self.job_input)
        
        # Work Experience (ComboBox)
        exp_label = QLabel("Work Experience")
        exp_label.setObjectName("inputLabel")
        form_layout.addWidget(exp_label)
        
        self.exp_combo = QComboBox()
        self.exp_combo.setObjectName("inputField")
        options = ["No experience", "1-2 years", "3-5 years", "5+ years"]
        self.exp_combo.addItems(options)
        
        # Set current selection
        if self.work_experience in options:
            self.exp_combo.setCurrentText(self.work_experience)
        else:
            # Try to match loosely or default to first
            index = self.exp_combo.findText(self.work_experience)
            if index >= 0:
                self.exp_combo.setCurrentIndex(index)
        
        form_layout.addWidget(self.exp_combo)
        
        container_layout.addLayout(form_layout)
        container_layout.addStretch()
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondaryButton")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        
        save_btn = QPushButton("Save Changes")
        save_btn.setObjectName("primaryButton")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self.save_profile)
        
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
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
                font-size: 24px; 
                font-weight: 800; 
                color: #111827; 
                margin-bottom: 10px;
            }
            QLabel#inputLabel {
                font-size: 14px;
                font-weight: 600;
                color: #374151;
            }
            QLineEdit#inputField, QComboBox#inputField { 
                padding: 10px 12px; 
                border: 1px solid #d1d5db; 
                border-radius: 8px; 
                font-size: 14px;
                background-color: #f9fafb;
            }
            QLineEdit#inputField:focus, QComboBox#inputField:focus {
                border-color: #3b82f6;
                background-color: white;
            }
            QPushButton { 
                padding: 10px 20px; 
                border-radius: 8px; 
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
            QPushButton#secondaryButton { 
                background-color: white; 
                border: 1px solid #d1d5db; 
                color: #374151; 
            }
            QPushButton#secondaryButton:hover { 
                background-color: #f9fafb; 
                border-color: #9ca3af; 
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
        """)

    def save_profile(self):
        job = self.job_input.text().strip()
        exp = self.exp_combo.currentText()
        if not job:
            QMessageBox.warning(self, "Error", "Job intention cannot be empty")
            return
            
        success, result = self.api_client.update_profile(job, exp)
        if success:
            msg = QMessageBox(self)
            msg.setWindowTitle("Success")
            msg.setText("Profile updated successfully!")
            msg.setIcon(QMessageBox.Information)
            msg.setStyleSheet("background-color: white;")
            msg.exec_()
            
            self.job_intention = job
            self.work_experience = exp
            self.accept()
        else:
            QMessageBox.warning(self, "Error", str(result))



class CustomMessageBox(QDialog):
    def __init__(self, title, message, icon_type="warning", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedSize(400, 200)
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
        
        # Icon/Title
        title_label = QLabel(title)
        title_label.setObjectName("dialogTitle")
        title_label.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(title_label)
        
        # Message
        msg_label = QLabel(message)
        msg_label.setObjectName("dialogDesc")
        msg_label.setAlignment(Qt.AlignCenter)
        msg_label.setWordWrap(True)
        container_layout.addWidget(msg_label)
        
        # Button
        btn = QPushButton("OK")
        btn.setObjectName("primaryButton")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedWidth(100)
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
                color: #111827; 
            }
            QLabel#dialogDesc { 
                font-size: 14px; 
                color: #6b7280; 
                line-height: 1.5;
            }
            QPushButton#primaryButton { 
                background-color: #3b82f6; 
                color: white; 
                border: none; 
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: 600;
            }
            QPushButton#primaryButton:hover { 
                background-color: #2563eb; 
            }
        """)


class HistoryWindow(QDialog):
    def __init__(self, api_client, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self.setWindowTitle("Interview History")
        self.setFixedSize(800, 600)
        self.init_ui()
        self.load_history()
        self.apply_styles()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        header = QLabel("Your Interview History")
        header.setObjectName("historyHeader")
        layout.addWidget(header)
        
        # Scroll Area for list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setSpacing(15)
        self.scroll_layout.setAlignment(Qt.AlignTop)
        
        scroll.setWidget(self.scroll_content)
        layout.addWidget(scroll)
        
        close_btn = QPushButton("Close")
        close_btn.setObjectName("secondaryButton")
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn, 0, Qt.AlignRight)
        
    def load_history(self):
        success, history = self.api_client.get_interview_history()
        if not success:
            QMessageBox.warning(self, "Error", f"Failed to load history: {history}")
            return
            
        # Clear existing
        for i in reversed(range(self.scroll_layout.count())): 
            self.scroll_layout.itemAt(i).widget().setParent(None)
            
        if not history:
            lbl = QLabel("No interview history found.")
            lbl.setStyleSheet("color: #6b7280; font-style: italic; margin-top: 20px;")
            lbl.setAlignment(Qt.AlignCenter)
            self.scroll_layout.addWidget(lbl)
            return
            
        for item in history:
            card = self.create_history_card(item)
            self.scroll_layout.addWidget(card)
            
    def create_history_card(self, item):
        card = QFrame()
        card.setObjectName("historyCard")
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        
        # Info
        info_layout = QVBoxLayout()
        title = QLabel(item.get('title', 'Interview'))
        title.setObjectName("cardTitle")
        info_layout.addWidget(title)
        
        date_str = item.get('created_at', '')[:10]
        meta = QLabel(f"Position: {item.get('job_position')} | Date: {date_str}")
        meta.setObjectName("cardMeta")
        info_layout.addWidget(meta)
        
        # Status
        status_map = {0: "Pending", 1: "Ongoing", 2: "Ended", 3: "Reviewed"}
        status_code = item.get('status', 0)
        status_text = status_map.get(status_code, "Unknown")
        
        status_lbl = QLabel(status_text)
        if status_code == 1:
            status_lbl.setStyleSheet("color: #2563eb; font-weight: bold;")
        elif status_code == 3:
            status_lbl.setStyleSheet("color: #10b981; font-weight: bold;")
        else:
            status_lbl.setStyleSheet("color: #6b7280; font-weight: bold;")
        info_layout.addWidget(status_lbl)
        
        card_layout.addLayout(info_layout)
        card_layout.addStretch()
        
        # Actions
        btn_layout = QVBoxLayout()
        
        if status_code == 1: # Ongoing
            rejoin_btn = QPushButton("Rejoin")
            rejoin_btn.setObjectName("primaryButton")
            rejoin_btn.setCursor(Qt.PointingHandCursor)
            rejoin_btn.clicked.connect(lambda: self.rejoin_interview(item))
            btn_layout.addWidget(rejoin_btn)
        elif status_code == 3: # Reviewed
            view_fb_btn = QPushButton("View Feedback")
            view_fb_btn.setObjectName("secondaryButton")
            view_fb_btn.setCursor(Qt.PointingHandCursor)
            view_fb_btn.clicked.connect(lambda: self.show_feedback(item))
            btn_layout.addWidget(view_fb_btn)
            
        card_layout.addLayout(btn_layout)
        return card

    def rejoin_interview(self, item):
        success, response = self.api_client.rejoin_interview(item['id'])
        if success:
            self.parent().interview_window = InterviewWindow(self.api_client, response)
            self.parent().interview_window.show()
            self.close()
        else:
            QMessageBox.warning(self, "Error", f"Failed to rejoin: {response}")

    def show_feedback(self, item):
        feedback = item.get('overall_feedback')
        # Use existing FeedbackDialog? We need to import it or recreate it.
        # FeedbackDialog is in interview_window.py but not exported? 
        # Actually it's better to just show a simple dialog here or move FeedbackDialog to a shared module.
        # For simplicity, let's use a standard QMessageBox or a simple dialog.
        
        dlg = QDialog(self)
        dlg.setWindowTitle("Feedback")
        dlg.setFixedSize(500, 400)
        l = QVBoxLayout(dlg)
        t = QTextEdit()
        t.setReadOnly(True)
        t.setText(str(feedback))
        l.addWidget(t)
        dlg.exec_()

    def apply_styles(self):
        self.setStyleSheet("""
            QDialog { background-color: #f3f4f6; }
            QLabel#historyHeader { font-size: 24px; font-weight: 800; color: #111827; }
            QFrame#historyCard { 
                background-color: white; 
                border-radius: 12px; 
                border: 1px solid #e5e7eb; 
            }
            QLabel#cardTitle { font-size: 18px; font-weight: 700; color: #1f2937; }
            QLabel#cardMeta { font-size: 14px; color: #6b7280; }
            QPushButton { padding: 6px 12px; border-radius: 6px; font-size: 13px; font-weight: 600; }
            QPushButton#primaryButton { background-color: #3b82f6; color: white; border: none; }
            QPushButton#primaryButton:hover { background-color: #2563eb; }
            QPushButton#secondaryButton { background-color: white; border: 1px solid #d1d5db; color: #374151; }
            QPushButton#secondaryButton:hover { background-color: #f9fafb; border-color: #9ca3af; }
        """)



class JoinDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Join Interview")
        self.setFixedSize(400, 250)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.code = None
        self.name = None
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        container = QFrame()
        container.setObjectName("dialogContainer")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(30, 30, 30, 30)
        container_layout.setSpacing(15)
        
        title = QLabel("Join Interview")
        title.setObjectName("dialogTitle")
        title.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(title)
        
        # Code Input
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("Enter Invite Code")
        self.code_input.setObjectName("inputField")
        container_layout.addWidget(self.code_input)
        
        # Name Input
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Your Name (Optional)")
        self.name_input.setObjectName("inputField")
        container_layout.addWidget(self.name_input)
        
        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondaryButton")
        cancel_btn.clicked.connect(self.reject)
        
        join_btn = QPushButton("Join")
        join_btn.setObjectName("primaryButton")
        join_btn.clicked.connect(self.accept_join)
        
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(join_btn)
        container_layout.addLayout(btn_layout)
        
        layout.addWidget(container)
        self.setLayout(layout)
        
        self.setStyleSheet("""
            QFrame#dialogContainer { background-color: white; border-radius: 16px; border: 1px solid #e5e7eb; }
            QLabel#dialogTitle { font-size: 20px; font-weight: bold; color: #111827; }
            QLineEdit#inputField { padding: 10px; border: 1px solid #d1d5db; border-radius: 8px; background-color: #f9fafb; }
            QPushButton { padding: 8px 16px; border-radius: 8px; font-weight: 600; }
            QPushButton#primaryButton { background-color: #3b82f6; color: white; border: none; }
            QPushButton#secondaryButton { background-color: white; border: 1px solid #d1d5db; color: #374151; }
        """)

    def accept_join(self):
        self.code = self.code_input.text().strip()
        self.name = self.name_input.text().strip() or "Anonymous"
        if self.code:
            self.accept()
        else:
            self.code_input.setPlaceholderText("Code is required!")


class MainWindow(QMainWindow):
    def __init__(self, api_client, user_data):
        super().__init__()
        self.api_client = api_client
        self.user_data = user_data
        self.setWindowTitle(f"MirrorView - Dashboard")
        self.setFixedSize(1000, 700)
        self.init_ui()
        self.apply_styles()

    def init_ui(self):
        central_widget = QWidget()
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Sidebar
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(20, 40, 20, 40)
        sidebar_layout.setSpacing(20)
        
        # App Logo/Title in Sidebar
        app_title = QLabel("MirrorView")
        app_title.setObjectName("appTitle")
        app_title.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(app_title)
        
        sidebar_layout.addStretch()

        
        # User Info in Sidebar
        user_info = QLabel(f"Logged in as:\n{self.user_data.get('username')}")
        user_info.setObjectName("userInfo")
        user_info.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(user_info)
        
        # Logout Button (placeholder functionality)
                # Edit Profile Button
        profile_btn = QPushButton("Edit Profile")
        profile_btn.setObjectName("secondaryButton")
        profile_btn.setCursor(Qt.PointingHandCursor)
        profile_btn.clicked.connect(self.edit_profile)
        sidebar_layout.addWidget(profile_btn)
        
        logout_btn = QPushButton("Logout")
        logout_btn.setObjectName("logoutButton")
        logout_btn.setCursor(Qt.PointingHandCursor)
        logout_btn.clicked.connect(self.close)
        sidebar_layout.addWidget(logout_btn)

        main_layout.addWidget(sidebar, 1)

        # Content Area
        content_area = QWidget()
        content_layout = QVBoxLayout(content_area)
        content_layout.setContentsMargins(50, 50, 50, 50)
        content_layout.setSpacing(30)
        
        # Welcome Header
        welcome_header = QLabel(f"Welcome back, {self.user_data.get('username')}!")
        welcome_header.setObjectName("welcomeHeader")
        content_layout.addWidget(welcome_header)
        
        subtitle = QLabel("Ready to practice your interview skills?")
        subtitle.setObjectName("subtitle")
        content_layout.addWidget(subtitle)
        
        content_layout.addSpacing(20)
        
        # Action Cards Container
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(20)
        
        # Start Interview Card
        start_card = self.create_card("Start New Interview", "Begin a mock interview session tailored to your profile.", "primaryButton", self.show_resume_dialog)
        cards_layout.addWidget(start_card)
        
        # Join Interview Card
        join_card = self.create_card("Join Interview", "Join an existing session as a listener using an invite code.", "secondaryButton", self.join_interview)
        cards_layout.addWidget(join_card)
        
        content_layout.addLayout(cards_layout)
        
        # History Section (Placeholder)
        history_frame = QFrame()
        history_frame.setObjectName("card")
        history_layout = QVBoxLayout(history_frame)
        
        history_title = QLabel("Recent Activity")
        history_title.setObjectName("cardTitle")
        history_layout.addWidget(history_title)
        
        history_desc = QLabel("Your interview history will appear here.")
        history_desc.setStyleSheet("color: #6b7280; font-style: italic;")
        history_layout.addWidget(history_desc)
        
        view_history_btn = QPushButton("View Full History")
        view_history_btn.setObjectName("linkButton")
        view_history_btn.setCursor(Qt.PointingHandCursor)
        view_history_btn.clicked.connect(self.view_history)
        history_layout.addWidget(view_history_btn, 0, Qt.AlignLeft)
        
        content_layout.addWidget(history_frame)
        content_layout.addStretch()
        
        main_layout.addWidget(content_area, 3)
        
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

    def create_card(self, title_text, desc_text, btn_style, callback):
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(15)
        
        title = QLabel(title_text)
        title.setObjectName("cardTitle")
        layout.addWidget(title)
        
        desc = QLabel(desc_text)
        desc.setWordWrap(True)
        desc.setObjectName("cardDesc")
        layout.addWidget(desc)
        
        layout.addStretch()
        
        btn = QPushButton(title_text)
        btn.setObjectName(btn_style)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(callback)
        layout.addWidget(btn)
        
        return card

    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f3f4f6;
            }
            QFrame#sidebar {
                background-color: #1f2937;
                border: none;
            }
            QLabel#appTitle {
                color: #ffffff;
                font-size: 24px;
                font-weight: bold;
                letter-spacing: 1px;
            }
            QLabel#userInfo {
                color: #9ca3af;
                font-size: 14px;
            }
            QLabel#welcomeHeader {
                color: #111827;
                font-size: 32px;
                font-weight: 800;
            }
            QLabel#subtitle {
                color: #6b7280;
                font-size: 18px;
            }
            QFrame#card {
                background-color: #ffffff;
                border-radius: 12px;
                border: 1px solid #e5e7eb;
            }
            QLabel#cardTitle {
                color: #111827;
                font-size: 20px;
                font-weight: 600;
            }
            QLabel#cardDesc {
                color: #4b5563;
                font-size: 14px;
                line-height: 1.4;
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
            QPushButton#secondaryButton {
                background-color: #ffffff;
                color: #374151;
                border: 1px solid #d1d5db;
            }
            QPushButton#secondaryButton:hover {
                background-color: #f9fafb;
                border-color: #9ca3af;
            }
            QPushButton#logoutButton {
                background-color: rgba(255, 255, 255, 0.1);
                color: #e5e7eb;
                border: none;
            }
            QPushButton#logoutButton:hover {
                background-color: rgba(255, 255, 255, 0.2);
                color: #ffffff;
            }
            QPushButton#linkButton {
                background-color: transparent;
                color: #3b82f6;
                border: none;
                text-align: left;
                padding: 5px 0;
            }
            QPushButton#linkButton:hover {
                text-decoration: underline;
            }
        """)

    def show_resume_dialog(self):
        # Open dialog to upload resume
        dialog = ResumeUploadDialog(self.api_client, self)
        
        # Check result: Accepted means Uploaded or Skipped (via Accept button if we had one for skip, but current skip calls reject)
        # Actually in resume_dialog:
        # Upload -> accept()
        # Skip -> reject()
        # Close -> reject()
        
        # Wait, if user skips, they still want to interview?
        # If user closes, they probably cancelled the action.
        
        # Let's check the dialog result
        result = dialog.exec_()
        
        # If we want "Skip" to also proceed, we should make Skip call accept() or use a custom code.
        # But if Close (X) calls reject(), we need to distinguish Skip from Close.
        
        # Current implementation in ResumeUploadDialog:
        # Skip button -> reject()
        # Close button -> reject()
        # Upload success -> accept()
        
        # We should change ResumeUploadDialog to have Skip call accept() or a different method?
        # Or better: Just check if we should proceed.
        
        # If we want to strictly stop on Close but proceed on Skip/Upload:
        # We need to change ResumeUploadDialog.
        
        # Let's assume for now we only proceed if result is Accepted (Upload success)
        # But wait, Skip should also allow proceeding.
        
        # I will modify this to only proceed if Accepted.
        # AND I need to go to ResumeUploadDialog and make "Skip" return Accepted (or a specific code).
        
        if result == QDialog.Accepted:
             self.start_interview()
        else:
            # If rejected (Skip or Close), currently we don't start.
            # But the user might want to Skip and start.
            # I will modify ResumeUploadDialog to handle Skip as a positive action to proceed without resume.
            pass

    def start_interview(self):
        # job_position is now fetched from user profile on server
        success, response = self.api_client.create_interview()
        if success:
            self.interview_window = InterviewWindow(self.api_client, response)
            self.interview_window.show()
            # self.hide() # Optional: hide main window
        else:
            if "ongoing interview" in str(response):
                dlg = CustomMessageBox("Active Interview Exists", 
                    "You already have an interview in progress. Please finish it or check your history to rejoin.",
                    parent=self)
                dlg.exec_()
            else:
                QMessageBox.warning(self, "Error", f"Failed to start interview: {response}")

    def join_interview(self):
        dialog = JoinDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            success, response = self.api_client.join_interview(dialog.code, dialog.name)
            if success:
                from client.ui.listener_window import ListenerWindow
                self.listener_window = ListenerWindow(self.api_client, response)
                self.listener_window.show()
            else:
                QMessageBox.warning(self, "Error", "Failed to join interview")

    def view_history(self):
        history_window = HistoryWindow(self.api_client, self)
        history_window.exec_()

    def edit_profile(self):
        # We need to get current user data, assuming self.user_data has it
        # Or better, fetch it or pass what we have
        current_job = self.user_data.get('job_intention', '')
        current_exp = self.user_data.get('work_experience', '')
        
        dialog = ProfileDialog(self.api_client, current_job, current_exp, self)
        if dialog.exec_() == QDialog.Accepted:
            # Update local data
            self.user_data['job_intention'] = dialog.job_intention
            self.user_data['work_experience'] = dialog.work_experience
            # Update UI if needed (e.g. welcome message or sidebar info)
            # Reload?
            pass
