"use strict";

// Dashboard dùng API cùng nguồn với FastAPI nên không cần cấu hình CORS.
// JWT chỉ nằm trong bộ nhớ JavaScript, không ghi vào localStorage hoặc cookie.
const $ = (id) => document.getElementById(id);
const PAGE_SIZE = 10;

let accessToken = null;
let expiresAt = 0;
let devices = [];
let selectedDeviceId = null;
let currentPage = 0;
let requestVersion = 0;

// Lưu thông báo chưa xem theo ID để không hiện trùng khi REST và WebSocket cùng gửi.
const pendingAlerts = new Map();
let alertSocket = null;
let reconnectTimer = null;
let realtimeGeneration = 0;
let reconnectAttempt = 0;
let websocketPingTimer = null;


// Đọc lỗi trả về từ FastAPI mà không hiển thị thông tin nội bộ.
function getErrorMessage(data, status) {
  if (typeof data?.detail === "string") return data.detail;
  if (Array.isArray(data?.detail)) {
    return data.detail.map((item) => item.msg || "Dữ liệu không hợp lệ").join("; ");
  }
  return `Yêu cầu thất bại (HTTP ${status}).`;
}

function clearSession(message = "") {
  stopRealtime();
  // Tăng phiên bản để các request cũ không thể cập nhật giao diện mới.
  requestVersion += 1;
  accessToken = null;
  expiresAt = 0;
  devices = [];
  selectedDeviceId = null;
  currentPage = 0;
  $("password").value = "";
  $("dashboard-view").hidden = true;
  $("login-view").hidden = false;
  $("login-error").textContent = message;
  $("login-error").hidden = !message;
  if (typeof dashboardManagementClear === "function") dashboardManagementClear();
  showAuthMode("login");
}

async function apiRequest(path, { method = "GET", body = null, authenticated = true } = {}) {
  if (authenticated && (!accessToken || Date.now() >= expiresAt)) {
    clearSession("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.");
    throw new Error("Phiên đăng nhập đã hết hạn.");
  }

  const headers = { Accept: "application/json" };
  if (body !== null) headers["Content-Type"] = "application/json";
  if (authenticated) headers.Authorization = `Bearer ${accessToken}`;

  // Chỉ gọi các đường dẫn cố định của Backend; không truyền URL từ người dùng.
  let response;
  try {
    response = await fetch(path, {
      method,
      headers,
      body: body === null ? undefined : JSON.stringify(body),
      cache: "no-store",
    });
  } catch (_error) {
    throw new Error("Không kết nối được Backend. Hãy kiểm tra Uvicorn.");
  }

  const text = await response.text();
  let data = null;
  if (text) {
    try { data = JSON.parse(text); } catch (_error) { data = null; }
  }

  if (!response.ok) {
    const message = getErrorMessage(data, response.status);
    if (authenticated && response.status === 401) {
      clearSession("Phiên đăng nhập không hợp lệ hoặc đã hết hạn.");
    }
    throw new Error(message);
  }
  return data;
}

function formatDate(isoString) {
  if (!isoString) return "Chưa nhận heartbeat";
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return "Không xác định";
  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  }).format(date);
}

function deviceName(device) {
  return device.display_name || device.device_id;
}

function showMessage(message, isError = false) {
  const banner = $("dashboard-message");
  banner.textContent = message;
  banner.classList.toggle("error", isError);
  banner.hidden = !message;
}

function updateDeviceCounters() {
  $("total-devices").textContent = String(devices.length);
  $("online-devices").textContent = String(devices.filter((d) => d.status === "online").length);
  $("offline-devices").textContent = String(devices.filter((d) => d.status !== "online").length);
}

