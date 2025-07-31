import importlib.metadata
import argparse
import asyncio
import importlib
import json
import logging
import os
import re
import signal
import ssl
import sys
import uuid
import threading

import aiohttp
from aiohttp import web, WSMsgType
from aiohttp.web_ws import WebSocketResponse
from aiohttp.web import Response

from marshmallow import ValidationError

from aiortc import (
    RTCSessionDescription,
    RTCPeerConnection,
    RTCRtpSender,
    RTCIceServer,
    RTCConfiguration,
)

from pyee import EventEmitter

from mgw_svc_core.helpers.lazy_import import LazyImport

from utils.config import (
    load_and_register_transformers_plugin,
    load_config,
    validate_config,
)
from mgw_svc_core.transformers_core.Transform import Transform

#added
logging.getLogger("numba").setLevel(logging.ERROR)
logging.getLogger("aiortc").setLevel(logging.INFO)

AudioTransformModule = LazyImport('mgw_svc_core.transformers_core.audio.AudioTransform')
AudioTransform = AudioTransformModule.module.AudioTransform

# optional, for better performance
try:
    import uvloop
except ImportError:
    uvloop = None


ROOT = os.path.dirname(__file__)

logger = logging.getLogger("pc")
pcs = set()

pc_dict = {}

config = None

#ice_server_urls = os.environ.get("ICESERVER_URLS", "stun:stun.l.google.com:19302,turn:192.167.149.18:3478?transport=udp")
#ice_server_username = os.environ.get("ICESERVER_USERNAME", "turnuser")
#ice_server_credential = os.environ.get("ICESERVER_CREDENTIAL", "turnpass")
ice_server_urls = os.environ.get("ICESERVER_URLS", None)
ice_server_username = os.environ.get("ICESERVER_USERNAME", None)
ice_server_credential = os.environ.get("ICESERVER_CREDENTIAL", None)



if ice_server_urls is not None:
    ice_server_urls = ice_server_urls.split(",")

    config = RTCConfiguration(
        [
            RTCIceServer(
                ice_server_urls,
                username=ice_server_username,
                credential=ice_server_credential,
                credentialType="password",
            )
        ]
    )


async def index(request):
    content = open(os.path.join(ROOT, "..", "..", "public", "index.html"), "r").read()
    return web.Response(content_type="text/html", text=content)


async def callback_handler(request):
    content = await request.json()
    sid = content.get("recipient_id")
    sid = sid.strip('"')
    logger.info(f"I am in the callback handler. SID : {sid}")
    # find associated peerconnection
    result = pc_dict.get(sid)
    if result is not None:
        logger.info(f"Result is not none")
        # send content to event emitter
        ee = result.get("event_emitter")
        ee.emit("callback", {"path": request.url.path, "content": content})
    else:
        logger.info(f"Result is none")
    # Process http response
    text = content.get("text")
    return web.Response(
        content_type="text/html",
        text=f"<html><body><h1>{sid}</h1><p>{text}</p></body></html>",
    )

def javascript(request):
    try:
        path = os.path.join(ROOT, "..", "..", "public", "client.js")
        print(f"[DEBUG] Trying to open: {path}")
        with open(path, "r") as f:
            content = f.read()

        regex = r"//getStunServers(.*?)//getStunServers - end"
        servers_part = ",".join(f'"{s}"' for s in ice_server_urls) if ice_server_urls else ""
        username_part = f'"username": "{ice_server_username}",' if ice_server_username else ""
        credential_part = f'"credential": "{ice_server_credential}",' if ice_server_credential else ""
        credential_type_part = '"credentialType": "password"' if ice_server_username or ice_server_credential else ""

        replacement = f"""
getStunServers = function () {{
    return {{
        "servers": [{servers_part}],
        {username_part}
        {credential_part}
        {credential_type_part}
    }}
}}
        """
        content = re.sub(regex, replacement, content, flags=re.DOTALL)
        return web.Response(content_type="application/javascript", text=content)

    except Exception as e:
        print(f"[ERROR] Failed to serve client.js: {e}")
        return web.Response(status=500, text="Internal Server Error")


