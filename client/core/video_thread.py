import cv2
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QImage
import time
import numpy as np

class VideoThread(QThread):
    change_pixmap_signal = pyqtSignal(QImage)
    frame_signal = pyqtSignal(np.ndarray) # New signal for raw frame

    def __init__(self):
        super().__init__()
        self._run_flag = True

    def run(self):
        # Capture from web cam
        cap = cv2.VideoCapture(1,cv2.CAP_AVFOUNDATION)
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
                convert_to_qt_format = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
                p = convert_to_qt_format.scaled(640, 480, Qt.KeepAspectRatio)
                self.change_pixmap_signal.emit(p)
            time.sleep(0.03) # Approx 30 FPS
        # Shut down capture system
        cap.release()

    def stop(self):
        """Sets run flag to False and waits for thread to finish"""
        self._run_flag = False
        self.wait()
