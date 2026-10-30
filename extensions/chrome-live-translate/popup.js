/**
 * Popup Script for TOAN AAS Live Translate & Dub (Manifest V3 / RT-FIX1).
 * Governed by owner-governed-codex, locked-focus-engineering.
 * Enforces:
 * 1. EXTENSION_CREATE_SESSION: Authenticated session creation before tabCapture.
 * 2. SESSION_ID_SERVER_OWNED and STREAM_TOKEN_SERVER_OWNED.
 * 3. Exact WebSocket URL dispatch.
 * 4. Fails closed with UI_STATE=FAILED if session creation or capture fails.
 */

const DEFAULT_API_BASE = "https://tg.toanaas.vn";

document.addEventListener("DOMContentLoaded", async () => {
  const selectMode = document.getElementById("select-mode");
  const selectLang = document.getElementById("select-lang");
  const selectVoice = document.getElementById("select-voice");
  const btnToggle = document.getElementById("btn-toggle");
  const statusMsg = document.getElementById("status-msg");

  // Check current session state
  chrome.runtime.sendMessage({ type: "GET_SESSION_STATUS" }, (response) => {
    if (response?.session?.active) {
      updateUiRunning();
    }
  });

  btnToggle.addEventListener("click", async () => {
    chrome.runtime.sendMessage({ type: "GET_SESSION_STATUS" }, async (statusRes) => {
      if (statusRes?.session?.active) {
        // Active -> Stop
        chrome.runtime.sendMessage({ type: "STOP_CAPTURE" }, () => {
          updateUiStopped();
        });
      } else {
        // Stopped -> Start: Handshake with authenticated backend FIRST
        btnToggle.disabled = true;
        btnToggle.textContent = "⏳ Đang khởi tạo phiên...";
        statusMsg.style.display = "block";
        statusMsg.textContent = "Đang xác thực tài khoản và cấp quyền phiên...";

        try {
          const apiBase = DEFAULT_API_BASE;
          const sessionPayload = {
            mode: selectMode.value,
            target_language: selectLang.value,
            gender_preference: selectVoice.value === "female" ? "female" : "male",
            voice_profile_id: selectVoice.value.startsWith("vp_") ? selectVoice.value : null,
          };

          const createRes = await fetch(`${apiBase}/api/v1/live-translate/sessions`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            credentials: "include", // Send session cookies for require_account
            body: JSON.stringify(sessionPayload),
          });

          if (!createRes.ok) {
            const errJson = await createRes.json().catch(() => ({}));
            throw new Error(errJson.detail || `Lỗi máy chủ (${createRes.status}): Vui lòng đăng nhập Web TOAN AAS`);
          }

          const sessionData = await createRes.json();
          if (!sessionData.ok || !sessionData.session_id || !sessionData.stream_token || !sessionData.websocket_url) {
            throw new Error("Dữ liệu phiên từ máy chủ không hợp lệ (Missing token/URL)");
          }

          // Full WebSocket URL
          let wsUrl = sessionData.websocket_url;
          if (wsUrl.startsWith("/")) {
            const wsProtocol = apiBase.startsWith("https") ? "wss:" : "ws:";
            const host = apiBase.replace(/^https?:\/\//, "");
            wsUrl = `${wsProtocol}//${host}${wsUrl}`;
          }

          // Handshake succeeded: Start capture with server-owned credentials
          chrome.runtime.sendMessage({
            type: "START_CAPTURE",
            sessionData: {
              sessionId: sessionData.session_id,
              streamToken: sessionData.stream_token,
              websocketUrl: wsUrl,
              mode: sessionData.mode,
              targetLanguage: sessionData.target_language,
            },
          }, (captureRes) => {
            btnToggle.disabled = false;
            if (captureRes?.ok) {
              updateUiRunning();
            } else {
              updateUiFailed(captureRes?.error || "Không thể bắt luồng âm thanh tab");
            }
          });

        } catch (err) {
          btnToggle.disabled = false;
          updateUiFailed(err.message);
        }
      }
    });
  });

  function updateUiRunning() {
    btnToggle.textContent = "■ Dừng dịch trực tiếp";
    btnToggle.className = "btn-primary btn-stop";
    statusMsg.style.display = "block";
    statusMsg.style.color = "#10b981";
    statusMsg.textContent = "🟢 Đang dịch & lồng tiếng thời gian thực";
    selectMode.disabled = true;
    selectLang.disabled = true;
    selectVoice.disabled = true;
  }

  function updateUiStopped() {
    btnToggle.textContent = "▶ Bắt đầu dịch tab này";
    btnToggle.className = "btn-primary";
    statusMsg.style.display = "none";
    selectMode.disabled = false;
    selectLang.disabled = false;
    selectVoice.disabled = false;
  }

  function updateUiFailed(errorMsg) {
    btnToggle.textContent = "Thử lại";
    btnToggle.className = "btn-primary btn-stop";
    statusMsg.style.display = "block";
    statusMsg.style.color = "#ef4444";
    statusMsg.textContent = `❌ ${errorMsg}`;
    selectMode.disabled = false;
    selectLang.disabled = false;
    selectVoice.disabled = false;
  }
});
