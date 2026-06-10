from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QTextEdit,
    QVBoxLayout,
)


class SkillWorker(QThread):
    stage_changed = pyqtSignal(str, int)
    finished_signal = pyqtSignal(bool, object)

    def __init__(self, run_callable, stages):
        super().__init__()
        self.run_callable = run_callable
        self.stages = stages or []

    def run(self):
        try:
            if self.stages:
                self.stage_changed.emit(self.stages[0], 10)
            self.msleep(180)
            if len(self.stages) > 1:
                self.stage_changed.emit(self.stages[1], 35)
            self.msleep(180)
            if len(self.stages) > 2:
                self.stage_changed.emit(self.stages[2], 60)

            ok, result = self.run_callable()
            self.stage_changed.emit("处理完成，正在渲染结果...", 95)
            self.finished_signal.emit(ok, result)
        except Exception as e:
            self.finished_signal.emit(False, str(e))


class CareerForgeDialogBase(QDialog):
    def __init__(self, api_client, title, subtitle, action_text, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self.worker = None
        self.setWindowTitle(title)
        self.resize(980, 760)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        header = QFrame()
        header.setObjectName("headerCard")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 18, 20, 18)
        header_layout.setSpacing(6)

        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("pageSubtitle")
        subtitle_label.setWordWrap(True)
        header_layout.addWidget(title_label)
        header_layout.addWidget(subtitle_label)
        root.addWidget(header)

        body = QGridLayout()
        body.setHorizontalSpacing(16)
        body.setVerticalSpacing(12)

        form_card = QFrame()
        form_card.setObjectName("panelCard")
        self.form_layout = QVBoxLayout(form_card)
        self.form_layout.setContentsMargins(16, 16, 16, 16)
        self.form_layout.setSpacing(10)
        body.addWidget(form_card, 0, 0)

        result_card = QFrame()
        result_card.setObjectName("panelCard")
        result_layout = QVBoxLayout(result_card)
        result_layout.setContentsMargins(16, 16, 16, 16)
        result_layout.setSpacing(10)

        process_title = QLabel("生成过程")
        process_title.setObjectName("panelTitle")
        result_layout.addWidget(process_title)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        result_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("等待开始")
        self.status_label.setObjectName("statusLabel")
        result_layout.addWidget(self.status_label)

        self.process_list = QListWidget()
        self.process_list.setObjectName("processList")
        self.process_list.setMinimumHeight(120)
        result_layout.addWidget(self.process_list)

        result_title = QLabel("生成结果")
        result_title.setObjectName("panelTitle")
        result_layout.addWidget(result_title)

        self.result_view = QTextEdit()
        self.result_view.setReadOnly(True)
        self.result_view.setObjectName("resultView")
        result_layout.addWidget(self.result_view)

        body.addWidget(result_card, 0, 1)
        body.setColumnStretch(0, 1)
        body.setColumnStretch(1, 1)
        root.addLayout(body)

        actions = QHBoxLayout()
        actions.addStretch()
        self.cancel_btn = QPushButton("关闭")
        self.cancel_btn.setObjectName("secondaryButton")
        self.cancel_btn.clicked.connect(self.reject)
        self.run_btn = QPushButton(action_text)
        self.run_btn.setObjectName("primaryButton")
        self.run_btn.clicked.connect(self.on_run_clicked)
        actions.addWidget(self.cancel_btn)
        actions.addWidget(self.run_btn)
        root.addLayout(actions)

        self.build_form()
        self.apply_styles()

    def apply_styles(self):
        self.setStyleSheet(
            """
            QDialog { background-color: #f3f4f6; }
            QFrame#headerCard {
                background-color: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 12px;
            }
            QFrame#panelCard {
                background-color: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 12px;
            }
            QLabel#pageTitle {
                font-size: 24px;
                font-weight: 800;
                color: #111827;
            }
            QLabel#pageSubtitle {
                font-size: 14px;
                color: #6b7280;
            }
            QLabel#panelTitle {
                font-size: 15px;
                font-weight: 700;
                color: #111827;
            }
            QLabel#statusLabel {
                font-size: 12px;
                color: #3b82f6;
                font-weight: 600;
            }
            QLineEdit, QTextEdit, QComboBox {
                border: 1px solid #d1d5db;
                border-radius: 8px;
                background-color: #f9fafb;
                color: #111827;
                font-size: 13px;
                padding: 8px;
            }
            QTextEdit#resultView {
                background-color: #f8fafc;
                border: 1px solid #cbd5e1;
                font-size: 13px;
                line-height: 1.5;
            }
            QListWidget#processList {
                border: 1px solid #d1d5db;
                border-radius: 8px;
                background-color: #f9fafb;
                font-size: 12px;
            }
            QProgressBar {
                border: 1px solid #d1d5db;
                border-radius: 6px;
                background-color: #eef2ff;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #3b82f6;
                border-radius: 5px;
            }
            QPushButton {
                border-radius: 8px;
                padding: 9px 18px;
                font-weight: 600;
                font-size: 13px;
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
                border: 1px solid #d1d5db;
                color: #374151;
            }
            QPushButton#secondaryButton:hover {
                background-color: #f9fafb;
            }
            """
        )

    def add_form_label(self, text):
        label = QLabel(text)
        label.setStyleSheet("font-size: 13px; font-weight: 700; color: #374151;")
        self.form_layout.addWidget(label)

    def append_process(self, text):
        self.process_list.addItem(text)
        self.process_list.scrollToBottom()

    def on_stage_changed(self, stage, progress):
        self.status_label.setText(stage)
        self.progress_bar.setValue(progress)
        self.append_process(stage)

    def on_finished(self, ok, result):
        self.run_btn.setEnabled(True)
        self.progress_bar.setValue(100 if ok else 0)
        if not ok:
            QMessageBox.warning(self, "请求失败", str(result))
            return
        self.render_result(result)
        self.append_process("结果展示完成")

    def on_run_clicked(self):
        payload = self.collect_payload()
        if payload is None:
            return
        self.result_view.clear()
        self.process_list.clear()
        self.run_btn.setEnabled(False)
        self.progress_bar.setValue(5)
        self.status_label.setText("任务已启动")
        self.start_worker(payload)

    def build_form(self):
        raise NotImplementedError

    def collect_payload(self):
        raise NotImplementedError

    def start_worker(self, payload):
        raise NotImplementedError

    def render_result(self, result):
        raise NotImplementedError


