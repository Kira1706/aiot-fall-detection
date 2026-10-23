"use strict";

// Milestone 10.8: bộ lọc và thống kê sử dụng JWT chỉ lưu trong RAM của app.js.
const mg = (id) => document.getElementById(id);
let managementGeneration = 0;
let managementAlertPage = 0;
let managementAlertRequest = 0;
let managementInviteRequest = 0;
const MANAGEMENT_PAGE_SIZE = 10;

function mgDateStart(value) {
  return value ? new Date(`${value}T00:00:00`).toISOString() : null;
}

function mgDateEnd(value) {
  if (!value) return null;
  const date = new Date(`${value}T00:00:00`);
  date.setDate(date.getDate() + 1);
  return date.toISOString();
}

function mgParams(prefix) {
  const params = new URLSearchParams({
    limit: String(MANAGEMENT_PAGE_SIZE),
    offset: String(managementAlertPage * MANAGEMENT_PAGE_SIZE),
    read_state: mg("notification-read-state").value,
  });
  const q = mg("notification-search").value.trim();
  if (q) params.set("q", q);
  const from = mgDateStart(mg(`${prefix}-from`).value);
  const to = mgDateEnd(mg(`${prefix}-to`).value);
  if (from) params.set("from_at", from);
  if (to) params.set("to_at", to);
  return params;
}

function mgTableMessage(message) {
  const row = document.createElement("tr");
  const cell = document.createElement("td");
  cell.colSpan = 5;
  cell.className = "management-empty";
  cell.textContent = message;
  row.appendChild(cell);
  mg("management-alert-rows").replaceChildren(row);
}

async function mgLoadAlertHistory() {
  if (!accessToken) return;
  const generation = managementGeneration;
  const request = ++managementAlertRequest;
  try {
    const params = mgParams("notification");
    const page = await apiRequest(`/management/alerts?${params.toString()}`);
    if (generation !== managementGeneration || request !== managementAlertRequest) return;
    const container = mg("management-alert-rows");
    container.replaceChildren();
    for (const item of page.items) {
      const row = document.createElement("tr");
      const columns = [formatDate(item.created_at), item.device_name || item.device_id,
                       `Fall #${item.event_id}`, item.read_at ? `Đã xem: ${formatDate(item.read_at)}` : "Chưa xem"];
      for (const text of columns) {
        const td = document.createElement("td");
        td.textContent = text;
        row.appendChild(td);
      }
      const action = document.createElement("td");
      if (!item.read_at) {
        const button = document.createElement("button");
        button.className = "button secondary small";
        button.type = "button";
        button.textContent = "Đánh dấu đã xem";
        button.addEventListener("click", async () => {
          button.disabled = true;
          try {
            await apiRequest(`/alerts/${item.notification_id}/read`, {method: "POST"});
            pendingAlerts.delete(item.notification_id);
            renderAlertList();
            await mgLoadAlertHistory();
            await mgLoadSummary();
          } catch (error) {
            showMessage(error.message, true);
            button.disabled = false;
          }
        });
        action.appendChild(button);
      } else {
        action.textContent = "—";
      }
      row.appendChild(action);
      container.appendChild(row);
    }
    if (!page.items.length) mgTableMessage("Không có thông báo phù hợp bộ lọc.");
    mg("management-alert-total").textContent = `Tổng ${page.total} thông báo`;
    mg("management-alert-page").textContent = `Trang ${managementAlertPage + 1}`;
    mg("management-alert-prev").disabled = managementAlertPage === 0;
    mg("management-alert-next").disabled = !page.has_next;
  } catch (error) {
    if (generation === managementGeneration && request === managementAlertRequest) {
      mgTableMessage(error.message);
      showMessage(error.message, true);
    }
  }
}

async function mgLoadSummary() {
  if (!accessToken) return;
  const generation = managementGeneration;
  try {
    const summary = await apiRequest("/management/summary");
    if (generation !== managementGeneration) return;
    mg("management-falls30").textContent = String(summary.falls_last_30_days);
    mg("management-unread").textContent = String(summary.unread_alerts);
    mg("management-pending").textContent = String(summary.pending_invitations);
  } catch (error) {
    if (generation === managementGeneration) showMessage(error.message, true);
  }
}

