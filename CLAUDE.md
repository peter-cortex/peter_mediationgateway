# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

**peter_mediationgateway** is a WebRTC mediation gateway with a pluggable transformer architecture for real-time audio/video processing. Its primary use case is the **PETER pipeline**: speech-to-text (WhisperX) → machine translation (Marian MT) → text-to-speech (XTTSv2) with emotion/urgency classification.

## Running the Server

```bash
python3 mediation_gateway_service/src/webrtc_service/server.py \
  --port 8443 \
  --cert-file certs/cert.pem \
  --key-file certs/key.pem \
  --config config/config.peter.yaml \
  --verbose
```

Key environment variables when using PETER plugin:
- `SRC_LANG`, `TRG_LANG` — language pair (en, fr, de, it)
- `MAX_CHUNK_DURATION` — audio chunk size in seconds
- `URGENCY_FROM` — urgency source: `both`, `text`, or `audio`
- `ICESERVER_URLS`, `ICESERVER_USERNAME`, `ICESERVER_CREDENTIAL` — STUN/TURN config

## Docker (PETER pipeline, GPU)

```bash
sudo docker build -f Dockerfile.PETER -t peter_mgw .

sudo docker run --gpus all -p 8443:8443 \
  -e SRC_LANG="en" -e TRG_LANG="it" \
  -e ICESERVER_URLS="stun:stun.l.google.com:19302" \
  -v ${PWD}/certs/server.crt:/app/certs/cert.pem \
  -v ${PWD}/config/config.peter.yaml:/app/config/config.yaml \
  --entrypoint python3 peter_mgw \
  /app/mediation_gateway_service/src/webrtc_service/server.py \
  --port 8443 --cert-file /app/certs/cert.pem --key-file /app/certs/key.pem \
  --config /app/config/config.yaml --verbose
```

## Installing Dependencies

```bash
python -m pip install -U pip setuptools wheel packaging build
pip install torch torchvision torchaudio
pip install -r requirements.peter.txt
```

## Architecture

### Core Server (`mediation_gateway_service/src/webrtc_service/server.py`)

- **aiohttp** async server handling WebSocket signaling and HTTP routes
- Manages `RTCPeerConnection` lifecycle via **aiortc**
- WebSocket message types: `offer`, `request-offer`, `answer`, `config`, `active-talkers`, `get-capabilities`, `close-peer-connection`
- HTTP routes: `GET /` (index), `GET /client.js` (injects ICE servers dynamically), `GET /ws` (WebSocket), `POST /register-audio-transformer`, `POST /callback/{service}`, `GET /vcaa/*`

### Plugin System

Plugins live under `plugins/` and must inherit from `WebRTCServicePluginInterface`. They are discovered via transformer names in the YAML config.

Plugin lifecycle hooks (in order):
1. `pre_processing()` — before SDP negotiation
2. `pre_sdp_negotiation()` — just before offer/answer sent
3. `do_processing()` — process live tracks
4. `post_sdp_negotiation()` — after negotiation completes
5. `on_track_ended()` — cleanup

Transformer types extracted per connection: `audio_transcript`, `video_transform`, `data_transform`.

### PETER Plugin (`plugins/webrtc_service_transformers_peter/`)

```
AudioPETERtoDataTransformChannel
  ├─ WhisperX (speech-to-text)
  ├─ Marian MT (translation)
  └─ Urgency classifier
       ↓
PETERSTSTTarget
  ├─ XTTSv2 (text-to-speech)
  └─ Audio sent back via data channel
```

All ML models are **preloaded at plugin registration time**, not per-connection.

### Configuration (`utils/config.py`)

YAML configs in `config/`. Validated with the `schema` library. Config references the plugin module path under `transformers[].name`. Example: `config/config.peter.yaml`.

### Web Client (`mediation_gateway_service/public/`)

`client.js` handles WebRTC peer connection setup, STUN/TURN negotiation, and the signaling protocol. ICE server config is injected server-side when `/client.js` is served.
