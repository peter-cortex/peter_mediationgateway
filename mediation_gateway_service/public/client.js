//get DOM elements
var dataChannelLog = document.getElementById('data-channel'),
    iceConnectionLog = document.getElementById('ice-connection-state'),
    iceGatheringLog = document.getElementById('ice-gathering-state'),
    signalingLog = document.getElementById('signaling-state');

//peer connection
var pc = null;
var pc2 = null;

//data channel
var dc = null, dcInterval = null;

//recording
let rec = null;
let recChunks = [];
let recMime = null;
let playbackUrl = null;


//creation of new MediaRecord
function startRecording(stream) {
  try {
    if (!window.MediaRecorder) {
      console.warn("MediaRecorder non supportato.");
      return;
    }

    //reset of pre existing
    try {
      if (rec && rec.state !== 'inactive') rec.stop();
    } catch {}
    rec = null;

    
    recMime =
      MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' :
      MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : '';

    //new recorder bonded to new stream
    rec = new MediaRecorder(stream, recMime ? { mimeType: recMime } : {});
    recChunks = [];
    rec.ondataavailable = (e) => { if (e.data && e.data.size) recChunks.push(e.data); };

    rec.start(1000); 
  } catch (e) {
    console.warn("startRecording error:", e);
  }
}

function stopRecordingToPlayer() {
  return new Promise((resolve) => {
    const player = document.getElementById('recording-audio');
    if (!rec || rec.state === 'inactive') {
      resolve(false);
      return;
    }
    rec.onstop = () => {
      try {
        if (playbackUrl) {
          URL.revokeObjectURL(playbackUrl);
          playbackUrl = null;
        }
        const blob = new Blob(recChunks, { type: recMime || 'audio/webm' });
        recChunks = [];
        playbackUrl = URL.createObjectURL(blob);

        player.srcObject = null;
        player.src = playbackUrl;
        player.currentTime = 0;

      } catch (e) {
        console.warn("stopRecordingToPlayer error:", e);
      } finally {
        //reset record for new start
        rec = null;
        resolve(true);
      }
    };
    try { rec.stop(); } catch { resolve(false); }
  });
}

//Reset called in start
function resetRecording() {
  try {
    if (rec && rec.state !== 'inactive') rec.stop();
  } catch {}
  rec = null;                
  recChunks = [];
  if (playbackUrl) {
    URL.revokeObjectURL(playbackUrl);
    playbackUrl = null;
  }
  const recEl = document.getElementById('recording-audio');
  if (recEl) {
    recEl.srcObject = null;
    recEl.src = '';
    recEl.currentTime = 0;
  }
}

//getStunServers
getStunServers = function () {
  return {
    "servers": [
      "stun:stun.l.google.com:19302",
      "stun:stun1.l.google.com:19302",
      "stun:stun2.l.google.com:19302",
      "stun:stun3.l.google.com:19302",
      "stun:stun4.l.google.com:19302",
      "stun:stun.ekiga.net",
      "stun:stun.stunprotocol.org:3478",
      "stun:stun.voipbuster.com",
      "stun:stun.voipstunt.com"
    ],
    "username": "",
    "credential": "",
    "credentialType": ""
  }
}
//getStunServers - end

//send text result to the page
const _values = () => document.querySelectorAll('.output-row .value'); // [0]=Urgency, [1]=Transcription, [2]=Translation
function updateUI({ transcription, translation, urgency }) {
  const vals = _values();
  if (urgency && vals[0]) {
    vals[0].textContent = urgency;
    vals[0].style.fontWeight = urgency === 'URGENT' ? '800' : '600';
    vals[0].style.color = urgency === 'URGENT' ? '#dc2626' : '#6b7280';
  }
  if (typeof transcription === 'string' && vals[1]) {
    vals[1].textContent = transcription;
  }
  if (typeof translation === 'string' && vals[2]) {
    vals[2].textContent = translation;
  }
}

