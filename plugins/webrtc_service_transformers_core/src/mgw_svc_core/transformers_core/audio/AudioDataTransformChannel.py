import json
import logging
import numpy as np
import openwakeword
import os
from mgw_svc_core.transformers_core.DataTransformChannel import DataTransformChannel
import pydub
import scipy.signal
import webrtcvad
import time
from aiortc import MediaStreamTrack
from aiortc.mediastreams import MediaStreamError
from huggingface_hub import login, hf_hub_download
from typing import Dict

logger = logging.getLogger(__name__)
# logging.basicConfig(level=logging.DEBUG)
# logging.root.setLevel(logging.DEBUG)



def init_word_detection(wakeword: str):
    logger.info(f"AudioDataTransformChannel.init_word_detection wakeword: {wakeword}")
    model_path = "/root/.cache/huggingface/hub/models--Alevxis--wakewordcova/snapshots/883f0b1733d7896dabc551e7ee9b276b1f468e6b/Cova.tflite"
    if wakeword == "Cova" and model_path is not None:
        word_detection = openwakeword.Model(
            wakeword_models=[model_path],
        )
    else:
        word_detection = openwakeword.Model(
            wakeword_models=[wakeword],
        )
    logger.info(f"AudioDataTransformChannel.init_word_detection result: {word_detection}")
    return word_detection


class AudioDataTransformChannel(DataTransformChannel):
    """
    A superclass for all audio stream data frame transformers.
    """
    MAX_SILENCE_DURATION = 0.2  # seconds

    kind = "audio"
    vad = webrtcvad.Vad()
    wakeword = os.getenv("WAKEWORD", "Cova")
    word_detection = None

    def __init__(self, track, channel, transform, event_emitter,
                 params: Dict[str, str] = None):
        # don't forget this!
        super().__init__(track, channel, transform, event_emitter, params)
        if (
            params is not None
            and "transcription_mode" in params
            and params["transcription_mode"] == "wakeword"
        ):
            self.ww_detection_enabled = True
            if AudioDataTransformChannel.word_detection is None:
                AudioDataTransformChannel.word_detection = init_word_detection
        else:
            self.ww_detection_enabled = False

        #Modifica mia per forzare la language_mode
        #self.language_mode = params["language_mode"]
        self.language_mode = params.get("language_mode", "en") if params else "en"
        logger.info(f"self.ww_detection_enabled : {self.ww_detection_enabled} language_mode : {self.language_mode}")

        self.last_ww_detection = [""]
        # if no wake word detection: always awake; start asleep if wwd
        self.awaken = not self.ww_detection_enabled

        self.sound_chunk = pydub.AudioSegment.empty()
        self.silent_count = 0



    async def _transcribe_correct(self):
        """
        To be reimplemented in daughter classes. Makes the transcription work
        or initiate it asynchronuously.

        Returns:
            str: an empty string when transcription is done in the background.
                 In this case, the transcription result will be written later
                 on in the channel, asynchronuously
        """
        return ""

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
            # logger.info(f"sound duration : {sound.duration_seconds}")
            sound = sound.set_channels(1)
            # interword silent detection
            if not AudioDataTransformChannel.vad.is_speech(sound.raw_data, 48000):

                self.silent_count += sound.duration_seconds
                if self.silent_count > AudioDataTransformChannel.MAX_SILENCE_DURATION:
                    self.past_sentence = ""
                    self.sound_chunk = pydub.AudioSegment.empty()
                    return audio_frame
            else:
                self.silent_count = 0

            self.sound_chunk += sound
            if (self.silent_count < (5 * sound.duration_seconds)
                    and self.awaken):
                return audio_frame

            if self.ww_detection_enabled:

                if (
                    0.07 <= self.sound_chunk.duration_seconds <= 0.09
                    and not self.awaken
                ):
                    target_sample_rate = 16000
                    samples = np.array(self.sound_chunk.get_array_of_samples())

                    num_samples = (int(len(samples)
                                       * target_sample_rate
                                       / self.sound_chunk.frame_rate))
                    resampled_samples = scipy.signal.resample(samples,
                                                              num_samples)

                    detection = AudioDataTransformChannel.word_detection.predict(resampled_samples)

                    logger.info(
                        f"READY TO RECOGNIZE WORD : {self.sound_chunk.duration_seconds} detection  : {detection[AudioDataTransformChannel.wakeword]} "
                    )
                    if detection[AudioDataTransformChannel.wakeword] > 0.15:
                        if self.last_ww_detection[-1] == "ww":
                            self.last_ww_detection.append("ww")
                        else:
                            self.last_ww_detection.append("ww")
                            logger.info(f"WORKING detection result :  {detection}")
                            self.awaken = True
                    else:
                        self.last_ww_detection.append("nww")
                    self.sound_chunk = pydub.AudioSegment.empty()

                    return audio_frame

            if self.sound_chunk.duration_seconds > (
                0.1 + (5 * sound.duration_seconds)
            ) and self.awaken:
                # Drop chunk if too low
                if self.sound_chunk.max_dBFS < -30.0:
                    logger.info(f"Chunk is too low : {self.sound_chunk.max_dBFS} dBFS")
                    self.sound_chunk = pydub.AudioSegment.empty()
                    return audio_frame

                logger.info(
                    "Sound Chunk length: %f", self.sound_chunk.duration_seconds
                )
                logger.info(
                    "Sound Chunk max dBFS: %s", str(self.sound_chunk.max_dBFS)
                )

                self.sound_chunk = self.sound_chunk.set_channels(1)

                transcribe = await self._transcribe()
                if self.ww_detection_enabled :
                    self.awaken = False

                if transcribe:
                    # _transcribe returns an empty string when transcription is
                    # done in the background. In this case, the transcription
                    # result will be written later on in the channel,
                    # asynchronuously
                    self.past_sentence += " " + transcribe
                    logger.info("Text: " + transcribe)
                    if self.channel is not None and len(transcribe) > 0:
                        try:
                            _result = {
                                "sid": self.channel.sid,
                                "type": "transcript",
                                "data": transcribe,
                                "language": self.language_mode,
                            }
                            await self.channel.send(
                                json.dumps(_result, ensure_ascii=False)
                            )
                        except Exception as e:
                            pass
                self.sound_chunk = pydub.AudioSegment.empty()

            return audio_frame

        except MediaStreamError as e:
            raise e
        except Exception as e:
            logger.error(e)

