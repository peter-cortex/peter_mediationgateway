# peter_mediationgateway

## How to use
Build the image
```
sudo docker build -f Dockerfile.PETER -t peter_mgw .
```

## Run the image
For Linux with the pipeline running in a server:
```
sudo docker run --gpus all -p 8443:8443 -e VERBOSE="--verbose" -e SRC_LANG="en" -e TRG_LANG="it" -e MAX_CHUNK_DURATION=5.0 -e URGENCY_FROM="both" -e ICESERVER_URLS="stun:stun.l.google.com:19302,turn:192.167.149.18:3478?transport=udp" -e ICESERVER_USERNAME="turnuser" -e ICESERVER_CREDENTIAL="turnpass" -v ${PWD}/certs/server.crt:/app/certs/cert.pem -v ${PWD}/certs/server.key:/app/certs/key.pem -v ${PWD}/config/config.peter.yaml:/app/config/config.yaml --entrypoint python3 peter_mgw /app/mediation_gateway_service/src/webrtc_service/server.py --port 8443 --cert-file /app/certs/cert.pem --key-file /app/certs/key.pem --config /app/config/config.yaml --verbose
```

Go to https://<server_address>:8443/
Uncheck datachannel 
Check "Use STUN server"
Click "Start"

## Paramenters:
- -p : port to use
- SRC_LANG : language of incoming audio
- TRG_LANG : language to translate into
- MAX_CHUNK_DURATION : maximum duration in seconds of a chunk
- URGENCY_FROM : [both, text, audio] source to consider for the urgency classification
- ICESERVER_URLS : urls of the stun/turn server
- ICESERVER_USERNAME : username for the turn server
- ICESERVER_CREDENTIAL : password for the turn server
- ${PWD}/certs/server.crt:/app/certs/cert.pem : volumes of the self signed certificate
- ${PWD}/certs/server.key:/app/certs/key.pem : volumes of the self signed certificate
- ${PWD}/config/config.peter.yaml:/app/config/config.yaml : volumes of the configuration file
  

For Windows with the pipeline running in local:
```
sudo docker run --gpus all -p 8443:8443 -e VERBOSE="--verbose" -e SRC_LANG="en" -e TRG_LANG="it" -e MAX_CHUNK_DURATION=5.0 -e URGENCY_FROM="both" -e ICESERVER_URLS="stun:stun.l.google.com:19302" -e ICESERVER_USERNAME="" -e ICESERVER_CREDENTIAL="" -v "$PWD\certs\server.crt:/app/certs/cert.pem" -v "$PWD\certs\server.key:/app/certs/key.pem" -v "$PWD\config\config.peter.yaml:/app/config/config.yaml" --entrypoint python3 peter_mgw /app/mediation_gateway_service/src/webrtc_service/server.py --port 8443 --cert-file /app/certs/cert.pem --key-file /app/certs/key.pem --config /app/config/config.yaml --verbose
```
Go to https://localhost:8443/
Uncheck datachannel 
Check "Use STUN server" (optional)
Click "Start"

