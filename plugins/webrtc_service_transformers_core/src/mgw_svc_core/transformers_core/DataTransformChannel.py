from aiortc import MediaStreamTrack
from typing import Dict
import logging

logger = logging.getLogger(__name__)

MAX_SILENCE_DURATION = 0.2  # seconds

inf = float("inf")


class DataTransformChannel(MediaStreamTrack):
    """
    A superclass for all stream data transformers.
    """

    kind = "data"

    def __init__(
        self, track, channel, transform, event_emitter, params: Dict[str, str] = None
    ):
        super().__init__()  # don't forget this!
        self.track = track
        self.channel = channel
        self.transform = transform
        self.ee = event_emitter
        self.params = params
