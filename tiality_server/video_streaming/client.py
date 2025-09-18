import grpc
from . import video_streaming_pb2
from . import video_streaming_pb2_grpc
import queue
import time

def run_grpc_client(server_address, frame_queue, frame_generator_func):
    """
    Main function to run the gRPC client.
    Contains the reconnection logic.
    """
    print("Starting gRPC client thread...")
    while True:
        try:
            # Establish a connection to the gRPC server.
            with grpc.insecure_channel(server_address) as channel:
                stub = video_streaming_pb2_grpc.VideoStreamingStub(channel)
                print(f"Successfully connected to server at {server_address}.")
                
                # Generator of frames
                frame_generator = frame_generator_func(frame_queue)
                
                # Start streaming frames to the server.
                response = stub.StreamVideo(frame_generator)
                print(f"Server response: {response.status_message}")

        except grpc.RpcError as e:
            print(f"Connection failed: {e.details()} ({e.code()})")
            print("Will attempt to reconnect in 5 seconds...")
        
        except Exception as e:
            print(f"An unexpected error occurred in the client run loop: {e}")
            break # Exit if a non-gRPC error occurs

        # Wait before the next connection attempt.
        time.sleep(5)

    