async def on_shutdown(app):
    # close peer connections
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()
    pc_dict = {}


async def config_handler(ws, message):
    logger.info("Configuration Handler")
    if message["data"].get("iceServers"):
        iceServers = message["data"].get("iceServers")

        rtcIceServers = []
        for iceServer in iceServers:
            rtcIceServers.append(
                RTCIceServer(
                    ",".join(iceServer.get("urls")),
                    username=iceServer.get("username"),
                    credential=iceServer.get("credential"),
                )
            )
        ws.config = RTCConfiguration(rtcIceServers)


async def connected_handler(ws, message):
    logger.info("Websocket connected")


async def heartbeat_handler(ws, message):
    logger.debug("Heartbeat")


async def closed_handler(ws, message):
    logger.info("Websocket closed")
    pass


async def offer_handler(ws: WebSocketResponse, message):
    logger.info("server offer_handler Offer requested")
    offer = RTCSessionDescription(sdp=message["sdp"], type=message["type"])

    pc = RTCPeerConnection(configuration=ws.config)
    pc_id = "PeerConnection(%s)" % uuid.uuid4()
    pcs.add(pc)

    sid = message["sid"]
    callId = message["callId"]

    event_emitter = EventEmitter()

    def log_info(msg, *args):
        logger.info(pc_id + " " + sid + " " + msg, *args)

    async def send_json(msg):
        try:
            if not ws.closed:
                await ws.send_json(msg)
        except Exception as e:
            logger.info("Except")
            pass

    transformers = Transform.extract_tranformers(
        message["options"], ws, callId, sid, pc, pc_dict, event_emitter
    )

    for transf in transformers:
        await transf.pre_processing(pc)
        
    @pc.on("datachannel")
    def on_datachannel(channel):
        @channel.on("message")
        def on_message(message):
            if isinstance(message, str) and message.startswith("ping"):
                channel.send("pong" + message[4:])

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        log_info("Connection state is %s", pc.connectionState)
        await send_json(
            {
                "type": "connectionState",
                "state": pc.connectionState,
                "sid": sid,
                "callId": callId,
            }
        )

        if pc.connectionState == "failed":
            await pc.close()
            pcs.discard(pc)
            result = None
            for _pc in pc_dict.items():
                if _pc[1].get("pc") == pc:
                    result = _pc[0]
            del pc_dict[result]

    @pc.on("iceconnectionstatechange")
    async def on_iceconnectionstatechange():
        log_info("ICE Connection state is %s", pc.iceConnectionState)
        await send_json(
            {
                "type": "iceConnectionState",
                "state": pc.iceConnectionState,
                "sid": sid,
                "callId": callId,
            }
        )

    @pc.on("icegatheringstatechange")
    async def on_iceconnectionstatechange():
        log_info("ICE Gathering state is %s", pc.iceGatheringState)
        await send_json(
            {
                "type": "iceGatheringState",
                "state": pc.iceGatheringState,
                "sid": sid,
                "callId": callId,
            }
        )

    @pc.on("signalingstatechange")
    async def on_iceconnectionstatechange():
        log_info("Signaling state is %s", pc.signalingState)
        await send_json(
            {
                "type": "signalingState",
                "state": pc.signalingState,
                "sid": sid,
                "callId": callId,
            }
        )

    @pc.on("track")
    def on_track(track):
        log_info("Track %s received", track.kind)

        for transf in transformers:
            transf.do_processing(track)

        @track.on("ended")
        async def on_ended():
            log_info("Track %s ended", track.kind)
            for transf in transformers:
                await transf.on_track_ended()

    # handle offer
    await pc.setRemoteDescription(offer)

    for transf in transformers:
        await transf.pre_sdp_negociation(pc)

    # send answer
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    pc_dict[sid] = {"pc": pc, "blackhole": None, "event_emitter": event_emitter}
    await send_json(
        {
            "sdp": pc.localDescription.sdp,
            "type": pc.localDescription.type,
            "sid": sid,
            "callId": callId,
        }
    )

    for transf in transformers:
        await transf.post_sdp_negociation(pc)


