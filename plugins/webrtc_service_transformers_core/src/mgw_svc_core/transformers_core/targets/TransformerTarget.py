import logging
import time
import uuid
from typing import Dict

logger = logging.getLogger("pc")

time_start = None


class TransformerTarget:

    def __init__(
        self,
        kind,
        websocket,
        callId,
        sid,
        peer_connection,
        peer_connection__dict,
        event_emitter=None,

        params: Dict[str, str] = None,
    ):
        self.kind = kind
        self.blackhole = None
        self.websocket = websocket
        self.callId = callId
        self.sid = sid
        self.peer_connection = peer_connection
        self.pc_dict = peer_connection__dict
        self.ee = event_emitter
        self.params = params

        def channel():
            return None

        self.channel = channel

    async def pre_processing(self, peer_connection):
        pass

    def do_processing(self, track):
        pass

    async def pre_sdp_negociation(self, peer_connection):
        pass

    async def post_sdp_negociation(self, peer_connection):
        pass

    async def on_track_ended(self):
        pass

    def current_stamp(self):
        global time_start

        if time_start is None:
            time_start = time.time()
            return 0
        else:
            return int((time.time() - time_start) * 1000000)

    def addTranceiver(self, pc, direction):
        transceiver = None
        try:
            transceiver = next(t for t in pc.getTransceivers() if t.kind == self.kind)
        except StopIteration as e:
            # Ignore
            pass

        if transceiver is None:
            pc.addTransceiver(self.kind, direction=self.transform.get("direction"))
        elif transceiver.direction != self.transform.get("direction"):
            if (
                (
                    transceiver.direction == "sendonly"
                    and self.transform.get("direction") == "recvonly"
                )
                or (
                    transceiver.direction == "recvonly"
                    and self.transform.get("direction") == "sendonly"
                )
                or self.transform.get("direction") == "sendrecv"
            ):
                transceiver.direction = "sendrecv"
            elif transceiver.direction == "inactive":
                transceiver.direction = self.transform.get("direction")
            elif self.transform.get("direction") == "inactive":
                # keep the existing state
                pass

    async def create_data_channel(self, peer_connection, channel_name):

        def channel_log(channel, t, message):
            logger.info("channel(%s) %s %s" % (channel.label, t, message))

        channel = peer_connection.createDataChannel(channel_name)
        channel.sid = self.sid
        channel_log(channel, "-", "created by remote party")

        # async def send_pings():
        #     while True:
        #         channel_log(channel, "", "ping %d" % self.current_stamp())
        #         await asyncio.sleep(1)

        @channel.on("open")
        def on_open():
            channel_log(channel, "-", "datachannel opened!")
            # asyncio.ensure_future(send_pings())

        @channel.on("message")
        def on_message(message):
            if isinstance(message, str) and message.startswith("pong"):
                elapsed_ms = (self.current_stamp() - int(message[5:])) / 1000
                logger.debug(" RTT %.2f ms" % elapsed_ms)
            if isinstance(message, str) and message.startswith("ping"):
                channel.send("pong" + message[4:])
            else:
                channel_log(channel, "<", message)

        return channel
