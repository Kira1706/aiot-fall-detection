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

// Đọc lỗi trả về từ FastAPI mà không hiển thị thông tin nội bộ.
function getErrorMessage(data, status) {
  if (typeof data?.detail === "string") return data.detail;
  if (Array.isArray(data?.detail)) {
    return data.detail.map((item) => item.msg || "Dữ liệu không hợp lệ").join("; ");
  }
  return `Yêu cầu thất bại (HTTP ${status}).`;
}

function clearSession(message = "") {
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

  for (const device of devices) {
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
  const path = selectedDeviceId
    ? `/devices/${encodeURIComponent(selectedDeviceId)}/fall-events`
    : "/fall-events";
  const query = `?limit=${PAGE_SIZE + 1}&offset=${currentPage * PAGE_SIZE}`;
  const data = await apiRequest(path + query);
  if (version !== requestVersion) return;
  if (!Array.isArray(data)) throw new Error("Dữ liệu lịch sử không đúng định dạng.");
  renderEvents(data.slice(0, PAGE_SIZE), data.length > PAGE_SIZE);
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
  } catch (error) {
    if (version === requestVersion) showMessage(error.message, true);
  } finally {
    if (version === requestVersion) $("refresh-button").disabled = false;
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

// Liên kết các thao tác giao diện với API đã được bảo vệ.
$("login-form").addEventListener("submit", login);
$("logout-button").addEventListener("click", () => clearSession("Bạn đã đăng xuất khỏi Dashboard."));
$("refresh-button").addEventListener("click", refreshDashboard);
$("view-all-button").addEventListener("click", () => selectDevice(null));
$("previous-page").addEventListener("click", () => changePage(-1));
$("next-page").addEventListener("click", () => changePage(1));
