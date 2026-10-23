"use strict";

// Chỉ sử dụng JWT đang ở trong bộ nhớ của Dashboard, không lưu mã vào localStorage.
const pairingEl = (id) => document.getElementById(id);
let pairingSelectedId = null;
let pairingRoleVersion = 0;

function pairingMessage(message, isError = false) {
  const node = pairingEl("pairing-message");
  node.textContent = message;
  node.style.color = isError ? "#b91c1c" : "";
}

function hideIssuedToken() {
  pairingEl("pairing-issued-value").textContent = "";
  pairingEl("pairing-issued-token").hidden = true;
}

async function refreshPairingRole() {
  const id = accessToken && selectedDeviceId ? selectedDeviceId : null;
  const version = ++pairingRoleVersion;
  if (id !== pairingSelectedId) hideIssuedToken();
  pairingSelectedId = id;
  pairingEl("pairing-owner-panel").hidden = !id;
  pairingEl("unlink-device-button").hidden = false;
  if (!id) return;
  pairingEl("pairing-current-device").textContent = id;
  try {
    const roleData = await apiRequest(`/devices/${encodeURIComponent(id)}/pairing-role`);
    if (version !== pairingRoleVersion) return;
    const isOwner = roleData.role === "owner";
    pairingEl("pairing-current-role").textContent = `Vai trò: ${roleData.role}`;
    pairingEl("pairing-owner-actions").hidden = !isOwner;
    pairingEl("pairing-viewer-message").textContent = isOwner ? "" :
      (roleData.role === "legacy" ? "Thiết bị cũ chưa được chỉ định chủ sở hữu; cần quản trị viên rà soát." :
        "Bạn chỉ có quyền theo dõi. Chủ sở hữu mới có thể mời hoặc thu hồi người khác.");
    // Chủ sở hữu không được hủy liên kết bằng API cũ.
    pairingEl("unlink-device-button").hidden = isOwner;
    if (!isOwner) return;
    const members = await apiRequest(`/devices/${encodeURIComponent(id)}/shares`);
    if (version !== pairingRoleVersion) return;
    const container = pairingEl("pairing-share-list");
    container.replaceChildren();
    for (const member of members) {
      const row = document.createElement("div");
      row.className = "pairing-share-row";
      const label = document.createElement("span");
      label.textContent = `${member.display_name} · ${member.email} (${member.role})`;
      row.appendChild(label);
      if (member.role === "viewer") {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "button secondary";
        button.textContent = "Thu hồi quyền";
        button.addEventListener("click", async () => {
          if (!confirm(`Thu hồi quyền theo dõi của ${member.email}?`)) return;
          try {
            await apiRequest(`/devices/${encodeURIComponent(id)}/shares/${member.account_id}`, {method: "DELETE"});
            pairingMessage("Đã thu hồi quyền theo dõi.");
            await refreshPairingRole();
            await refreshDashboard();
          } catch (error) { pairingMessage(error.message, true); }
        });
        row.appendChild(button);
      }
      container.appendChild(row);
    }
  } catch (error) {
    if (version === pairingRoleVersion) pairingMessage(error.message, true);
  }
}

pairingEl("pairing-claim-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const token = pairingEl("pairing-token").value.trim();
    const result = await apiRequest("/pairing/claim", {method: "POST", body: {token}});
    pairingEl("pairing-token").value = "";
    pairingMessage(`Đã nhận quyền sở hữu ${result.device_id}. Hãy chọn thiết bị trong danh sách.`);
    await refreshDashboard();
  } catch (error) { pairingMessage(error.message, true); }
});

pairingEl("pairing-accept-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const token = pairingEl("invitation-token").value.trim();
    const result = await apiRequest("/shares/accept", {method: "POST", body: {token}});
    pairingEl("invitation-token").value = "";
    pairingMessage(`Đã được cấp quyền theo dõi ${result.device_id}.`);
    await refreshDashboard();
  } catch (error) { pairingMessage(error.message, true); }
});

pairingEl("pairing-invite-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!selectedDeviceId) return;
  const id = selectedDeviceId;
  try {
    const result = await apiRequest(`/devices/${encodeURIComponent(id)}/shares/invitations`, {
      method: "POST", body: {invitee_email: pairingEl("pairing-invite-email").value.trim()},
    });
    pairingEl("pairing-issued-value").textContent = result.invitation_token;
    pairingEl("pairing-issued-token").hidden = false;
    pairingMessage(`Mã mời dành riêng cho ${result.invitee_email}, hết hạn sau 24 giờ.`);
  } catch (error) { pairingMessage(error.message, true); }
});

pairingEl("pairing-hide-token").addEventListener("click", hideIssuedToken);

// Khi chọn thiết bị, app.js thay textContent của phần chi tiết.
// Observer này không thay đổi logic đăng nhập, cảnh báo hoặc lịch sử đã PASS.
const detailObserver = new MutationObserver(() => { void refreshPairingRole(); });
detailObserver.observe(pairingEl("detail-id"), {childList: true, characterData: true, subtree: true});
detailObserver.observe(pairingEl("device-detail"), {attributes: true, attributeFilter: ["hidden"]});
const sessionObserver = new MutationObserver(() => {
  if (pairingEl("dashboard-view").hidden) {
    pairingRoleVersion += 1;
    pairingSelectedId = null;
    hideIssuedToken();
    pairingEl("pairing-owner-panel").hidden = true;
    pairingMessage("");
  }
});
sessionObserver.observe(pairingEl("dashboard-view"), {attributes: true, attributeFilter: ["hidden"]});
