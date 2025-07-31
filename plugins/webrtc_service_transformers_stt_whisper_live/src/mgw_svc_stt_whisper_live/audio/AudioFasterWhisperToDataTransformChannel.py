import aiohttp
import logging
import os
import tempfile

from aiortc.mediastreams import MediaStreamError
from typing import Dict

from mgw_svc_core.transformers_core.audio.AudioDataTransformChannel import AudioDataTransformChannel

logger = logging.getLogger(__name__)

server_host = os.environ.get("FASTER_WHISPER_HOST", "faster-whisper-api")
server_port = os.environ.get("FASTER_WHISPER_PORT", 8383)

class AudioFasterWhisperToDataTransformChannel(AudioDataTransformChannel):
    """
    A audio stream track that transforms frames into transcript text.
    """

    kind = "audio"

    def __init__(self, track, channel, transform, event_emitter,
                 params: Dict[str, str] = None):
        # don't forget this!
        super().__init__(track, channel, transform, event_emitter, params)

        @self.ee.on("active-talkers")
        async def on_activetalkers(message):
            pass

    @staticmethod
    def create_transformer(track, channel, transform,
                           event_emitter, params: Dict[str, str] = None):
        transformer = AudioFasterWhisperToDataTransformChannel(
            track, channel, transform, event_emitter, params=params)
        return transformer

    async def _transcribe(self):
        logger.info(f"AudioFasterWhisperToDataTransformChannel._transcribe")
        if self.track.readyState != "live":
            raise MediaStreamError
        self.sound_chunk = self.sound_chunk.set_frame_rate(16000)
        tf = tempfile.NamedTemporaryFile(delete=False)
        self.sound_chunk.export(tf.name, format="wav")

        with open(tf.name, "rb") as myfile:
            # Prepare the file for the request
            files = {"upload_file": myfile}
            async with aiohttp.ClientSession() as session:
                async with session.post(
                        f"http://{server_host}:{server_port}/transcribe",
                        data=files) as response:

                    if response.status == 200:
                        response_json = await response.json()
                        logger.debug(
                            f"AudioFasterWhisperToDataTransformChannel response is: {response_json }")
                        transcription = response_json["transcription"]
                    else:
                        # There was an error
                        logger.error(
                            f"AudioFasterWhisperToDataTransformChannel Error during call to Faster Whisper API: "
                            f"{response.status}")
                        transcription = ""

        # Print the generated text
        logger.info(f"AudioFasterWhisperToDataTransformChannel._transcribe result: {transcription.strip()}")

        os.unlink(tf.name)
        return transcription.strip()
