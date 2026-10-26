"use strict";

// Chỉ sử dụng JWT qua API có sẵn; không lưu token vào localStorage.
// Hàm này trả token từ biến JS đã có nếu app chính cung cấp bridge.
(function () {
  const node = document.getElementById("reliability-panel");
  if (!node) return;

  // Mở rộng không can thiệp vào WebSocket đã PASS của các milestone trước.
  const status = node.querySelector("#reliability-status");
  const output = node.querySelector("#reliability-output");
  const eventInput = node.querySelector("#reliability-event-id");
  const noteInput = node.querySelector("#reliability-note");

  async function request(path, options = {}) {
    // app.js cần khai báo window.fallguardAuthorizedFetch dùng JWT trong bộ nhớ.
    if (typeof window.fallguardAuthorizedFetch !== "function") {
      throw new Error("Chưa kết nối hàm API đã xác thực từ app.js.");
    }
    return await window.fallguardAuthorizedFetch(path, options);
  }

  async function overview() {
    try {
      const data = await request("/reliability/overview");
      output.textContent = `Thiết bị: ${data.devices_total} | Offline: ${data.devices_offline} | Chưa xem: ${data.unread_notifications} | Sự cố chưa xử lý: ${data.incidents_without_action}`;
      status.textContent = "Đã cập nhật";
    } catch (error) {
      status.textContent = `Không tải được thống kê: ${error.message}`;
    }
  }

  async function update(kind) {
    const eventId = Number(eventInput.value);
    if (!Number.isSafeInteger(eventId) || eventId <= 0) {
      status.textContent = "Vui lòng nhập Event ID hợp lệ.";
      return;
    }
    try {
      const data = await request(`/reliability/incidents/${eventId}`, {
        method: "PUT", body: {status: kind, note: noteInput.value || null}
      });
      status.textContent = `Sự cố ${data.event_id}: ${data.status}`;
      await overview();
    } catch (error) {
      status.textContent = `Cập nhật thất bại: ${error.message}`;
    }
  }

  node.querySelector("#reliability-refresh").addEventListener("click", overview);
  node.querySelector("#reliability-ack").addEventListener("click", () => update("acknowledged"));
  node.querySelector("#reliability-resolve").addEventListener("click", () => update("resolved"));
  node.addEventListener("fallguard:authenticated", overview);
  // Chỉ cập nhật khi người dùng chọn xem, không gọi API liên tục lúc chưa đăng nhập.
})();
