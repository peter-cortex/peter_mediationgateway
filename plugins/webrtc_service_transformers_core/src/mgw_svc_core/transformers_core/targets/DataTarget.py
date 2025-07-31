import asyncio

# from asyncore import loop
import os
from ..targets.TransformerTarget import TransformerTarget
from aiortc.contrib.media import MediaBlackhole

from ..audio.playback.AudioFileTrack import AudioFileTrack
from aiortc import MediaStreamTrack
from ..audio.playback.AudioOpenaiTTSTrack import AudioOpenaiTTSTrack
from aiortc import RTCPeerConnection
import logging
from typing import Dict

# from pydub.generators import Sine

# import threading

logger = logging.getLogger("pc")


class DataTarget(TransformerTarget):

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

    async def pre_processing(self, peer_connection):
        self.blackhole = MediaBlackhole()

        if self.transform.get("channel") == "data":
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
                logger.info(
                    "ICE Gathering state is %s", self.pc_publish.iceGatheringState
                )

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

            self.channel = await self.create_data_channel(
                self.pc_publish, "JanusDataChannel"
            )
            
            # Intercept additional channel creation form PC   
            def on_datachannel(channel):
                @channel.on("message")
                def on_message(message):
                    # May be the goal is to propagate the message to event emitter for later consumption
                    self.ee.emit("channel_message", message)
                    pass
            self.peer_connection.on("datachannel",on_datachannel)         
            self.pc_publish.on("datachannel",on_datachannel) 
        else:
            self.channel = await self.create_websocket_channel(self.websocket)
            

        

        if self.transform.get("direction"):
            self.addTranceiver(peer_connection, self.transform.get("direction"))


        if self.kind == 'audio':
            audioTrack = self.create_audio_track()
            audioFileTrack = AudioFileTrack()

            @self.ee.on("audio_play")
            async def on_audio_play(path):
                await audioFileTrack.queue.put(path)

            """
            blank_file = '/tmp/toto.wav' #tempfile.NamedTemporaryFile(suffix=".wav")
            sine_generator = Sine(300)  # 0.1 sec silence
            silence = pydub.AudioSegment.silent(duration=100)
            dot = sine_generator.to_audio_segment(duration=150)
            dash = sine_generator.to_audio_segment(duration=300)
            signal = [dot, dot, dot, dash, dash, dash, dot, dot, dot]
            sound = pydub.AudioSegment.empty()

            for piece in signal:
                sound += piece + silence

            sound.export(blank_file, format="wav")

            await audioFileTrack.queue.put( blank_file )

            def delayed_function():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(audioFileTrack.queue.put( blank_file ))
                loop.close()

            delay = 20  # Delay in seconds
            timer = threading.Timer(delay, threading.Thread(target=delayed_function).start)
            timer.start() """

            self.peer_connection.addTrack(audioTrack)

    async def create_websocket_channel(self, websocket):
        def channel():
            return None

        _channel = channel
        _channel.sid = self.sid

        def send(msg):
            try:
                if not websocket.closed:
                    asyncio.create_task(websocket.send_str(msg))
            except Exception as e:
                logger.info("Except")
                pass

        _channel.readyState = "open"
        _channel.send = send

        return channel

    def create_audio_track(self) -> MediaStreamTrack:
        audioTrack = AudioOpenaiTTSTrack(self.ee)
        @self.ee.on("say")
        async def on_say (message):
            logger.info(f" Target on_say {message}")
            payload = message.copy()
            if 'options' in payload and 'voice' in payload ['options']:
                payload ['voice'] = payload ['options']['voice']
            self.ee.emit ("tts_request", payload)
        return audioTrack 

    async def pre_sdp_negociation(self, peer_connection):
        await self.blackhole.start()

    async def post_sdp_negociation(self, peer_connection):
        if self.pc_publish is not None:
            if (
                len(self.pc_publish.getTransceivers()) > 0
                or len(self.pc_publish.getReceivers()) > 0
                or self.pc_publish.sctp is not None
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
                        "kind": "application",
                    }
                )

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
        if self.kind == "audio" and self.player is not None:
            self.player.audio.stop()
