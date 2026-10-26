"use strict";

// Phiên JWT chỉ giữ trong RAM của tab hiện tại, không dùng localStorage.
let accessToken = "";
let adminProfile = null;
let currentPage = "overview";
let eventOffset = 0;
let lastDeviceList = [];
const $ = (id) => document.getElementById(id);

function showError(message) {
  // Tránh dùng innerHTML với dữ liệu đến từ Backend.
  $("global-error").textContent = message;
  $("global-error").hidden = !message;
}

function toast(message) {
  const element = $("toast");
  element.textContent = message;
  element.hidden = false;
  window.setTimeout(() => { element.hidden = true; }, 4200);
}

function displayTime(value) {
  if (!value) return "Chưa có";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? String(value) : date.toLocaleString("vi-VN");
}

function statusPill(label, className = "muted") {
  const element = document.createElement("span");
  element.className = `pill ${className}`;
  element.textContent = label;
  return element;
}

function cell(row, content) {
  const td = document.createElement("td");
  if (content instanceof Node) td.appendChild(content);
  else td.textContent = content == null ? "—" : String(content);
  row.appendChild(td);
  return td;
}

function emptyTable(tbody, message, colSpan) {
  tbody.replaceChildren();
  const tr = document.createElement("tr");
  const td = document.createElement("td");
  td.colSpan = colSpan;
  td.textContent = message;
  td.className = "muted";
  tr.appendChild(td);
  tbody.appendChild(tr);
}

