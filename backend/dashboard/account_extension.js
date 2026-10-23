"use strict";

// Bổ sung quản lý tài khoản mà không thay thế logic Dashboard/Realtime đã PASS.
// JWT tiếp tục được giữ trong bộ nhớ bởi app.js, không lưu vào localStorage.
const accountEl = (id) => document.getElementById(id);
let accountProfile = null;

function showAccountPublicMessage(text) {
  const node = accountEl("account-public-message");
  node.textContent = text;
  node.hidden = !text;
}

async function fetchAccountProfile() {
  if (!accessToken) return;
  try {
    accountProfile = await apiRequest("/account/me");
    accountEl("profile-name").value = accountProfile.display_name || "";
    accountEl("account-status").textContent =
      `${accountProfile.email} · ${accountProfile.email_verified ? "Email đã xác minh" : "Email chưa xác minh"}` +
      ` · ${accountProfile.google_linked ? "Đã liên kết Google" : "Chưa liên kết Google"}`;
    accountEl("request-verification").hidden = !!accountProfile.email_verified;
    accountEl("link-google-button").disabled = !!accountProfile.google_linked;
    accountEl("change-password-form").hidden = !accountProfile.has_password;
  } catch (error) {
    if (accessToken) showMessage(error.message, true);
  }
}

// Sau khi đăng nhập thành công, Dashboard bỏ thuộc tính hidden.
const accountObserver = new MutationObserver(() => {
  const visible = !accountEl("dashboard-view").hidden;
  if (visible) fetchAccountProfile();
  else accountProfile = null;
});
accountObserver.observe(accountEl("dashboard-view"), { attributes: true, attributeFilter: ["hidden"] });

accountEl("forgot-toggle").addEventListener("click", () => {
  accountEl("forgot-form").hidden = !accountEl("forgot-form").hidden;
  accountEl("reset-form").hidden = true;
  showAccountPublicMessage("");
});

accountEl("forgot-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const data = await apiRequest("/account/password/forgot", {
      method: "POST", authenticated: false,
      body: { email: accountEl("forgot-email").value.trim() },
    });
    showAccountPublicMessage(data.message);
  } catch (error) { showAccountPublicMessage(error.message); }
});

let resetToken = null;
const fragment = new URLSearchParams(window.location.hash.slice(1));
const verifyToken = fragment.get("verify");
resetToken = fragment.get("reset");
if (verifyToken || resetToken) {
  // Xóa mã khỏi địa chỉ ngay sau khi đọc; fragment không được gửi tới HTTP server.
  window.history.replaceState({}, "", window.location.pathname + window.location.search);
}
if (verifyToken) {
  apiRequest("/account/verification/confirm", {
    method: "POST", authenticated: false, body: { token: verifyToken },
  }).then(() => showAccountPublicMessage("Email đã được xác minh. Bạn có thể đăng nhập."))
    .catch((error) => showAccountPublicMessage(error.message));
}
if (resetToken) {
  accountEl("login-form").hidden = true;
  accountEl("register-form").hidden = true;
  accountEl("reset-form").hidden = false;
  showAccountPublicMessage("Hãy đặt mật khẩu mới để hoàn tất yêu cầu khôi phục.");
}
accountEl("reset-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!resetToken) return;
  try {
    const result = await apiRequest("/account/password/reset", {
      method: "POST", authenticated: false,
      body: { token: resetToken, new_password: accountEl("reset-password").value },
    });
    resetToken = null;
    accountEl("reset-form").hidden = true;
    accountEl("login-form").hidden = false;
    accountEl("reset-password").value = "";
    showAccountPublicMessage(result.message);
  } catch (error) { showAccountPublicMessage(error.message); }
});

accountEl("profile-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await apiRequest("/account/me", {
      method: "PATCH", body: { display_name: accountEl("profile-name").value.trim() },
    });
    await fetchAccountProfile();
    accountEl("account-name").textContent = accountProfile.display_name;
    showMessage("Đã cập nhật hồ sơ.");
  } catch (error) { showMessage(error.message, true); }
});

accountEl("request-verification").addEventListener("click", async () => {
  try {
    const result = await apiRequest("/account/verification/request", { method: "POST" });
    showMessage(result.message);
  } catch (error) { showMessage(error.message, true); }
});

accountEl("change-password-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const result = await apiRequest("/account/password/change", {
      method: "POST", body: {
        current_password: accountEl("current-password").value,
        new_password: accountEl("new-password").value,
      },
    });
    accountEl("current-password").value = "";
    accountEl("new-password").value = "";
    clearSession(result.message);
  } catch (error) { showMessage(error.message, true); }
});

accountEl("link-google-button").addEventListener("click", async () => {
  const password = accountEl("google-link-password").value;
  accountEl("google-link-password").value = "";
  try {
    const result = await apiRequest("/auth/google/link/prepare", {
      method: "POST", body: { current_password: password },
    });
    if (result.start_path !== "/auth/google/link/start") throw new Error("Đường dẫn liên kết Google không hợp lệ.");
    window.location.assign(result.start_path);
  } catch (error) { showMessage(error.message, true); }
});


// Quản lý các liên kết đang được cấp quyền, dùng API có sẵn từ Milestone 4.
accountEl("rename-device-button").addEventListener("click", async () => {
  if (!selectedDeviceId) return;
  const newName = accountEl("rename-device-name").value.trim();
  if (!newName) return showMessage("Hãy nhập tên thiết bị.", true);
  try {
    await apiRequest(`/devices/${encodeURIComponent(selectedDeviceId)}/nickname`, {
      method: "PATCH", body: { display_name: newName },
    });
    await refreshDashboard();
    showMessage("Đã cập nhật tên hiển thị của thiết bị.");
  } catch (error) { showMessage(error.message, true); }
});

accountEl("unlink-device-button").addEventListener("click", async () => {
  if (!selectedDeviceId) return;
  const deviceId = selectedDeviceId;
  if (!window.confirm(`Hủy theo dõi ${deviceId}? Bạn sẽ không còn xem được dữ liệu thiết bị này.`)) return;
  try {
    await apiRequest(`/devices/${encodeURIComponent(deviceId)}/link`, { method: "DELETE" });
    selectedDeviceId = null;
    await refreshDashboard();
    await loadUnreadAlerts();
    showMessage("Đã hủy theo dõi thiết bị. Sự kiện cũ vẫn được lưu trên Server.");
  } catch (error) { showMessage(error.message, true); }
});
