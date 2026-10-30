/**
 * Popup Script for TOAN AAS Live Translate & Dub.
 * Governed by owner-governed-codex, locked-focus-engineering.
 */

document.addEventListener("DOMContentLoaded", async () => {
  const selectMode = document.getElementById("select-mode");
  const selectLang = document.getElementById("select-lang");
  const selectVoice = document.getElementById("select-voice");
  const btnToggle = document.getElementById("btn-toggle");
  const statusMsg = document.getElementById("status-msg");

  // Check current session state
  chrome.runtime.sendMessage({ type: "GET_SESSION_STATUS" }, (response) => {
    if (response?.session) {
      updateUiRunning();
    }
  });

  btnToggle.addEventListener("click", async () => {
    chrome.runtime.sendMessage({ type: "GET_SESSION_STATUS" }, (response) => {
      if (response?.session) {
        // Active -> Stop
        chrome.runtime.sendMessage({ type: "STOP_CAPTURE" }, () => {
          updateUiStopped();
        });
      } else {
        // Stopped -> Start
        const config = {
          mode: selectMode.value,
          targetLanguage: selectLang.value,
          genderPreference: selectVoice.value === "female" ? "female" : "male",
          voiceProfileId: selectVoice.value === "voice_vault" ? "my_vault_voice" : null,
        };

        chrome.runtime.sendMessage({ type: "START_CAPTURE", config: config }, (res) => {
          if (res?.ok) {
            updateUiRunning();
          } else {
            alert("Không thể bắt đầu dịch: " + (res?.error || "Lỗi không xác định"));
          }
        });
      }
    });
  });

  function updateUiRunning() {
    btnToggle.textContent = "■ Dừng dịch trực tiếp";
    btnToggle.classList.add("btn-stop");
    statusMsg.style.display = "block";
    statusMsg.textContent = "🟢 Đang dịch & lồng tiếng thời gian thực";
    selectMode.disabled = true;
    selectLang.disabled = true;
    selectVoice.disabled = true;
  }

  function updateUiStopped() {
    btnToggle.textContent = "▶ Bắt đầu dịch tab này";
    btnToggle.classList.remove("btn-stop");
    statusMsg.style.display = "none";
    selectMode.disabled = false;
    selectLang.disabled = false;
    selectVoice.disabled = false;
  }
});
