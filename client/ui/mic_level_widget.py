"""
Microphone Input Level Meter
=============================
Real-time VU meter showing microphone input volume.

Visual: horizontal bar that fills green→yellow→red
        with a peak hold indicator.

Usage:
    meter = MicLevelWidget()
    meter.set_level(0.0)   # 0.0 = silent, 1.0 = max
    meter.set_level(0.7)   # speaking moderately loudly
"""

from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QTimer, QRectF
from PyQt5.QtGui import QPainter, QBrush, QColor, QPen, QFont


class MicLevelWidget(QWidget):
    """Real-time microphone input level bar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._level = 0.0        # current smoothed level
        self._target = 0.0       # target from mic
        self._peak = 0.0         # peak hold
        self._peak_decay = 0.0   # peak decay timer
        self._is_active = False  # whether mic is currently recording
        self.setFixedHeight(14)
        self.setMinimumWidth(120)

        # Paint timer — 20fps for smooth animation
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(50)

    def set_level(self, val: float):
        """Set raw mic level (0.0 — 1.0+). Clamped internally."""
        self._target = max(0.0, min(1.0, val))

    def set_active(self, active: bool):
        """Show recording state."""
        self._is_active = active

    def _tick(self):
        """Smooth interpolation."""
        # Smooth rise, quick fall
        if self._target > self._level:
            self._level += (self._target - self._level) * 0.4
        else:
            self._level += (self._target - self._level) * 0.15

        # Peak hold
        if self._level > self._peak:
            self._peak = self._level
            self._peak_decay = 30  # hold for ~30 ticks (~1.5s)
        elif self._peak_decay > 0:
            self._peak_decay -= 1
        else:
            self._peak *= 0.9

        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        margin = 2
        bar_w = w - margin * 2
        bar_h = h - margin * 2
        bar_y = margin
        r = bar_h / 2  # corner radius

        # Background — light gray matching the design
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(229, 231, 235)))  # #e5e7eb
        p.drawRoundedRect(QRectF(margin, bar_y, bar_w, bar_h), r, r)

        if not self._is_active and self._level < 0.01:
            # Idle state — subtle dot
            p.setBrush(QBrush(QColor(156, 163, 175)))  # #9ca3af
            idle_w = int(bar_w * 0.05)
            p.drawRoundedRect(QRectF(margin, bar_y, idle_w, bar_h), r, r)
            p.end()
            return

        # Active fill
        fill_w = max(1, int(bar_w * max(self._level, 0.03)))

        # Color: green → yellow → red
        if self._level < 0.5:
            r2, g2, b2 = 16, int(185 + self._level * 70), 129
        elif self._level < 0.8:
            t = (self._level - 0.5) / 0.3
            r2, g2, b2 = int(245 * t), int(255 - 70 * t), int(129 - 129 * t)
        else:
            r2, g2, b2 = 239, 68, 68

        color = QColor(r2, g2, b2, 220)
        p.setBrush(QBrush(color))
        p.drawRoundedRect(QRectF(margin, bar_y, fill_w, bar_h), r, r)

        # Peak hold dot
        if self._peak > 0.02:
            peak_x = min(int(bar_w * self._peak), int(bar_w - 2))
            p.setBrush(QBrush(QColor(55, 65, 81, 200)))  # #374151
            p.drawEllipse(peak_x - 3, int(bar_y + r - 3), 6, 6)

        # Recording indicator (pulsing red dot on left)
        if self._is_active:
            import math, time  # noqa
            pulse = (math.sin(time.time() * 6) + 1) / 2
            dot_alpha = int(150 + 105 * pulse)
            p.setBrush(QBrush(QColor(239, 68, 68, dot_alpha)))
            p.drawEllipse(margin + 1, bar_y + 2, bar_h - 4, bar_h - 4)

        p.end()
