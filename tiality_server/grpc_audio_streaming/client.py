import grpc
from . import audio_streaming_pb2
from . import audio_streaming_pb2_grpc
import queue
import time

def run_grpc_audio_client(server_address, audio_packet_queue, packet_generator_func):
    """
    Main function to run the gRPC audio client with reconnection logic
    """
    print("Starting gRPC audio client thread...")
    while True:
        try:
            with grpc.insecure_channel(server_address) as channel:
                stub = audio_streaming_pb2_grpc.AudioStreamingStub(channel)
                print(f"Audio client connected to server at {server_address}.")
                
                # Generator of audio packets
                packet_generator = packet_generator_func(audio_packet_queue)
                
                # Start streaming audio packets to server
                response = stub.StreamAudio(packet_generator)
                print(f"Audio server response: {response.status_message}")

        except grpc.RpcError as e:
            print(f"Audio connection failed: {e.details()} ({e.code()})")
            print("Will attempt to reconnect in 5 seconds...")
        
        except Exception as e:
            print(f"Unexpected error in audio client: {e}")
            break
        
        time.sleep(5)