function renderDevices() {
  const list = $("device-list");
  list.replaceChildren();

  if (devices.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "Bạn chưa theo dõi thiết bị nào. Liên hệ người quản lý để được cấp quyền liên kết thiết bị.";
    list.appendChild(empty);
    return;
  }

  // Chỉ lọc các Device đã được Backend cho phép; không lấy dữ liệu của người khác.
  const keyword = ($("device-search")?.value || "").trim().toLocaleLowerCase("vi-VN");
  const visibleDevices = devices.filter((device) =>
    `${device.device_id} ${deviceName(device)}`.toLocaleLowerCase("vi-VN").includes(keyword)
  );
  for (const device of visibleDevices) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `device-item${selectedDeviceId === device.device_id ? " selected" : ""}`;
    button.setAttribute("aria-pressed", String(selectedDeviceId === device.device_id));

    const symbol = document.createElement("span");
    symbol.className = "device-icon";
    symbol.textContent = "▣";

    const info = document.createElement("span");
    info.className = "device-info";
    const name = document.createElement("span");
    name.className = "device-name";
    name.textContent = deviceName(device);
    const id = document.createElement("span");
    id.className = "device-sub";
    id.textContent = device.device_id;
    info.append(name, id);

    const dot = document.createElement("span");
    dot.className = `status-dot${device.status === "online" ? " online" : ""}`;
    dot.title = device.status === "online" ? "Online" : "Offline";
    button.append(symbol, info, dot);
    button.addEventListener("click", () => selectDevice(device.device_id));
    list.appendChild(button);
  }
}

function renderDetail(device, status) {
  if (!device || !status) {
    $("device-detail-empty").hidden = false;
    $("device-detail").hidden = true;
    return;
  }
  $("device-detail-empty").hidden = true;
  $("device-detail").hidden = false;
  $("detail-name").textContent = deviceName(device);
  $("detail-id").textContent = device.device_id;
  $("detail-model").textContent = device.model_version || "Chưa báo cáo";
  $("detail-seen").textContent = formatDate(status.last_seen_at);
  $("detail-timeout").textContent = `${status.timeout_seconds} giây`;
  $("detail-status").textContent = status.status === "online" ? "● ONLINE" : "● OFFLINE";
  $("detail-status").classList.toggle("online", status.status === "online");
}

function renderEvents(events, hasNext) {
  const body = $("event-list");
  body.replaceChildren();
  $("visible-events").textContent = String(events.length);
  $("page-label").textContent = `Trang ${currentPage + 1}`;
  $("previous-page").disabled = currentPage === 0;
  $("next-page").disabled = !hasNext;

  if (events.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 5;
    cell.className = "empty-table";
    cell.textContent = "Chưa có sự kiện ngã trong phạm vi đang xem.";
    row.appendChild(cell);
    body.appendChild(row);
    return;
  }

  // Dùng textContent để không thực thi HTML từ dữ liệu Device hoặc Fall Event.
  for (const event of events) {
    const row = document.createElement("tr");
    const model = event.model_version || "—";
    const confidence = event.confidence == null
      ? "—" : `${Math.round(event.confidence * 100)}%`;
    const values = [formatDate(event.event_time), event.device_id, "Phát hiện ngã", confidence, model];
    for (let index = 0; index < values.length; index += 1) {
      const cell = document.createElement("td");
      if (index === 2) {
        const chip = document.createElement("span");
        chip.className = "fall-chip";
        chip.textContent = values[index];
        cell.appendChild(chip);
      } else {
        cell.textContent = values[index];
      }
      row.appendChild(cell);
    }
    body.appendChild(row);
  }
}

async function loadDetail(version) {
  const id = selectedDeviceId;
  if (!id) {
    renderDetail(null, null);
    return;
  }
  const device = devices.find((item) => item.device_id === id);
  if (!device) return;
  const data = await apiRequest(`/devices/${encodeURIComponent(id)}/status`);
  if (version !== requestVersion) return;
  renderDetail(device, data);
}

async function loadEvents(version) {
  // Lịch sử nâng cao được lọc và phân trang tại Backend theo JWT hiện tại.
  const params = new URLSearchParams({
    limit: String(PAGE_SIZE), offset: String(currentPage * PAGE_SIZE),
  });
  if (selectedDeviceId) params.set("device_id", selectedDeviceId);
  const search = $("history-search")?.value.trim();
  if (search) params.set("q", search);
  const start = $("history-from")?.value;
  const end = $("history-to")?.value;
  if (start) params.set("from_at", new Date(`${start}T00:00:00`).toISOString());
  if (end) {
    const exclusive = new Date(`${end}T00:00:00`);
    exclusive.setDate(exclusive.getDate() + 1);
    params.set("to_at", exclusive.toISOString());
  }
  const confidence = $("history-confidence")?.value;
  if (confidence) params.set("min_confidence", confidence);
  const page = await apiRequest(`/management/fall-events?${params.toString()}`);
  if (version !== requestVersion) return;
  if (!Array.isArray(page?.items)) throw new Error("Trang lịch sử không hợp lệ.");
  $("history-total").textContent = `Tổng ${page.total} sự kiện phù hợp`;
  renderEvents(page.items, page.has_next);
}

