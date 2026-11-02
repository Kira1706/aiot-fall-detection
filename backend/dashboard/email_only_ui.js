"use strict";

// Phương án B: chỉ hiển thị email/mật khẩu; không xóa tính năng Google trên Backend.
// Tích hợp bằng capture listener để giữ nguyên app.js đã vượt qua regression test.
(() => {
  const el = (id) => document.getElementById(id);
  const loginForm = el("login-form");
  const registerForm = el("register-form");
  const loginView = el("login-view");
  if (!loginForm || !registerForm || !loginView) {
    console.error("FallGuard: không tìm thấy các form đăng nhập/đăng ký.");
    return;
  }

  // Cập nhật yêu cầu mật khẩu đồng nhất với Pydantic ở Backend.
  const registerPassword = el("register-password");
  if (registerPassword) registerPassword.minLength = 10;
  const registerPasswordLabel = document.querySelector('label[for="register-password"]');
  if (registerPasswordLabel) registerPasswordLabel.textContent = "Mật khẩu (10–128 ký tự)";

  // Ẩn các nút Google ở giao diện; không xóa dữ liệu liên kết Google hiện có.
  el("google-button")?.closest("a")?.setAttribute("hidden", "");
  const googleLink = el("link-google-button");
  if (googleLink) googleLink.closest(".account-form")?.setAttribute("hidden", "");
  document.querySelector(".auth-divider")?.setAttribute("hidden", "");
  document.querySelector(".login-hint")?.setAttribute("hidden", "");

  // Loại bỏ dòng liên kết Google khi thông tin hồ sơ được cập nhật.
  const accountStatus = el("account-status");
  if (accountStatus) {
    const simplify = () => {
      const oldText = accountStatus.textContent || "";
      const newText = oldText.replace(/ · (?:Đã|Chưa) liên kết Google/g, "");
      if (newText !== oldText) accountStatus.textContent = newText;
    };
    new MutationObserver(simplify).observe(accountStatus, { childList: true, subtree: true, characterData: true });
    simplify();
  }

  // Giao diện kích hoạt tài khoản xuất hiện ngay sau đăng ký hoặc đăng nhập chưa xác minh.
  const pending = document.createElement("section");
  pending.id = "email-only-pending";
  pending.hidden = true;
  pending.setAttribute("aria-live", "polite");
  const heading = document.createElement("h3");
  heading.textContent = "Xác minh email để hoàn tất đăng ký";
  const description = document.createElement("p");
  description.id = "email-only-description";
  const feedback = document.createElement("p");
  feedback.id = "email-only-feedback";
  feedback.setAttribute("role", "status");
  const resend = document.createElement("button");
  resend.type = "button";
  resend.className = "button secondary full-width";
  resend.textContent = "Gửi lại email xác minh";
  const recheck = document.createElement("button");
  recheck.type = "button";
  recheck.className = "button primary full-width";
  recheck.textContent = "Tôi đã xác minh — Tiếp tục";
  const returnLogin = document.createElement("button");
  returnLogin.type = "button";
  returnLogin.className = "button text-button";
  returnLogin.textContent = "Quay về đăng nhập";
  pending.append(heading, description, feedback, resend, recheck, returnLogin);
  registerForm.insertAdjacentElement("afterend", pending);

  let pendingSession = null;
  let pendingEmail = "";
  function showPending(email, session, message) {
    pendingSession = session;
    pendingEmail = email;
    el("auth-title").textContent = "Kiểm tra hộp thư email";
    el("auth-description").textContent = "Bạn cần xác minh địa chỉ email trước khi theo dõi thiết bị.";
    loginForm.hidden = true;
    registerForm.hidden = true;
    pending.hidden = false;
    el("auth-switch-button")?.setAttribute("hidden", "");
    el("auth-switch-caption")?.setAttribute("hidden", "");
    el("forgot-toggle")?.setAttribute("hidden", "");
    el("forgot-form")?.setAttribute("hidden", "");
    description.textContent = `Email đăng ký: ${email}. Mở hộp thư, nhấn liên kết FallGuard rồi quay lại đây.`;
    feedback.textContent = message;
  }

  function goLogin() {
    pendingSession = null;
    pendingEmail = "";
    pending.hidden = true;
    el("auth-switch-button")?.removeAttribute("hidden");
    el("auth-switch-caption")?.removeAttribute("hidden");
    el("forgot-toggle")?.removeAttribute("hidden");
    if (typeof showAuthMode === "function") showAuthMode("login");
    loginForm.hidden = false;
    registerForm.hidden = true;
  }

  // Request này không dùng JWT của Dashboard, tránh mở Dashboard khi email chưa xác minh.
  async function pendingRequest(path, token, method = "GET") {
    const response = await fetch(path, {
      method,
      headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
      cache: "no-store",
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
    return body;
  }

  async function authenticatedProfile(loginData) {
    if (!loginData?.access_token || !Number.isFinite(Number(loginData.expires_in))) {
      throw new Error("Backend không trả JWT đăng nhập hợp lệ.");
    }
    const profile = await pendingRequest("/account/me", loginData.access_token);
    return profile;
  }

  async function activateOrVerify(loginData, email, initialMessage = "") {
    const profile = await authenticatedProfile(loginData);
    if (profile.email_verified) {
      pendingSession = null;
      pending.hidden = true;
      el("auth-switch-button")?.removeAttribute("hidden");
      el("auth-switch-caption")?.removeAttribute("hidden");
      el("forgot-toggle")?.removeAttribute("hidden");
      await activateSession(loginData);
      return;
    }
    showPending(email, loginData, initialMessage || "Email chưa được xác minh. Hãy kiểm tra hộp thư.");
  }

  // Chặn handler mặc định đã đăng ký ở app.js rồi sử dụng quy trình xác minh mới.
  registerForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    event.stopImmediatePropagation();
    const err = el("register-error");
    err.hidden = true;
    const password = registerPassword.value;
    if (password !== el("register-confirm").value) {
      err.textContent = "Hai mật khẩu không trùng nhau.";
      err.hidden = false;
      return;
    }
    const button = el("register-button");
    button.disabled = true;
    const email = el("register-email").value.trim();
    try {
      await apiRequest("/auth/register", {
        method: "POST", authenticated: false,
        body: { email, password, display_name: el("register-name").value.trim() },
      });
      // Login tạm thời chỉ phục vụ yêu cầu xác minh; chưa bật Dashboard.
      const loginData = await apiRequest("/auth/login", {
        method: "POST", authenticated: false, body: { email, password },
      });
      showPending(email, loginData, "Tài khoản đã được tạo. Đang yêu cầu gửi email xác minh...");
      try {
        await pendingRequest("/account/verification/request", loginData.access_token, "POST");
        feedback.textContent = "Đã gửi yêu cầu xác minh. Kiểm tra cả thư mục Spam nếu chưa thấy email.";
      } catch (error) {
        feedback.textContent = `Không gửi được yêu cầu xác minh: ${error.message}. Bạn có thể thử gửi lại.`;
      }
      registerPassword.value = "";
      el("register-confirm").value = "";
    } catch (error) {
      err.textContent = error.message;
      err.hidden = false;
    } finally {
      button.disabled = false;
    }
  }, true);

  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    event.stopImmediatePropagation();
    const err = el("login-error");
    err.hidden = true;
    const button = el("login-button");
    button.disabled = true;
    const email = el("email").value.trim();
    try {
      const loginData = await apiRequest("/auth/login", {
        method: "POST", authenticated: false,
        body: { email, password: el("password").value },
      });
      await activateOrVerify(loginData, email);
    } catch (error) {
      err.textContent = error.message;
      err.hidden = false;
    } finally {
      button.disabled = false;
    }
  }, true);

  resend.addEventListener("click", async () => {
    if (!pendingSession) return;
    resend.disabled = true;
    try {
      await pendingRequest("/account/verification/request", pendingSession.access_token, "POST");
      feedback.textContent = "Đã tiếp nhận yêu cầu. Hãy kiểm tra email; hệ thống giới hạn số lần gửi lại.";
    } catch (error) {
      feedback.textContent = `Không thể gửi lại: ${error.message}`;
    } finally {
      resend.disabled = false;
    }
  });

  recheck.addEventListener("click", async () => {
    if (!pendingSession) return;
    recheck.disabled = true;
    try {
      await activateOrVerify(pendingSession, pendingEmail, "Bạn chưa xác minh xong. Vui lòng nhấn liên kết trong email.");
    } catch (error) {
      feedback.textContent = `Không kiểm tra được trạng thái email: ${error.message}. Hãy đăng nhập lại nếu phiên đã hết hạn.`;
    } finally {
      recheck.disabled = false;
    }
  });

  returnLogin.addEventListener("click", goLogin);
})();
