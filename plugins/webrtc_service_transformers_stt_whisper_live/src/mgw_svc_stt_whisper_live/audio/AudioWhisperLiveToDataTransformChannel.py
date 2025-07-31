import json
import logging
import numpy as np
import os
import pydub
import textwrap
import threading
import time
import uuid
from mgw_svc_core.transformers_core.audio.AudioDataTransformChannel import AudioDataTransformChannel
import websocket

from aiortc.mediastreams import MediaStreamError
from typing import Dict



logger = logging.getLogger(__name__)

server_host = os.environ.get("WHISPER_LIVE_HOST", "localhost")
server_port = os.environ.get("WHISPER_LIVE_PORT", 9090)
wh_live_model = os.environ.get("WHISPER_LIVE_model", "small")
use_vad = os.environ.get("WHISPER_LIVE_USE_VAD", True)


class WhisperLiveClient:
    """
    Handles audio recording, streaming, and communication with a server using
    WebSocket.
    """

    INSTANCES = {}

    def __init__(self, host=None, port=None, lang=None, translate=False, model="small"):
        """
        Initializes a WhisperLiveClient instance for audio recording and
        streaming to a server.

        If host and port are not provided, the WebSocket connection will not be
        established.
        When translate is True, the task will be set to "translate" instead of
        "transcribe".
        The audio recording starts immediately upon initialization.

        Args:
            host (str): The hostname or IP address of the server.
            port (int): The port number for the WebSocket server.
            lang (str, optional): The selected language for transcription.
              Default is None.
            translate (bool, optional): Specifies if the task is translation.
              Default is False.
        """
        self.recording = False
        self.task = "transcribe"
        self.uid = str(uuid.uuid4())
        self.waiting = False
        self.language = lang
        self.model = model
        self.server_error = False

        if translate:
            self.task = "translate"

        self.timestamp_offset = 0.0
        self.audio_bytes = None

        if host is not None and port is not None:
            socket_url = f"ws://{host}:{port}"
            self.client_socket = websocket.WebSocketApp(
                socket_url,
                on_open=lambda ws: self.on_open(ws),
                on_message=lambda ws, message: self.on_message(ws, message),
                on_error=lambda ws, error: self.on_error(ws, error),
                on_close=lambda ws, close_status_code, close_msg: self.on_close(
                    ws, close_status_code, close_msg
                ),
            )
        else:
            logger.error("No host or port specified.")
            return

        WhisperLiveClient.INSTANCES[self.uid] = self

        # start websocket client in a thread
        self.ws_thread = threading.Thread(target=self.client_socket.run_forever)
        self.ws_thread.setDaemon(True)
        self.ws_thread.start()

        self.frames = b""
        self.transcript = []
        self.text_ = []
        self.message_transcript = ""
        logger.info("* recording")
        self.time_received = []
        self.start_time = []
        self.end_time = []
        self.time_elapsed = ""

    def on_message(self, ws, message):
        """
        Callback function called when a message is received from the server.

        It updates various attributes of the client based on the received
        message, including recording status, language detection, and server
        messages. If a disconnect message is received, it sets the recording
        status to False.

        Args:
            ws (websocket.WebSocketApp): The WebSocket client instance.
            message (str): The received message from the server.

        """
        message = json.loads(message)
        logger.info(f"WhisperLiveClient on_message got: {message}")
        if self.uid != message.get("uid"):
            logger.error("invalid client uid")
            return

        if "status" in message.keys():
            if message["status"] == "WAIT":
                self.waiting = True
                logger.info(
                    f"Server is full. Estimated wait time "
                    f"{round(message['message'])} minutes."
                )
            elif message["status"] == "ERROR":
                logger.error(f"Message from Server: {message['message']}")
                self.server_error = True
            return

        if "message" in message.keys() and message["message"] == "DISCONNECT":
            logger.info("Server overtime disconnected.")
            self.recording = False

        if "message" in message.keys() and message["message"] == "SERVER_READY":
            self.recording = True
            self.server_backend = message["backend"]
            logger.info(f"Server Running with backend {self.server_backend}")
            return

        if "language" in message.keys():
            self.language = message.get("language")
            lang_prob = message.get("language_prob")
            logger.info(
                f"Server detected language {self.language} with "
                f"probability {lang_prob}"
            )
            return

        if "segments" not in message.keys():
            return

        message = message["segments"]
        #logger.info(
        #    f'This is the received message : {message} last text : {message[-1]["text"]}'
        #)
        n_segments = len(self.transcript)
        self.transcript.append(message[-1]["text"])
        self.start_time.append(message[-1]["start"])
        self.end_time.append(message[-1]["end"])

        #logger.info(
        #    f" Transcript : {self.transcript} start : {self.start_time}   end : {self.end_time}"
        #)
        if n_segments > 1:
            #logger.info(f"Transcript : {self.transcript}")
            if (
                self.transcript[-1] == self.transcript[-2]
                and self.start_time[-1] == self.start_time[-2]
                and self.end_time[-1] == self.end_time[-2]
            ):
                self.message_transcript = message[-1]["text"]
                self.time_received = []

    def on_error(self, ws, error):
        logger.error(error)

    def on_close(self, ws, close_status_code, close_msg):
        logger.info(
            f"Websocket connection closed: {close_status_code}: " f"{close_msg}"
        )

    def on_open(self, ws):
        """
        Callback function called when the WebSocket connection is successfully
        opened.

        Sends an initial configuration message to the server, including client
        UID, language selection, and task type.

        Args:
            ws (websocket.WebSocketApp): The WebSocket client instance.

        """
        logger.info("Opened connection")
        ws.send(
            json.dumps(
                {
                    "uid": self.uid,
                    "language": self.language,
                    "task": self.task,
                    "model": self.model,
                    "use_vad": use_vad,
                }
            )
        )

    def bytes_to_float_array(self, audio_bytes):
        """
        Convert audio data from bytes to a NumPy float array.

        It assumes that the audio data is in 16-bit PCM format. The audio data
        is normalized to
        have values between -1 and 1.

        Args:
            audio_bytes (bytes): Audio data in bytes.

        Returns:
            np.ndarray: A NumPy array containing the audio data as float values
            normalized between -1 and 1.
        """
        raw_data = np.frombuffer(buffer=audio_bytes, dtype=np.int16)
        return raw_data.astype(np.float32) / 32768.0

    def send_packet_to_server(self, message):
        """
        Send an audio packet to the server using WebSocket.

        Args:
            message (bytes): The audio data packet in bytes to be sent to the
            server.

        """
        try:
            self.client_socket.send(message, websocket.ABNF.OPCODE_BINARY)
        except Exception as e:
            logger.error(e)

    def close_websocket(self):
        """
        Close the WebSocket connection and join the WebSocket thread.

        First attempts to close the WebSocket connection using
        `self.client_socket.close()`. After
        closing the connection, it joins the WebSocket thread to ensure proper
        termination.

        """
        try:
            self.client_socket.close()
        except Exception as e:
            logger.error("Error closing WebSocket:", e)

        try:
            self.ws_thread.join()
        except Exception as e:
            logger.error("Error joining WebSocket thread:", e)

    def get_client_socket(self):
        """
        Get the WebSocket client socket instance.

        Returns:
            WebSocketApp: The WebSocket client socket instance currently in use
            by the client.
        """
        return self.client_socket