function renderScope() {
  const device = devices.find((item) => item.device_id === selectedDeviceId);
  $("event-scope").textContent = device
    ? `Chỉ hiển thị sự kiện của ${deviceName(device)}`
    : "Tất cả thiết bị được theo dõi";
}

async function selectDevice(id) {
  selectedDeviceId = id;
  currentPage = 0;
  const version = ++requestVersion;
  showMessage("");
  renderDevices();
  renderScope();
  try {
    await Promise.all([loadDetail(version), loadEvents(version)]);
  } catch (error) {
    if (version === requestVersion) showMessage(error.message, true);
  }
}

async function changePage(delta) {
  currentPage = Math.max(0, currentPage + delta);
  const version = ++requestVersion;
  try {
    await loadEvents(version);
  } catch (error) {
    if (version === requestVersion) showMessage(error.message, true);
  }
}

async function refreshDashboard() {
  const version = ++requestVersion;
  $("refresh-button").disabled = true;
  showMessage("");
  try {
    const data = await apiRequest("/devices");
    if (version !== requestVersion) return;
    if (!Array.isArray(data)) throw new Error("Danh sách thiết bị không hợp lệ.");
    devices = data;
    if (selectedDeviceId && !devices.some((d) => d.device_id === selectedDeviceId)) {
      selectedDeviceId = null;
      currentPage = 0;
    }
    renderDevices();
    updateDeviceCounters();
    renderScope();
    await Promise.all([loadDetail(version), loadEvents(version)]);
    if (version !== requestVersion) return;
    $("updated-at").textContent = formatDate(new Date().toISOString());
    if (typeof dashboardManagementRefresh === "function") void dashboardManagementRefresh();
  } catch (error) {
    if (version === requestVersion) showMessage(error.message, true);
  } finally {
    if (version === requestVersion) $("refresh-button").disabled = false;
  }
}

// Tự đăng ký email/mật khẩu hoặc chọn tài khoản Google.
let authMode = "login";

function showAuthMode(mode) {
  authMode = mode;
  const register = mode === "register";
  $("login-form").hidden = register;
  $("register-form").hidden = !register;
  $("auth-title").textContent = register ? "Tạo tài khoản caregiver" : "Chào mừng trở lại";
  $("auth-description").textContent = register
    ? "Tạo tài khoản bằng email hoặc tiếp tục nhanh với Google."
    : "Đăng nhập để theo dõi các thiết bị được cấp quyền.";
  $("auth-switch-caption").textContent = register ? "Đã có tài khoản?" : "Chưa có tài khoản?";
  $("auth-switch-button").textContent = register ? "Đăng nhập" : "Đăng ký miễn phí";
  $("login-error").hidden = true;
  $("register-error").hidden = true;
}

async function activateSession(loginData) {
  if (!loginData?.access_token || !Number.isFinite(Number(loginData.expires_in))) {
    throw new Error("Backend trả thông tin phiên đăng nhập không hợp lệ.");
  }
  accessToken = loginData.access_token;
  expiresAt = Date.now() + Number(loginData.expires_in) * 1000;
  $("password").value = "";
  const me = await apiRequest("/auth/me");
  $("account-name").textContent = me.display_name || "Caregiver";
  $("account-email").textContent = me.email || "";
  $("login-view").hidden = true;
  $("dashboard-view").hidden = false;
  selectedDeviceId = null;
  currentPage = 0;
  await refreshDashboard();
  await loadUnreadAlerts();
  startRealtime();
}

async function registerAccount(event) {
  event.preventDefault();
  $("register-error").hidden = true;
  const password = $("register-password").value;
  if (password !== $("register-confirm").value) {
    $("register-error").textContent = "Hai mật khẩu không khớp.";
    $("register-error").hidden = false;
    return;
  }
  $("register-button").disabled = true;
  try {
    const email = $("register-email").value.trim();
    await apiRequest("/auth/register", {
      method: "POST", authenticated: false,
      body: {
        display_name: $("register-name").value.trim(),
        email,
        password,
      },
    });
    const loginData = await apiRequest("/auth/login", {
      method: "POST", authenticated: false,
      body: {email, password},
    });
    $("register-password").value = "";
    $("register-confirm").value = "";
    await activateSession(loginData);
  } catch (error) {
    if (!$("login-view").hidden) {
      $("register-error").textContent = error.message;
      $("register-error").hidden = false;
    } else {
      showMessage(error.message, true);
    }
  } finally {
    $("register-button").disabled = false;
  }
}

