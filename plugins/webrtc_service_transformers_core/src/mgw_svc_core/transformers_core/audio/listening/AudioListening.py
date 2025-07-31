import asyncio
import logging

from typing import Dict

from mgw_svc_core.transformers_core.audio.AudioDataTransformChannel import AudioDataTransformChannel

logger = logging.getLogger(__name__)


class AudioListening(AudioDataTransformChannel):
    """
    A audio stream track that only listen.
    """

    kind = "audio"

    def __init__(self, track, channel, transform, event_emitter,
                 params: Dict[str, str] = None):
        super().__init__(track, channel, transform, event_emitter, params)  # don't forget this!

    @staticmethod
    def create_transformer(track, channel, transform, event_emitter,
                           params: Dict[str, str] = None):
        return AudioListening(track, channel, transform, event_emitter,
                              params=params)

    async def recv(self):
       await asyncio.sleep(1e-3)
       pass
