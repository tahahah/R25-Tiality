import grpc
import time
from concurrent import futures
import queue

from . import video_streaming_pb2
from . import video_streaming_pb2_grpc

# A thread-safe queue to hold the most recent video frame.
# This allows the gRPC server thread to communicate with your main GUI thread.
# maxsize=1 ensures you always get the most recent frame, preventing lag.

class VideoStreamingServicer(video_streaming_pb2_grpc.VideoStreamingServicer):
    """
    The implementation of the gRPC service defined in the .proto file.
    This class handles the actual logic of the video stream.
    """
    def __init__(self, threadsafe_queue, connection_established_event, shutdown_event):
        super().__init__()

        self.video_frame_queue = threadsafe_queue
        self.connection_established_event = connection_established_event
        self.shutdown_event = shutdown_event

    def StreamVideo(self, request_iterator, context):
        """
        This method is called when a client (the Pi) connects and starts streaming.
        'request_iterator' is an iterator that yields VideoFrame messages from the client.
        """
        print("Client connected and started streaming.")
        

        try:
            # Iterate over the incoming stream of video frames from the client.
            for video_frame in request_iterator:
                if not self.shutdown_event.is_set():
                    # This is the raw byte data of the frame.
                    frame_data = video_frame.frame_data

                    # TODO: Implement Load Balancer

                    # Use a "dumping" pattern on the queue to ensure it only holds
                    # the single most recent frame.
                    try:
                        # Clear any old frame that the GUI hasn't processed yet.
                        self.video_frame_queue.get_nowait()
                    except queue.Empty:
                        # The queue was already empty, which is fine.
                        pass
                    
                    # Put the new, most recent frame into the queue.
                    self.video_frame_queue.put_nowait(frame_data)

                else:
                    break

        except grpc.RpcError as e:
            # This exception is commonly raised when the client disconnects abruptly.
            # We catch it to handle the dropout gracefully.
            print(f"Client disconnected unexpectedly: {e.code()}")

        finally:
            # This block runs whether the stream finishes cleanly or the client disconnects.
            print("Client stream ended. Ready for new connection.")
        
        # Once the stream ends (either cleanly or by dropout), send a final response.
        return video_streaming_pb2.StreamResponse(status_message="Stream ended.")


def serve(grpc_port, video_queue, connection_established_event, shutdown_event):
    """
    Starts the gRPC server and keeps it running.
    This function is designed to run forever and handle reconnections automatically.
    """
    # Create a gRPC server instance. We use a ThreadPoolExecutor to handle
    # incoming requests concurrently.
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=3))
    video_streaming_pb2_grpc.add_VideoStreamingServicer_to_server(
        VideoStreamingServicer(video_queue, connection_established_event, shutdown_event), server
    )
    
    # The server listens on all available network interfaces on port 50051.
    # Using f'[::]:{str(grpc_port)}' makes it listen on both IPv4 and IPv6.
    server.add_insecure_port(f'[::]:{str(grpc_port)}')
    
    print(f"gRPC server starting on port {grpc_port}...")
    server.start()
    print("Server started. Waiting for connections...")
    
    try:
        # The server will run indefinitely. The main thread will sleep here,
        # while the server's worker threads handle connections.
        # This is the core of handling reconnections: the server never stops.
        while not shutdown_event.is_set():
            
            time.sleep(5) # Sleep for one day at a time.
    except KeyboardInterrupt:
        # This allows you to stop the server cleanly with Ctrl+C.
        print("Server stopping...")
        server.stop(0)
        print("Server stopped.")

    finally:
        print(f"Shutdown: {shutdown_event.is_set()}")
        print("Video Producer thread manager completely shutdown")