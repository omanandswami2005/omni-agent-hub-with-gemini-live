import asyncio
import logging
import sounddevice as sd
import numpy as np

logger = logging.getLogger(__name__)

class AudioStreamer:
    def __init__(self, ws_client):
        self.ws_client = ws_client
        self.input_stream = None
        self.output_stream = None
        self.is_recording = False

        # Output buffer queue for playback
        self.playback_queue = asyncio.Queue()
        self.playback_task = None

        # Audio configuration from server requirements
        self.input_sample_rate = 16000
        self.output_sample_rate = 24000
        self.channels = 1
        self.dtype = np.int16

    def start_recording(self):
        if self.is_recording:
            return

        logger.info("Starting audio recording")
        self.is_recording = True

        try:
            # Capture the running event loop from the main thread
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.error("Failed to start audio recording: No running event loop found")
            self.is_recording = False
            return

        def audio_callback(indata, frames, time, status):
            if status:
                logger.warning(f"Audio input status: {status}")

            # Send audio directly to WebSocket via asyncio thread-safe call
            if self.ws_client and self.ws_client.connected and self.is_recording:
                # Convert numpy array to bytes
                audio_bytes = indata.tobytes()

                # Send asynchronously using the captured loop
                if loop.is_running() and hasattr(self.ws_client, "send_audio"):
                    asyncio.run_coroutine_threadsafe(
                        self.ws_client.send_audio(audio_bytes),
                        loop
                    )

        try:
            self.input_stream = sd.InputStream(
                samplerate=self.input_sample_rate,
                channels=self.channels,
                dtype=self.dtype,
                callback=audio_callback,
                blocksize=4096 # Reasonable block size for 16kHz
            )
            self.input_stream.start()
        except Exception as e:
            logger.error(f"Failed to start audio recording: {e}")
            self.is_recording = False

    def stop_recording(self):
        if not self.is_recording:
            return

        logger.info("Stopping audio recording")
        self.is_recording = False
        if self.input_stream:
            self.input_stream.stop()
            self.input_stream.close()
            self.input_stream = None

    async def _playback_loop(self):
        """Continuously reads from queue and writes to output stream"""
        logger.info("Starting audio playback loop")
        try:
            # We need to use output stream without a callback for queue-based playback
            # to prevent blocking the asyncio loop
            self.output_stream = sd.OutputStream(
                samplerate=self.output_sample_rate,
                channels=self.channels,
                dtype=self.dtype
            )
            self.output_stream.start()

            while True:
                # Wait for next audio chunk
                audio_bytes = await self.playback_queue.get()

                # Convert bytes to numpy array
                data = np.frombuffer(audio_bytes, dtype=self.dtype)

                # Write to stream
                if self.output_stream and not self.output_stream.closed:
                    self.output_stream.write(data)

                self.playback_queue.task_done()

        except asyncio.CancelledError:
            logger.info("Playback loop cancelled")
        except Exception as e:
            logger.error(f"Playback error: {e}")
        finally:
            if self.output_stream:
                self.output_stream.stop()
                self.output_stream.close()
                self.output_stream = None

    def start_playback(self):
        if self.playback_task and not self.playback_task.done():
            return

        loop = asyncio.get_event_loop()
        self.playback_task = loop.create_task(self._playback_loop())

    def stop_playback(self):
        if self.playback_task and not self.playback_task.done():
            self.playback_task.cancel()
            self.playback_task = None

    async def queue_audio(self, audio_bytes: bytes):
        """Queue received binary audio from websocket for playback"""
        if not self.playback_task or self.playback_task.done():
            self.start_playback()

        await self.playback_queue.put(audio_bytes)