async function api(path, options = {}) {
  const headers = { Accept: "application/json", ...(options.headers || {}) };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(path, {
    method: options.method || "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  if (response.status === 401 && path !== "/auth/login") {
    logout(false);
    throw new Error("Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại.");
  }
  if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
  return data;
}

function logout(message = true) {
  accessToken = "";
  adminProfile = null;
  $("login-password").value = "";
  $("app-shell").hidden = true;
  $("login-screen").hidden = false;
  showError("");
  if (message) toast("Đã đóng phiên Admin trên tab này.");
}

async function login(event) {
  event.preventDefault();
  $("login-error").textContent = "";
  const submit = $("login-form").querySelector("button[type=submit]");
  submit.disabled = true;
  try {
    const result = await api("/auth/login", {
      method: "POST",
      body: { email: $("login-email").value.trim(), password: $("login-password").value },
    });
    accessToken = result.access_token;
    adminProfile = await api("/admin/api/me");
    $("current-admin").textContent = adminProfile.email;
    $("login-screen").hidden = true;
    $("app-shell").hidden = false;
    await openSection("overview");
    toast("Đã xác thực quyền quản trị.");
  } catch (error) {
    accessToken = "";
    $("login-error").textContent = error.message === "Chỉ quản trị viên đã xác minh email được phép sử dụng."
      ? "Tài khoản này chưa được cấp quyền admin hoặc chưa xác minh email."
      : error.message;
  } finally {
    submit.disabled = false;
  }
}

const pageLabels = {
  overview: ["Tổng quan hệ thống", "Theo dõi hoạt động và chuẩn bị trình diễn với giảng viên."],
  devices: ["Quản lý thiết bị", "Quan sát trạng thái, chủ sở hữu và người theo dõi."],
  accounts: ["Tài khoản & chia sẻ", "Danh sách caregiver và quyền truy cập."],
  events: ["Sự kiện té ngã", "Lịch sử các lần ngã và số thông báo đã tạo."],
  simulation: ["Mô phỏng & kiểm thử", "Thao tác demo nhanh, không cần mở Swagger."],
  audit: ["Nhật ký hệ thống", "Theo dõi các thao tác bảo mật đã ghi nhận."],
};

async function openSection(section) {
  currentPage = section;
  showError("");
  for (const name of Object.keys(pageLabels)) $("section-" + name).hidden = name !== section;
  document.querySelectorAll(".nav-item").forEach((node) => {
    node.classList.toggle("active", node.dataset.section === section);
  });
  $("page-title").textContent = pageLabels[section][0];
  $("page-subtitle").textContent = pageLabels[section][1];
  try {
    if (section === "overview") await loadOverview();
    if (section === "devices") await loadDevices();
    if (section === "accounts") await loadAccounts();
    if (section === "events") await loadEvents();
    if (section === "simulation") await loadSimulation();
    if (section === "audit") await loadAudit();
  } catch (error) { showError(error.message); }
}

async function loadOverview() {
  const result = await api("/admin/api/summary");
  $("stat-devices").textContent = result.devices;
  $("stat-online").textContent = result.online_devices;
  $("stat-accounts").textContent = result.accounts;
  $("stat-events").textContent = result.fall_events;
}

async function runDiagnostics() {
  const result = await api("/admin/api/diagnostics");
  $("diagnostics-output").replaceChildren();
  for (const check of result.checks) {
    const row = document.createElement("div");
    row.className = "check-item";
    const name = document.createElement("div");
    name.textContent = check.name;
    const status = document.createElement("span");
    status.textContent = check.status === "pass" ? "PASS" : "FAIL";
    if (check.status !== "pass") status.className = "fail";
    row.append(name, status);
    $("diagnostics-output").appendChild(row);
  }
  toast(result.ok ? "Các kiểm tra nhanh đã PASS." : "Một số hạng mục kiểm tra FAIL.");
}

async function loadDevices() {
  const q = $("device-search").value.trim();
  const result = await api("/admin/api/devices?q=" + encodeURIComponent(q));
  lastDeviceList = result.items;
  const body = $("device-table");
  body.replaceChildren();
  if (!result.items.length) return emptyTable(body, "Không tìm thấy thiết bị.", 5);
  result.items.forEach((item) => {
    const row = document.createElement("tr");
    cell(row, item.device_id);
    cell(row, statusPill(item.status === "online" ? "Online" : "Offline", item.status === "online" ? "good" : "bad"));
    cell(row, item.owner_email || "Chưa có owner");
    cell(row, String(item.watcher_count));
    const button = document.createElement("button");
    button.className = "table-action";
    button.textContent = "Xem người theo dõi";
    button.addEventListener("click", () => loadWatchers(item.device_id));
    cell(row, button);
    body.appendChild(row);
  });
}

async function loadWatchers(deviceId) {
  try {
    const result = await api("/admin/api/devices/" + encodeURIComponent(deviceId) + "/watchers");
    $("watcher-title").textContent = "Người theo dõi — " + deviceId;
    $("watcher-list").replaceChildren();
    for (const watcher of result.items) {
      const row = document.createElement("div");
      row.className = "person-row";
      const identity = document.createElement("span");
      identity.textContent = watcher.email;
      row.append(identity, statusPill(watcher.role === "owner" ? "Owner" : "Viewer", watcher.role === "owner" ? "good" : "muted"));
      $("watcher-list").appendChild(row);
    }
    if (!result.items.length) $("watcher-list").textContent = "Chưa có người theo dõi.";
    $("watcher-panel").hidden = false;
  } catch (error) { showError(error.message); }
}

async function loadAccounts() {
  const result = await api("/admin/api/accounts?q=" + encodeURIComponent($("account-search").value.trim()));
  const body = $("account-table");
  body.replaceChildren();
  if (!result.items.length) return emptyTable(body, "Không tìm thấy tài khoản.", 5);
  result.items.forEach((item) => {
    const row = document.createElement("tr");
    cell(row, "#" + item.account_id);
    cell(row, item.email);
    cell(row, statusPill(item.verified ? "Đã xác minh" : "Chưa xác minh", item.verified ? "good" : "bad"));
    cell(row, String(item.devices));
    cell(row, item.is_admin ? "Admin" : "Caregiver");
    body.appendChild(row);
  });
}

async function loadEvents() {
  const device = $("events-device").value.trim();
  const result = await api(`/admin/api/events?device_id=${encodeURIComponent(device)}&limit=15&offset=${eventOffset}`);
  const body = $("events-table");
  body.replaceChildren();
  if (!result.items.length) emptyTable(body, "Không có FallEvent nào.", 6);
  result.items.forEach((item) => {
    const row = document.createElement("tr");
    cell(row, String(item.event_id));
    cell(row, item.device_id);
    cell(row, displayTime(item.event_time));
    cell(row, item.confidence == null ? "—" : Math.round(item.confidence * 100) + "%");
    cell(row, item.model_version);
    cell(row, String(item.alert_count));
    body.appendChild(row);
  });
  $("events-total").textContent = `Hiển thị ${result.items.length ? eventOffset + 1 : 0}–${eventOffset + result.items.length} / ${result.total}`;
  $("events-prev").disabled = eventOffset <= 0;
  $("events-next").disabled = !result.has_next;
}

async function loadSimulation() {
  const devices = await api("/admin/api/devices");
  lastDeviceList = devices.items;
  for (const selectId of ["simulation-device", "pairing-device"]) {
    const selection = $(selectId);
    const old = selection.value;
    selection.replaceChildren();
    const prompt = document.createElement("option");
    prompt.textContent = "Chọn thiết bị";
    prompt.value = "";
    selection.appendChild(prompt);
    for (const device of devices.items) {
      const option = document.createElement("option");
      option.value = device.device_id;
      option.textContent = `${device.device_id} — ${device.status}`;
      selection.appendChild(option);
    }
    if (devices.items.some((item) => item.device_id === old)) selection.value = old;
  }
  $("demo-mode-badge").textContent = adminProfile.demo_mode ? "● DEMO MODE" : "DEMO MODE TẮT";
  $("demo-mode-badge").className = adminProfile.demo_mode ? "pill good" : "pill bad";
  $("simulate-btn").disabled = !adminProfile.demo_mode;
  $("pairing-btn").disabled = !adminProfile.demo_mode;
}

async function simulateFall(event) {
  event.preventDefault();
  const device = $("simulation-device").value;
  if (!device) return toast("Hãy chọn thiết bị cần kiểm thử.");
  if (!window.confirm(`Tạo một FallEvent GIẢ LẬP cho ${device}?\n\nThông báo demo sẽ được lưu và gửi cho người theo dõi.`)) return;
  $("simulate-btn").disabled = true;
  try {
    const result = await api("/admin/api/demo/fall", {
      method: "POST",
      body: { device_id: device, confidence: Number($("simulation-confidence").value) / 100 },
    });
    $("simulate-result").hidden = false;
    $("simulate-result").textContent = `Đã lưu sự kiện demo #${result.event_id}\nThiết bị: ${result.device_id}\nTrạng thái: ${result.status}\nĐã tạo ${result.alert_count} thông báo caregiver.\n\nHãy chuyển sang Dashboard caregiver để quan sát.`;
    toast("FallEvent mô phỏng đã được ghi nhận.");
  } catch (error) { showError(error.message); }
  finally { $("simulate-btn").disabled = !adminProfile.demo_mode; }
}

async function issuePairing() {
  const device = $("pairing-device").value;
  if (!device) return toast("Hãy chọn thiết bị.");
  if (!window.confirm(`Cấp mã ghép nối MỚI cho ${device}? Mã cũ (nếu có) sẽ mất hiệu lực.`)) return;
  $("pairing-btn").disabled = true;
  try {
    const result = await api(`/admin/api/devices/${encodeURIComponent(device)}/pairing-token`, { method: "POST" });
    $("pairing-result").hidden = false;
    $("pairing-result").textContent = `Mã ghép nối (chỉ hiện lần này):\n${result.pairing_token}\n\nHết hạn: ${displayTime(result.expires_at)}\nDán mã này vào Dashboard caregiver để nhận quyền Owner.`;
    toast("Đã cấp mã ghép nối một lần.");
  } catch (error) { showError(error.message); }
  finally { $("pairing-btn").disabled = !adminProfile.demo_mode; }
}

async function loadAudit() {
  const result = await api("/admin/api/audit?limit=25");
  const body = $("audit-table");
  body.replaceChildren();
  if (!result.items.length) return emptyTable(body, "Chưa có nhật ký.", 5);
  result.items.forEach((item) => {
    const row = document.createElement("tr");
    cell(row, displayTime(item.created_at));
    cell(row, item.actor_account_id);
    cell(row, item.action);
    cell(row, statusPill(item.result, item.result === "success" ? "good" : "bad"));
    cell(row, item.request_id);
    body.appendChild(row);
  });
}

// Mỗi nút đều thực hiện hành động thật trên API, không có nút chỉ để trang trí.
$("login-form").addEventListener("submit", login);
$("logout-btn").addEventListener("click", async () => {
  // Thu hồi token ở Backend trước khi xóa khỏi bộ nhớ trình duyệt.
  try {
    await api("/security/logout", { method: "POST" });
  } catch (error) {
    // Dù mạng lỗi, giao diện vẫn khóa lại để không tiếp tục sử dụng JWT cũ.
  } finally {
    logout();
  }
});
$("refresh-page").addEventListener("click", () => openSection(currentPage));
$("navigation").addEventListener("click", (event) => {
  const node = event.target.closest("[data-section]");
  if (node) openSection(node.dataset.section);
});
$("run-diagnostics").addEventListener("click", async () => {
  try { await runDiagnostics(); } catch (error) { showError(error.message); }
});
$("device-search-btn").addEventListener("click", () => openSection("devices"));
$("account-search-btn").addEventListener("click", () => openSection("accounts"));
$("events-search-btn").addEventListener("click", () => { eventOffset = 0; openSection("events"); });
$("events-prev").addEventListener("click", () => { eventOffset = Math.max(0, eventOffset - 15); openSection("events"); });
$("events-next").addEventListener("click", () => { eventOffset += 15; openSection("events"); });
$("simulation-confidence").addEventListener("input", () => { $("confidence-label").textContent = $("simulation-confidence").value + "%"; });
$("simulate-form").addEventListener("submit", simulateFall);
$("pairing-btn").addEventListener("click", issuePairing);
