import aiohttp
import asyncio
import json
import logging
import os
from typing import Dict

from aiortc.contrib.media import MediaBlackhole
from mgw_svc_core.transformers_core.targets.DataTarget import DataTarget
from mgw_svc_peter.audio.playback.AudioPETERTTSTrack import AudioPETERTTSTrack

logger = logging.getLogger("PETERSTSTTarget")


class PETERSTSTTarget(DataTarget):

    def __init__(self,
                 kind,
                 mediaStack,
                 transform,
                 websocket,
                 callId,
                 sid,
                 peer_connection,
                 peer_connection__dict,
                 event_emitter=None,
                 params: Dict[str, str] = None) -> None:
        super().__init__(kind, mediaStack, transform, websocket, callId, sid,
                         peer_connection, peer_connection__dict,
                         event_emitter, params=params)
        logger.debug("PETERSTSTTarget.__init__")

        self.params = params or {}
        logger.info(f"[PETERSTSTTarget] Params SELF: {self.params}")
        logger.info(f"[PETERSTSTTarget] Params DIRETTO: {params}")

    def create_audio_track(self):
        audioTrack = AudioPETERTTSTrack(self.ee)

        @self.ee.on("say")
        async def on_say(message):
            logger.debug(f"PETERSTSTTarget on_say: {message}")
            payload = message.copy()
            if 'options' in payload and 'voice' in payload['options']:
                payload['voice'] = payload['options']['voice']
            self.ee.emit("tts_request", payload)

        return audioTrack

    async def create_websocket_channel(self, websocket):
        logger.info(f"CREATE_WEBSOCKET_CHANNEL CALLED!!")
        def channel(): return None
        _channel = channel
        _channel.sid = self.sid

        async def send(msg):
            try:
                jsonmsg = json.loads(msg)
                logger.info(f"PETERSTSTTarget new send: {jsonmsg}")
                logger.info("PETERSTSTTarget.send() CALLED!")
                logger.info(f"[PETERSTSTTarget] Params: {self.params}")
                language = self.params.get("language", "it")
                logger.info(f"[PETERSTSTTarget] Language: {language}")
                logger.debug(f"PETERSTSTTarget.pre_processing.send "
                             f"{jsonmsg['data']}")
                message = None
                if ("type" in jsonmsg and jsonmsg["type"] == "transcript"
                        and "data" in jsonmsg):
                    message = {
                      "sid": self.sid,
                      "voice": "af",
                      "text": jsonmsg['data'],
                      "language": language,
                      "action": "start"}
                else:
                    logger.info("PETERSTSTTarget send: no usable data in received "
                                "message")
                if message is not None:
                    logger.info(
                      f"PETERSTSTTarget.pre_processing.send sending to callback: "
                      f"{message}")
                    logger.info(f"EMITTING TTS: {message}")
                    self.ee.emit("tts_request", message )
            except Exception as e:
                logger.info(f"STSTTarget Exception during call to STST: {e}")
                pass

        _channel.readyState = 'open'
        _channel.send = send

        @self.ee.on("callback")
        def on_callback(message):
            logger.info(f"PETERSTSTTarget on_callback {message}")

            content = message.get('content').copy()
            try:
                if (content.get("audio") is not None
                        and isinstance(content.get("audio"), str)):
                    self.ee.emit("audio_play", content.get("audio"))
                elif not self.websocket.closed:
                    content["type"] = "transcript"
                    content["callId"] = self.callId
                    content["sid"] = content.pop("recipient_id")

                    asyncio.create_task(self.websocket.send_json(content))
            except Exception as e:
                logger.info(f'Except during callback : {message}')
                pass

        return channel