function handleDCJSON(content) {
  if (!content || !content.type) return;

  if (content.type === 'result' && content.data) {
    const { transcription, translation, urgency } = content.data;
    updateUI({ transcription, translation, urgency });
    return;
  }

  if (content.type === 'transcript') {
    const meta = content.meta || {};
    const raw = typeof content.data === 'string' ? content.data : String(content.data ?? '');

    let urgency = meta.urgency;
    if (!urgency) {
      const m = raw.match(/^\s*\[(URGENT|NOT\s+URGENT)\]\s*(.*)$/i);
      urgency = m ? m[1].toUpperCase().replace(/\s+/g, ' ') : 'UNKNOWN';
    }

    let translation = meta.translation;
    if (!translation) {
      const m = raw.match(/^\s*\[(?:URGENT|NOT\s+URGENT)\]\s*(.*)$/i);
      translation = m ? m[1] : raw;
    }

    const transcription = typeof meta.transcription === 'string' ? meta.transcription : undefined;

    updateUI({ transcription, translation, urgency });
    return;
  }

}

//for set up the ready text 
function setTopBanner(text) {
  const bar = document.querySelector('.bar'); 
  if (bar) bar.textContent = text;
}

startWebsocket = function () {
    let protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
    let socket = new WebSocket(`${protocol}//${window.location.hostname}${window.location.port ? ":" + window.location.port : ""}/ws`);


    heartbeat = function () {
        if (!socket) return;
        if (socket.readyState !== 1) return;
        socket.send(JSON.stringify(
            {
                type: "heartbeat"
            }));
        setTimeout(heartbeat, 5000);
    }

    socket.onopen = function (e) {
        console.debug("[open] Connection established");
        console.debug("Sending to server");
        socket.send(JSON.stringify(
            {
                type: "control",
                state: "connected"
            }));
        
        authentication = getStunServers().credentialType ? {
            username: getStunServers().username,
            credential: getStunServers().credential,
            credentialType: getStunServers().credentialType
        } : {};
        socket.send(JSON.stringify(
            {
                type: "config",
                data: {
                    "iceServers": getStunServers().servers.map((server) => {
                        return { "urls": [server], ...authentication }
                    })
                }
            }));
        socket.send(JSON.stringify(
            {
                type: "get-capabilities",
            }
        ));
        heartbeat();
    };


    socket.onmessage = function (event) {
        let response = JSON.parse(event.data);
        switch (response.type) {
            case "answer":
                console.info(`[message] Answer received from server: ${event.data}`);
                console.debug("ANSWER SDP:\n", response.sdp);
                document.getElementById('answer-sdp').textContent = response.sdp;
                pc.setRemoteDescription(response);
                break;
            case "offer":
                console.info(`[message] Offer received from server: ${event.data}`);
                console.debug("OFFER SDP:\n", response.sdp);
                document.getElementById('offer-sdp').textContent = response.sdp;
                pc2 = createPeerConnection();
                pc2.setRemoteDescription(response);
                negociateAnswer(pc2, response);

                pc2.ondatachannel = (evt) => {
                    channel = evt.channel;

                    channel.onmessage = (message) => {
                       try {
                        const content = JSON.parse(message.data);
                        handleDCJSON(content);
                      } catch {
                        // fallback for non-JSON
                        try {
                          const content = JSON.parse(message.data); 
                          if (content && content.type === "data") {
                            const data = content.data;
                            console.log(Date());
                            if (data.location_data) {
                              drawPoints(data.location_data, ctx, canvas);
                            }
                          }
                        } catch {
                          console.log("Non-JSON DataChannel msg:", message.data);
                        }
                      }
                    };

                    channel.onopen = (message) => {
                        channel.send('sending a message');
                    };

                    channel.onclose = (message) => {
                    };


                };
                break;
            case 'data':
            /*case 'keypoints':
                var canvas = document.getElementById("outputCanvas");
                var canvasWidth = canvas.width;
                var canvasHeight = canvas.height;
                var ctx = canvas.getContext("2d");
                drawPoints(response.data.location_data, ctx, canvas);
                break;*/
            case 'capabilities':
                var audio_transform = document.getElementById("audio-transform");
                var video_transform = document.getElementById("video-transform");
                if( response.data.audio && response.data.audio.length ) {                    
                    while (audio_transform.options.length > 0) {
                        audio_transform.remove(0);
                    } 
                    response.data.audio.forEach( value => {
                        const option = document.createElement('option');
                        option.value = value.type;
                        option.textContent = value.title;
                        option.title = value.description
                        if( value.type == 'none' ) {
                            option.selected = true
                        }
                        audio_transform.appendChild(option);
                    })
                } else {
                    audio_transform.disabled = true;
                    var use_audio = document.getElementById("use-audio");
                    use_audio.disabled = true;
                    use_audio.checked = false;
                }
                if( response.data.video && response.data.video.length ) { 
                    while (video_transform.options.length > 0) {
                        video_transform.remove(0);
                    }           
                    response.data.video.forEach( value => {
                        const option = document.createElement('option');
                        option.value = value.type;
                        option.textContent = value.title;
                        option.title = value.description
                        if( value.type == 'none' ) {
                            option.selected = true
                        }
                        video_transform.appendChild(option);
                    })
                } else {
                    video_transform.disabled = true;
                    var use_video = document.getElementById("use-video");
                    use_video.disabled = true;
                    use_video.checked = false;
                }
                break;
            default:
                break;
        }
    };

    socket.onclose = function (event) {
        if (event.wasClean) {
            console.info(`[close] Connection closed cleanly, code=${event.code} reason=${event.reason}`);
        } else {
            console.error('[close] Connection died');
        }
    };

    socket.onerror = function (error) {
        console.error(`[error]` + error);
    };
    return socket;
}

