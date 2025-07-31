import asyncio
from aiortc import MediaStreamTrack
from pathlib import Path
import logging.handlers
import logging
from typing import Dict

from mgw_svc_core.transformers_core.DataTransformChannel import DataTransformChannel

logger = logging.getLogger(__name__)


class VideoListening(DataTransformChannel):
    """
    A video stream track that only listen.
    """

    kind = "video"

    def __init__(self, track, channel, transform, event_emitter,
                 params: Dict[str, str] = None):
        # don't forget this!
        super().__init__(track, channel, transform, event_emitter, params)

    @staticmethod
    def create_transformer(track, channel, transform, event_emitter,
                           params: Dict[str, str] = None):
        return VideoListening(track, channel, transform, event_emitter,
                              params=params)

    async def recv(self):
       await asyncio.sleep(1e-3)
       pass
