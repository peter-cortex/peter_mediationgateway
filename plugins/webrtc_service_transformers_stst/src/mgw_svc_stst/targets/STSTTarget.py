import aiohttp
import asyncio
import json
import logging
import os
from typing import Dict

from aiortc.contrib.media import MediaBlackhole
from mgw_svc_core.transformers_core.targets.DataTarget import DataTarget

logger = logging.getLogger("STSTTarget")

bias = {
  "en": [
    "the",
    "www.mooji.org",
    "<u>Transcribed</u> by https://otter.ai"
  ],
  "nl": [
    "Ondertitels ingediend door de Amara.org gemeenschap",
    "Ondertiteld door de Amara.org gemeenschap",
    "Ondertiteling door de Amara.org gemeenschap"
  ],
  "de": [
    "Untertitelung aufgrund der Amara.org-Community"
    "Untertitel im Auftrag des ZDF für funk, 2017",
    "Untertitel von Stephanie Geiges",
    "Untertitel der Amara.org-Community",
    "Untertitel im Auftrag des ZDF, 2017",
    "Untertitel im Auftrag des ZDF, 2020",
    "Untertitel im Auftrag des ZDF, 2018",
    "Untertitel im Auftrag des ZDF, 2021",
    "Untertitelung im Auftrag des ZDF, 2021",
    "Copyright WDR 2021",
    "Copyright WDR 2020",
    "Copyright WDR 2019",
    "SWR 2021",
    "SWR 2020",
  ],
  "fr": [
    "– Sous-titrage Réalisé par Le Crayon d'oreille –",
    "Abonne-toi!",
    "Les autres sous-titres réalisés par la communauté d'Amara.org",
    "Sous-titrage Société Radio-Canada",
    "Sous-titres réalisés para la communauté d'Amara.org",
    "Sous-titres réalisés par la communauté d'Amara.org",
    "Sous-titres fait par Sous-titres par Amara.org",
    "Sous-titres réalisés par les SousTitres d'Amara.org",
    "Sous-titres par Amara.org",
    "Sous-titres par la communauté d'Amara.org",
    "Sous-titres réalisés pour la communauté d'Amara.org",
    "Sous-titres réalisés par la communauté de l'Amara.org",
    "Sous-Titres faits par la communauté d'Amara.org",
    "Sous-titres par l'Amara.org",
    "Sous-titres fait par la communauté d'Amara.org"
    "Sous-titrage ST' 501",
    "Sous-titrage ST'501",
    "Cliquez-vous sur les sous-titres et abonnez-vous à la chaîne d'Amara.org",
    "❤️ par SousTitreur.com",
  ],
  "it": [
    "Sottotitoli creati dalla comunità Amara.org",
    "Sottotitoli di Sottotitoli di Amara.org",
    "Sottotitoli e revisione al canale di Amara.org",
    "Sottotitoli e revisione a cura di Amara.org",
    "Sottotitoli e revisione a cura di QTSS",
    "Sottotitoli e revisione a cura di QTSS.",
    "Sottotitoli a cura di QTSS",
  ],
  "es": [
    "Subtítulos realizados por la comunidad de Amara.org",
    "Subtitulado por la comunidad de Amara.org",
    "Subtítulos por la comunidad de Amara.org",
    "Subtítulos creados por la comunidad de Amara.org",
    "Subtítulos en español de Amara.org",
    "Subtítulos hechos por la comunidad de Amara.org",
    "Subtitulos por la comunidad de Amara.org"
    "Más información www.alimmenta.com",
    "www.mooji.org",
  ],
  "gl": [
    "Subtítulos realizados por la comunidad de Amara.org"
  ],
  "ja": [
    "by H.",
  ],
  "la": [
    "Sottotitoli creati dalla comunità Amara.org",
    "Sous-titres réalisés para la communauté d'Amara.org"
  ],
  "ln": [
    "Sous-titres réalisés para la communauté d'Amara.org"
  ],
  "pl": [
    "Napisy stworzone przez społeczność Amara.org",
    "Napisy wykonane przez społeczność Amara.org",
    "Zdjęcia i napisy stworzone przez społeczność Amara.org",
    "napisy stworzone przez społeczność Amara.org",
    "Tłumaczenie i napisy stworzone przez społeczność Amara.org",
    "Napisy stworzone przez społeczności Amara.org",
    "Tłumaczenie stworzone przez społeczność Amara.org",
    "Napisy robione przez społeczność Amara.org"
    "www.multi-moto.eu",
  ],
  "pt": [
    "Legendas pela comunidade Amara.org",
    "Legendas pela comunidade de Amara.org",
    "Legendas pela comunidade do Amara.org",
    "Legendas pela comunidade das Amara.org",
    "Transcrição e Legendas pela comunidade de Amara.org"
  ],
  "ru": [
    "Редактор субтитров А.Синецкая Корректор А.Егорова"
  ],
  "tr": [
    "Yorumlarınızıza abone olmayı unutmayın.",
  ],
  "su": [
    "Sottotitoli creati dalla comunità Amara.org"
  ],
  "zh": [
    "字幕由Amara.org社区提供",
    "小編字幕由Amara.org社區提供",
    "請不吝點贊訂閱轉發打賞支持明鏡與點點欄目"
  ]
}

class STSTTarget(DataTarget):

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
        logger.debug("STSTTarget.__init__")

    async def create_websocket_channel(self, websocket):
        logger.info(f"CREATE_WEBSOCKET_CHANNEL CALLED!!")
        def channel(): return None
        _channel = channel
        _channel.sid = self.sid

        async def send(msg):
            try:
                jsonmsg = json.loads(msg)
                logger.info(f"STSTTarget new send: {jsonmsg}")
                logger.info("---------- STSTTarget.send() CALLED!")
                if ('data' in jsonmsg and 'text' in jsonmsg['data']
                        and jsonmsg['data']['text'] in bias["en"]):
                    logger.debug(f"STSTTarget.pre_processing.send Ignoring "
                                 f"biased transcription")
                    return
                logger.debug(f"STSTTarget.pre_processing.send "
                             f"{jsonmsg['data']}")
                message = None
                if ("type" in jsonmsg and jsonmsg["type"] == "transcript"
                        and "data" in jsonmsg):
                    message = {
                      "sid": self.sid,
                      "voice": "af",
                      "text": jsonmsg['data'],
                      "action": "start"}
                else:
                    logger.info("STSTTarget send: no usable data in received "
                                "message")
                if message is not None:
                    logger.info(
                      f"STSTTarget.pre_processing.send sending to callback: "
                      f"{message}")
                    logger.info(f"---------- EMITTING TTS: {message}")
                    self.ee.emit("tts_request", message )
            except Exception as e:
                logger.info(f"STSTTarget Exception during call to STST: {e}")
                pass

        _channel.readyState = 'open'
        _channel.send = send

        @self.ee.on("callback")
        def on_callback(message):
            logger.info(f"STSTTarget on_callback {message}")

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