let socket = startWebsocket();

function createPeerConnection() {
    var config = {
        sdpSemantics: 'unified-plan'
    };

    if (document.getElementById('use-stun').checked) {
        authentication = getStunServers().credentialType ? {
            username: getStunServers().username,
            credential: getStunServers().credential,
            credentialType: getStunServers().credentialType
        } : {};
        config.iceServers = getStunServers().servers.map((server) => {
            return { "urls": [server], ...authentication }
        });
    }

    pc = new RTCPeerConnection(config);

    // register some listeners to help debugging
    pc.addEventListener('icegatheringstatechange', function () {
        iceGatheringLog.textContent += ' -> ' + pc.iceGatheringState;
    }, false);
    iceGatheringLog.textContent = pc.iceGatheringState;

    pc.addEventListener('iceconnectionstatechange', function () {
        iceConnectionLog.textContent += ' -> ' + pc.iceConnectionState;
        if (pc.iceConnectionState === 'connected' || pc.iceConnectionState === 'completed') {
            setTopBanner('Ready to talk');
        }
    }, false);
    iceConnectionLog.textContent = pc.iceConnectionState;

    pc.addEventListener('signalingstatechange', function () {
        signalingLog.textContent += ' -> ' + pc.signalingState;
        
    }, false);
    signalingLog.textContent = pc.signalingState;

    // connect audio / video
    pc.addEventListener('track', function (evt) {
      if (evt.track.kind === 'video') {
        document.getElementById('video').srcObject = evt.streams[0];
      } else {
        const stream = evt.streams[0];
        const translationEl = document.getElementById('audio');

        translationEl.src = '';
        translationEl.srcObject = stream;

        if (document.getElementById('enable-recording')?.checked) {
          startRecording(stream);
        }
      }
    });
    
    pc.ondatachannel = (evt) => {
      const channel = evt.channel;

      const canvas = document.getElementById("outputCanvas");
      const ctx = canvas.getContext("2d");

      channel.onmessage = (message) => {
        try {
          const content = JSON.parse(message.data);
          handleDCJSON(content);
        } catch {
          console.log("Non-JSON message:", message.data);
          try {
            const content = JSON.parse(message.data);
            if (content && content.type === "data") {
              const data = content.data;
              console.log(Date());
              if (data.location_data) {
                drawPoints(data.location_data, ctx, canvas);
              }
            }
          } catch {}
        }
      };

      channel.onopen  = () => channel.send('sending a message');
      channel.onclose = () => {};
    }; 
    return pc;
}