async function completeGoogleRedirect() {
  const params = new URLSearchParams(window.location.search);
  const googleFlag = params.get("google");
  const googleError = params.get("google_error");
  const googleLinked = params.get("linked") === "1";
  if (googleFlag === null && googleError === null) return;
  // Không để URL giữ lại cờ đăng nhập Google sau khi xử lý.
  window.history.replaceState({}, "", "/dashboard");
  if (googleError) {
    const errors = {
      conflict: "Email này đã có tài khoản. Vui lòng đăng nhập bằng mật khẩu; hệ thống chưa tự liên kết hai phương thức.",
      oauth: "Google đã hủy hoặc từ chối yêu cầu đăng nhập.",
      verify: "Google chưa cung cấp tài khoản có email được xác minh.",
      server: "Chưa thể hoàn tất đăng nhập Google. Vui lòng thử lại.",
      link_conflict: "Liên kết Google thất bại: email không khớp hoặc Google đã dùng ở tài khoản khác.",
      link_expired: "Phiên liên kết Google hết hạn. Vui lòng thử lại.",
    };
    $("login-error").textContent = errors[googleError] || errors.server;
    $("login-error").hidden = false;
    return;
  }
  try {
    // Cookie HttpOnly chỉ gửi cùng nguồn; JWT trả qua JSON, không nằm trong URL.
    const loginData = await apiRequest("/auth/google/complete", {
      method: "POST", authenticated: false,
    });
    await activateSession(loginData);
    if (googleLinked) showMessage("Đã liên kết Google thành công.");
  } catch (error) {
    $("login-error").textContent = error.message;
    $("login-error").hidden = false;
  }
}

async function login(event) {
  event.preventDefault();
  $("login-error").hidden = true;
  $("login-button").disabled = true;
  const email = $("email").value.trim();
  const password = $("password").value;
  try {
    const loginData = await apiRequest("/auth/login", {
      method: "POST", body: { email, password }, authenticated: false,
    });
    if (!loginData?.access_token || !Number.isFinite(Number(loginData.expires_in))) {
      throw new Error("Backend trả thông tin đăng nhập không hợp lệ.");
    }
    await activateSession(loginData);
  } catch (error) {
    if ($("login-view").hidden === false) {
      $("login-error").textContent = error.message;
      $("login-error").hidden = false;
    } else {
      showMessage(error.message, true);
    }
  } finally {
    $("login-button").disabled = false;
  }
}

// ------------------------------------------------------------
// Cảnh báo realtime: REST dùng để nhận lại, WS dùng để báo nhanh.
// ------------------------------------------------------------
function setRealtimeStatus(message, connected = false) {
  $("realtime-status").textContent = message;
  $("realtime-status").classList.toggle("connected", connected);
}

function renderAlertList() {
  const container = $("alert-list");
  container.replaceChildren();
  $("alert-unread-count").textContent = String(pendingAlerts.size);

  const alerts = Array.from(pendingAlerts.values())
    .sort((a, b) => b.notification_id - a.notification_id)
    .slice(0, 20);
  if (!alerts.length) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "Không có thông báo ngã nào chưa xem.";
    container.appendChild(empty);
    return;
  }

  for (const alert of alerts) {
    const item = document.createElement("article");
    item.className = "alert-item";
    const content = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = `CẢNH BÁO NGÃ — ${alert.device_name || alert.device_id}`;
    const details = document.createElement("p");
    details.textContent = `${formatDate(alert.event_time)} · ${alert.device_id} · Tin cậy: ${
      alert.confidence == null ? "không có" : Math.round(alert.confidence * 100) + "%"
    }`;
    content.append(title, details);

    const button = document.createElement("button");
    button.className = "button secondary small";
    button.type = "button";
    button.textContent = "Đã xem";
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        await apiRequest(`/alerts/${alert.notification_id}/read`, { method: "POST" });
        pendingAlerts.delete(alert.notification_id);
        renderAlertList();
      } catch (error) {
        button.disabled = false;
        showMessage(error.message, true);
      }
    });
    item.append(content, button);
    container.appendChild(item);
  }
}

