import sys
import cv2
import numpy as np
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QPushButton)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QImage, QPixmap


class CameraWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.initCamera()

    def initUI(self):
        # 设置窗口
        self.setWindowTitle('摄像头显示界面')
        self.setGeometry(100, 100, 1200, 500)

        # 创建中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 创建水平布局
        main_layout = QHBoxLayout(central_widget)

        # 左侧：本地摄像头区域
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        # 添加标题
        left_title = QLabel('本地摄像头')
        left_title.setAlignment(Qt.AlignCenter)
        left_title.setStyleSheet("font-size: 16px; font-weight: bold; padding: 5px;")

        # 摄像头显示区域
        self.local_camera_label = QLabel()
        self.local_camera_label.setFixedSize(500, 400)
        self.local_camera_label.setStyleSheet("border: 2px solid black; background-color: #2b2b2b;")
        self.local_camera_label.setAlignment(Qt.AlignCenter)
        self.local_camera_label.setText("摄像头启动中...")

        # 控制按钮
        self.local_btn = QPushButton('打开本地摄像头')
        self.local_btn.clicked.connect(self.toggle_local_camera)

        left_layout.addWidget(left_title)
        left_layout.addWidget(self.local_camera_label)
        left_layout.addWidget(self.local_btn)

        # 右侧：远程流区域
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        # 添加标题
        right_title = QLabel('远程流')
        right_title.setAlignment(Qt.AlignCenter)
        right_title.setStyleSheet("font-size: 16px; font-weight: bold; padding: 5px;")

        # 远程流显示区域（暂时显示占位符）
        self.remote_stream_label = QLabel()
        self.remote_stream_label.setFixedSize(500, 400)
        self.remote_stream_label.setStyleSheet("border: 2px solid black; background-color: #2b2b2b;")
        self.remote_stream_label.setAlignment(Qt.AlignCenter)
        self.remote_stream_label.setText("远程流\n(等待连接...)")

        # 远程流控制按钮（暂时禁用）
        self.remote_btn = QPushButton('连接远程流')
        self.remote_btn.setEnabled(False)

        right_layout.addWidget(right_title)
        right_layout.addWidget(self.remote_stream_label)
        right_layout.addWidget(self.remote_btn)

        # 将左右两个区域添加到主布局
        main_layout.addWidget(left_widget)
        main_layout.addWidget(right_widget)

    def initCamera(self):
        # 初始化摄像头
        self.cap = None
        self.camera_is_open = False
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)

    def toggle_local_camera(self):
        if not self.camera_is_open:
            # 打开摄像头
            self.cap = cv2.VideoCapture(1,cv2.CAP_AVFOUNDATION)  #
            if self.cap.isOpened():
                self.camera_is_open = True
                self.local_btn.setText('关闭本地摄像头')
                self.timer.start(30)  # 每30毫秒更新一次画面
            else:
                self.local_camera_label.setText("无法打开摄像头")
        else:
            # 关闭摄像头
            self.timer.stop()
            if self.cap:
                self.cap.release()
            self.camera_is_open = False
            self.local_btn.setText('打开本地摄像头')
            self.local_camera_label.setText("摄像头已关闭")
            self.local_camera_label.setStyleSheet("border: 2px solid black; background-color: #2b2b2b;")

    def update_frame(self):
        if self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                # 转换颜色空间（OpenCV使用BGR，Qt使用RGB）
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                # 获取帧的尺寸
                h, w, ch = frame.shape
                bytes_per_line = ch * w

                # 转换为QImage
                q_image = QImage(frame.data, w, h, bytes_per_line, QImage.Format_RGB888)

                # 缩放以适应标签大小
                pixmap = QPixmap.fromImage(q_image)
                scaled_pixmap = pixmap.scaled(self.local_camera_label.size(),
                                              Qt.KeepAspectRatio,
                                              Qt.SmoothTransformation)

                # 显示画面
                self.local_camera_label.setPixmap(scaled_pixmap)
                self.local_camera_label.setStyleSheet("border: 2px solid black;")

    def closeEvent(self, event):
        # 关闭窗口时释放摄像头资源
        if self.cap and self.cap.isOpened():
            self.cap.release()
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = CameraWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()