function negotiate() {
    return pc.createOffer().then(function (offer) {
        return pc.setLocalDescription(offer);
    }).then(function () {
        // wait for ICE gathering to complete
        return new Promise(function (resolve) {
            if (pc.iceGatheringState === 'complete') {
                resolve();
            } else {
                function checkState() {
                    if (pc.iceGatheringState === 'complete') {
                        pc.removeEventListener('icegatheringstatechange', checkState);
                        resolve();
                    }
                }
                pc.addEventListener('icegatheringstatechange', checkState);
            }
        });
    }).then(function () {
        var offer = pc.localDescription;
        var codec;

        codec = document.getElementById('audio-codec').value;
        if (codec !== 'default') {
            offer.sdp = sdpFilterCodec('audio', codec, offer.sdp);
        }

        codec = document.getElementById('video-codec').value;
        if (codec !== 'default') {
            offer.sdp = sdpFilterCodec('video', codec, offer.sdp);
        }

        document.getElementById('offer-sdp').textContent = offer.sdp;

        var array = new Uint32Array(1);
        window.crypto.getRandomValues(array);

        console.log("Sending OFFER with SDP:\n", offer.sdp);
        console.log("OPTIONS:\n", JSON.stringify({
          video_transform: document.getElementById('use-video').checked ? { "type": document.getElementById('video-transform').value, "channel": document.getElementById('use-datachannel').checked ? "data": "" } : null,
          audio_transcript: document.getElementById('use-audio').checked ? { "type": document.getElementById('audio-transform').value, "channel": document.getElementById('use-datachannel').checked ? "data": "" } : null
          }, null, 2));

        socket.send(JSON.stringify({
            sid: array.toString(),
            callId: "dummy",
            sdp: offer.sdp,
            type: offer.type,
            options: {
                video_transform: document.getElementById('use-video').checked ? { "type": document.getElementById('video-transform').value, "channel": document.getElementById('use-datachannel').checked ? "data": "" } : null,
                audio_transcript: document.getElementById('use-audio').checked ? { "type": document.getElementById('audio-transform').value, "channel": document.getElementById('use-datachannel').checked ? "data": "" } : null
            }
        }))
    });
}

function negociateAnswer(pc, offer) {
    constraints = {}
    kinds = offer.kind.split("+")
    for (i in kinds) {
        constraints[kinds[i]] = true;
    }

    /*if (constraints.video) {
        document.getElementById('media').style.display = 'block';
    }*/

    return navigator.mediaDevices.getUserMedia(constraints)
        .then(function (stream) {
            stream.getTracks().forEach(function (track) {
                pc.addTrack(track, stream);
            });

        }, function (err) {
            console.error('Could not acquire audio media: ' + err);
        })
        .then(() => {
            return pc.createAnswer()
        })
        .then((answer) => pc.setLocalDescription(answer))
        .then(function () {
            // wait for ICE gathering to complete
            return new Promise(function (resolve) {
                if (pc.iceGatheringState === 'complete') {
                    resolve();
                } else {
                    function checkState() {
                        if (pc.iceGatheringState === 'complete') {
                            pc.removeEventListener('icegatheringstatechange', checkState);
                            resolve();
                        }
                    }
                    pc.addEventListener('icegatheringstatechange', checkState);
                }
            });
        }).then(() => {
            return navigator.mediaDevices.getUserMedia(constraints).then(function (stream) {
                stream.getTracks().forEach(function (track) {
                    pc.addTrack(track, stream);
                });

            }, function (err) {
                console.error('Could not acquire media: ' + err);
            });
        }).then(() => {
            var answer = pc.localDescription;
            socket.send(JSON.stringify({
                sid: offer.sid,
                sdp: answer.sdp,
                type: answer.type
            }))
            document.getElementById('stop').style.display = 'inline-block';
        });
}

