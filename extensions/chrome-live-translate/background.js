/**
 * Background Service Worker for TOAN AAS Live Translate & Dub (Manifest V3 / RT-FIX1).
 * Governed by owner-governed-codex, locked-focus-engineering.
 */

let activeSession = null;
let creatingOffscreenPromise = null;

async function setupOffscreenDocument(path) {
  const offscreenUrl = chrome.runtime.getURL(path);
  const existingContexts = await chrome.runtime.getContexts({
    contextTypes: ["OFFSCREEN_DOCUMENT"],
    documentUrls: [offscreenUrl],
  });

  if (existingContexts.length > 0) {
    return;
  }

  if (creatingOffscreenPromise) {
    await creatingOffscreenPromise;
    return;
  }

  creatingOffscreenPromise = chrome.offscreen.createDocument({
    url: path,
    reasons: ["USER_MEDIA", "AUDIO_PLAYBACK"],
    justification: "Recording tab audio, resampling to 16kHz PCM, and playing dubbing TTS audio with ducking.",
  });

  await creatingOffscreenPromise;
  creatingOffscreenPromise = null;
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "START_CAPTURE") {
    handleStartCapture(message.sessionData, sender.tab?.id || message.tabId)
      .then((res) => sendResponse({ ok: true, data: res }))
      .catch((err) => sendResponse({ ok: false, error: err.message }));
    return true;
  }

  if (message.type === "STOP_CAPTURE") {
    handleStopCapture()
      .then(() => sendResponse({ ok: true }))
      .catch((err) => sendResponse({ ok: false, error: err.message }));
    return true;
  }

  if (message.type === "GET_SESSION_STATUS") {
    sendResponse({ ok: true, session: activeSession });
    return false;
  }

  // Relay downstream events to content script
  if (message.target === "CONTENT_SCRIPT" && activeSession?.tabId) {
    chrome.tabs.sendMessage(activeSession.tabId, message).catch(() => {});
    return false;
  }

  if (message.type === "OFFSCREEN_ERROR") {
    // Fail closed: stop capture and notify tab
    handleStopCapture().then(() => {
      if (activeSession?.tabId) {
        chrome.tabs.sendMessage(activeSession.tabId, {
          type: "SESSION_FAILED",
          error: message.error || "Lỗi luồng âm thanh/WebSocket",
        }).catch(() => {});
      }
    });
    return false;
  }
});

async function handleStartCapture(sessionData, tabId) {
  if (!sessionData || !sessionData.sessionId || !sessionData.streamToken || !sessionData.websocketUrl) {
    throw new Error("Missing server-owned session credentials (sessionId/streamToken/websocketUrl)");
  }

  if (!tabId) {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    tabId = tab?.id;
  }
  if (!tabId) {
    throw new Error("No active tab found to capture audio.");
  }

  await setupOffscreenDocument("offscreen.html");

  const streamId = await chrome.tabCapture.getMediaStreamId({
    targetTabId: tabId,
  });

  if (!streamId) {
    throw new Error("chrome.tabCapture did not yield a valid streamId");
  }

  activeSession = {
    active: true,
    tabId: tabId,
    sessionId: sessionData.sessionId,
    streamToken: sessionData.streamToken,
    websocketUrl: sessionData.websocketUrl,
    startedAt: Date.now(),
  };

  chrome.runtime.sendMessage({
    type: "INIT_AUDIO_CAPTURE",
    streamId: streamId,
    config: sessionData,
  });

  chrome.tabs.sendMessage(tabId, {
    type: "SESSION_STARTED",
    config: sessionData,
  }).catch(() => {});

  return { tabId, streamId, sessionId: sessionData.sessionId };
}

async function handleStopCapture() {
  if (!activeSession) return;

  chrome.runtime.sendMessage({ type: "STOP_AUDIO_CAPTURE" });

  if (activeSession.tabId) {
    chrome.tabs.sendMessage(activeSession.tabId, { type: "SESSION_STOPPED" }).catch(() => {});
  }

  activeSession = null;
}
