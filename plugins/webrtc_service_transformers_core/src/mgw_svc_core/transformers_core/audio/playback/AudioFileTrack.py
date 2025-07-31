import asyncio
import fractions
import logging
import time
from typing import Tuple
import av
from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription, clock
from aiortc.contrib.media import MediaPlayer

AUDIO_PTIME = 0.020  # 20ms audio packetization

logger = logging.getLogger(__name__)

class MediaStreamError(Exception):
    pass

class AudioFileTrack(MediaStreamTrack):

    kind = "audio"

    _start: float
    _timestamp: int

    def __init__(self):
        super().__init__()  # don't forget this!
        self.player = None
        self.queue = asyncio.Queue()
        self.playing = False


    async def recv(self):

        if self.readyState != "live":
            raise MediaStreamError

        if not self.playing:
            asyncio.create_task(self.play())

        sample_rate = 8000
        samples = int(AUDIO_PTIME * sample_rate)

        if hasattr(self, "_timestamp"):
            self._timestamp += samples
            wait = self._start + (self._timestamp / sample_rate) - time.time()
            await asyncio.sleep(wait)
        else:
            self._start = time.time()
            self._timestamp = 0

        if not self.player:
            # send blank content
            frame = av.AudioFrame(format="s16", layout="mono", samples=samples)
            for p in frame.planes:
                p.update(bytes(p.buffer_size))
            frame.pts = self._timestamp
            frame.sample_rate = sample_rate
            frame.time_base = fractions.Fraction(1, sample_rate)
            return frame

        try:
            frame = await self.player.audio.recv()
            frame.pts = self._timestamp
            if frame:
                return frame
            else:
                # send blank content
                frame = av.AudioFrame(format="s16", layout="mono", samples=samples)
                for p in frame.planes:
                    p.update(bytes(p.buffer_size))
                frame.pts = self._timestamp
                frame.sample_rate = sample_rate
                frame.time_base = fractions.Fraction(1, sample_rate)
                return frame
        except:
            # send blank content
            frame = av.AudioFrame(format="s16", layout="mono", samples=samples)
            for p in frame.planes:
                p.update(bytes(p.buffer_size))
            frame.pts = self._timestamp
            frame.sample_rate = sample_rate
            frame.time_base = fractions.Fraction(1, sample_rate)
            return frame

    async def play(self):
        self.playing = True
        while self.readyState == "live":
            path = await self.queue.get()
            if path is None:
                break
            done = asyncio.Event()
            logger.info("*********************** Play file: %s", path)
            self.player = MediaPlayer(path)
            await asyncio.sleep(0.5)
            @self.player.audio.on("ended")
            def on_ended():
               self.player = None
               self.queue.task_done()
               done.set()

            await done.wait()

    async def stop(self):
        self.playing = False
        if self.player and self.player.audio:
            self.player.audio.stop()
        await self.queue.put(None)