function start() {
    resetRecording();

    if (socket.readyState == socket.CLOSED || socket.readyState == socket.CLOSING) {
        socket = startWebsocket();
    }
    document.getElementById('start').style.display = 'none';
    document.getElementById('reverse-offer').style.display = 'none';

    pc = createPeerConnection();

    var time_start = null;

    function current_stamp() {
        if (time_start === null) {
            time_start = new Date().getTime();
            return 0;
        } else {
            return new Date().getTime() - time_start;
        }
    }

    if (document.getElementById('use-datachannel').checked) {
        var parameters = JSON.parse(document.getElementById('datachannel-parameters').value);

        dc = pc.createDataChannel('chat', parameters);
        dc.onclose = function () {
            clearInterval(dcInterval);
            dataChannelLog.textContent += '- close\n';
        };
        dc.onopen = function () {
            dataChannelLog.textContent += '- open\n';
            dcInterval = setInterval(function () {
                if (dc.readyState === "open") {
                    var message = 'ping ' + current_stamp();
                    dataChannelLog.textContent = '> ' + message + '\n' + dataChannelLog.textContent;
                    dc.send(message);
                }
            }, 1000);
        };
        dc.onmessage = function (evt) {
            dataChannelLog.textContent += '< ' + evt.data + '\n';

            if (evt.data.substring(0, 4) === 'pong') {
                var elapsed_ms = current_stamp() - parseInt(evt.data.substring(5), 10);
                dataChannelLog.textContent += ' RTT ' + elapsed_ms + ' ms\n';
            }
        };

        dc = pc.createDataChannel('vcaa', parameters);

        dc.onclose = function () {
            clearInterval(dcInterval);
            isClosed = true
            dataChannelLog.textContent += '- close\n';
        };
        dc.onopen = function (_this, ev) {
            
            // Start processing frames
            processFrame(dc);
            dataChannelLog.textContent += '- open\n';
            dcInterval = setInterval(function () {
                if (dc.readyState === "open") {
                    var message = 'ping ' + current_stamp();
                    dataChannelLog.textContent = '> ' + message + '\n' + dataChannelLog.textContent;
                    dc.send(message);
                }
            }, 1000);
        };
        dc.onmessage = function (evt) {
            dataChannelLog.textContent += '< ' + evt.data + '\n';

            if (evt.data.substring(0, 4) === 'pong') {
                var elapsed_ms = current_stamp() - parseInt(evt.data.substring(5), 10);
                dataChannelLog.textContent += ' RTT ' + elapsed_ms + ' ms\n';
            }
        };



    }

    var constraints = {
        audio: document.getElementById('use-audio').checked,
        video: false
    };

    if (document.getElementById('use-video').checked) {
        var resolution = document.getElementById('video-resolution').value;
        if (resolution) {
            resolution = resolution.split('x');
            constraints.video = {
                width: parseInt(resolution[0], 0),
                height: parseInt(resolution[1], 0)
            };
        } else {
            constraints.video = true;
        }
    }

    if (constraints.audio || constraints.video) {
       /* if (constraints.video) {
            document.getElementById('media').style.display = 'block';
        }*/
        navigator.mediaDevices.getUserMedia(constraints).then(function (stream) {
            stream.getTracks().forEach(function (track) {
                pc.addTrack(track, stream);
            });
            return negotiate();
        }, function (err) {
            console.error('Could not acquire media: ' + err);
        });
    } else {
        negotiate();
    }

    document.getElementById('stop').style.display = 'inline-block';
}

function reverse_offer() {
    if (socket.readyState == socket.CLOSED || socket.readyState == socket.CLOSING) {
        socket = startWebsocket();
    }
    document.getElementById('start').style.display = 'none';
    document.getElementById('reverse-offer').style.display = 'none';

    var array = new Uint32Array(1);
    window.crypto.getRandomValues(array);


    socket.send(JSON.stringify({
        sid: array.toString(),
        callId: "dummy",
        type: "request-offer",
        options: {
            video_transform: document.getElementById('use-video').checked ? { "type": document.getElementById('video-transform').value, "direction": "recvonly", "channel": document.getElementById('use-datachannel').checked ? "data": "" } : null,
            audio_transcript: document.getElementById('use-audio').checked ? { "type": document.getElementById('audio-transform').value, "direction": "sendrecv", "channel": document.getElementById('use-datachannel').checked ? "data": "" } : null
        }
    }))
}

