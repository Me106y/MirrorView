from PyQt5.QtWidgets import (QWidget, QLabel, QPushButton, QVBoxLayout, QScrollArea,
                             QApplication, QMessageBox, QInputDialog, QMainWindow, QFrame, QHBoxLayout, QDialog, QLineEdit, QComboBox,
                             QTextEdit, QSizePolicy, QFileDialog, QListView, QStyledItemDelegate)
from PyQt5.QtCore import Qt, QTimer
from client.ui.interview_window import InterviewWindow
from client.ui.voice_interview_window import VoiceInterviewWindow
from client.ui.resume_dialog import ResumeUploadDialog
import os
import socket
import subprocess
import sys
import json
import tempfile
import webbrowser
from urllib.parse import urlencode


# ---------------------------------------------------------------------------
# Mode Selection Dialog
# ---------------------------------------------------------------------------

class ModeSelectDialog(QDialog):
    """Let user choose between Classic (text) and Voice (TTS+avatar) interview."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择面试模式")
        self.setFixedSize(620, 420)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.selected_mode = None  # "classic" or "voice"
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("dialogContainer")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(30, 35, 30, 30)
        container_layout.setSpacing(18)

        # Header
        title = QLabel("🎯 请选择面试模式")
        title.setObjectName("dialogTitle")
        title.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(title)

        subtitle = QLabel("请选择您希望与 AI 面试官互动的方式")
        subtitle.setObjectName("dialogDesc")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        container_layout.addWidget(subtitle)

        # --- Two cards side by side ---
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(18)

        # Classic Mode Card
        classic_card = self._create_card(
            icon="💬",
            title="经典模式",
            desc="与 AI 面试官进行文字对话。\n输入答案并查看回复。\n\n✅ 适合安静环境\n✅ 完整聊天记录可见\n✅ 支持旁听功能",
            color="#3b82f6",
        )
        classic_card.mousePressEvent = lambda e: self._select("classic")
        classic_card.setCursor(Qt.PointingHandCursor)
        cards_layout.addWidget(classic_card)

        # Voice Mode Card
        voice_card = self._create_card(
            icon="🎙️",
            title="语音模式",
            desc="实时语音对话体验。\n自然开口，AI 实时回应。\n\n🔊 TTS 语音播报\n🎤 语音输入（STT）\n🤖 动态 AI 头像\n⚡ 更沉浸的互动感",
            color="#10b981",
        )
        voice_card.mousePressEvent = lambda e: self._select("voice")
        voice_card.setCursor(Qt.PointingHandCursor)
        cards_layout.addWidget(voice_card)

        container_layout.addLayout(cards_layout)

        # Cancel
        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("secondaryButton")
        cancel_btn.setFixedWidth(100)
        cancel_btn.clicked.connect(self.reject)
        container_layout.addWidget(cancel_btn, 0, Qt.AlignCenter)

        layout.addWidget(container)
        self.setLayout(layout)

        self.setStyleSheet("""
            QFrame#dialogContainer {
                background-color: white;
                border-radius: 20px;
                border: 1px solid #e5e7eb;
            }
            QLabel#dialogTitle {
                font-size: 22px; font-weight: 800; color: #111827;
            }
            QLabel#dialogDesc {
                font-size: 14px; color: #6b7280;
            }
            QPushButton#secondaryButton {
                background-color: white; border: 1px solid #d1d5db;
                color: #374151; border-radius: 8px; padding: 8px 20px;
                font-size: 14px; font-weight: 600;
            }
            QPushButton#secondaryButton:hover {
                background-color: #f9fafb; border-color: #9ca3af;
            }
        """)

    def _create_card(self, icon, title, desc, color):
        """Create a selectable mode card."""
        card = QFrame()
        card.setObjectName("modeCard")

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 20, 16, 16)
        card_layout.setSpacing(10)

        # Icon
        icon_label = QLabel(icon)
        icon_label.setStyleSheet(f"font-size: 40px;")
        icon_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(icon_label)

        # Title
        title_label = QLabel(title)
        title_label.setStyleSheet(
            f"font-size: 17px; font-weight: 700; color: {color};")
        title_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(title_label)

        # Description
        desc_label = QLabel(desc)
        desc_label.setStyleSheet(
            "font-size: 12px; color: #6b7280; line-height: 1.6;")
        desc_label.setAlignment(Qt.AlignCenter)
        desc_label.setWordWrap(True)
        card_layout.addWidget(desc_label)

        card_layout.addStretch()

        # Hover effect via stylesheet
        card.setStyleSheet(f"""
            QFrame#modeCard {{
                background: white;
                border: 2px solid #e5e7eb;
                border-radius: 14px;
            }}
            QFrame#modeCard:hover {{
                border-color: {color};
                background: #f8fafc;
            }}
        """)

        return card

    def _select(self, mode):
        self.selected_mode = mode
        self.accept()


class ExperienceItemDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(max(size.height(), 44))
        return size


class ProfileDialog(QDialog):
    def __init__(self, api_client, current_role, current_jd, current_exp, has_resume=False, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self.setWindowTitle("编辑个人信息")
        self.setFixedSize(560, 620)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.target_role = current_role or ""
        self.target_jd = current_jd or ""
        self.work_experience = current_exp or ""
        self.has_resume = bool(has_resume)
        self.selected_resume_path = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("dialogContainer")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(30, 30, 30, 30)
        container_layout.setSpacing(16)

        title = QLabel("编辑个人信息")
        title.setObjectName("dialogTitle")
        title.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(title)

        form_layout = QVBoxLayout()
        form_layout.setSpacing(12)

        role_label = QLabel("目标岗位")
        role_label.setObjectName("inputLabel")
        form_layout.addWidget(role_label)

        self.role_input = QLineEdit(self.target_role)
        self.role_input.setPlaceholderText("如：AI应用开发")
        self.role_input.setObjectName("inputField")
        form_layout.addWidget(self.role_input)

        jd_label = QLabel("JD")
        jd_label.setObjectName("inputLabel")
        form_layout.addWidget(jd_label)

        self.jd_input = QTextEdit()
        self.jd_input.setObjectName("jdField")
        self.jd_input.setPlaceholderText("请粘贴目标岗位 JD，便于后续匹配分析与面试准备。")
        self.jd_input.setPlainText(self.target_jd)
        self.jd_input.setMinimumHeight(150)
        form_layout.addWidget(self.jd_input)

        exp_label = QLabel("工作经验")
        exp_label.setObjectName("inputLabel")
        form_layout.addWidget(exp_label)

        self.exp_combo = QComboBox()
        self.exp_combo.setObjectName("inputField")
        popup_view = QListView()
        popup_view.setObjectName("experiencePopup")
        popup_view.setMouseTracking(True)
        popup_view.setUniformItemSizes(True)
        popup_view.setItemDelegate(ExperienceItemDelegate(popup_view))
        popup_view.setStyleSheet("""
            QListView#experiencePopup {
                background-color: #ffffff;
                color: #111827;
                border: 1px solid #d1d5db;
                border-radius: 12px;
                padding: 6px;
                outline: none;
            }
            QListView#experiencePopup::item {
                min-height: 44px;
                padding: 8px 14px;
                border-radius: 9px;
                color: #111827;
                background-color: #ffffff;
            }
            QListView#experiencePopup::item:hover {
                background-color: #3b82f6;
                color: #ffffff;
            }
            QListView#experiencePopup::item:selected {
                background-color: #3b82f6;
                color: #ffffff;
            }
        """)
        self.exp_combo.setView(popup_view)
        options = ["无经验", "1-2 年", "3-5 年", "5 年以上"]
        legacy_map = {
            "No experience": "无经验",
            "1-2 years": "1-2 年",
            "3-5 years": "3-5 年",
            "5+ years": "5 年以上",
        }
        self.exp_combo.addItems(options)
        normalized_exp = legacy_map.get(self.work_experience, self.work_experience)
        if normalized_exp in options:
            self.exp_combo.setCurrentText(normalized_exp)
        form_layout.addWidget(self.exp_combo)

        resume_label = QLabel("简历（PDF）")
        resume_label.setObjectName("inputLabel")
        form_layout.addWidget(resume_label)

        resume_row = QHBoxLayout()
        resume_row.setSpacing(10)
        self.resume_status = QLabel("已上传简历" if self.has_resume else "未上传简历")
        self.resume_status.setObjectName("resumeStatus")
        resume_row.addWidget(self.resume_status)
        resume_row.addStretch()

        self.resume_btn = QPushButton("上传简历")
        self.resume_btn.setObjectName("secondaryButton")
        self.resume_btn.setCursor(Qt.PointingHandCursor)
        self.resume_btn.clicked.connect(self.select_resume)
        resume_row.addWidget(self.resume_btn)
        form_layout.addLayout(resume_row)

        container_layout.addLayout(form_layout)
        container_layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)

        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("secondaryButton")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("保存修改")
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
                margin-bottom: 8px;
            }
            QLabel#inputLabel {
                font-size: 14px;
                font-weight: 600;
                color: #374151;
            }
            QLabel#resumeStatus {
                font-size: 13px;
                color: #6b7280;
            }
            QLineEdit#inputField {
                padding: 10px 12px;
                border: 1px solid #d1d5db;
                border-radius: 8px;
                font-size: 14px;
                background-color: #f9fafb;
            }
            QTextEdit#jdField {
                padding: 10px 12px;
                border: 1px solid #d1d5db;
                border-radius: 8px;
                font-size: 13px;
                background-color: #f9fafb;
            }
            QLineEdit#inputField:focus, QTextEdit#jdField:focus {
                border-color: #3b82f6;
                background-color: white;
            }
            QComboBox#inputField {
                padding: 10px 12px;
                border: 1px solid #d1d5db;
                border-radius: 12px;
                font-size: 14px;
                background-color: #ffffff;
                color: #111827;
            }
            QComboBox#inputField:focus {
                border-color: #3b82f6;
            }
            QComboBox#inputField::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox#inputField QAbstractItemView {
                background-color: #ffffff;
                color: #111827;
                border: 1px solid #d1d5db;
                border-radius: 10px;
                outline: none;
            }
            QListView#experiencePopup {
                background-color: #ffffff;
                color: #111827;
                border: 1px solid #d1d5db;
                border-radius: 12px;
                padding: 4px;
                outline: none;
            }
            QListView#experiencePopup::item {
                min-height: 44px;
                padding: 8px 14px;
                border-radius: 9px;
                color: #111827;
                background-color: #ffffff;
            }
            QListView#experiencePopup::item:hover {
                background-color: #3b82f6;
                color: #ffffff;
            }
            QListView#experiencePopup::item:selected {
                background-color: #3b82f6;
                color: #ffffff;
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
        """)

    def select_resume(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择简历文件", "", "PDF Files (*.pdf)")
        if not file_path:
            return
        self.selected_resume_path = file_path
        self.resume_status.setText(f"待上传：{os.path.basename(file_path)}")
        self.resume_status.setStyleSheet("color: #1d4ed8;")

    def save_profile(self):
        role = self.role_input.text().strip() or self.target_role
        jd_text = self.jd_input.toPlainText().strip()
        exp = self.exp_combo.currentText()
        if not role:
            QMessageBox.warning(self, "提示", "目标岗位不能为空")
            return

        success, result = self.api_client.update_profile(role, jd_text, exp)
        if not success:
            QMessageBox.warning(self, "失败", str(result))
            return

        upload_error = None
        if self.selected_resume_path:
            uploaded, upload_result = self.api_client.upload_resume(self.selected_resume_path)
            if uploaded:
                self.has_resume = True
            else:
                upload_error = str(upload_result)

        self.target_role = role
        self.target_jd = jd_text
        self.work_experience = exp

        if upload_error:
            QMessageBox.warning(self, "部分成功", f"信息已保存，但简历上传失败：{upload_error}")
        else:
            msg = QMessageBox(self)
            msg.setWindowTitle("成功")
            msg.setText("个人信息更新成功！")
            msg.setIcon(QMessageBox.Information)
            msg.setStyleSheet("background-color: white;")
            msg.exec_()
        self.accept()



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
        btn = QPushButton("确定")
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
        self.setWindowTitle("面试历史")
        self.setFixedSize(800, 600)
        self.init_ui()
        self.load_history()
        self.apply_styles()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        header = QLabel("您的面试历史")
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
        
        close_btn = QPushButton("关闭")
        close_btn.setObjectName("secondaryButton")
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn, 0, Qt.AlignRight)
        
    def load_history(self):
        success, history = self.api_client.get_interview_history()
        if not success:
            QMessageBox.warning(self, "错误", f"加载历史失败：{history}")
            return
            
        # Clear existing
        for i in reversed(range(self.scroll_layout.count())): 
            self.scroll_layout.itemAt(i).widget().setParent(None)
            
        if not history:
            lbl = QLabel("暂无面试历史记录。")
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
        title = QLabel(item.get('title', '面试'))
        title.setObjectName("cardTitle")
        info_layout.addWidget(title)
        
        date_str = item.get('created_at', '')[:10]
        meta = QLabel(f"岗位：{item.get('job_position')} | 日期：{date_str}")
        meta.setObjectName("cardMeta")
        info_layout.addWidget(meta)
        
        # Status
        status_map = {0: "待开始", 1: "进行中", 2: "已结束", 3: "已评估"}
        status_code = item.get('status', 0)
        status_text = status_map.get(status_code, "未知")
        
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
            rejoin_btn = QPushButton("继续面试")
            rejoin_btn.setObjectName("primaryButton")
            rejoin_btn.setCursor(Qt.PointingHandCursor)
            rejoin_btn.clicked.connect(lambda: self.rejoin_interview(item))
            btn_layout.addWidget(rejoin_btn)
        elif status_code == 3: # Reviewed
            view_fb_btn = QPushButton("查看反馈")
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
            QMessageBox.warning(self, "错误", f"继续面试失败：{response}")

    def show_feedback(self, item):
        feedback = item.get('overall_feedback')
        # Use existing FeedbackDialog? We need to import it or recreate it.
        # FeedbackDialog is in interview_window.py but not exported? 
        # Actually it's better to just show a simple dialog here or move FeedbackDialog to a shared module.
        # For simplicity, let's use a standard QMessageBox or a simple dialog.
        
        dlg = QDialog(self)
        dlg.setWindowTitle("面试反馈")
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
        self.setWindowTitle("加入旁听")
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
        
        title = QLabel("加入旁听")
        title.setObjectName("dialogTitle")
        title.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(title)
        
        # Code Input
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("请输入邀请码")
        self.code_input.setObjectName("inputField")
        container_layout.addWidget(self.code_input)
        
        # Name Input
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("您的昵称（可选）")
        self.name_input.setObjectName("inputField")
        container_layout.addWidget(self.name_input)
        
        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("secondaryButton")
        cancel_btn.clicked.connect(self.reject)
        
        join_btn = QPushButton("加入")
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
        self.name = self.name_input.text().strip() or "旁听者"
        if self.code:
            self.accept()
        else:
            self.code_input.setPlaceholderText("请输入邀请码")


