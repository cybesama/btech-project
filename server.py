import zmq
import cv2

# Receives compressed frames from the mobile camera
context = zmq.Context()
socket  = context.socket(zmq.SUB)
socket.connect('tcp://192.168.137.213:5555')
socket.setsockopt_string(zmq.SUBSCRIBE, '')

# Forwards frames to main.py on the same machine
context_1 = zmq.Context()
socket_1  = context_1.socket(zmq.PUB)
socket_1.bind('tcp://127.0.0.1:5555')

while True:
    message = socket.recv_pyobj()
    socket_1.send_pyobj(message)            # forward to main.py

    # Debug preview — remove in production
    data = cv2.imdecode(message['shreasi'], cv2.IMREAD_COLOR)
    cv2.imshow("Mobile Feed", data)
    cv2.waitKey(1)
