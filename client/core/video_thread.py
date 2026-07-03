import cv2
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QImage
import time
import numpy as np

class VideoThread(QThread):
    change_pixmap_signal = pyqtSignal(QImage)
    frame_signal = pyqtSignal(np.ndarray)

    def __init__(self, capture_width=1280, capture_height=720):
        super().__init__()
        self._run_flag = True
        self.capture_width = capture_width
        self.capture_height = capture_height

    def run(self):
        # Capture from web cam
        cap = cv2.VideoCapture(1, cv2.CAP_AVFOUNDATION)
        if self.capture_width and self.capture_height:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(self.capture_width))
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(self.capture_height))
        while self._run_flag:
            ret, cv_img = cap.read()
            if ret:
                # Mirror the frame
                cv_img = cv2.flip(cv_img, 1)
                
                # Emit raw frame for FFmpeg (in BGR)
                self.frame_signal.emit(cv_img)
                
                rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb_image.shape
                bytes_per_line = ch * w
                convert_to_qt_format = QImage(
                    rgb_image.data,
                    w,
                    h,
                    bytes_per_line,
                    QImage.Format_RGB888
                ).copy()
                self.change_pixmap_signal.emit(convert_to_qt_format)
            time.sleep(0.03) # Approx 30 FPS
        # Shut down capture system
        cap.release()

    def stop(self):
        """Sets run flag to False and waits for thread to finish"""
        self._run_flag = False
        self.wait()