async def request_offer_handler(ws, message):
    logger.info("Request offer received")
    pc_reverse = RTCPeerConnection(configuration=ws.config)
    pcs.add(pc_reverse)

    pc_id = "PeerConnection(%s)" % uuid.uuid4()

    sid = message["sid"]
    callId = message["callId"]

    event_emitter = EventEmitter()

    def log_info(msg, *args):
        logger.info(pc_id + " " + sid + " " + msg, *args)

    async def send_json(msg):
        try:
            if not ws.closed:
                await ws.send_json(msg)
        except Exception as e:
            logger.info("Except")
            pass

    transformers = Transform.extract_tranformers(
        message["options"], ws, callId, sid, pc_reverse, pc_dict, event_emitter
    )

    for transf in transformers:
        await transf.pre_processing(pc_reverse)

    @pc_reverse.on("datachannel")
    def on_datachannel(channel):
        @channel.on("message")
        def on_message(message):
            if isinstance(message, str) and message.startswith("ping"):
                channel.send("pong" + message[4:])

    @pc_reverse.on("connectionstatechange")
    async def on_connectionstatechange():
        log_info("Connection state is %s", pc_reverse.connectionState)
        try:
            await send_json(
                {
                    "type": "connectionState",
                    "state": pc_reverse.connectionState,
                    "sid": sid,
                    "callId": callId,
                }
            )
        except Exception:
            pass
        if pc_reverse.connectionState == "failed":
            await pc_reverse.close()
            pcs.discard(pc_reverse)
            result = None
            for _pc in pc_dict.items():
                if _pc[1].get("pc") == pc_reverse:
                    result = _pc[0]
            del pc_dict[result]

    @pc_reverse.on("iceconnectionstatechange")
    async def on_iceconnectionstatechange():
        log_info("ICE Connection state is %s", pc_reverse.iceConnectionState)
        await send_json(
            {
                "type": "iceConnectionState",
                "state": pc_reverse.iceConnectionState,
                "sid": sid,
                "callId": callId,
            }
        )

    @pc_reverse.on("icegatheringstatechange")
    async def on_iceconnectionstatechange():
        log_info("ICE Gathering state is %s", pc_reverse.iceGatheringState)
        await send_json(
            {
                "type": "iceGatheringState",
                "state": pc_reverse.iceGatheringState,
                "sid": sid,
                "callId": callId,
            }
        )

    @pc_reverse.on("signalingstatechange")
    async def on_iceconnectionstatechange():
        log_info("Signaling state is %s", pc_reverse.signalingState)
        await send_json(
            {
                "type": "signalingState",
                "state": pc_reverse.signalingState,
                "sid": sid,
                "callId": callId,
            }
        )

    @pc_reverse.on("track")
    def on_track(track):
        log_info("Track %s received", track.kind)

        for transf in transformers:
            transf.do_processing(track)

        @track.on("ended")
        async def on_ended():
            log_info("Track %s ended", track.kind)
            for transf in transformers:
                await transf.on_track_ended()

    # Create offer
    offer = await pc_reverse.createOffer()
    await pc_reverse.setLocalDescription(offer)

    kinds = {}
    for transf in transformers:
        kinds[transf.kind] = True
    kind = str.join("+", sorted(kinds.keys()))

    sid = message["sid"]  # + "-reverse"
    callId = message["callId"]
    pc_dict[sid] = {
        "pc": pc_reverse,
        "transformers": transformers,
        "event_emitter": event_emitter,
    }
    await send_json(
        {
            "sdp": pc_reverse.localDescription.sdp,
            "type": pc_reverse.localDescription.type,
            "sid": sid,
            "callId": callId,
            "kind": kind,
        }
    )


