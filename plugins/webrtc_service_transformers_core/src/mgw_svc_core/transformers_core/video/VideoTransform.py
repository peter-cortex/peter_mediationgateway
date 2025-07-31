import logging
import json

from mgw_svc_core.transformers_core.targets.ConsumeOnlyTarget import (
    ConsumeOnlyTarget
)
from mgw_svc_core.transformers_core.targets.MediaTarget import (
    MediaTarget
)
from mgw_svc_core.transformers_core.video.listening.VideoListening import (
    VideoListening,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
logging.root.setLevel(logging.INFO)

logger.info(f"INITIALIZE VideoTransform")


class VideoTransform:
    channels = {}
    targets = {}
    transformers = {}

    @classmethod
    def register_transformer(cls, id: str, data: dict):
        if id in cls.transformers:
            raise ValueError(
                f"There is already an VideoTransform registerd " f"with the id {id}"
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
                f"There is already a channel registerd "
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
    def create_video_transformer(
        transform,
        websocket,
        callId,
        sid,
        peer_connection,
        peer_connection__dict,
        event_emitter=None,
    ):
        """if transform.get('type') == "face_detection":
            return DataTarget('video',VideoToDataTransformChannel.create_transformer, transform, websocket, callId, sid, peer_connection, peer_connection__dict, None, event_emitter)
        elif transform.get('type') == "vcaa":
            return MediaTarget('video',VCAATransformTrack.create_transformer, transform, websocket, callId, sid, peer_connection, peer_connection__dict, None, event_emitter)
        elif transform.get('type') == "none":
            return ConsumeOnlyTarget('audio', VideoListening.create_transformer, transform, websocket, callId, sid, peer_connection, peer_connection__dict, None, event_emitter)
        else:
            return MediaTarget('video',VideoTransformTrack.create_transformer, transform, websocket, callId, sid, peer_connection, peer_connection__dict, None, event_emitter)
        """
        logger.info(f"VideoTransform.create_video_transformer : {callId}")

        params = {}

        data = {"bubble_id": json.dumps(callId)}

        if transform.get("type") in VideoTransform.transformers.keys():
            channel = VideoTransform.transformers[transform.get("type")][0]
            target = VideoTransform.transformers[transform.get("type")][1]
            return VideoTransform.targets[target](
                "video",
                VideoTransform.channels[channel].create_transformer,
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
            return MediaTarget(
                "video",
                VideoListening.create_transformer,
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


# Generic Registration
VideoTransform.register_transformer(
    "none",
    {
        "title": "No Transform",
        "description": "",
        "channel": ("none", VideoListening),
        "target": ("consume", ConsumeOnlyTarget),
    },
)
