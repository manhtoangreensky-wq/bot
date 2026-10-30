/**
 * Offscreen Document Worker for TOAN AAS Live Translate & Dub (Manifest V3 / RT-FIX1).
 * Handles tab audio capture, 16kHz PCM downsampling, binary sequence streaming,
 * WebSocket lifecycle, and audio ducking with TTS playback.
 * Governed by owner-governed-codex, locked-focus-engineering.
 */

let audioContext = null;
let mediaStream = null;
let originalGainNode = null;
let scriptProcessor = null;
let webSocket = null;
let currentSeq = 0;
let lastAckSeq = 0;

chrome.runtime.onMessage.addListener((message) => {
  if (message.type === "INIT_AUDIO_CAPTURE") {
    startCapture(message.streamId, message.config).catch((err) => {
      console.error("[TOAN_AAS_OFFSCREEN] Capture initialization failed:", err);
      notifyFailure(err.message);
    });
  } else if (message.type === "STOP_AUDIO_CAPTURE") {
    stopCapture();
  }
});

function notifyFailure(errorMessage) {
  stopCapture();
  chrome.runtime.sendMessage({
    type: "OFFSCREEN_ERROR",
    error: errorMessage,
  });
}

async function startCapture(streamId, config) {
  stopCapture();
  currentSeq = 0;
  lastAckSeq = 0;

  if (!config?.websocketUrl) {
    throw new Error("Missing exact websocketUrl in offscreen configuration");
  }

  // 1. Capture tab media stream
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        mandatory: {
          chromeMediaSource: "tab",
          chromeMediaSourceId: streamId,
        },
      },
      video: false,
    });
  } catch (err) {
    throw new Error(`getUserMedia tabCapture failed: ${err.message}`);
  }

  audioContext = new (window.AudioContext || window.webkitAudioContext)();
  const source = audioContext.createMediaStreamSource(mediaStream);

  // 2. Loopback to destination with Audio Ducking GainNode (NO TAB MUTING)
  originalGainNode = audioContext.createGain();
  originalGainNode.gain.setValueAtTime(1.0, audioContext.currentTime);
  source.connect(originalGainNode);
  originalGainNode.connect(audioContext.destination);

  // 3. Connect exact returned WebSocket URL
  try {
    webSocket = new WebSocket(config.websocketUrl);
  } catch (e) {
    throw new Error(`Failed to initialize WebSocket with URL '${config.websocketUrl}': ${e.message}`);
  }

  webSocket.binaryType = "arraybuffer";

  webSocket.onerror = (err) => {
    console.error("[TOAN_AAS_OFFSCREEN] WebSocket error:", err);
    notifyFailure("Kết nối WebSocket tới máy chủ thất bại.");
  };

  webSocket.onclose = (event) => {
    console.warn(`[TOAN_AAS_OFFSCREEN] WebSocket closed (code ${event.code}): ${event.reason}`);
    if (event.code === 4401 || event.code === 4403 || event.code === 4404) {
      notifyFailure(`Máy chủ từ chối kết nối (${event.code}): ${event.reason}`);
    }
  };

  webSocket.onmessage = (event) => {
    handleDownstreamEvent(event.data);
  };

  // 4. Downsample to 16kHz mono PCM and stream with monotonic sequence
  const inputSampleRate = audioContext.sampleRate;
  const targetSampleRate = 16000;
  const bufferSize = 4096;

  scriptProcessor = audioContext.createScriptProcessor(bufferSize, 1, 1);
  scriptProcessor.onaudioprocess = (e) => {
    if (!webSocket || webSocket.readyState !== WebSocket.OPEN) return;

    const inputData = e.inputBuffer.getChannelData(0);
    const pcm16 = downsampleAndConvertToPcm16(inputData, inputSampleRate, targetSampleRate);
    if (pcm16 && pcm16.byteLength > 0) {
      currentSeq += 1;
      // Binary envelope: [uint32 sequence LE][PCM 16-bit bytes]
      const frame = new Uint8Array(4 + pcm16.byteLength);
      new DataView(frame.buffer).setUint32(0, currentSeq, true);
      frame.set(new Uint8Array(pcm16.buffer), 4);
      webSocket.send(frame.buffer);
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

    if (event.type === "ack" && event.seq) {
      lastAckSeq = event.seq;
    }

    if (event.type === "tts.audio" && event.audio_base64 && originalGainNode && audioContext) {
      // Audio Ducking: lower original video audio to 25%
      originalGainNode.gain.cancelScheduledValues(audioContext.currentTime);
      originalGainNode.gain.setValueAtTime(0.25, audioContext.currentTime);

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
    console.warn("[TOAN_AAS_OFFSCREEN] Error processing downstream event:", err);
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
