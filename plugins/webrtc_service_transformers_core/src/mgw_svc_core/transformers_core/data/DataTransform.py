from ..data.listening.DataListening import DataListening

from ..targets.ConsumeOnlyTarget import ConsumeOnlyTarget


class DataTransform:
    channels = {}
    targets = {}
    transformers = {}

    @classmethod
    def register_transformer(cls, id: str, data: dict):
        if id in cls.transformers:
            raise ValueError(
                f"There is already an DataTransform registerd " f"with the id {id}"
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
    def create_data_transformer(
        transform,
        websocket,
        callId,
        sid,
        peer_connection,
        peer_connection__dict,
        event_emitter=None,
    ):
        if transform.get("type") == "listening":
            return ConsumeOnlyTarget(
                "data",
                DataListening.create_transformer,
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