class ResumeMatchDialog(CareerForgeDialogBase):
    def __init__(self, api_client, parent=None):
        super().__init__(
            api_client=api_client,
            title="简历匹配分析",
            subtitle="对简历与 JD 进行多维评分、差距分析与优化建议输出。",
            action_text="开始匹配分析",
            parent=parent,
        )

    def build_form(self):
        self.add_form_label("目标岗位（可选）")
        self.target_role = QLineEdit()
        self.target_role.setPlaceholderText("例如：AI 产品经理 / Python 后端工程师")
        self.form_layout.addWidget(self.target_role)

        self.add_form_label("简历内容")
        self.resume_input = QTextEdit()
        self.resume_input.setPlaceholderText("粘贴简历文本（支持中文/英文）")
        self.resume_input.setMinimumHeight(190)
        self.form_layout.addWidget(self.resume_input)

        self.add_form_label("岗位 JD")
        self.jd_input = QTextEdit()
        self.jd_input.setPlaceholderText("粘贴岗位职责、任职要求等 JD 内容")
        self.jd_input.setMinimumHeight(190)
        self.form_layout.addWidget(self.jd_input)

    def collect_payload(self):
        resume_text = self.resume_input.toPlainText().strip()
        jd_text = self.jd_input.toPlainText().strip()
        target_role = self.target_role.text().strip()
        if not resume_text:
            QMessageBox.warning(self, "缺少信息", "请先填写简历内容。")
            return None
        if not jd_text:
            QMessageBox.warning(self, "缺少信息", "请先填写岗位 JD。")
            return None
        return {
            "resume_text": resume_text,
            "jd_text": jd_text,
            "target_role": target_role,
        }

    def start_worker(self, payload):
        stages = [
            "加载匹配分析引擎",
            "解析简历与 JD 上下文",
            "计算匹配评分并生成建议",
        ]
        self.worker = SkillWorker(
            lambda: self.api_client.run_resume_match(
                payload["resume_text"], payload["jd_text"], payload["target_role"]
            ),
            stages,
        )
        self.worker.stage_changed.connect(self.on_stage_changed)
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.start()

    def render_result(self, response):
        result = (response or {}).get("result", {})
        dims = result.get("dimension_scores") or []
        lines = [
            f"整体匹配度：{result.get('overall_score', '-')}/100",
            f"匹配等级：{result.get('match_level', '-')}",
            f"总结：{result.get('summary', '')}",
            "",
            "【维度评分】",
        ]
        for item in dims:
            lines.append(f"- {item.get('name', '维度')}：{item.get('score', '-')}/100")
            if item.get("highlight"):
                lines.append(f"  亮点：{item.get('highlight')}")
            if item.get("gap"):
                lines.append(f"  差距：{item.get('gap')}")
            if item.get("advice"):
                lines.append(f"  建议：{item.get('advice')}")
        if result.get("critical_missing"):
            lines.append("")
            lines.append("【关键缺失项】")
            lines.extend([f"- {x}" for x in result.get("critical_missing", [])])
        if result.get("optimization_suggestions"):
            lines.append("")
            lines.append("【优化建议】")
            lines.extend([f"- {x}" for x in result.get("optimization_suggestions", [])])
        if result.get("optimized_resume_markdown"):
            lines.append("")
            lines.append("【优化后简历（Markdown）】")
            lines.append(result.get("optimized_resume_markdown"))
        self.result_view.setPlainText("\n".join(lines))