async def answer_handler(ws, message):
    logger.info("Answer received")
    result = pc_dict.get(message.get("sid"))
    if result is None:
        logger.error("Unexpected answer message with sid %s", message.get("sid"))
        return

    sdp = message["sdp"]
    if "m=application" in sdp:
        sdp = sdp.replace("group:BUNDLE 2", "group:BUNDLE 0")
        sdp = sdp.replace("a=mid:2", "a=mid:0")

    answer = RTCSessionDescription(sdp=sdp, type=message["type"])
    await result.get("pc").setRemoteDescription(answer)
    if result.get("transformers") is not None:
        for transf in result.get("transformers"):
            await transf.pre_sdp_negociation(result.get("pc"))
            await transf.post_sdp_negociation(result.get("pc"))


async def close_peer_connection(ws, message):
    logger.info("Close peerconnection received")
    result = pc_dict.get(message.get("sid"))
    if result is not None:
        await result.get("pc").close()
    pass


async def ping_handler(ws, message):
    try:
        if not ws.closed:
            await ws.send_json({"type": "pong"})
    except Exception as e:
        logger.info("Except")
        pass


async def active_talkers(ws, message):
    logger.info("Active talkers message received")
    callId = message["callId"]
    sid = message["sid"]
    talkers = message["talkers"]

    result = pc_dict.get(sid)
    if result is None:
        logger.error(
            "Unexpected active talkers message with sid %s", message.get("sid")
        )
        return

    ee = result.get("event_emitter")
    if ee is None:
        logger.error("No Event Emitter defined for sid %s", message.get("sid"))
        return

    ee.emit("active-talkers", message)

    # Find associated Peer Connection

    # TODO forward the information if a service is requiering it.

async def get_capabilities(ws, message):
    try:
        if not ws.closed:
            result = {
                'type': "capabilities",
                'data': Transform.get_capabilities()
            }
            await ws.send_json(result)
    except Exception as e:
        logger.info("Except")
        pass



async def default_handler(ws, message):
    logger.info("Unexpected message", message)


async def register_audio_transformer(request):
    # get json body with transformer id and channel and target definitions
    content = await request.json()
    logger.info(f"register_audio_transformer {content}")
    transformer_id = content["id"]
    channel_id = content["channel"]["id"]
    channel_mod = content["channel"]["module"]
    channel_cls = content["channel"]["class"]

    channel_module = importlib.import_module(channel_mod)
    channel_class = getattr(channel_module, channel_cls)  # Get the class by name

    # get the channel and target class from their names,
    target_id = content["target"]["id"]
    target_mod = content["target"]["module"]
    target_cls = content["target"]["class"]
    target_module = importlib.import_module(target_mod)
    target_class = getattr(target_module, target_cls)  # Get the class by name

    # call AudioTransform.register_transformer
    AudioTransform.register_transformer(
        transformer_id,
        {"channel": (channel_id, channel_class), "target": (target_id, target_class)},
    )

    # ALTERNATIVE: add in AudioTransform a default registering from a file
    # given using an environment variable

    return web.Response(text="Success", status=200)


