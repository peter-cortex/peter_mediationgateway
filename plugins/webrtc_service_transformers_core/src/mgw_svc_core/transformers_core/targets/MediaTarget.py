import logging
from ..targets.TransformerTarget import TransformerTarget
from aiortc import RTCPeerConnection, RTCRtpSender
from aiortc.contrib.media import MediaRelay
from typing import Dict

relay = MediaRelay()

logger = logging.getLogger("pc")


class MediaTarget(TransformerTarget):
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
        self.relay_proxy = None
        self.pc_publish = None

    @staticmethod
    def force_codec(pc, sender, forced_codec):
        kind = forced_codec.split("/")[0]
        codecs = RTCRtpSender.getCapabilities(kind).codecs
        transceiver = next(t for t in pc.getTransceivers() if t.sender == sender)
        transceiver.setCodecPreferences(
            [codec for codec in codecs if codec.mimeType == forced_codec]
        )

    async def pre_processing(self, peer_connection):
        self.pc_publish = RTCPeerConnection(configuration=self.websocket.config)

        @self.pc_publish.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info("Connection state is %s", self.pc_publish.connectionState)

            await self.websocket.send_json(
                {
                    "type": "connectionstate",
                    "state": self.pc_publish.connectionState,
                    "sid": self.sid + "-publish",
                    "callId": self.callId,
                }
            )

            if self.pc_publish.connectionState == "failed":
                await self.pc_publish.close()
                del self.pc_dict[self.sid + "-publish"]

        @self.pc_publish.on("iceconnectionstatechange")
        async def on_iceconnectionstatechange():
            logger.info(
                "ICE Connection state is %s", self.pc_publish.iceConnectionState
            )

            await self.websocket.send_json(
                {
                    "type": "iceconnectionstate",
                    "state": self.pc_publish.iceConnectionState,
                    "sid": self.sid + "-publish",
                    "callId": self.callId,
                }
            )

        @self.pc_publish.on("icegatheringstatechange")
        async def on_iceconnectionstatechange():
            logger.info("ICE Gathering state is %s", self.pc_publish.iceGatheringState)

            await self.websocket.send_json(
                {
                    "type": "icegatheringstate",
                    "state": self.pc_publish.iceGatheringState,
                    "sid": self.sid + "-publish",
                    "callId": self.callId,
                }
            )

        @self.pc_publish.on("signalingstatechange")
        async def on_iceconnectionstatechange():
            logger.info("Signaling state is %s", self.pc_publish.signalingState)

            await self.websocket.send_json(
                {
                    "type": "signalingState",
                    "state": self.pc_publish.signalingState,
                    "sid": self.sid + "-publish",
                    "callId": self.callId,
                }
            )

        if self.transform.get("direction"):
            self.addTranceiver(peer_connection, self.transform.get("direction"))
            
        # Intercept additional channel creation form PC   
        def on_datachannel(channel):
            @channel.on("message")
            def on_message(message):
                # May be the goal is to propagate the message to event emitter for later consumption
                self.ee.emit("channel_message", message)
                pass
        self.peer_connection.on("datachannel",on_datachannel)         
        self.pc_publish.on("datachannel",on_datachannel) 

    async def pre_sdp_negociation(self, peer_connection):
        pass

    async def post_sdp_negociation(self, peer_connection):
        if (
            len(self.pc_publish.getTransceivers()) > 0
            or len(self.pc_publish.getReceivers()) > 0
        ):
            offer = await self.pc_publish.createOffer()
            await self.pc_publish.setLocalDescription(offer)
            sid = self.sid + "-publish"
            self.pc_dict[sid] = {"pc": self.pc_publish, "blackhole": None}
            await self.websocket.send_json(
                {
                    "sdp": self.pc_publish.localDescription.sdp,
                    "type": self.pc_publish.localDescription.type,
                    "sid": sid,
                    "callId": self.callId,
                    "kind": "video",
                }
            )

    def do_processing(self, track):
        if track.kind == self.kind:
            self.relay_proxy = relay.subscribe(track)
            video_sender = self.pc_publish.addTrack(
                self.mediaStack(
                    self.relay_proxy,
                    channel=self.channel,
                    transform=self.transform,
                    event_emitter=self.ee,
                    params=self.params,
                )
            )
            self.force_codec(self.pc_publish, video_sender, "video/VP8")

    async def on_track_ended(self):
        if self.relay_proxy:
            self.relay_proxy.stop()
