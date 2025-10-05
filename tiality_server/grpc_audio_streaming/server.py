import grpc
import time
from concurrent import futures
import queue

from . import audio_streaming_pb2
from . import audio_streaming_pb2_grpc

class AudioStreamingServicer(audio_streaming_pb2_grpc.AudioStreamingServicer):
    """
    gRPC service for receiving audio streams from Pi
    """
    def __init__(self, threadsafe_queue, connection_established_event, shutdown_event):
        super().__init__()
        self.audio_packet_queue = threadsafe_queue
        self.connection_established_event = connection_established_event
        self.shutdown_event = shutdown_event

    def StreamAudio(self, request_iterator, context):
        """
        Receives stream of Opus-encoded audio packets from Pi
        """
        print("Audio client connected and started streaming.")
        
        try:
            for audio_packet in request_iterator:
                if not self.shutdown_event.is_set():
                    # Extract packet data
                    packet_data = {
                        'audio_data': audio_packet.audio_data,
                        'timestamp': audio_packet.timestamp,
                        'sequence_number': audio_packet.sequence_number,
                        'packet_length': audio_packet.packet_length,
                        'algorithm_delay': audio_packet.algorithm_delay
                    }
                    
                    # Put packet in queue (FIFO for audio, unlike video)
                    try:
                        self.audio_packet_queue.put_nowait(packet_data)
                    except queue.Full:
                        # Drop oldest packet if queue is full
                        try:
                            self.audio_packet_queue.get_nowait()
                            self.audio_packet_queue.put_nowait(packet_data)
                        except (queue.Empty, queue.Full):
                            pass
                else:
                    break
                    
        except grpc.RpcError as e:
            try:
                print(f"Audio client disconnected: {e.code()}")
            except AttributeError:
                print(f"Audio client disconnected: {type(e).__name__}")
        finally:
            print("Audio stream ended. Ready for new connection.")
        
        return audio_streaming_pb2.StreamResponse(status_message="Audio stream ended.")


def serve(grpc_port, audio_queue, connection_established_event, shutdown_event):
    """
    Starts the gRPC audio server
    """
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    audio_streaming_pb2_grpc.add_AudioStreamingServicer_to_server(
        AudioStreamingServicer(audio_queue, connection_established_event, shutdown_event), 
        server
    )
    
    server.add_insecure_port(f'[::]:{str(grpc_port)}')
    
    print(f"gRPC audio server starting on port {grpc_port}...")
    server.start()
    print("Audio server started. Waiting for connections...")
    
    try:
        while not shutdown_event.is_set():
            time.sleep(5)
    except KeyboardInterrupt:
        print("Audio server stopping...")
        server.stop(0)
        print("Audio server stopped.")
    finally:
        print("Audio server thread manager shutdown")