"""
Voice Interview Window (Light Theme)
=====================================
Matches MirrorView's white/minimal design:
- bg: #f3f4f6  |  cards: #ffffff + border #e5e7eb
- primary: #3b82f6  |  text: #111827 / #6b7280
"""

import os, threading
import numpy as np

from PyQt5.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QFrame, QDialog, QSplitter, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap

from client.ui.ai_avatar_widget import AIAvatarWidget
from client.ui.mic_level_widget import MicLevelWidget
from client.ui.stt_sherpa import STTWorkerSherpa  # Sherpa-ONNX streaming STT
from utils.logger_handler import logger

# ── Optional imports ──
try:
    from client.core.audio_player import AudioPlayer
    from client.core.tts_client import TTSClient; _VOICE = True
except ImportError: _VOICE = False

_BOSON_KEY = os.environ.get("BOSON_API_KEY", "")
_TTS_READY = bool(_BOSON_KEY)


# ═══════════════════════════════════════════════════════
# Lightweight Camera (15fps)
# ═══════════════════════════════════════════════════════

class LightweightCamera(QThread):
    frame_ready = pyqtSignal(QImage)

    def __init__(self, camera_index=0):
        super().__init__()
        self._camera_index = camera_index
        self._running = True

    def run(self):
        import cv2
        for idx in (self._camera_index, 0, 1):
            cap = cv2.VideoCapture(idx)
            if cap.isOpened(): break
        if not cap.isOpened(): return
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
        cap.set(cv2.CAP_PROP_FPS, 15)
        while self._running:
            ret, frame = cap.read()
            if ret:
                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                qimg = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888)
                self.frame_ready.emit(qimg.copy())
            self.msleep(66)
        cap.release()

    def stop(self):
        self._running = False; self.wait(1000)


# ═══════════════════════════════════════════════════════
# TTS Playback
# ═══════════════════════════════════════════════════════

class TTSPlaybackThread(QThread):
    started = pyqtSignal(); finished = pyqtSignal(); error = pyqtSignal(str)

    def __init__(self, tts_client, text, voice="default"):
        super().__init__()
        self._client = tts_client; self._text = text; self._voice = voice; self._cancelled = False

    def run(self):
        if not self._client: self.error.emit("No TTS client"); return
        try:
            player = AudioPlayer(volume=0.8); player.start(); self.started.emit()
            for chunk in self._client.stream_tts(text=self._text, voice=self._voice, mode="sentence"):
                if self._cancelled: break
                player.feed(chunk)
            if not self._cancelled: player.finish(); player.wait(timeout=30)
        except Exception as e: self.error.emit(str(e))
        finally: self.finished.emit()

    def cancel(self): self._cancelled = True; self.wait(1000)


# ═══════════════════════════════════════════════════════
# Voice Interview Window (Light Theme)
# ═══════════════════════════════════════════════════════