class MainWindow(QMainWindow):
    def __init__(self, api_client, user_data):
        super().__init__()
        self.api_client = api_client
        self.user_data = user_data
        self._resume_match_streamlit_proc = None
        self._resume_match_streamlit_port = 8511
        self._resume_craft_streamlit_proc = None
        self._resume_craft_streamlit_port = 8512
        self._cover_letter_streamlit_proc = None
        self._cover_letter_streamlit_port = 8513
        self.setWindowTitle("MirrorView - 控制台")
        self.setFixedSize(1160, 760)
        self.init_ui()
        self.apply_styles()
        self.center_on_screen()

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
        user_info = QLabel(f"当前登录：\n{self.user_data.get('username')}")
        user_info.setObjectName("userInfo")
        user_info.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(user_info)
        
        # Logout Button (placeholder functionality)
                # Edit Profile Button
        profile_btn = QPushButton("编辑信息")
        profile_btn.setObjectName("secondaryButton")
        profile_btn.setCursor(Qt.PointingHandCursor)
        profile_btn.clicked.connect(self.edit_profile)
        sidebar_layout.addWidget(profile_btn)
        
        logout_btn = QPushButton("退出登录")
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
        welcome_header = QLabel(f"欢迎使用，{self.user_data.get('username')}！")
        welcome_header.setObjectName("welcomeHeader")
        content_layout.addWidget(welcome_header)
        
        subtitle = QLabel("准备开始您的求职训练了吗？")
        subtitle.setObjectName("subtitle")
        content_layout.addWidget(subtitle)

        content_layout.addSpacing(20)

        toolbox_title = QLabel("求职工具箱")
        toolbox_title.setObjectName("cardTitle")
        content_layout.addWidget(toolbox_title)

        tools_grid = QHBoxLayout()
        tools_grid.setSpacing(16)

        match_card = self.create_card(
            "简历匹配分析",
            "多维评分、差距定位与优化建议。",
            "secondaryButton",
            self.open_resume_match,
        )
        tools_grid.addWidget(match_card)

        craft_card = self.create_card(
            "简历生成",
            "生成结构化简历内容和排版建议。",
            "secondaryButton",
            self.open_resume_craft,
        )
        tools_grid.addWidget(craft_card)

        letter_card = self.create_card(
            "求职信撰写",
            "输出邮件版求职信和招聘平台沟通文案。",
            "secondaryButton",
            self.open_cover_letter,
        )
        tools_grid.addWidget(letter_card)
        content_layout.addLayout(tools_grid)

        interview_row = QHBoxLayout()
        interview_row.setSpacing(20)

        interview_card = self.create_card(
            "模拟面试",
            "智能问答驱动面试。",
            "secondaryButton",
            self.show_resume_dialog,
        )
        interview_row.addWidget(interview_card)

        join_card = self.create_card(
            "加入旁听",
            "使用邀请码加入正在进行的面试旁听。",
            "secondaryButton",
            self.join_interview,
        )
        interview_row.addWidget(join_card)


        find_card = self.create_card(
            "寻找工作",
            "筛选并输出高匹配岗位清单。",
            "secondaryButton",
            self.open_job_hunt,
        )
        interview_row.addWidget(find_card)

        content_layout.addLayout(interview_row)
        
        # History Section (Placeholder)
        history_frame = QFrame()
        history_frame.setObjectName("card")
        history_layout = QVBoxLayout(history_frame)
        
        history_title = QLabel("最近活动")
        history_title.setObjectName("cardTitle")
        history_layout.addWidget(history_title)
        
        history_desc = QLabel("您的面试历史和反馈将显示在这里。")
        history_desc.setStyleSheet("color: #6b7280; font-style: italic;")
        history_layout.addWidget(history_desc)
        
        view_history_btn = QPushButton("查看完整历史")
        view_history_btn.setObjectName("linkButton")
        view_history_btn.setCursor(Qt.PointingHandCursor)
        view_history_btn.clicked.connect(self.view_history)
        history_layout.addWidget(view_history_btn, 0, Qt.AlignLeft)
        
        content_layout.addWidget(history_frame)
        content_layout.addStretch()
        
        main_layout.addWidget(content_area, 3)
        
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

    def center_on_screen(self):
        screen = QApplication.primaryScreen()
        if not screen:
            return
        screen_geometry = screen.availableGeometry()
        frame_geometry = self.frameGeometry()
        frame_geometry.moveCenter(screen_geometry.center())
        self.move(frame_geometry.topLeft())

    def create_card(self, title_text, desc_text, btn_style, callback):
        card = QFrame()
        card.setObjectName("card")
        card.setFixedHeight(158)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(8)
        
        title = QLabel(title_text)
        title.setObjectName("featureCardTitle")
        title.setWordWrap(True)
        layout.addWidget(title)
        
        desc = QLabel(desc_text)
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        desc.setObjectName("cardDesc")
        desc.setMinimumHeight(36)
        layout.addWidget(desc)
        
        layout.addStretch()
        
        btn = QPushButton(title_text)
        btn.setObjectName(btn_style)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(34)
        btn.setMinimumWidth(120)
        btn.setMaximumWidth(170)
        btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        btn.clicked.connect(callback)
        layout.addWidget(btn, 0, Qt.AlignHCenter)
        
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
            QLabel#featureCardTitle {
                color: #111827;
                font-size: 16px;
                font-weight: 700;
            }
            QLabel#cardDesc {
                color: #4b5563;
                font-size: 12px;
                line-height: 1.4;
                font-style: italic;
            }
            QPushButton {
                border-radius: 10px;
                padding: 6px 12px;
                font-weight: 600;
                font-size: 13px;
            }
            QFrame#card QPushButton {
                min-height: 34px;
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
        # We don't necessarily need the result, just that they closed it (uploaded or skipped)
        # Then we start the interview
        dialog.exec_()
        self.start_interview()

    def start_interview(self):
        # job_position is now fetched from user profile on server
        success, response = self.api_client.create_interview()
        if success:
            # Show mode selection dialog
            mode_dlg = ModeSelectDialog(self)
            if mode_dlg.exec_() != QDialog.Accepted:
                return  # User cancelled

            if mode_dlg.selected_mode == "voice":
                # Open voice-first interview
                self.interview_window = VoiceInterviewWindow(
                    self.api_client, response)
            else:
                # Open classic text interview
                self.interview_window = InterviewWindow(
                    self.api_client, response)

            self.interview_window.show()
        else:
            if "ongoing interview" in str(response):
                dlg = CustomMessageBox("已有进行中的面试", 
                    "您已有进行中的面试，请先完成当前面试，或在历史中继续。",
                    parent=self)
                dlg.exec_()
            else:
                QMessageBox.warning(self, "错误", f"开始面试失败：{response}")

    def join_interview(self):
        dialog = JoinDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            success, response = self.api_client.join_interview(dialog.code, dialog.name)
            if success:
                from client.ui.listener_window import ListenerWindow
                self.listener_window = ListenerWindow(self.api_client, response)
                self.listener_window.show()
            else:
                QMessageBox.warning(self, "错误", "加入旁听失败")

    def view_history(self):
        history_window = HistoryWindow(self.api_client, self)
        history_window.exec_()

    def edit_profile(self):
        # Always read latest profile from database before opening editor.
        ok, profile = self.api_client.get_profile()
        if ok and isinstance(profile, dict):
            self.user_data.update(profile)

        current_role = self.user_data.get('target_role') or self.user_data.get('job_intention', '')
        current_jd = self.user_data.get('target_jd', '')
        current_exp = self.user_data.get('work_experience', '')
        has_resume = self.user_data.get('has_resume', False)

        dialog = ProfileDialog(self.api_client, current_role, current_jd, current_exp, has_resume, self)
        if dialog.exec_() == QDialog.Accepted:
            self.user_data['target_role'] = dialog.target_role
            self.user_data['job_intention'] = dialog.target_role
            self.user_data['target_jd'] = dialog.target_jd
            self.user_data['work_experience'] = dialog.work_experience
            self.user_data['has_resume'] = dialog.has_resume

    def open_job_hunt(self):
        target_role = (self.user_data.get('target_role') or self.user_data.get('job_intention') or '').strip()
        target_jd = (self.user_data.get('target_jd') or '').strip()
        work_experience = (self.user_data.get('work_experience') or '').strip()

        if not target_role:
            target_role, ok = QInputDialog.getText(self, "补充信息", "请输入目标岗位：")
            if not ok:
                return
            target_role = target_role.strip()
            if not target_role:
                QMessageBox.warning(self, "提示", "请先填写目标岗位，再进行岗位搜索。")
                return

        success, response = self.api_client.run_job_hunt(
            target_role=target_role,
            target_jd=target_jd,
            work_experience=work_experience,
        )
        if not success:
            QMessageBox.warning(self, "错误", f"调用 Job Hunt 失败：{response}")
            return

        result = response.get("result", {}) if isinstance(response, dict) else {}
        summary_text = self._format_job_hunt_result(result)
        dlg = QDialog(self)
        dlg.setWindowTitle("Job Hunt 结果")
        dlg.setFixedSize(720, 560)
        layout = QVBoxLayout(dlg)

        title = QLabel("寻找工作（Job Hunt）已执行")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #111827;")
        layout.addWidget(title)

        body = QTextEdit()
        body.setReadOnly(True)
        body.setText(summary_text)
        body.setStyleSheet("background: #ffffff; border: 1px solid #e5e7eb; border-radius: 10px;")
        layout.addWidget(body)

        close_btn = QPushButton("关闭")
        close_btn.setObjectName("secondaryButton")
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, 0, Qt.AlignRight)
        dlg.exec_()

    @staticmethod
    def _format_job_hunt_result(result):
        if not isinstance(result, dict):
            return "未获取到有效结果。"

        lines = []
        summary = (result.get("summary") or "").strip()
        if summary:
            lines.append(f"总览：{summary}")

        jobs = result.get("top_jobs") or []
        if jobs:
            lines.append("")
            lines.append("推荐岗位：")
            for idx, job in enumerate(jobs[:10], start=1):
                title = job.get("title", "未命名岗位")
                company = job.get("company", "未知公司")
                location = job.get("location", "地点未标注")
                salary = job.get("salary", "薪资未标注")
                level = job.get("match_level", "unknown")
                reason = job.get("match_reason", "")
                url = job.get("url", "")
                lines.append(f"{idx}. {title} - {company}")
                lines.append(f"   地点：{location} | 薪资：{salary} | 匹配等级：{level}")
                if reason:
                    lines.append(f"   匹配点：{reason}")
                if url:
                    lines.append(f"   链接：{url}")
                lines.append("")

        next_actions = result.get("next_actions") or []
        if next_actions:
            lines.append("下一步建议：")
            for i, item in enumerate(next_actions[:5], start=1):
                lines.append(f"{i}. {item}")

        assumptions = result.get("assumptions") or []
        if assumptions:
            lines.append("")
            lines.append("备注：")
            for item in assumptions[:5]:
                lines.append(f"- {item}")

        if not lines:
            return "已调用 Job Hunt Skill，但暂未返回可展示的内容。"
        return "\n".join(lines)

    def open_resume_match(self):
        prefill_params = self._get_streamlit_prefill_params()

        app_path = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "streamlit",
                "resume_match_agent_app.py",
            )
        )
        app_path = os.path.normpath(app_path)

        if not os.path.exists(app_path):
            QMessageBox.warning(self, "错误", f"未找到 Streamlit 页面：{app_path}")
            return

        base_url = f"http://localhost:{self._resume_match_streamlit_port}"
        url = self._build_streamlit_url(base_url, prefill_params)

        if self._is_port_open(self._resume_match_streamlit_port):
            webbrowser.open(url)
            return

        try:
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            env = os.environ.copy()
            env["PYTHONPATH"] = project_root + os.pathsep + env.get("PYTHONPATH", "")
            cmd = [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                app_path,
                "--server.port",
                str(self._resume_match_streamlit_port),
                "--server.headless",
                "true",
                "--browser.gatherUsageStats",
                "false",
            ]
            self._resume_match_streamlit_proc = subprocess.Popen(
                cmd,
                cwd=project_root,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            QTimer.singleShot(1800, lambda u=url: webbrowser.open(u))
        except Exception as e:
            QMessageBox.warning(self, "错误", f"启动简历匹配页面失败：{e}")

    def open_resume_craft(self):
        prefill_params = self._get_streamlit_prefill_params()

        app_path = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "streamlit",
                "resume_craft_agent_app.py",
            )
        )
        app_path = os.path.normpath(app_path)

        if not os.path.exists(app_path):
            QMessageBox.warning(self, "错误", f"未找到 Streamlit 页面：{app_path}")
            return

        base_url = f"http://localhost:{self._resume_craft_streamlit_port}"
        url = self._build_streamlit_url(base_url, prefill_params)

        if self._is_port_open(self._resume_craft_streamlit_port):
            webbrowser.open(url)
            return

        try:
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            env = os.environ.copy()
            env["PYTHONPATH"] = project_root + os.pathsep + env.get("PYTHONPATH", "")
            cmd = [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                app_path,
                "--server.port",
                str(self._resume_craft_streamlit_port),
                "--server.headless",
                "true",
                "--browser.gatherUsageStats",
                "false",
            ]
            self._resume_craft_streamlit_proc = subprocess.Popen(
                cmd,
                cwd=project_root,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            QTimer.singleShot(1800, lambda u=url: webbrowser.open(u))
        except Exception as e:
            QMessageBox.warning(self, "错误", f"启动简历生成页面失败：{e}")

    def open_cover_letter(self):
        prefill_params = self._get_streamlit_prefill_params()

        app_path = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "streamlit",
                "cover_letter_agent_app.py",
            )
        )
        app_path = os.path.normpath(app_path)

        if not os.path.exists(app_path):
            QMessageBox.warning(self, "错误", f"未找到 Streamlit 页面：{app_path}")
            return

        base_url = f"http://localhost:{self._cover_letter_streamlit_port}"
        url = self._build_streamlit_url(base_url, prefill_params)

        if self._is_port_open(self._cover_letter_streamlit_port):
            webbrowser.open(url)
            return

        try:
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            env = os.environ.copy()
            env["PYTHONPATH"] = project_root + os.pathsep + env.get("PYTHONPATH", "")
            cmd = [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                app_path,
                "--server.port",
                str(self._cover_letter_streamlit_port),
                "--server.headless",
                "true",
                "--browser.gatherUsageStats",
                "false",
            ]
            self._cover_letter_streamlit_proc = subprocess.Popen(
                cmd,
                cwd=project_root,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            QTimer.singleShot(1800, lambda u=url: webbrowser.open(u))
        except Exception as e:
            QMessageBox.warning(self, "错误", f"启动求职信页面失败：{e}")

    def _get_streamlit_prefill_params(self):
        ok, profile = self.api_client.get_profile()
        if ok and isinstance(profile, dict):
            self.user_data.update(profile)

        role = (self.user_data.get("target_role") or self.user_data.get("job_intention") or "").strip()
        jd_text = (self.user_data.get("target_jd") or "").strip()
        resume_path = (self.user_data.get("resume_path") or "").strip()
        has_resume = bool(self.user_data.get("has_resume"))

        if not role or not jd_text:
            return {}

        prefill_file = self._create_streamlit_prefill_file(role, jd_text, resume_path, has_resume)
        if prefill_file:
            return {"profile_source": "saved", "prefill_file": prefill_file}
        params = {"profile_source": "saved", "target_role": role, "target_jd": jd_text}
        if resume_path:
            params["resume_path"] = resume_path
        if has_resume:
            params["has_resume"] = "1"
        return params

    @staticmethod
    def _create_streamlit_prefill_file(target_role, target_jd, resume_path="", has_resume=False):
        payload = {
            "target_role": (target_role or "").strip(),
            "target_jd": (target_jd or "").strip(),
            "resume_path": (resume_path or "").strip(),
            "has_resume": bool(has_resume),
        }
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False, suffix=".json") as tmp:
                json.dump(payload, tmp, ensure_ascii=False)
                return tmp.name
        except Exception:
            return ""

    @staticmethod
    def _build_streamlit_url(base_url, query_params):
        params = {k: v for k, v in (query_params or {}).items() if v}
        if not params:
            return base_url
        return f"{base_url}?{urlencode(params)}"

    @staticmethod
    def _is_port_open(port):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.4)
        try:
            return sock.connect_ex(("127.0.0.1", port)) == 0
        finally:
            sock.close()
