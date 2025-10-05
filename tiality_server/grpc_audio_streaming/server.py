import grpc
import time
from concurrent import futures
import queue

from . import audio_streaming_pb2
from . import audio_streaming_pb2_grpc

class AudioStreamingServicer(audio_streaming_pb2_grpc.AudioStreamingServicer):
    """
    The implementation of the gRPC service defined in the .proto file.
    This class handles the actual logic of the audio stream.
    """
    def __init__(self, threadsafe_queue, connection_established_event, shutdown_event):
        super().__init__()
        
        self.audio_packet_queue = threadsafe_queue
        self.connection_established_event = connection_established_event
        self.shutdown_event = shutdown_event
        
    def StreamAudio(self, request_iterator, context):
        """
        This method is called when a client (the Pi) connects and starts streaming.
        'request_iterator' is an iterator that yields AudioPacket messages from the client.
        """
        print("Audio client connected and started streaming.")
        
        try:
            # Iterate over the incoming stream of audio packets from the client.
            for audio_packet in request_iterator:
                if not self.shutdown_event.is_set():
                    # Extract packet data and metadata
                    packet_info = {
                        'data': audio_packet.packet_data,
                        'timestamp': audio_packet.timestamp,
                        'sequence_number': audio_packet.sequence_number,
                        'algorithm_delay': audio_packet.algorithm_delay
                    }
                    
                    # Use a "dumping" pattern on the queue to ensure it only holds
                    # the single most recent packet.
                    try:
                        # Clear any old packet that hasn't been processed yet.
                        self.audio_packet_queue.get_nowait()
                    except queue.Empty:
                        # The queue was already empty, which is fine.
                        pass
                    
                    # Put the new, most recent packet into the queue.
                    self.audio_packet_queue.put_nowait(packet_info)
                    
                else:
                    break
                    
        except grpc.RpcError as e:
            # This exception is commonly raised when the client disconnects abruptly.
            print(f"Audio client disconnected unexpectedly: {e.code()}")
            
        finally:
            # This block runs whether the stream finishes cleanly or the client disconnects.
            print("Audio client stream ended. Ready for new connection.")
        
        # Once the stream ends (either cleanly or by dropout), send a final response.
        return audio_streaming_pb2.StreamResponse(status_message="Audio stream ended.")


def serve(grpc_port, audio_queue, connection_established_event, shutdown_event):
    """
    Starts the gRPC audio server and keeps it running.
    This function is designed to run forever and handle reconnections automatically.
    """
    # Create a gRPC server instance. We use a ThreadPoolExecutor to handle
    # incoming requests concurrently.
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=3))
    audio_streaming_pb2_grpc.add_AudioStreamingServicer_to_server(
        AudioStreamingServicer(audio_queue, connection_established_event, shutdown_event), server
    )
    
    # The server listens on all available network interfaces on the specified port.
    server.add_insecure_port(f'[::]:{str(grpc_port)}')
    
    print(f"gRPC audio server starting on port {grpc_port}...")
    server.start()
    print("Audio server started. Waiting for connections...")
    
    try:
        # The server will run indefinitely. The main thread will sleep here,
        # while the server's worker threads handle connections.
        while not shutdown_event.is_set():
            time.sleep(5)
    except KeyboardInterrupt:
        # This allows you to stop the server cleanly with Ctrl+C.
        print("Audio server stopping...")
        server.stop(0)
        print("Audio server stopped.")
        
    finally:
        print(f"Audio server shutdown: {shutdown_event.is_set()}")
        print("Audio producer thread manager completely shutdown")
