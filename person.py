import cv2
import numpy as np
import zmq
import pickle


from util.vis import visualize_frame
context = zmq.Context()
socket = context.socket(zmq.PUB)
socket.bind('tcp://0.0.0.0:5555')



# context_1 = zmq.Context()
# socket_1 = context_1.socket(zmq.SUB)
# socket_1.connect('tcp://192.168.70.221:5555')
# socket_1.setsockopt_string(zmq.SUBSCRIBE,'')

cap = cv2.VideoCapture(0)
encode_param = [int(cv2.IMWRITE_JPEG_QUALITY),90]
while True:
    ret, frame = cap.read()
    if not ret or frame is None:
        print("[Warning] Could not read frame from webcam. Retrying...")
        continue
    frame = cv2.resize(frame, (500, 500), interpolation=cv2.INTER_LINEAR)
    r, en_img = cv2.imencode(".jpg", frame, encode_param)
    message = {'shreasi': en_img}
    socket.send_pyobj(message)
    print("sending ...")
    # Show the frame locally for debugging
    cv2.imshow("Webcam Frame", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break
cv2.destroyAllWindows()