function stop() {
    document.getElementById('stop').style.display = 'none';

    // close data channel
    if (dc) {
        dc.close();
    }
    if (document.getElementById('enable-recording')?.checked) {
      stopRecordingToPlayer().then(() => {
        // document.getElementById('recording-audio').play().catch(()=>{});
      });
    }

    
    setTopBanner('Waiting for connection...');

    if (pc.getTransceivers) {
        pc.getTransceivers().forEach(function (transceiver) {
            if (transceiver.stop) {
                transceiver.stop();
            }
        });
    }

    pc.getSenders().forEach(function (sender) {
        sender.track?.stop();
    });

    if (pc2?.getTransceivers) {
        pc2.getTransceivers().forEach(function (transceiver) {
            if (transceiver.stop) {
                transceiver.stop();
            }
        });
    }

    pc2?.getSenders().forEach(function (sender) {
        sender.track?.stop();
    });

    document.getElementById('audio').srcObject?.getTracks()?.forEach((track) => {
        track.stop()
    })
    document.getElementById('audio').srcObject = null;

    document.getElementById('video').srcObject?.getTracks()?.forEach((track) => {
        track.stop()
    })
    document.getElementById('video').srcObject = null

    navigator.mediaDevices.getUserMedia({ audio: true, video: true })
        .then(stream => {
            stream.getTracks().forEach((track) => {
                track.stop();
            });
        })
        .catch((err) => {
            console.log(err);
        });

    // close peer connection
    setTimeout(function () {
        pc.close();
        document.getElementById('start').style.display = 'inline-block';
        document.getElementById('reverse-offer').style.display = 'inline-block';
    }, 500);
}

function sdpFilterCodec(kind, codec, realSdp) {
    var allowed = []
    var rtxRegex = new RegExp('a=fmtp:(\\d+) apt=(\\d+)\r$');
    var codecRegex = new RegExp('a=rtpmap:([0-9]+) ' + escapeRegExp(codec))
    var videoRegex = new RegExp('(m=' + kind + ' .*?)( ([0-9]+))*\\s*$')

    var lines = realSdp.split('\n');

    var isKind = false;
    for (var i = 0; i < lines.length; i++) {
        if (lines[i].startsWith('m=' + kind + ' ')) {
            isKind = true;
        } else if (lines[i].startsWith('m=')) {
            isKind = false;
        }

        if (isKind) {
            var match = lines[i].match(codecRegex);
            if (match) {
                allowed.push(parseInt(match[1]));
            }

            match = lines[i].match(rtxRegex);
            if (match && allowed.includes(parseInt(match[2]))) {
                allowed.push(parseInt(match[1]));
            }
        }
    }

    var skipRegex = 'a=(fmtp|rtcp-fb|rtpmap):([0-9]+)';
    var sdp = '';

    isKind = false;
    for (var i = 0; i < lines.length; i++) {
        if (lines[i].startsWith('m=' + kind + ' ')) {
            isKind = true;
        } else if (lines[i].startsWith('m=')) {
            isKind = false;
        }

        if (isKind) {
            var skipMatch = lines[i].match(skipRegex);
            if (skipMatch && !allowed.includes(parseInt(skipMatch[2]))) {
                continue;
            } else if (lines[i].match(videoRegex)) {
                sdp += lines[i].replace(videoRegex, '$1 ' + allowed.join(' ')) + '\n';
            } else {
                sdp += lines[i] + '\n';
            }
        } else {
            sdp += lines[i] + '\n';
        }
    }

    return sdp;
}

window.start = start;
window.stop = stop;
window.reverse_offer = reverse_offer;