function receiveAlert(data) {
  if (!data || !Number.isInteger(data.notification_id) || data.read_at) return;
  if (pendingAlerts.has(data.notification_id)) return;
  pendingAlerts.set(data.notification_id, data);
  renderAlertList();
  // Lịch sử ngã vẫn lấy từ API có phân quyền như Milestone 7.
  refreshDashboard();
  if (typeof dashboardManagementRefresh === "function") void dashboardManagementRefresh();
}

async function loadUnreadAlerts() {
  const version = realtimeGeneration;
  try {
    // API trả thông báo chưa xem; WS tiếp tục đưa về các bản ghi kế tiếp.
    const data = await apiRequest("/alerts?unread_only=true&limit=100");
    if (version !== realtimeGeneration || !Array.isArray(data)) return;
    for (const alert of data) {
      if (!pendingAlerts.has(alert.notification_id)) {
        pendingAlerts.set(alert.notification_id, alert);
      }
    }
    renderAlertList();
  } catch (error) {
    if (accessToken) showMessage(`Không tải được cảnh báo: ${error.message}`, true);
  }
}

function stopRealtime() {
  realtimeGeneration += 1;
  if (reconnectTimer !== null) clearTimeout(reconnectTimer);
  reconnectTimer = null;
  if (websocketPingTimer !== null) clearInterval(websocketPingTimer);
  websocketPingTimer = null;
  if (alertSocket) {
    const socket = alertSocket;
    alertSocket = null;
    socket.onclose = null;
    socket.close();
  }
  pendingAlerts.clear();
  renderAlertList();
  setRealtimeStatus("Chưa kết nối");
}

function startRealtime() {
  if (!accessToken || Date.now() >= expiresAt) return;
  const generation = realtimeGeneration;
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${scheme}://${window.location.host}/ws/alerts`);
  alertSocket = socket;
  setRealtimeStatus("Đang kết nối...");

  socket.onopen = () => {
    if (generation !== realtimeGeneration) return;
    // Trình duyệt không hỗ trợ tự đặt Authorization header cho WebSocket.
    // Vì vậy JWT được gửi trong thông điệp đầu, KHÔNG gắn trên URL.
    socket.send(JSON.stringify({ type: "auth", token: accessToken }));
  };

  socket.onmessage = (event) => {
    if (generation !== realtimeGeneration) return;
    let message;
    try { message = JSON.parse(event.data); } catch (_error) { return; }
    if (message.type === "authenticated") {
      reconnectAttempt = 0;
      setRealtimeStatus("Đang kết nối trực tiếp", true);
      if (websocketPingTimer !== null) clearInterval(websocketPingTimer);
      websocketPingTimer = setInterval(() => {
        if (socket.readyState === WebSocket.OPEN) socket.send("ping");
      }, 20000);
    } else if (message.type === "fall_alert") {
      receiveAlert(message.data);
    }
  };

  socket.onclose = (event) => {
    if (generation !== realtimeGeneration || !accessToken) return;
    alertSocket = null;
    if (websocketPingTimer !== null) clearInterval(websocketPingTimer);
    websocketPingTimer = null;
    if (event.code === 4401 || Date.now() >= expiresAt) {
      clearSession("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.");
      return;
    }
    setRealtimeStatus("Mất kết nối — đang thử lại");
    const delay = Math.min(15000, 1000 * 2 ** Math.min(reconnectAttempt, 4));
    reconnectAttempt += 1;
    reconnectTimer = setTimeout(async () => {
      reconnectTimer = null;
      if (generation !== realtimeGeneration || !accessToken) return;
      await loadUnreadAlerts();
      startRealtime();
    }, delay);
  };

  socket.onerror = () => {
    // Chờ onclose để tự kết nối lại, không in JWT vào log.
    setRealtimeStatus("Kết nối gặp lỗi");
  };
}

// Liên kết các thao tác giao diện với API đã được bảo vệ.
$("login-form").addEventListener("submit", login);
$("logout-button").addEventListener("click", () => clearSession("Bạn đã đăng xuất khỏi Dashboard."));
$("refresh-button").addEventListener("click", refreshDashboard);
$("view-all-button").addEventListener("click", () => selectDevice(null));
$("previous-page").addEventListener("click", () => changePage(-1));
$("next-page").addEventListener("click", () => changePage(1));

// Giao diện đăng ký và phản hồi sau khi Google chuyển hướng về Dashboard.
$("register-form").addEventListener("submit", registerAccount);
$("auth-switch-button").addEventListener("click", () => {
  showAuthMode(authMode === "login" ? "register" : "login");
});
completeGoogleRedirect();
