from aiortc.contrib.media import MediaBlackhole
import logging
from typing import Dict

from ..targets.TransformerTarget import (
    TransformerTarget,
)

logger = logging.getLogger("pc")


class ConsumeOnlyTarget(TransformerTarget):

    def __init__(
        self,
        kind,
        mediaStack,
        transform,
        websocket,
        callId,
        sid,
        peer_connection,
        peer_connection__dict,
        event_emitter=None,
        params: Dict[str, str] = None,
    ) -> None:
        super().__init__(
            kind,
            websocket,
            callId,
            sid,
            peer_connection,
            peer_connection__dict,
            event_emitter,
            params=params,
        )
        self.mediaStack = mediaStack
        self.transform = transform
        self.pc_publish = None
        self.player = None

        def channel():
            return None

        self.channel = channel

    async def pre_processing(self, peer_connection):
        self.blackhole = MediaBlackhole()

        if self.transform.get("direction"):
            self.addTranceiver(peer_connection, self.transform.get("direction"))

    async def pre_sdp_negociation(self, peer_connection):
        if peer_connection.sctp is not None:
            self.channel = await self.create_data_channel(
                self.peer_connection, "JanusDataChannel"
            )

        await self.blackhole.start()

    async def post_sdp_negociation(self, peer_connection):
        pass

    def do_processing(self, track):
        if track.kind == self.kind:
            self.blackhole.addTrack(
                self.mediaStack(
                    track,
                    self.channel,
                    transform=self.transform,
                    event_emitter=self.ee,
                    params=self.params,
                )
            )

    async def on_track_ended(self):
        await self.blackhole.stop()