class ResumeCraftDialog(CareerForgeDialogBase):
    def __init__(self, api_client, parent=None):
        super().__init__(
            api_client=api_client,
            title="简历生成",
            subtitle="生成可投递的结构化简历内容，并给出排版风格建议。",
            action_text="开始生成简历",
            parent=parent,
        )

    def build_form(self):
        top = QHBoxLayout()
        left = QVBoxLayout()
        right = QVBoxLayout()

        left_label = QLabel("目标岗位")
        left_label.setStyleSheet("font-size: 13px; font-weight: 700; color: #374151;")
        self.target_role = QLineEdit()
        self.target_role.setPlaceholderText("例如：AI 产品运营")
        left.addWidget(left_label)
        left.addWidget(self.target_role)

        right_label = QLabel("语言")
        right_label.setStyleSheet("font-size: 13px; font-weight: 700; color: #374151;")
        self.language = QComboBox()
        self.language.addItems(["zh", "en"])
        right.addWidget(right_label)
        right.addWidget(self.language)

        top.addLayout(left)
        top.addLayout(right)
        self.form_layout.addLayout(top)

        self.add_form_label("模板风格")
        self.template = QComboBox()
        self.template.addItems(
            [
                "",
                "Editorial",
                "Minimal",
                "Sidebar Navy",
                "Sidebar Dark",
                "Dark Header",
                "Clean Teal",
                "Elegant",
            ]
        )
        self.form_layout.addWidget(self.template)

        self.add_form_label("简历基础内容")
        self.resume_input = QTextEdit()
        self.resume_input.setPlaceholderText("粘贴您已有的简历内容，或先填一个简要版本。")
        self.resume_input.setMinimumHeight(170)
        self.form_layout.addWidget(self.resume_input)

        self.add_form_label("优化目标（可选）")
        self.goal_input = QTextEdit()
        self.goal_input.setPlaceholderText("例如：突出项目成果、压缩到两页内、强调数据分析能力。")
        self.goal_input.setMinimumHeight(100)
        self.form_layout.addWidget(self.goal_input)

    def collect_payload(self):
        resume_text = self.resume_input.toPlainText().strip()
        if not resume_text:
            QMessageBox.warning(self, "缺少信息", "请先填写简历基础内容。")
            return None
        return {
            "resume_text": resume_text,
            "target_role": self.target_role.text().strip(),
            "language": self.language.currentText().strip(),
            "template": self.template.currentText().strip(),
            "optimization_goal": self.goal_input.toPlainText().strip(),
        }

    def start_worker(self, payload):
        stages = [
            "加载简历生成引擎",
            "整合简历信息与模板偏好",
            "输出结构化简历草案",
        ]
        self.worker = SkillWorker(
            lambda: self.api_client.run_resume_craft(
                payload["resume_text"],
                payload["target_role"],
                payload["language"],
                payload["template"],
                payload["optimization_goal"],
            ),
            stages,
        )
        self.worker.stage_changed.connect(self.on_stage_changed)
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.start()

    def render_result(self, response):
        result = (response or {}).get("result", {})
        lines = [
            f"标题：{result.get('title', '')}",
            f"概述：{result.get('profile_summary', '')}",
            "",
            "【版式建议】",
        ]
        lines.extend([f"- {x}" for x in result.get("style_advice", [])])
        if result.get("sections"):
            lines.append("")
            lines.append("【结构化章节】")
            for sec in result.get("sections", []):
                lines.append(f"- {sec.get('title', '章节')}")
                content = sec.get("content_markdown", "")
                if content:
                    lines.append(content)
                    lines.append("")
        if result.get("resume_markdown"):
            lines.append("【完整简历（Markdown）】")
            lines.append(result.get("resume_markdown"))
        if result.get("next_actions"):
            lines.append("")
            lines.append("【下一步建议】")
            lines.extend([f"- {x}" for x in result.get("next_actions", [])])
        self.result_view.setPlainText("\n".join(lines))