async def websocket_handler(request):
    ws = web.WebSocketResponse()
    ws.config = config

    await ws.prepare(request)

    d = {
        "config": config_handler,
        "connected": connected_handler,
        "control": connected_handler,
        "closed": closed_handler,
        "heartbeat": heartbeat_handler,
        "offer": offer_handler,  # offer_handler_old,
        "answer": answer_handler,
        "request-offer": request_offer_handler,
        "close-peer-connection": close_peer_connection,
        "active-talkers": active_talkers,
        "ping": ping_handler,
        "get-capabilities": get_capabilities,
    }

    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            try:
                message = json.loads(msg.data)
                if message and message["type"]:
                    handler = d.get(message["type"], default_handler)
                    await handler(ws, message)
            except ValidationError as e:
                print(msg.data)
                pass
        elif msg.type == aiohttp.WSMsgType.PING:
            await ws.pong()
        elif msg.type == aiohttp.WSMsgType.PONG:
            print("Pong received")
        elif msg.type == web.WSMsgType.CLOSE:
            await ws.close()
        elif msg.type == WSMsgType.ERROR:
            print("ws connection closed with exception %s" % ws.exception())
            await ws.close()
        else:
            print("Non supported type received")

    return ws


def force_codec(pc, sender, forced_codec):
    kind = forced_codec.split("/")[0]
    codecs = RTCRtpSender.getCapabilities(kind).codecs
    transceiver = next(t for t in pc.getTransceivers() if t.sender == sender)
    transceiver.setCodecPreferences(
        [codec for codec in codecs if codec.mimeType == forced_codec]
    )


def aiohttp_server():

    app = web.Application()
    app.on_shutdown.append(on_shutdown)
    
    # Middleware to add necessary headers
    @web.middleware
    async def add_cross_origin_headers(request, handler):
        response = await handler(request)
        response.headers['Cross-Origin-Opener-Policy'] = 'same-origin'
        response.headers['Cross-Origin-Embedder-Policy'] = 'require-corp'
        return response

    app.middlewares.append(add_cross_origin_headers)
    
    app.router.add_get("/", index)
    app.router.add_get("/client.js", javascript)
    app.router.add_post("/callback/{service}", callback_handler)

    app.add_routes(
        [
            web.get("/ws", websocket_handler),
            web.post("/register-audio-transformer", register_audio_transformer),
        ]
    )
    
    app.router.add_static('/vcaa/', path=os.path.join(ROOT, "..", "..", "public", "vcaa"), name='vcaa', append_version=True)
    


    runner = web.AppRunner(app)
    return runner


def run_server(runner, host, port, ssl_context):

    # if uvloop is not None:
    #    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

    loop = asyncio.new_event_loop()
    loop.run_until_complete(runner.setup())
    site = web.TCPSite(runner, host, port, ssl_context=ssl_context)
    loop.run_until_complete(site.start())
    loop.run_forever()


if __name__ == "__main__":
    print(sys.argv)
    parser = argparse.ArgumentParser(
        description="WebRTC audio / video / data-channels demo"
    )
    parser.add_argument("--cert-file", help="SSL certificate file (for HTTPS)")
    parser.add_argument("--key-file", help="SSL key file (for HTTPS)")
    parser.add_argument(
        "--host", default="0.0.0.0", help="Host for HTTP server (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Port for HTTP server (default: 8080)"
    )
    parser.add_argument("--record-to", help="Write received media to a file."),
    parser.add_argument("--verbose", "-v", action="count")
    parser.add_argument("--config", type=str, help="Path to the configuration file")

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
        logging.root.setLevel(logging.DEBUG)

        # logging.basicConfig(filename='traces.log', filemode='w', level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
        logging.root.setLevel(logging.INFO)

    if args.cert_file:
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(args.cert_file, args.key_file)
    else:
        ssl_context = None

    # Config loading
    default_path = "/etc/webrtc-service/config.yaml"
    config_path = args.config if args.config else default_path

    if not os.path.exists(config_path):
        print(f"Configuration file not found at {config_path}")
        exit

    configuration = load_config(config_path)
    validate_config(configuration)

    load_and_register_transformers_plugin(configuration.get("transformers"))

    # Process loop startup
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.add_signal_handler(signal.SIGINT, loop.stop)

    t = threading.Thread(
        target=run_server, args=(aiohttp_server(), args.host, args.port, ssl_context)
    )
    t.start()
    t.join()
