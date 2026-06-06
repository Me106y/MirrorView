"""
AI Interviewer Avatar Widget (Light Theme)
===========================================
Matches MirrorView's white/minimal design language.

Colors: white bg, blue accent (#3b82f6), light gray (#f3f4f6)
"""

import math

from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QFrame
from PyQt5.QtCore import Qt, QTimer, QRectF, pyqtSignal, QPointF
from PyQt5.QtGui import (
    QPainter, QPen, QBrush, QColor, QRadialGradient, QFont, QFontMetrics
)


class WaveBar(QWidget):
    """Lightweight waveform — white bg with blue bars."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._amp = 0.0
        self._target = 0.0
        self._phase = 0.0
        self.setFixedHeight(28)

    def set_amplitude(self, val: float):
        self._target = max(0.0, min(1.0, val))

    def tick(self):
        self._amp += (self._target - self._amp) * 0.25
        self._phase += 0.3
        if self._amp > 0.001 or self._target > 0:
            self.update()

    def paintEvent(self, event):
        if self._amp < 0.01 and self._target < 0.01:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        n, bw, sp = 5, max(3, w / 18), max(3, w / 18) * 1.6
        total_w = n * sp
        sx = cx - total_w / 2
        for i in range(n):
            a = self._amp * (0.3 + 0.7 * math.sin(i * 1.2))
            bh = max(3, h * 0.12 + h * 0.75 * a * (math.sin(self._phase + i * 0.9) * 0.5 + 0.5))
            x = sx + i * sp
            y = cy - bh / 2
            c = QColor(59, 130, 246, 100 + int(a * 140))
            p.setBrush(QBrush(c))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(x, y, bw, bh), bw / 2, bw / 2)
        p.end()


class AvatarRing(QWidget):
    """Circular avatar — white bg, blue accent ring."""

    COLORS = {
        "idle":       QColor(59, 130, 246),
        "listening":  QColor(16, 185, 129),
        "thinking":   QColor(245, 158, 11),
        "speaking":   QColor(99, 102, 241),
    }

    def __init__(self, size=140, parent=None):
        super().__init__(parent)
        self._size = size
        self._state = "idle"
        self._pulse = 0.0
        self._glow = 0.0
        self.setFixedSize(size + 36, size + 36)

    def set_state(self, s):
        self._state = s

    def tick(self):
        if self._state == "speaking":
            self._pulse = (self._pulse + 0.12) % (2 * math.pi)
            self._glow += (14.0 - self._glow) * 0.1
        elif self._state == "thinking":
            self._pulse = (self._pulse + 0.06) % (2 * math.pi)
            self._glow += (5.0 - self._glow) * 0.1
        elif self._state == "listening":
            self._pulse = (self._pulse + 0.08) % (2 * math.pi)
            self._glow += (7.0 - self._glow) * 0.1
        else:
            self._glow *= 0.9
            self._pulse = (self._pulse + 0.02) % (2 * math.pi)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        r = self._size / 2
        bc = self.COLORS.get(self._state, self.COLORS["idle"])

        # Glow ring
        for i in range(2):
            gr = r + 5 + i * 5 + self._glow * 0.2 * math.sin(self._pulse + i)
            glow_alpha = max(0, int(40 + self._glow * 5) - i * 30)
            gc = QColor(bc.red(), bc.green(), bc.blue(), glow_alpha)
            grad = QRadialGradient(QPointF(cx, cy), gr)
            grad.setColorAt(0.7, gc)
            grad.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setBrush(QBrush(grad))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(cx, cy), gr, gr)

        # Main circle — white bg
        bg_grad = QRadialGradient(QPointF(cx - 5, cy - 5), r)
        bg_grad.setColorAt(0.0, QColor(255, 255, 255))
        bg_grad.setColorAt(0.9, QColor(245, 247, 250))
        bg_grad.setColorAt(1.0, QColor(240, 243, 247))
        p.setBrush(QBrush(bg_grad))
        p.setPen(QPen(QColor(209, 213, 219), 2))
        p.drawEllipse(QPointF(cx, cy), r, r)

        # Eyes
        p.setPen(Qt.NoPen)
        eye_y = cy - r * 0.12
        es = r * 0.28
        er = r * 0.06
        ec = QColor(59, 130, 246, 180)
        p.setBrush(QBrush(ec))
        p.drawEllipse(QPointF(cx - es, eye_y), er, er)
        p.drawEllipse(QPointF(cx + es, eye_y), er, er)

        # Mouth
        mouth_y = cy + r * 0.25
        mw = r * 0.3
        if self._state == "speaking":
            mh = 6 + 8 * abs(math.sin(self._pulse * 2.5))
        elif self._state == "listening":
            mh = 3 + 2 * abs(math.sin(self._pulse))
        else:
            mh = 3
        mc = QColor(bc.red(), bc.green(), bc.blue(), 140)
        p.setBrush(QBrush(mc))
        p.drawRoundedRect(QRectF(cx - mw, mouth_y - mh / 2, mw * 2, mh), mh / 2, mh / 2)

        # Emoji icon
        font = QFont("Apple Color Emoji", int(r * 0.4))
        p.setFont(font)
        p.setPen(QColor(30, 41, 59, 140))
        icon = {"idle": "🤖", "listening": "👂", "thinking": "💭", "speaking": "🗣️"}.get(self._state, "🤖")
        fm = QFontMetrics(font)
        tw = fm.horizontalAdvance(icon)
        p.drawText(int(cx - tw / 2), int(cy + fm.height() / 3), icon)
        p.end()


class AIAvatarWidget(QFrame):
    """Complete AI avatar widget — white card style."""

    subtitle_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("aiAvatarCard")
        self._state = "idle"
        self._subtitle_full = ""
        self._subtitle_pos = 0

        self._build()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(66)

    def _build(self):
        l = QVBoxLayout(self)
        l.setContentsMargins(16, 20, 16, 16)
        l.setSpacing(6)
        l.setAlignment(Qt.AlignCenter)

        self.ring = AvatarRing(size=130, parent=self)
        l.addWidget(self.ring, 0, Qt.AlignCenter)

        self.name_lbl = QLabel("AI Interviewer")
        self.name_lbl.setAlignment(Qt.AlignCenter)
        self.name_lbl.setStyleSheet("font-size:18px; font-weight:700; color:#111827;")
        l.addWidget(self.name_lbl)

        self.status_lbl = QLabel("Ready")
        self.status_lbl.setAlignment(Qt.AlignCenter)
        self.status_lbl.setStyleSheet("font-size:12px; color:#6b7280;")
        l.addWidget(self.status_lbl)

        self.wavebar = WaveBar(self)
        l.addWidget(self.wavebar)

        self.sub_lbl = QLabel("")
        self.sub_lbl.setAlignment(Qt.AlignCenter)
        self.sub_lbl.setWordWrap(True)
        self.sub_lbl.setStyleSheet(
            "font-size:14px; color:#374151; background:#f9fafb;"
            "border:1px solid #e5e7eb; border-radius:10px;"
            "padding:10px 14px; min-height:44px;")
        l.addWidget(self.sub_lbl)
        l.addStretch()

        self.setStyleSheet("""
            QFrame#aiAvatarCard {
                background:#ffffff;
                border-radius:12px;
                border:1px solid #e5e7eb;
            }
        """)

    def _tick(self):
        self.ring.tick()
        self.wavebar.tick()
        if self._subtitle_full and self._subtitle_pos < len(self._subtitle_full):
            self._subtitle_pos = min(self._subtitle_pos + 2, len(self._subtitle_full))
            partial = self._subtitle_full[:self._subtitle_pos]
            self.sub_lbl.setText(
                f'<span style="color:#111827">{partial}</span>'
                f'<span style="color:#9ca3af">▌</span>')

    # ── Public API ─────────────────────────────────

    def set_state(self, s: str):
        self._state = s
        self.ring.set_state(s)
        if s == "speaking":
            self.wavebar.set_amplitude(0.8)
            self.status_lbl.setText("Speaking...")
            self.status_lbl.setStyleSheet("font-size:12px; color:#6366f1;")
        elif s == "listening":
            self.wavebar.set_amplitude(0.4)
            self.status_lbl.setText("Listening...")
            self.status_lbl.setStyleSheet("font-size:12px; color:#10b981;")
        elif s == "thinking":
            self.wavebar.set_amplitude(0.2)
            self.status_lbl.setText("Thinking...")
            self.status_lbl.setStyleSheet("font-size:12px; color:#f59e0b;")
        else:
            self.wavebar.set_amplitude(0.0)
            self.status_lbl.setText("Ready")
            self.status_lbl.setStyleSheet("font-size:12px; color:#6b7280;")

    def set_subtitle(self, text: str):
        self._subtitle_full = text
        self._subtitle_pos = 0
        self.subtitle_changed.emit(text)

    def clear_subtitle(self):
        self._subtitle_full = ""
        self._subtitle_pos = 0
        self.sub_lbl.setText("")

    def set_name(self, name: str):
        self.name_lbl.setText(name)
