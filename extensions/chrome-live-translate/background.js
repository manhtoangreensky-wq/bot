/**
 * Background Service Worker for TOAN AAS Live Translate & Dub (Manifest V3).
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
    handleStartCapture(message.config, sender.tab?.id || message.tabId)
      .then((res) => sendResponse({ ok: true, data: res }))
      .catch((err) => sendResponse({ ok: false, error: err.message }));
    return true; // Keep message channel open for async response
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

  // Relay downstream events from offscreen document to tab content script
  if (message.target === "CONTENT_SCRIPT" && activeSession?.tabId) {
    chrome.tabs.sendMessage(activeSession.tabId, message).catch(() => {});
    return false;
  }
});

async function handleStartCapture(config, tabId) {
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

  activeSession = {
    tabId: tabId,
    config: config,
    startedAt: Date.now(),
  };

  // Dispatch streamId and config to offscreen document
  chrome.runtime.sendMessage({
    type: "INIT_AUDIO_CAPTURE",
    streamId: streamId,
    config: config,
  });

  // Notify tab to open floating widget
  chrome.tabs.sendMessage(tabId, {
    type: "SESSION_STARTED",
    config: config,
  }).catch(() => {});

  return { tabId, streamId };
}

async function handleStopCapture() {
  if (!activeSession) return;

  chrome.runtime.sendMessage({ type: "STOP_AUDIO_CAPTURE" });

  if (activeSession.tabId) {
    chrome.tabs.sendMessage(activeSession.tabId, { type: "SESSION_STOPPED" }).catch(() => {});
  }

  activeSession = null;
}
