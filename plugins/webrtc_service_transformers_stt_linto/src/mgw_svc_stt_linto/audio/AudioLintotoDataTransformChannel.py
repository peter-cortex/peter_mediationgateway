import json
from aiortc.mediastreams import MediaStreamError
import asyncio
import pydub
import os
import numpy as np
from typing import Dict
import logging

import yarl

import aiohttp
from aiohttp import ClientSession
from aiohttp import ClientWebSocketResponse

from mgw_svc_core.transformers_core.audio.AudioDataTransformChannel import AudioDataTransformChannel

logger = logging.getLogger(__name__)

MAX_SILENCE_DURATION: float = 0.2  # seconds

linto_username: str = os.environ.get('LINTO_WS_CREDENTIAL_USERNAME', None)
linto_password: str = os.environ.get('LINTO_WS_CREDENTIAL_PASSWORD', None)
linto_url:str = os.environ.get('LINTO_WS_URL', None)  # wss://api.linto.ai/stt-us-streaming/streaming"


class AudioLintotoDataTransformChannel(AudioDataTransformChannel):
    """
    A audio stream track that transforms frames into transcript text.
    """

    kind = "audio"

    def __init__(self, track, channel, transform, event_emitter,
                 params: Dict[str, str] = None):
        # don't forget this!
        super().__init__(track, channel, transform, event_emitter, params)
        self.linto_init()
        self.transcript_init_done = False

    @staticmethod
    def create_transformer(track, channel, transform,
                           event_emitter, params: Dict[str, str] = None):
        return AudioLintotoDataTransformChannel(
            track, channel, transform, event_emitter, params=params)

    def linto_init(self):
        # Linto init
        self.linto_ws = None

        if linto_url is None:
            raise Exception("Missing Linto URL!")

        async def linto_ws_dispatch(ws: ClientWebSocketResponse,
                                    last_sentence: str) -> None:
            while True:
                msg = await ws.receive()
                logger.debug(f"linto_ws_dispatch: message type: {msg.type}")

                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data.strip())
                    text = ''
                    if 'text' in data:
                        text = data["text"]

                    if text != last_sentence:
                        last_sentence = text
                        if text == '':
                            logger.info(f"linto_ws_dispatch: no text in {data}")
                            continue
                        if self.channel is not None:
                            logger.info(f"AudioLintotoDataTransformChannel._transcribe sending: {last_sentence}")
                            try:
                                result = {
                                    'sid': self.channel.sid,
                                    'type': 'transcript',
                                    'data': last_sentence
                                }
                                await self.channel.send(
                                    json.dumps(result, ensure_ascii=False))
                            except Exception as e:
                                logger.error(f"linto_ws_dispatch got exception"
                                             f" sending to channel: {e}")
                                traceback.print_tb(e.__traceback__)
                                pass
                        else:
                            logger.info(f"AudioLintotoDataTransformChannel._transcribe linto_ws_dispatch channel is None")

                elif msg.type == aiohttp.WSMsgType.BINARY:
                    logger.info("Binary: ", msg.data)
                elif msg.type == aiohttp.WSMsgType.PING:
                    logger.info("Ping received")
                    await ws.pong()
                elif msg.type == aiohttp.WSMsgType.PONG:
                    logger.info("Pong received")
                elif msg.type == aiohttp.WSMsgType.CLOSE:
                    logger.info("Close received")
                    await ws.close()
                    break
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error("Error during receive %s" % ws.exception())
                    break
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    logger.info("Closed received")
                    pass
                else:
                    logger.info(f"linto_ws_dispatch: unhandled message type: "
                                 f"{msg.type}")

        async def linto_ws_handler() -> None:

            client = ClientSession()
            url = yarl.URL(linto_url)

            try:
                self.linto_ws = await client.ws_connect(
                    url,
                    auth=aiohttp.BasicAuth(linto_username, linto_password),
                    autoclose=False,
                    autoping=True)
            except aiohttp.client_exceptions.InvalidURL:
                logger.error(f"Exception in linto_ws_handler: invalid url "
                             f"{url}")
                return

            last_sentence = ""
            await linto_ws_dispatch(self.linto_ws, last_sentence)

        loop = asyncio.get_event_loop()
        loop.create_task(linto_ws_handler())

    async def _transcribe(self):
        logger.info(f"AudioLintotoDataTransformChannel._transcribe")

        if self.linto_ws is None:
            logger.warn(f"AudioLintotoDataTransformChannel._transcribe Linto is not ready")
            return ""

        if self.transcript_init_done is False:
            await self.linto_ws.send_str(
                f'{{"config" : {{"sample_rate" : '
                f'{self.sound_chunk.frame_rate}}}}}')
            self.transcript_init_done = True

        buffer = np.array(self.sound_chunk.get_array_of_samples())
        if not self.linto_ws.closed:
            logger.debug(f"AudioLintotoDataTransformChannel._transcribe sending to Linto")
            await self.linto_ws.send_bytes(buffer.tobytes())

        return ""
