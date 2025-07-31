import sys
import requests
from ..targets.ConsumeOnlyTarget import ConsumeOnlyTarget
import logging
import json
import os

from ..audio.listening.AudioListening import AudioListening

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
logging.root.setLevel(logging.INFO)

cova_method = os.environ.get("COVA_METHOD", "http")
cova_host = os.environ.get("COVA_HOST", "generator")
cova_port = os.environ.get("COVA_PORT", 80)
logger.info(f"INITIALIZE AudioTransform")


class AudioTransform:
    channels = {}
    targets = {}
    transformers = {}

    @classmethod
    def register_transformer(cls, id: str, data: dict):
        if id in cls.transformers:
            raise ValueError(
                f"There is already an AudioTransform registerd " f"with the id {id}"
            )
        if "channel" not in data:
            raise ValueError(
                f"Must provide a channel class under the " f"'channel' key"
            )
        if "target" not in data:
            raise ValueError(f"Must provide a target class under the " f"'target' key")
        if len(data["channel"]) != 2:
            raise ValueError(
                f"The channel must be defined by a tuple "
                f"composed of a channel id and a channel class."
            )
        if len(data["target"]) != 2:
            raise ValueError(
                f"The target must be defined by a tuple "
                f"composed of a tuple id and a tuple class."
            )
        if (
            data["channel"][0] in cls.channels
            and data["channel"][1] != cls.channels[data["channel"][0]]
        ):
            raise ValueError(
                f"There is already a channel registered "
                f"with the id {data['channel'][0]}"
            )
        if (
            data["target"][0] not in cls.targets
            or data["target"][1] == cls.targets[data["target"][0]]
        ):            
            cls.targets[data["target"][0]] = data["target"][1]

        cls.channels[data["channel"][0]] = data["channel"][1]
        cls.transformers[id] = (data["channel"][0], data["target"][0], data["title"], data["description"])

    @staticmethod
    def create_audio_transformer(
        transform,
        websocket,
        callId,
        sid,
        peer_connection,
        peer_connection__dict,
        event_emitter=None,
    ):

        logger.info(f"AudioTransform.create_audio_transformer : {callId}")

      #  transcription_payload = {"bubble_id": callId}
      #  logger.info(f"transcription_payload : {transcription_payload}")
      #  transcription_url = (
      #      f"{cova_method}://{cova_host}:{cova_port}" f"/get_transcription_mode/"
      #  )
      #  transcription_response = requests.get(
      #      transcription_url, params=transcription_payload
      #  )

       # if transcription_response.status_code == 200:
       #     transcription_mode = transcription_response.json()
       # else:
       #     transcription_mode = "default"
       # logger.info(f"transcription_mode: {transcription_mode}")
       # params = {"transcription_mode": transcription_mode}

       # intent_history_reset_url = (
       #     f"{cova_method}://{cova_host}:{cova_port}/reset-intent-history/"
       # )
       # headers = {
       #     "accept": "application/json",
       #    "Content-Type": "application/json",
       # }
       # data = {"bubble_id": json.dumps(callId)}

       # try:
       #     requests.post(intent_history_reset_url, headers=headers, json=data)
       # except Exception as e:
       #     logger.info(f"Exception while resetting intent history : {e}")
        params = {}
        if transform.get("type") in AudioTransform.transformers.keys():
            channel = AudioTransform.transformers[transform.get("type")][0]
            target = AudioTransform.transformers[transform.get("type")][1]
            return AudioTransform.targets[target](
                "audio",
                AudioTransform.channels[channel].create_transformer,
                transform,
                websocket,
                callId,
                sid,
                peer_connection,
                peer_connection__dict,
                event_emitter,
                params=params,
            )
        elif transform.get("type") == "none":
            return ConsumeOnlyTarget(
                "audio",
                AudioListening.create_transformer,
                transform,
                websocket,
                callId,
                sid,
                peer_connection,
                peer_connection__dict,
                event_emitter,
            )
        else:
            return None