class CoverLetterDialog(CareerForgeDialogBase):
    def __init__(self, api_client, parent=None):
        super().__init__(
            api_client=api_client,
            title="求职信撰写",
            subtitle="生成邮件版求职信或招聘平台打招呼消息。",
            action_text="开始生成求职信",
            parent=parent,
        )

    def build_form(self):
        row = QHBoxLayout()

        scenario_col = QVBoxLayout()
        scenario_label = QLabel("场景")
        scenario_label.setStyleSheet("font-size: 13px; font-weight: 700; color: #374151;")
        self.scenario = QComboBox()
        self.scenario.addItems(["email", "chat"])
        scenario_col.addWidget(scenario_label)
        scenario_col.addWidget(self.scenario)

        lang_col = QVBoxLayout()
        lang_label = QLabel("语言")
        lang_label.setStyleSheet("font-size: 13px; font-weight: 700; color: #374151;")
        self.language = QComboBox()
        self.language.addItems(["zh", "en"])
        lang_col.addWidget(lang_label)
        lang_col.addWidget(self.language)

        company_col = QVBoxLayout()
        company_label = QLabel("公司名（可选）")
        company_label.setStyleSheet("font-size: 13px; font-weight: 700; color: #374151;")
        self.company = QLineEdit()
        self.company.setPlaceholderText("例如：DeepVision AI")
        company_col.addWidget(company_label)
        company_col.addWidget(self.company)

        row.addLayout(scenario_col)
        row.addLayout(lang_col)
        row.addLayout(company_col)
        self.form_layout.addLayout(row)

        self.add_form_label("简历内容")
        self.resume_input = QTextEdit()
        self.resume_input.setPlaceholderText("粘贴简历文本。")
        self.resume_input.setMinimumHeight(170)
        self.form_layout.addWidget(self.resume_input)

        self.add_form_label("岗位 JD")
        self.jd_input = QTextEdit()
        self.jd_input.setPlaceholderText("粘贴目标岗位 JD。")
        self.jd_input.setMinimumHeight(170)
        self.form_layout.addWidget(self.jd_input)

    def collect_payload(self):
        resume_text = self.resume_input.toPlainText().strip()
        jd_text = self.jd_input.toPlainText().strip()
        if not resume_text:
            QMessageBox.warning(self, "缺少信息", "请先填写简历内容。")
            return None
        if not jd_text:
            QMessageBox.warning(self, "缺少信息", "请先填写岗位 JD。")
            return None
        return {
            "resume_text": resume_text,
            "jd_text": jd_text,
            "scenario": self.scenario.currentText().strip(),
            "language": self.language.currentText().strip(),
            "company_name": self.company.text().strip(),
        }

    def start_worker(self, payload):
        stages = [
            "加载求职信撰写引擎",
            "提取简历亮点并匹配 JD",
            "生成求职信与打招呼消息",
        ]
        self.worker = SkillWorker(
            lambda: self.api_client.run_cover_letter(
                payload["resume_text"],
                payload["jd_text"],
                payload["scenario"],
                payload["language"],
                payload["company_name"],
            ),
            stages,
        )
        self.worker.stage_changed.connect(self.on_stage_changed)
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.start()

    def render_result(self, response):
        result = (response or {}).get("result", {})
        lines = [
            f"场景：{result.get('scenario', '')}",
            f"语言：{result.get('language', '')}",
            "",
            "【邮件版求职信】",
            result.get("cover_letter", ""),
            "",
            "【招聘平台打招呼】",
            result.get("greeting_message", ""),
        ]
        if result.get("key_points"):
            lines.append("")
            lines.append("【核心卖点】")
            lines.extend([f"- {x}" for x in result.get("key_points", [])])
        if result.get("tailoring_notes"):
            lines.append("")
            lines.append("【定制说明】")
            lines.extend([f"- {x}" for x in result.get("tailoring_notes", [])])
        self.result_view.setPlainText("\n".join(lines))
