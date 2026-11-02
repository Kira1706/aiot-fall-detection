"use strict";

// Giao diện cảnh báo bổ sung; không thay đổi luồng lưu FallEvent và WebSocket.
(() => {
  if (window.FallGuardNotifier) return;

  const dashboard = document.getElementById("dashboard-view");
  const alertPanel = document.getElementById("alerts-panel");
  if (!dashboard || !alertPanel) {
    console.warn("FallGuard: chưa tìm thấy khu vực Dashboard/Cảnh báo.");
    return;
  }

  const create = (tag, className, content) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (content !== undefined) node.textContent = content;
    return node;
  };

  const settings = create("div", "fg-alert-settings");
  const heading = create("strong", "", "Cảnh báo âm thanh");
  const description = create("p", "", "Bật tiếng chuông trên trình duyệt đang mở. Khi đóng trang, chuông sẽ không hoạt động.");
  const actions = create("div", "fg-alert-settings-actions");
  const enableSound = create("button", "button secondary small", "Bật âm thanh");
  const testSound = create("button", "button secondary small", "Thử cảnh báo");
  const enableDesktop = create("button", "button secondary small", "Bật thông báo máy tính");
  const status = create("p", "fg-alert-status", "Âm thanh hiện đang tắt.");
  for (const button of [enableSound, testSound, enableDesktop]) button.type = "button";
  actions.append(enableSound, testSound, enableDesktop);
  settings.append(heading, description, actions, status);
  alertPanel.prepend(settings);

  const popup = create("aside", "fg-fall-popup");
  popup.hidden = true;
  popup.setAttribute("role", "alert");
  popup.setAttribute("aria-live", "assertive");
  const popupTitle = create("h3", "", "Cảnh báo té ngã");
  const popupDetails = create("p", "", "");
  const popupHint = create("p", "fg-fall-popup-hint", "Hãy kiểm tra tình trạng người thân. Đóng cửa sổ này không đánh dấu đã xem.");
  const popupActions = create("div", "fg-fall-popup-actions");
  const viewButton = create("button", "button primary small", "Xem cảnh báo");
  const dismissButton = create("button", "button secondary small", "Đóng thông báo");
  const muteButton = create("button", "button secondary small", "Tắt chuông");
  for (const button of [viewButton, dismissButton, muteButton]) button.type = "button";
  popupActions.append(viewButton, dismissButton, muteButton);
  popup.append(popupTitle, popupDetails, popupHint, popupActions);
  document.body.appendChild(popup);

  let audioContext = null;
  let soundEnabled = false;
  let lastRingAt = 0;
  const seenIds = new Set();
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;

  function ring() {
    if (!soundEnabled || !audioContext || audioContext.state !== "running") return;
    if (Date.now() - lastRingAt < 1800) return;
    lastRingAt = Date.now();
    const base = audioContext.currentTime;
    for (const delay of [0, 0.32, 0.64]) {
      const start = base + delay;
      const osc = audioContext.createOscillator();
      const gain = audioContext.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(840, start);
      osc.frequency.setValueAtTime(690, start + 0.11);
      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.exponentialRampToValueAtTime(0.13, start + 0.025);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.23);
      osc.connect(gain);
      gain.connect(audioContext.destination);
      osc.start(start);
      osc.stop(start + 0.24);
    }
  }

  async function activateSound() {
    if (!AudioContextClass) {
      status.textContent = "Trình duyệt này không hỗ trợ phát chuông bằng Web Audio.";
      return false;
    }
    try {
      if (!audioContext) audioContext = new AudioContextClass();
      // Hàm resume được gọi trực tiếp trong sự kiện nhấn nút.
      await audioContext.resume();
      soundEnabled = audioContext.state === "running";
      enableSound.textContent = soundEnabled ? "Tắt âm thanh" : "Bật âm thanh";
      status.textContent = soundEnabled ? "Đã bật chuông cảnh báo trên tab hiện tại." : "Không thể bật âm thanh. Hãy kiểm tra trình duyệt.";
      return soundEnabled;
    } catch (_error) {
      status.textContent = "Trình duyệt không cho phát âm thanh. Hãy kiểm tra quyền âm thanh.";
      return false;
    }
  }

  function mute() {
    soundEnabled = false;
    enableSound.textContent = "Bật âm thanh";
    status.textContent = "Đã tắt âm thanh cảnh báo.";
  }

  function navigateToAlerts() {
    popup.hidden = true;
    if (document.getElementById("cg-alerts")) {
      window.location.hash = "cg-alerts";
    } else {
      alertPanel.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    window.focus();
  }

  function showPopup(data, isTest = false) {
    const name = data.device_name || data.device_id || "Thiết bị";
    const level = data.confidence != null && Number.isFinite(Number(data.confidence))
      ? ` · Độ tin cậy: ${Math.round(Number(data.confidence) * 100)}%` : "";
    popupTitle.textContent = isTest ? "THỬ CHUÔNG — Không tạo FallEvent" : "PHÁT HIỆN TÉ NGÃ!";
    popupDetails.textContent = `${name}${level}`;
    popup.hidden = false;
    ring();
  }

  function showSystemNotification(id) {
    // Notification thông thường chỉ hoạt động khi trang vẫn mở.
    if (!document.hidden || !("Notification" in window) || Notification.permission !== "granted") return;
    try {
      const notice = new Notification("FallGuard có cảnh báo té ngã", {
        body: "Mở FallGuard để kiểm tra tình trạng người thân.",
        tag: `fallguard-${id}`,
      });
      notice.onclick = () => {
        window.focus();
        navigateToAlerts();
        notice.close();
      };
    } catch (_error) {
      // Một số trình duyệt điện thoại không hỗ trợ Notification từ tab.
    }
  }

  function onNewAlert(data) {
    if (dashboard.hidden || !data || !Number.isInteger(data.notification_id) || data.read_at) return;
    const id = data.notification_id;
    if (seenIds.has(id)) return;
    seenIds.add(id);
    if (seenIds.size > 500) seenIds.delete(seenIds.values().next().value);

    // Không phát chuông khi WebSocket gửi lại thông báo cũ lúc mới đăng nhập.
    const created = Date.parse(data.created_at || "");
    const age = Date.now() - created;
    if (!Number.isFinite(created) || age < -30000 || age > 90000) return;

    showPopup(data);
    showSystemNotification(id);
  }

  enableSound.addEventListener("click", () => {
    if (soundEnabled) mute();
    else void activateSound();
  });

  testSound.addEventListener("click", async () => {
    if (!soundEnabled && !(await activateSound())) return;
    lastRingAt = 0;
    showPopup({ device_name: "DEV-001 (minh họa)", confidence: 0.95 }, true);
  });

  enableDesktop.addEventListener("click", async () => {
    if (!("Notification" in window) || !window.isSecureContext) {
      status.textContent = "Trình duyệt chưa hỗ trợ thông báo máy tính ở địa chỉ này.";
      return;
    }
    try {
      const permission = await Notification.requestPermission();
      status.textContent = permission === "granted"
        ? "Đã bật thông báo máy tính khi tab còn mở."
        : "Chưa cấp quyền thông báo máy tính.";
    } catch (_error) {
      status.textContent = "Không thể xin quyền thông báo trên trình duyệt này.";
    }
  });

  viewButton.addEventListener("click", navigateToAlerts);
  dismissButton.addEventListener("click", () => { popup.hidden = true; });
  muteButton.addEventListener("click", mute);

  window.FallGuardNotifier = { onNewAlert };
})();