class TranscriptionClient:
    def __call__(self):
        self.client.record()


class AudioWhisperLiveToDataTransformChannel(AudioDataTransformChannel):
    """
    A audio stream track that transforms frames into transcript text.
    """

    kind = "audio"

    def __init__(self, track, channel, transform, event_emitter,
                 params: Dict[str, str] = None):
        # don't forget this!
        super().__init__(track, channel, transform, event_emitter, params)

        self.client = WhisperLiveClient(
            server_host, server_port, lang="en", translate=False,
            model=wh_live_model
        )
        self.transcribe = ""
        self.stable_duration = ""
        self.current_transcript = ""
        self.check_stability = False

        @self.ee.on("active-talkers")
        async def on_activetalkers(message):
            pass

    @staticmethod
    def create_transformer(track, channel, transform,
                           event_emitter, params: Dict[str, str] = None):
        transformer = AudioWhisperLiveToDataTransformChannel(
            track, channel, transform, event_emitter, params=params)

        logger.info("Waiting for Whisper Live server ready ...")
        while not transformer.client.recording:
            if transformer.client.waiting or transformer.client.server_error:
                transformer.client.close_websocket()
                return None
            time.sleep(0.1)
        logger.info("Whisper Live Server Ready!")
        return transformer

    async def recv(self):
        try:
            if self.track.readyState != "live":
                raise MediaStreamError
            audio_frame = await self.track.recv()
            sound = pydub.AudioSegment(
                data=audio_frame.to_ndarray().tobytes(),
                sample_width=audio_frame.format.bytes,
                frame_rate=audio_frame.sample_rate,
                channels=len(audio_frame.layout.channels),
            )

            self.sound_chunk += sound

            if self.sound_chunk.duration_seconds > 0.40:
                # logger.info(f"duration_seconds : {self.sound_chunk.duration_seconds} ")
                self.sound_chunk = self.sound_chunk.set_channels(1)

                self.sound_chunk = self.sound_chunk.set_frame_rate(16000)

                samples = self.sound_chunk.get_array_of_samples()
                buffer = np.array(samples).T.astype(np.float32)
                buffer /= 32768.0

                self.client.send_packet_to_server(buffer.tobytes())

                self.sound_chunk = pydub.AudioSegment.empty()

            if self.client.transcript != self.current_transcript:
                self.stable_duration = time.time()
                self.check_stability = True
            if (
                self.check_stability
                and self.current_transcript == self.client.transcript
            ):
                elapsed_time = time.time() - self.stable_duration
                if len(self.client.transcript) > 1:
                    if elapsed_time > 2 and (
                        self.client.transcript[-1] != self.client.transcript[-2]
                    ):
                        # logger.info(f"THE STABLE TRANSCRIPT IS : {self.client.transcript[-1]}")
                        self.client.message_transcript = self.client.transcript[-1]
                        self.check_stability = False
                if len(self.client.transcript) == 1 and elapsed_time > 2:
                    self.client.message_transcript = self.client.transcript[-1]
                    # logger.info(f"2 THE STABLE TRANSCRIPT IS : {self.client.transcript[-1]}")
                    self.check_stability = False
            self.current_transcript = self.client.transcript

            if (
                self.client.message_transcript
                and self.client.message_transcript != self.transcribe
            ):
                self.transcribe = self.client.message_transcript
                logger.info(f"the transcription is {self.transcribe}")

                if self.channel is not None and len(self.transcribe) > 0:
                    try:
                        _result = {
                            "sid": self.channel.sid,
                            "type": "transcript",
                            "data": self.transcribe,
                        }
                        await self.channel.send(json.dumps(_result, ensure_ascii=False))
                    except Exception as e:
                        pass

            return audio_frame

        except MediaStreamError as e:
            data = b"END_OF_AUDIO"
            self.client.send_packet_to_server(data)
            raise e
        except Exception as e:
            logger.error(e)
