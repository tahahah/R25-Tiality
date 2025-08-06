import socket
import numpy
import time
import threading

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect(('127.0.0.1', 8000))

while True:
    try:
        client.send('Video'.encode())
        time.sleep(1)
    finally:
        connected = False