async function mgLoadInvitations() {
  const id = selectedDeviceId;
  const container = mg("management-invitations");
  const request = ++managementInviteRequest;
  const generation = managementGeneration;
  container.replaceChildren();
  if (!accessToken || !id) return;
  try {
    const role = await apiRequest(`/devices/${encodeURIComponent(id)}/pairing-role`);
    if (request !== managementInviteRequest || generation !== managementGeneration || id !== selectedDeviceId) return;
    if (role.role !== "owner") return;
    const invites = await apiRequest(`/management/devices/${encodeURIComponent(id)}/invitations`);
    if (request !== managementInviteRequest || generation !== managementGeneration || id !== selectedDeviceId) return;
    if (!invites.length) {
      const p = document.createElement("p");
      p.className = "muted";
      p.textContent = "Không có lời mời đang chờ.";
      container.appendChild(p);
    }
    for (const invite of invites) {
      const row = document.createElement("div");
      row.className = "pairing-share-row";
      const label = document.createElement("span");
      label.textContent = `${invite.invitee_email} · Hết hạn: ${formatDate(invite.expires_at)}`;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "button secondary small";
      button.textContent = "Thu hồi lời mời";
      button.addEventListener("click", async () => {
        if (!confirm(`Thu hồi lời mời tới ${invite.invitee_email}?`)) return;
        button.disabled = true;
        try {
          await apiRequest(`/management/devices/${encodeURIComponent(id)}/invitations/${invite.invitation_id}`, {method: "DELETE"});
          pairingMessage("Đã thu hồi lời mời. Mã cũ không còn dùng được.");
          await mgLoadInvitations();
          await mgLoadSummary();
        } catch (error) {
          pairingMessage(error.message, true);
          button.disabled = false;
        }
      });
      row.append(label, button);
      container.appendChild(row);
    }
  } catch (error) {
    if (request === managementInviteRequest && generation === managementGeneration) {
      pairingMessage(error.message, true);
    }
  }
}

// API được app.js gọi khi đăng nhập xong, làm mới hoặc nhận cảnh báo.
function dashboardManagementRefresh() {
  if (!accessToken) return;
  void mgLoadSummary();
  void mgLoadAlertHistory();
  void mgLoadInvitations();
}

function dashboardManagementClear() {
  managementGeneration += 1;
  managementAlertRequest += 1;
  managementInviteRequest += 1;
  managementAlertPage = 0;
  mg("management-alert-total").textContent = "—";
  mg("management-falls30").textContent = "—";
  mg("management-unread").textContent = "—";
  mg("management-pending").textContent = "—";
  mgTableMessage("Đăng nhập để xem lịch sử.");
  mg("management-invitations").replaceChildren();
}

// Các bộ lọc cũ vẫn dùng trong app.js để giữ bảng FallEvent duy nhất.
mg("history-filter-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  currentPage = 0;
  const version = ++requestVersion;
  try { await loadEvents(version); }
  catch (error) { if (version === requestVersion) showMessage(error.message, true); }
});
mg("history-filter-reset").addEventListener("click", async () => {
  mg("history-filter-form").reset();
  currentPage = 0;
  const version = ++requestVersion;
  try { await loadEvents(version); }
  catch (error) { if (version === requestVersion) showMessage(error.message, true); }
});
mg("device-search").addEventListener("input", renderDevices);
mg("notification-filter-form").addEventListener("submit", (event) => {
  event.preventDefault();
  managementAlertPage = 0;
  void mgLoadAlertHistory();
});
mg("notification-filter-reset").addEventListener("click", () => {
  mg("notification-filter-form").reset();
  managementAlertPage = 0;
  void mgLoadAlertHistory();
});
mg("management-alert-prev").addEventListener("click", () => {
  managementAlertPage = Math.max(0, managementAlertPage - 1);
  void mgLoadAlertHistory();
});
mg("management-alert-next").addEventListener("click", () => {
  managementAlertPage += 1;
  void mgLoadAlertHistory();
});

// Đổi Device phải tải lại lời mời theo quyền chủ sở hữu.
const mgDetailObserver = new MutationObserver(() => { void mgLoadInvitations(); });
mgDetailObserver.observe(mg("detail-id"), {childList: true, characterData: true, subtree: true});

// Reset dữ liệu khi người dùng đăng xuất, tránh giữ thông tin tài khoản trước.
const mgSessionObserver = new MutationObserver(() => {
  if (mg("dashboard-view").hidden) dashboardManagementClear();
  else dashboardManagementRefresh();
});
mgSessionObserver.observe(mg("dashboard-view"), {attributes: true, attributeFilter: ["hidden"]});
