import grpc
from . import audio_streaming_pb2
from . import audio_streaming_pb2_grpc
import queue
import time

def run_grpc_audio_client(server_address, audio_packet_queue, packet_generator_func):
    """
    Main function to run the gRPC audio client.
    Contains the reconnection logic.
    """
    print("Starting gRPC audio client thread...")
    while True:
        try:
            # Establish a connection to the gRPC server.
            with grpc.insecure_channel(server_address) as channel:
                stub = audio_streaming_pb2_grpc.AudioStreamingStub(channel)
                print(f"Successfully connected to audio server at {server_address}.")
                
                # Generator of audio packets
                packet_generator = packet_generator_func(audio_packet_queue)
                
                # Start streaming packets to the server.
                response = stub.StreamAudio(packet_generator)
                print(f"Audio server response: {response.status_message}")
                
        except grpc.RpcError as e:
            print(f"Audio connection failed: {e.details()} ({e.code()})")
            print("Will attempt to reconnect in 5 seconds...")
        
        except Exception as e:
            print(f"An unexpected error occurred in the audio client run loop: {e}")
            break  # Exit if a non-gRPC error occurs
        
        # Wait before the next connection attempt.
        time.sleep(5)
