"use strict";

// Chuông cảnh báo lặp lại cho đến khi caregiver chủ động tắt.
(() => {
  if (window.FallGuardNotifier) return;

  const dashboard = document.getElementById("dashboard-view");
  const alertPanel = document.getElementById("alerts-panel");
  if (!dashboard || !alertPanel) return;

  const create = (tag, cls, value) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (value !== undefined) node.textContent = value;
    return node;
  };

  const settings = create("div", "fg-alert-settings");
  const heading = create("strong", "", "Chuông cảnh báo té ngã");
  const description = create("p", "", "Khi có cảnh báo mới, chuông sẽ lặp lại đến khi bạn bấm Tắt chuông. Chỉ hoạt động khi trang đang mở; âm lượng thực tế còn phụ thuộc thiết bị.");
  const actions = create("div", "fg-alert-settings-actions");
  const enableSound = create("button", "button secondary small", "Bật âm thanh");
  const testSound = create("button", "button secondary small", "Thử chuông liên tục");
  const stopSound = create("button", "button secondary small", "Tắt chuông đang kêu");
  const enableDesktop = create("button", "button secondary small", "Bật thông báo máy tính");
  const volumeLabel = create("label", "fg-alarm-volume-label", "Âm lượng chuông: ");
  const volume = create("input", "fg-alarm-volume");
  volume.type = "range";
  volume.min = "10";
  volume.max = "100";
  volume.step = "10";
  volume.value = "80";
  const volumeText = create("span", "", "80%");
  volumeLabel.append(volume, volumeText);
  const status = create("p", "fg-alert-status", "Hãy bấm Bật âm thanh một lần để trình duyệt cho phép phát chuông.");
  for (const button of [enableSound, testSound, stopSound, enableDesktop]) button.type = "button";
  actions.append(enableSound, testSound, stopSound, enableDesktop);
  settings.append(heading, description, actions, volumeLabel, status);
  alertPanel.prepend(settings);

  const popup = create("aside", "fg-fall-popup");
  popup.hidden = true;
  popup.setAttribute("role", "alertdialog");
  popup.setAttribute("aria-live", "assertive");
  popup.setAttribute("aria-label", "Cảnh báo té ngã");
  const popupTitle = create("h3", "", "PHÁT HIỆN TÉ NGÃ!");
  const popupDetails = create("p", "", "");
  const popupHint = create("p", "fg-fall-popup-hint", "Vui lòng kiểm tra người thân. Tắt chuông không đánh dấu cảnh báo đã xử lý.");
  const popupActions = create("div", "fg-fall-popup-actions");
  const viewButton = create("button", "button primary small", "Xem cảnh báo");
  const dismissButton = create("button", "button secondary small", "Ẩn popup");
  const muteButton = create("button", "button secondary small fg-stop-alarm", "Tắt chuông");
  for (const button of [viewButton, dismissButton, muteButton]) button.type = "button";
  popupActions.append(viewButton, muteButton, dismissButton);
  popup.append(popupTitle, popupDetails, popupHint, popupActions);
  document.body.appendChild(popup);

  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  const seenIds = new Set();
  let ctx = null;
  let soundEnabled = false;
  let alarmTimer = null;
  let alarmActive = false;
  let volumeLevel = 0.8;

  function playPattern() {
    if (!alarmActive || !soundEnabled || !ctx || ctx.state !== "running") return;
    const base = ctx.currentTime + 0.02;
    // Hai cặp âm cao-thấp, âm lượng có giới hạn để tránh méo tiếng.
    for (const [i, delay] of [0, 0.30, 0.68, 0.98].entries()) {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      const start = base + delay;
      osc.type = "triangle";
      osc.frequency.setValueAtTime(i % 2 === 0 ? 980 : 740, start);
      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.linearRampToValueAtTime(0.40 * volumeLevel, start + 0.025);
      gain.gain.setValueAtTime(0.40 * volumeLevel, start + 0.18);
      gain.gain.linearRampToValueAtTime(0.0001, start + 0.25);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(start);
      osc.stop(start + 0.27);
    }
  }

  function stopAlarm() {
    alarmActive = false;
    if (alarmTimer !== null) {
      window.clearInterval(alarmTimer);
      alarmTimer = null;
    }
    status.textContent = soundEnabled ? "Chuông đã tắt. Vẫn sẵn sàng cho cảnh báo mới." : "Chuông đã tắt. Hãy bật âm thanh để nhận chuông mới.";
  }

  function startAlarm() {
    if (alarmActive) return;
    alarmActive = true;
    if (!soundEnabled || !ctx || ctx.state !== "running") {
      status.textContent = "Có cảnh báo mới nhưng âm thanh chưa được bật. Hãy bấm Bật âm thanh!";
      return;
    }
    playPattern();
    alarmTimer = window.setInterval(playPattern, 1600);
    status.textContent = "CHUÔNG ĐANG KÊU — Bấm Tắt chuông để dừng.";
  }

  async function enableAudio() {
    if (!AudioContextClass) {
      status.textContent = "Trình duyệt không hỗ trợ Web Audio.";
      return false;
    }
    try {
      if (!ctx) ctx = new AudioContextClass();
      await ctx.resume();
      soundEnabled = ctx.state === "running";
      enableSound.textContent = soundEnabled ? "Tắt âm thanh" : "Bật âm thanh";
      if (soundEnabled && alarmActive && alarmTimer === null) {
        playPattern();
        alarmTimer = window.setInterval(playPattern, 1600);
      }
      status.textContent = soundEnabled ? (alarmActive ? "CHUÔNG ĐANG KÊU — Bấm Tắt chuông để dừng." : "Đã bật âm thanh cảnh báo.") : "Không thể bật âm thanh.";
      return soundEnabled;
    } catch (_error) {
      status.textContent = "Không thể bật âm thanh. Hãy kiểm tra quyền trình duyệt.";
      return false;
    }
  }

  function disableAudio() {
    stopAlarm();
    soundEnabled = false;
    enableSound.textContent = "Bật âm thanh";
    status.textContent = "Đã tắt âm thanh. Popup vẫn hiển thị cảnh báo mới.";
  }

  function navigateToAlerts() {
    popup.hidden = true;
    if (document.getElementById("cg-alerts")) window.location.hash = "cg-alerts";
    else alertPanel.scrollIntoView({ behavior: "smooth", block: "start" });
    window.focus();
  }

  function showPopup(data, test = false) {
    const name = data.device_name || data.device_id || "Thiết bị";
    const confidence = Number(data.confidence);
    const level = data.confidence != null && Number.isFinite(confidence)
      ? ` · Độ tin cậy: ${Math.round(confidence * 100)}%` : "";
    popupTitle.textContent = test ? "THỬ CHUÔNG — Không tạo FallEvent" : "PHÁT HIỆN TÉ NGÃ!";
    popupDetails.textContent = `${name}${level}`;
    popup.hidden = false;
    startAlarm();
  }

  function notifyDesktop(id) {
    if (!document.hidden || !("Notification" in window) || Notification.permission !== "granted") return;
    try {
      const note = new Notification("FallGuard: phát hiện té ngã", {
        body: "Vui lòng mở FallGuard và kiểm tra người thân.",
        tag: `fallguard-${id}`,
      });
      note.onclick = () => { window.focus(); navigateToAlerts(); note.close(); };
    } catch (_error) { /* Trình duyệt có thể không hỗ trợ. */ }
  }

  function onNewAlert(data) {
    if (dashboard.hidden || !data || !Number.isInteger(data.notification_id) || data.read_at) return;
    const id = data.notification_id;
    if (seenIds.has(id)) return;
    seenIds.add(id);
    if (seenIds.size > 500) seenIds.delete(seenIds.values().next().value);
    // Không đánh thức chuông vì thông báo cũ được nạp lại khi đăng nhập.
    const created = Date.parse(data.created_at || "");
    const age = Date.now() - created;
    if (!Number.isFinite(created) || age < -30000 || age > 90000) return;
    showPopup(data);
    notifyDesktop(id);
  }

  enableSound.addEventListener("click", () => {
    if (soundEnabled) disableAudio();
    else void enableAudio();
  });
  stopSound.addEventListener("click", stopAlarm);
  muteButton.addEventListener("click", stopAlarm);
  dismissButton.addEventListener("click", () => { popup.hidden = true; });
  viewButton.addEventListener("click", navigateToAlerts);
  testSound.addEventListener("click", async () => {
    if (!soundEnabled && !(await enableAudio())) return;
    showPopup({ device_name: "DEV-001 (minh họa)", confidence: 0.95 }, true);
  });
  volume.addEventListener("input", () => {
    volumeLevel = Number(volume.value) / 100;
    volumeText.textContent = `${volume.value}%`;
  });
  enableDesktop.addEventListener("click", async () => {
    if (!("Notification" in window) || !window.isSecureContext) {
      status.textContent = "Trình duyệt chưa hỗ trợ thông báo ở địa chỉ này.";
      return;
    }
    try {
      const permission = await Notification.requestPermission();
      status.textContent = permission === "granted" ? "Đã bật thông báo máy tính khi tab còn mở." : "Chưa cấp quyền thông báo.";
    } catch (_error) {
      status.textContent = "Không thể bật thông báo máy tính.";
    }
  });

  window.addEventListener("pagehide", stopAlarm);
  window.FallGuardNotifier = { onNewAlert, stopAlarm, get isRinging() { return alarmActive; } };
})();
