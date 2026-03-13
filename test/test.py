import cv2

cap = cv2.VideoCapture(1, cv2.CAP_AVFOUNDATION)

# 后面的代码保持不变
while True:
    ret, frame = cap.read()
    if not ret or frame is None:
        print("无法读取视频帧")
        break
    frame = cv2.flip(frame, 1)
    cv2.imshow('frame', frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()