class VoiceInterviewWindow(QWidget):
    closed = pyqtSignal()

    def __init__(self, api_client, response_data):
        super().__init__()
        self.api_client = api_client
        self.response_data = response_data
        self.interview_id = response_data.get('interview_id')
        self.initial_message = response_data.get('initial_message', '')

        self._tts_enabled = True
        self._stt_worker = None; self._tts_thread = None; self._cam_thread = None

        self._tts_client = None
        if _VOICE and _TTS_READY:
            base = api_client.base_url.replace('/api', '')
            self._tts_client = TTSClient(base_url=base, timeout=60)

        self._build_ui()
        self._start_camera()
        QTimer.singleShot(500, self._greet)

    # ── UI (light theme) ──────────────────────────────

    def _build_ui(self):
        self.setWindowTitle("MirrorView — Voice Interview 🎙️")
        self.resize(1200, 750)
        self.setMinimumSize(900, 600)
        self.setStyleSheet("""
            QWidget { background-color: #f3f4f6; font-family: 'Segoe UI', Arial, sans-serif; }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(10)

        # ── Top split ──
        split = QSplitter(Qt.Horizontal)
        split.setHandleWidth(2)
        split.setStyleSheet("QSplitter::handle { background-color: #e5e7eb; }")

        # ── Camera panel ──
        cam = QFrame()
        cam.setObjectName("card")
        cam.setStyleSheet("""
            QFrame#card { background:#ffffff; border-radius:12px; border:1px solid #e5e7eb; }
        """)
        cl = QVBoxLayout(cam)
        cl.setContentsMargins(12, 12, 12, 8)
        cl.setSpacing(4)

        self.video_label = QLabel("📷")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.video_label.setStyleSheet("background:#000; color:#fff; border-radius:10px; font-size:16px;")
        cl.addWidget(self.video_label, 1)  # stretch factor 1 → fills all available space

        you_lbl = QLabel("You")
        you_lbl.setAlignment(Qt.AlignCenter)
        you_lbl.setFixedHeight(22)
        you_lbl.setStyleSheet("color:#9ca3af; font-size:12px; border:none; background:transparent;")
        cl.addWidget(you_lbl, 0)  # stretch factor 0 → fixed, doesn't grow
        split.addWidget(cam)

        # ── Avatar panel ──
        av = QFrame()
        av.setObjectName("card")
        av.setStyleSheet("QFrame#card { background:#ffffff; border-radius:12px; border:1px solid #e5e7eb; }")
        al = QVBoxLayout(av)
        al.setContentsMargins(0, 0, 0, 0)
        self.avatar = AIAvatarWidget(self)
        self.avatar.set_name("AI Interviewer")
        al.addWidget(self.avatar)
        split.addWidget(av)

        split.setStretchFactor(0, 1); split.setStretchFactor(1, 1)
        split.setSizes([580, 580])
        root.addWidget(split, 1)

        # ── Bottom bar ──
        bar = QFrame()
        bar.setObjectName("controlBar")
        bar.setFixedHeight(72)
        bar.setStyleSheet("""
            QFrame#controlBar {
                background:#ffffff; border-radius:12px; border:1px solid #e5e7eb;
            }
        """)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(14, 6, 14, 6); bl.setSpacing(10)

        # Mic button
        self.mic_btn = QPushButton("🎤  Hold to Speak")
        self.mic_btn.setCursor(Qt.PointingHandCursor)
        self.mic_btn.setFixedHeight(46); self.mic_btn.setMinimumWidth(180)
        self.mic_btn.setStyleSheet("""
            QPushButton { background:#3b82f6; color:#fff; border:none;
            border-radius:23px; padding:10px 28px; font-size:15px; font-weight:700; }
            QPushButton:hover { background:#2563eb; }
        """)
        self.mic_btn.pressed.connect(self._mic_down)
        self.mic_btn.released.connect(self._mic_up)
        bl.addWidget(self.mic_btn)

        # Mic level
        self.mic_meter = MicLevelWidget()
        self.mic_meter.setFixedWidth(150)
        bl.addWidget(self.mic_meter)

        # Pipeline status
        self.pipeline_lbl = QLabel("")
        self.pipeline_lbl.setStyleSheet("color:#3b82f6; font-size:12px; font-weight:600;")
        bl.addWidget(self.pipeline_lbl)

        bl.addStretch()

        # TTS status
        tts_ok = _TTS_READY
        self.tts_status = QLabel("🔊 TTS ready" if tts_ok else "🔇 TTS: no key")
        self.tts_status.setStyleSheet(f"color:{'#10b981' if tts_ok else '#ef4444'}; font-size:11px;")
        bl.addWidget(self.tts_status)

        # TTS toggle
        self.tts_btn = QPushButton("🔊 On" if tts_ok else "🔇 Off")
        self.tts_btn.setCheckable(True); self.tts_btn.setChecked(tts_ok)
        self.tts_btn.setEnabled(tts_ok); self.tts_btn.setCursor(Qt.PointingHandCursor)
        self.tts_btn.setFixedHeight(38)
        self.tts_btn.setStyleSheet("""
            QPushButton { background:#ffffff; border:1px solid #d1d5db; color:#374151;
            border-radius:8px; padding:6px 12px; font-size:12px; font-weight:600; }
            QPushButton:checked { background:#10b981; color:#fff; border-color:#059669; }
        """)
        self.tts_btn.toggled.connect(
            lambda c: [self.tts_btn.setText("🔊 On" if c else "🔇 Off"),
                       setattr(self, '_tts_enabled', c)])
        bl.addWidget(self.tts_btn)

        # End
        end_btn = QPushButton("⏹  End Interview")
        end_btn.setCursor(Qt.PointingHandCursor); end_btn.setFixedHeight(38)
        end_btn.setStyleSheet("""
            QPushButton { background:#ef4444; color:#fff; border:none;
            border-radius:8px; padding:6px 18px; font-size:12px; font-weight:600; }
            QPushButton:hover { background:#dc2626; }
        """)
        end_btn.clicked.connect(self._end_interview)
        bl.addWidget(end_btn)

        root.addWidget(bar)

    # ── Camera ──────────────────────────────────────────

    def _start_camera(self):
        self._cam_thread = LightweightCamera()
        self._cam_thread.frame_ready.connect(self._on_frame)
        self._cam_thread.start()

    def _on_frame(self, qimg):
        self.video_label.setPixmap(
            QPixmap.fromImage(qimg).scaled(
                self.video_label.width(), self.video_label.height(),
                Qt.KeepAspectRatio, Qt.SmoothTransformation))

    # ── Greeting ────────────────────────────────────────

    def _greet(self):
        greeting = self.initial_message or (
            "Hello! Welcome to your mock interview. I'm your AI interviewer. "
            "Let's start — tell me about yourself."
        )
        self.avatar.set_state("speaking")
        self.avatar.set_subtitle(greeting[:200])
        self.pipeline_lbl.setText("🔊 AI speaking...")
        if self._tts_enabled and self._tts_client:
            self._speak(greeting)
        else:
            QTimer.singleShot(2000, lambda: [
                self.avatar.set_state("listening"),
                self.pipeline_lbl.setText("👂 Your turn — hold mic to speak")
            ])

    # ── Mic ─────────────────────────────────────────────

    def _mic_down(self):
        logger.info("[Voice] Mic pressed — Sherpa-ONNX streaming STT")
        self.mic_btn.setText("🔴 Recording... Release to Send")
        self.mic_btn.setStyleSheet(
            self.mic_btn.styleSheet().replace("#3b82f6", "#dc2626").replace("#2563eb", "#b91c1c"))
        self.mic_meter.set_active(True)
        self.avatar.set_state("listening")
        self.pipeline_lbl.setText("👂 Listening...")

        self._stt_worker = STTWorkerSherpa()
        self._stt_worker.partial_result.connect(self._on_stt_partial)
        self._stt_worker.final_result.connect(self._on_stt_ok)
        self._stt_worker.mic_level.connect(self.mic_meter.set_level)
        self._stt_worker.error.connect(self._on_stt_err)
        self._stt_worker.start()

    def _mic_up(self):
        logger.info("[Voice] Mic released — finalizing")
        self.mic_meter.set_active(False)
        self.mic_btn.setText("🎤  Hold to Speak")
        self.mic_btn.setStyleSheet(
            self.mic_btn.styleSheet().replace("#dc2626", "#3b82f6").replace("#b91c1c", "#2563eb"))
        if self._stt_worker and self._stt_worker.isRunning():
            self._stt_worker.stop()

    def _on_stt_partial(self, text):
        """Live partial results — show immediately during recording."""
        self.pipeline_lbl.setText(f"📝 {text[:60]}...")
        self.avatar.set_subtitle(f'You: "{text}"')

    def _on_stt_ok(self, text):
        logger.info(f"[Voice] STT final: {text[:80]}")
        self.pipeline_lbl.setText(f"📝 {text[:50]}...")
        self.avatar.set_subtitle(f'You: "{text}"')
        self._send_to_ai(text)

    def _on_stt_err(self, err):
        logger.warning(f"[Voice] STT FAIL: {err}")
        self.pipeline_lbl.setText(f"⚠️ {err[:50]}")
        self.avatar.set_state("listening")

    # ── AI ──────────────────────────────────────────────

    def _send_to_ai(self, text):
        self.avatar.set_state("thinking")
        self.pipeline_lbl.setText("💭 AI thinking...")
        logger.info(f"[Voice] Sending to AI: {text[:50]}...")

        class Streamer(QThread):
            chunk = pyqtSignal(str); done = pyqtSignal(str); err = pyqtSignal(str)

            def __init__(self, c, iid, msg):
                super().__init__()
                self.c, self.iid, self.msg = c, iid, msg

            def run(self):
                acc = []
                def cb(t): acc.append(t); self.chunk.emit(t)
                try:
                    ok, result = self.c.send_message(self.iid, self.msg, stream=True, callback=cb)
                    full = ''.join(acc)
                    logger.info(f"[Voice] send_message result: ok={ok}, len(full)={len(full)}")
                    if ok and full.strip():
                        self.done.emit(full)
                    elif ok:
                        # Server returned success but no content — fallback text
                        logger.warning("[Voice] AI returned empty response")
                        self.done.emit("I see. Let me ask you another question — could you tell me more about your experience?")
                    else:
                        self.err.emit(str(result))
                except Exception as e:
                    logger.error(f"[Voice] Streamer exception: {e}", exc_info=True)
                    self.err.emit(str(e))

        self._ai_worker = Streamer(self.api_client, self.interview_id, text)
        self._ai_worker.chunk.connect(lambda c: None)
        self._ai_worker.done.connect(self._on_ai_done)
        self._ai_worker.err.connect(self._on_ai_err)
        self._ai_worker.start()

    def _on_ai_done(self, full):
        self.avatar.set_state("speaking")
        self.avatar.set_subtitle(full[:250])
        self.pipeline_lbl.setText("🔊 Speaking via TTS...")
        if self._tts_enabled and self._tts_client and full.strip():
            self._speak(full)
        else:
            QTimer.singleShot(1500, self._ready_for_input)

    def _on_ai_err(self, err):
        logger.error(f"[Voice] AI error: {err}")
        self.pipeline_lbl.setText(f"⚠️ AI error: {err[:40]}")
        self.avatar.set_subtitle(f"⚠️ Error: {err[:100]}")
        # Fallback: use TTS to inform the user
        fallback = "Sorry, I encountered an issue. Let me try again — what are your key technical strengths?"
        self.avatar.set_state("speaking")
        if self._tts_enabled and self._tts_client: self._speak(fallback)
        else: QTimer.singleShot(2000, self._ready_for_input)

    # ── TTS ─────────────────────────────────────────────

    def _speak(self, text):
        if self._tts_thread and self._tts_thread.isRunning(): self._tts_thread.cancel()
        self.tts_status.setText("🔊 Speaking..."); self.tts_status.setStyleSheet("color:#f59e0b; font-size:11px;")
        self._tts_thread = TTSPlaybackThread(self._tts_client, text)
        self._tts_thread.started.connect(
            lambda: [self.avatar.set_state("speaking"),
                     self.tts_status.setText("🔊 Playing"),
                     self.tts_status.setStyleSheet("color:#10b981; font-size:11px;")])
        self._tts_thread.finished.connect(self._on_tts_done)
        self._tts_thread.error.connect(
            lambda e: [self.tts_status.setText(f"🔇 Error"), self.tts_status.setStyleSheet("color:#ef4444; font-size:11px;"),
                       self._ready_for_input()])
        self._tts_thread.start()

    def _on_tts_done(self):
        self.tts_status.setText("🔊 Ready"); self.tts_status.setStyleSheet("color:#10b981; font-size:11px;")
        self._ready_for_input()

    def _ready_for_input(self):
        self.avatar.set_state("listening")
        self.pipeline_lbl.setText("👂 Your turn — hold mic to speak")

    # ── End ─────────────────────────────────────────────

    def _end_interview(self):
        if self._cam_thread: self._cam_thread.stop()
        if self._tts_thread: self._tts_thread.cancel()
        try: self.api_client.finish_interview(self.interview_id)
        except Exception: pass
        dlg = QDialog(self)
        dlg.setWindowTitle("Complete"); dlg.setFixedSize(420, 240)
        dlg.setStyleSheet("""
            QDialog { background:#f3f4f6; }
            QFrame#fbCard { background:#ffffff; border-radius:16px; border:1px solid #e5e7eb; }
        """)
        l = QVBoxLayout(dlg); l.setContentsMargins(0,0,0,0)
        card = QFrame(); card.setObjectName("fbCard"); cl = QVBoxLayout(card)
        cl.setContentsMargins(30,30,30,30); cl.setSpacing(16)
        t = QLabel("✅  Interview Complete!")
        t.setStyleSheet("color:#10b981; font-size:20px; font-weight:800;"); t.setAlignment(Qt.AlignCenter)
        cl.addWidget(t)
        b = QPushButton("Back to Home")
        b.setStyleSheet("""
            QPushButton { background:#3b82f6; color:#fff; border:none;
            border-radius:10px; padding:12px 32px; font-size:15px; font-weight:700; }
            QPushButton:hover { background:#2563eb; }
        """); b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(lambda: (dlg.accept(), self.close()))
        cl.addWidget(b, 0, Qt.AlignCenter)
        l.addWidget(card); dlg.exec_()

    def closeEvent(self, event):
        if self._cam_thread: self._cam_thread.stop()
        if self._tts_thread: self._tts_thread.cancel()
        self.closed.emit()
        super().closeEvent(event)
