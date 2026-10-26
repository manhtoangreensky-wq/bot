/**
 * Offscreen Document Worker for TOAN AAS Live Translate & Dub.
 * Handles tab audio capture, 16kHz PCM downsampling, WebSocket streaming,
 * and audio ducking with TTS playback.
 * Governed by owner-governed-codex, locked-focus-engineering.
 */

let audioContext = null;
let mediaStream = null;
let originalGainNode = null;
let scriptProcessor = null;
let webSocket = null;
let isDucking = false;

chrome.runtime.onMessage.addListener((message) => {
  if (message.type === "INIT_AUDIO_CAPTURE") {
    startCapture(message.streamId, message.config).catch((err) => {
      console.error("[TOAN_AAS_OFFSCREEN] Capture failed:", err);
    });
  } else if (message.type === "STOP_AUDIO_CAPTURE") {
    stopCapture();
  }
});

async function startCapture(streamId, config) {
  stopCapture();

  // 1. Capture tab media stream
  mediaStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      mandatory: {
        chromeMediaSource: "tab",
        chromeMediaSourceId: streamId,
      },
    },
    video: false,
  });

  audioContext = new (window.AudioContext || window.webkitAudioContext)();
  const source = audioContext.createMediaStreamSource(mediaStream);

  // 2. Loopback to destination with Audio Ducking GainNode
  // CRITICAL FIX: prevents tab muting, keeps audio playing to user's speakers
  originalGainNode = audioContext.createGain();
  originalGainNode.gain.setValueAtTime(1.0, audioContext.currentTime);
  source.connect(originalGainNode);
  originalGainNode.connect(audioContext.destination);

  // 3. Connect WebSocket to backend Gateway
  const wsUrl = config.websocketUrl || "wss://tg.toanaas.vn/api/v1/live-translate/sessions/" + config.sessionId + "/stream?token=" + config.streamToken;
  try {
    webSocket = new WebSocket(wsUrl);
  } catch (e) {
    console.warn("[TOAN_AAS_OFFSCREEN] WebSocket init error, running in local preview mode:", e);
  }

  if (webSocket) {
    webSocket.binaryType = "arraybuffer";
    webSocket.onmessage = (event) => {
      handleDownstreamEvent(event.data);
    };
  }

  // 4. Downsample to 16kHz mono PCM and stream
  const inputSampleRate = audioContext.sampleRate;
  const targetSampleRate = 16000;
  const bufferSize = 4096;

  scriptProcessor = audioContext.createScriptProcessor(bufferSize, 1, 1);
  scriptProcessor.onaudioprocess = (e) => {
    if (!webSocket || webSocket.readyState !== WebSocket.OPEN) return;

    const inputData = e.inputBuffer.getChannelData(0);
    const pcm16 = downsampleAndConvertToPcm16(inputData, inputSampleRate, targetSampleRate);
    if (pcm16 && pcm16.byteLength > 0) {
      webSocket.send(pcm16.buffer);
    }
  };

  source.connect(scriptProcessor);
  scriptProcessor.connect(audioContext.destination);
}

function downsampleAndConvertToPcm16(inputBuffer, inputSampleRate, targetSampleRate) {
  if (inputSampleRate === targetSampleRate) {
    const pcm = new Int16Array(inputBuffer.length);
    for (let i = 0; i < inputBuffer.length; i++) {
      let s = Math.max(-1, Math.min(1, inputBuffer[i]));
      pcm[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    return pcm;
  }

  const sampleRatio = inputSampleRate / targetSampleRate;
  const newLength = Math.round(inputBuffer.length / sampleRatio);
  const pcm16 = new Int16Array(newLength);

  for (let i = 0; i < newLength; i++) {
    const originalIndex = Math.min(Math.round(i * sampleRatio), inputBuffer.length - 1);
    let s = Math.max(-1, Math.min(1, inputBuffer[originalIndex]));
    pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
  }

  return pcm16;
}

async function handleDownstreamEvent(rawData) {
  if (typeof rawData !== "string") return;

  try {
    const event = JSON.parse(rawData);

    if (event.type === "tts.audio" && event.audio_base64 && originalGainNode && audioContext) {
      // Audio Ducking: lower original video audio to 25%
      originalGainNode.gain.cancelScheduledValues(audioContext.currentTime);
      originalGainNode.gain.setValueAtTime(0.25, audioContext.currentTime);

      // Play dubbing TTS audio
      const binaryString = atob(event.audio_base64);
      const len = binaryString.length;
      const bytes = new Uint8Array(len);
      for (let i = 0; i < len; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      const audioBuffer = await audioContext.decodeAudioData(bytes.buffer);
      const ttsSource = audioContext.createBufferSource();
      ttsSource.buffer = audioBuffer;
      ttsSource.connect(audioContext.destination);

      ttsSource.onended = () => {
        // Restore original audio to 100% after TTS finishes
        if (originalGainNode && audioContext) {
          originalGainNode.gain.cancelScheduledValues(audioContext.currentTime);
          originalGainNode.gain.setValueAtTime(1.0, audioContext.currentTime);
        }
      };
      ttsSource.start();
    }

    // Relay to content script for subtitle rendering
    chrome.runtime.sendMessage({
      target: "CONTENT_SCRIPT",
      type: "SERVER_EVENT",
      data: event,
    });
  } catch (err) {
    console.warn("[TOAN_AAS_OFFSCREEN] Error processing event:", err);
  }
}

function stopCapture() {
  if (scriptProcessor) {
    scriptProcessor.disconnect();
    scriptProcessor = null;
  }
  if (originalGainNode) {
    originalGainNode.disconnect();
    originalGainNode = null;
  }
  if (mediaStream) {
    mediaStream.getTracks().forEach((t) => t.stop());
    mediaStream = null;
  }
  if (audioContext && audioContext.state !== "closed") {
    audioContext.close();
    audioContext = null;
  }
  if (webSocket) {
    webSocket.close();
    webSocket = null;
  }
}
