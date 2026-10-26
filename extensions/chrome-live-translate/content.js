/**
 * Content Script for TOAN AAS Live Translate & Dub.
 * Injects a modern floating draggable widget into any webpage (Facebook, YouTube, etc.).
 * Governed by owner-governed-codex, locked-focus-engineering.
 */

(function () {
  if (window.__TOAN_AAS_LIVE_WIDGET_LOADED__) return;
  window.__TOAN_AAS_LIVE_WIDGET_LOADED__ = true;

  let isExpanded = true;
  let isDragging = false;
  let dragOffsetX = 0;
  let dragOffsetY = 0;
  let fontSize = 16;
  let isDubbingEnabled = true;

  // Create Widget Root Container
  const container = document.createElement("div");
  container.id = "toan-aas-live-widget-root";
  container.innerHTML = `
    <!-- Collapsed Pill -->
    <div id="toan-aas-pill" class="toan-aas-pill" style="display: none;">
      <span class="toan-aas-pill-icon">文 VI</span>
      <span class="toan-aas-pill-text">TOAN AAS Live</span>
      <span id="toan-aas-pill-dot" class="toan-aas-live-dot active"></span>
    </div>

    <!-- Expanded Floating Widget Window -->
    <div id="toan-aas-window" class="toan-aas-window">
      <div id="toan-aas-header" class="toan-aas-header">
        <div class="toan-aas-title-group">
          <span class="toan-aas-badge">文 VI</span>
          <span class="toan-aas-title">TOAN AAS Live Dub</span>
          <span id="toan-aas-status-dot" class="toan-aas-live-dot active"></span>
        </div>
        <div class="toan-aas-actions">
          <button id="toan-aas-btn-min" class="toan-aas-icon-btn" title="Thu nhỏ">−</button>
          <button id="toan-aas-btn-close" class="toan-aas-icon-btn" title="Đóng">✕</button>
        </div>
      </div>

      <!-- Subtitle Display Area -->
      <div class="toan-aas-body">
        <div class="toan-aas-subtitle-box">
          <div id="toan-aas-trans-text" class="toan-aas-trans-text" style="font-size: ${fontSize}px;">
            🇻🇳 Chờ âm thanh phát... (Bật video trên trang để dịch tự động)
          </div>
          <div id="toan-aas-orig-text" class="toan-aas-orig-text" style="font-size: ${fontSize - 2}px;">
            🇺🇸 Waiting for audio stream...
          </div>
        </div>
      </div>

      <!-- Controls Toolbar -->
      <div class="toan-aas-footer">
        <button id="toan-aas-btn-dub" class="toan-aas-btn active" title="Bật/Tắt lồng tiếng">
          <span id="toan-aas-dub-icon">🔊</span> Lồng tiếng
        </button>
        <div class="toan-aas-btn-group">
          <button id="toan-aas-font-dec" class="toan-aas-btn-small" title="Giảm cỡ chữ">A-</button>
          <button id="toan-aas-font-inc" class="toan-aas-btn-small" title="Tăng cỡ chữ">A+</button>
        </div>
        <button id="toan-aas-btn-export" class="toan-aas-btn-small" title="Tải phụ đề SRT">💾 SRT</button>
      </div>
    </div>
  `;

  document.body.appendChild(container);

  // Element Selectors
  const pill = container.querySelector("#toan-aas-pill");
  const win = container.querySelector("#toan-aas-window");
  const header = container.querySelector("#toan-aas-header");
  const btnMin = container.querySelector("#toan-aas-btn-min");
  const btnClose = container.querySelector("#toan-aas-btn-close");
  const origText = container.querySelector("#toan-aas-orig-text");
  const transText = container.querySelector("#toan-aas-trans-text");
  const btnDub = container.querySelector("#toan-aas-btn-dub");
  const dubIcon = container.querySelector("#toan-aas-dub-icon");
  const fontDec = container.querySelector("#toan-aas-font-dec");
  const fontInc = container.querySelector("#toan-aas-font-inc");
  const btnExport = container.querySelector("#toan-aas-btn-export");

  // Subtitle history for export
  const historySegments = [];

  // Toggle Collapse / Expand
  btnMin.addEventListener("click", () => {
    isExpanded = false;
    win.style.display = "none";
    pill.style.display = "flex";
  });

  pill.addEventListener("click", () => {
    isExpanded = true;
    win.style.display = "flex";
    pill.style.display = "none";
  });

  btnClose.addEventListener("click", () => {
    container.style.display = "none";
    chrome.runtime.sendMessage({ type: "STOP_CAPTURE" });
  });

  // Toggle Dubbing
  btnDub.addEventListener("click", () => {
    isDubbingEnabled = !isDubbingEnabled;
    if (isDubbingEnabled) {
      btnDub.classList.add("active");
      dubIcon.textContent = "🔊";
    } else {
      btnDub.classList.remove("active");
      dubIcon.textContent = "🔇";
    }
  });

  // Font Size Controls
  fontInc.addEventListener("click", () => {
    if (fontSize < 28) {
      fontSize += 2;
      transText.style.fontSize = fontSize + "px";
      origText.style.fontSize = fontSize - 2 + "px";
    }
  });

  fontDec.addEventListener("click", () => {
    if (fontSize > 12) {
      fontSize -= 2;
      transText.style.fontSize = fontSize + "px";
      origText.style.fontSize = fontSize - 2 + "px";
    }
  });

  // Export SRT
  btnExport.addEventListener("click", () => {
    if (historySegments.length === 0) {
      alert("Chưa có phụ đề trong phiên này.");
      return;
    }
    let srtContent = "";
    historySegments.forEach((seg, idx) => {
      const start = formatSrtTime(seg.start_ms || idx * 3000);
      const end = formatSrtTime(seg.end_ms || (idx + 1) * 3000);
      srtContent += `${idx + 1}\n${start} --> ${end}\n${seg.translated_text || seg.text}\n\n`;
    });

    const blob = new Blob([srtContent], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `TOAN_AAS_Subtitle_${Date.now()}.srt`;
    a.click();
    URL.revokeObjectURL(url);
  });

  function formatSrtTime(ms) {
    const totalSec = Math.floor(ms / 1000);
    const msec = ms % 1000;
    const s = totalSec % 60;
    const m = Math.floor(totalSec / 60) % 60;
    const h = Math.floor(totalSec / 3600);
    return `${pad(h)}:${pad(m)}:${pad(s)},${pad(msec, 3)}`;
  }

  function pad(num, size = 2) {
    let s = "000" + num;
    return s.substr(s.length - size);
  }

  // Draggable Mechanics
  header.addEventListener("mousedown", (e) => {
    if (e.target.tagName === "BUTTON") return;
    isDragging = true;
    dragOffsetX = e.clientX - win.getBoundingClientRect().left;
    dragOffsetY = e.clientY - win.getBoundingClientRect().top;
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
  });

  function onMouseMove(e) {
    if (!isDragging) return;
    const x = Math.max(10, Math.min(window.innerWidth - win.offsetWidth - 10, e.clientX - dragOffsetX));
    const y = Math.max(10, Math.min(window.innerHeight - win.offsetHeight - 10, e.clientY - dragOffsetY));
    win.style.left = x + "px";
    win.style.top = y + "px";
    win.style.right = "auto";
  }

  function onMouseUp() {
    isDragging = false;
    document.removeEventListener("mousemove", onMouseMove);
    document.removeEventListener("mouseup", onMouseUp);
  }

  // Message Listener from Background
  chrome.runtime.onMessage.addListener((message) => {
    if (message.type === "SESSION_STARTED") {
      container.style.display = "block";
      win.style.display = "flex";
      pill.style.display = "none";
      transText.textContent = "🇻🇳 Đang kết nối luồng âm thanh...";
      origText.textContent = "🇺🇸 Audio stream active...";
    }

    if (message.type === "SESSION_STOPPED") {
      transText.textContent = "🇻🇳 Phiên dịch đã kết thúc.";
      origText.textContent = "🇺🇸 Session ended.";
    }

    if (message.type === "SERVER_EVENT" && message.data) {
      const data = message.data;

      if (data.type === "stt.final" && data.text) {
        origText.textContent = data.text;
      }

      if (data.type === "translation.final" && data.translated_text) {
        transText.textContent = data.translated_text;
        historySegments.push(data);
      }
    }
  });
})();
