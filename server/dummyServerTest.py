from server_manager import *
import time

server = TialityServerManager("127.0.0.1", 8000, 8001)
server.start_servers()
if server.servers_active:
    print("Servers Online")
    time.sleep(5)
    print("Test Procedure Active")
    max_time = 60
    old_time = time.time()
    while max_time > 0:
        frame = server.get_video_frame()
        if frame is not None:
            print(frame)
        server.send_command(str(max_time))
        max_time -= time.time() - old_time
        old_time = time.time()