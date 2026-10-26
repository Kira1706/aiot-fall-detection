"use strict";

// Lớp giao diện chỉ sắp xếp lại các phần HTML đã có, không tự gọi API hoặc giữ JWT.
// Những ID cũ được giữ nguyên để Login, WebSocket, Account, Pairing và Management hoạt động.
(() => {
  const dashboard = document.getElementById("dashboard-view");
  const content = dashboard?.querySelector("main.content");
  const sidebar = dashboard?.querySelector(".sidebar");
  const navigation = sidebar?.querySelector("nav");
  if (!dashboard || !content || !sidebar || !navigation) {
    console.warn("Không tìm thấy bố cục Dashboard caregiver; bỏ qua giao diện mở rộng.");
    return;
  }

  // Nếu source đã được chỉnh tay và thiếu phần quan trọng, không di chuyển nửa chừng.
  const required = [
    "alerts-panel", "account-section", "pairing-section", "devices-section",
    "events-section", "notification-history",
  ];
  if (required.some((id) => !document.getElementById(id))) {
    console.warn("Dashboard không đúng cấu trúc tham chiếu 10.8+; giữ nguyên giao diện cũ.");
    return;
  }
  if (document.getElementById("cg-workspace")) return;

  const pages = [
    { id: "home", icon: "⌂", label: "Tổng quan", title: "Tình hình hôm nay", description: "Xem nhanh kết nối thiết bị và các thông báo cần chú ý." },
    { id: "devices", icon: "▣", label: "Thiết bị", title: "Thiết bị đang theo dõi", description: "Chọn thiết bị để xem trạng thái, đổi tên hoặc kiểm tra kết nối." },
    { id: "alerts", icon: "♢", label: "Cảnh báo", title: "Cảnh báo & xử lý sự cố", description: "Kiểm tra cảnh báo chưa xem, lịch sử thông báo và tình trạng xử lý." },
    { id: "history", icon: "◷", label: "Lịch sử ngã", title: "Lịch sử sự kiện ngã", description: "Tìm lại sự kiện theo thiết bị, thời gian và mức độ tin cậy." },
    { id: "sharing", icon: "♧", label: "Ghép nối & chia sẻ", title: "Ghép nối & chia sẻ", description: "Thêm thiết bị hoặc quản lý những người đang theo dõi cùng bạn." },
    { id: "account", icon: "♙", label: "Tài khoản", title: "Tài khoản & bảo mật", description: "Quản lý hồ sơ, mật khẩu và phương thức đăng nhập." },
  ];

  // Tạo phần tử nội dung bằng textContent, không chèn dữ liệu người dùng qua innerHTML.
  function node(tag, className, value) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (value !== undefined) el.textContent = value;
    return el;
  }

  const header = node("div", "cg-section-heading");
  const tag = node("span", "cg-section-tag", "TRANG CHỦ");
  const title = node("h2", "cg-section-title", "Tình hình hôm nay");
  title.id = "cg-section-title";
  const description = node("p", "cg-section-description", pages[0].description);
  header.append(tag, title, description);
  const workspace = node("div", "cg-workspace");
  workspace.id = "cg-workspace";
  const sections = new Map();
  for (const page of pages) {
    const section = node("section", "cg-view");
    section.id = `cg-${page.id}`;
    section.dataset.page = page.id;
    section.setAttribute("aria-labelledby", "cg-section-title");
    section.hidden = page.id !== "home";
    sections.set(page.id, section);
    workspace.appendChild(section);
  }

  // Thêm giao diện điều hướng trước các nội dung; mọi nút/form cũ vẫn được giữ nguyên.
  const notice = document.getElementById("dashboard-message");
  if (notice?.parentElement === content) {
    notice.insertAdjacentElement("afterend", header);
  } else {
    content.prepend(header);
  }
  header.insertAdjacentElement("afterend", workspace);

  const place = (id, page) => {
    const el = document.getElementById(id);
    if (el) sections.get(page).appendChild(el);
  };

  // Tổng quan: giữ lại các con số hữu ích nhất, ưu tiên tình trạng kết nối.
  const welcome = node("div", "cg-welcome");
  welcome.appendChild(node("div", "cg-welcome-visual", "♥"));
  const welcomeText = node("div", "cg-welcome-text");
  welcomeText.appendChild(node("span", "cg-welcome-eyebrow", "FALLGUARD / THEO DÕI AN TOÀN"));
  welcomeText.appendChild(node("h3", "", "Bạn đang theo dõi những người thân yêu"));
  welcomeText.appendChild(node("p", "", "Tình trạng thiết bị và cảnh báo mới nhất được cập nhật tại đây. Nếu thiết bị mất kết nối, hãy kiểm tra nguồn điện và Wi-Fi."));
  welcome.appendChild(welcomeText);
  sections.get("home").appendChild(welcome);

  const metrics = content.querySelector(".metrics");
  if (metrics) {
    sections.get("home").appendChild(metrics);
    // Không xóa các ID cũ, chỉ giấu chỉ số ít ý nghĩa đối với caregiver phổ thông.
    const visibleEvents = document.getElementById("visible-events")?.closest(".metric");
    if (visibleEvents) visibleEvents.hidden = true;
  }
  const managementMetrics = content.querySelector(".management-metrics");
  if (managementMetrics) {
    sections.get("home").appendChild(managementMetrics);
    const pendingMetric = document.getElementById("management-pending")?.closest(".metric");
    if (pendingMetric) pendingMetric.hidden = true;
  }

  const summary = node("div", "cg-attention");
  const attentionIcon = node("span", "cg-attention-icon", "!");
  attentionIcon.setAttribute("aria-hidden", "true");
  const attentionInfo = node("div", "cg-attention-copy");
  const attentionTitle = node("strong", "", "Đang kiểm tra cảnh báo...");
  const attentionDetail = node("p", "", "Thông báo chưa xem và trạng thái kết nối sẽ xuất hiện tại đây.");
  attentionInfo.append(attentionTitle, attentionDetail);
  const attentionButton = node("button", "button cg-primary-action", "Xem cảnh báo");
  attentionButton.type = "button";
  attentionButton.addEventListener("click", () => navigate("alerts"));
  summary.append(attentionIcon, attentionInfo, attentionButton);
  sections.get("home").appendChild(summary);

  const quick = node("div", "cg-quick-actions");
  const quickTitle = node("h3", "", "Bạn muốn làm gì tiếp?");
  const quickButtons = node("div", "cg-quick-grid");
  [
    { icon: "▣", label: "Xem thiết bị", detail: "Kiểm tra Online / Offline", page: "devices" },
    { icon: "◷", label: "Xem lịch sử ngã", detail: "Tra cứu sự kiện đã lưu", page: "history" },
    { icon: "♧", label: "Thêm người theo dõi", detail: "Ghép nối & chia sẻ quyền", page: "sharing" },
  ].forEach((item) => {
    const button = node("button", "cg-quick-card");
    button.type = "button";
    button.append(node("span", "cg-quick-symbol", item.icon));
    const group = node("span", "cg-quick-copy");
    group.append(node("strong", "", item.label), node("small", "", item.detail));
    button.append(group, node("span", "cg-quick-arrow", "→"));
    button.addEventListener("click", () => navigate(item.page));
    quickButtons.appendChild(button);
  });
  quick.append(quickTitle, quickButtons);
  sections.get("home").appendChild(quick);

  place("devices-section", "devices");
  place("alerts-panel", "alerts");
  place("notification-history", "alerts");
  place("reliability-panel", "alerts");
  place("events-section", "history");
  place("pairing-section", "sharing");
  place("account-section", "account");

  // Đưa dòng cập nhật vào cuối phần tổng quan, không làm mất ID mà app.js cập nhật.
  const lastUpdate = content.querySelector(".last-update");
  if (lastUpdate) sections.get("home").appendChild(lastUpdate);

  // Nội dung hỗ trợ ngắn, không quảng cáo rằng hệ thống thay thế việc chăm sóc thực tế.
  const help = node("p", "cg-guidance", "Lưu ý: Thông báo đã xem không có nghĩa sự cố đã được xử lý. Nếu nghi ngờ có người bị thương, hãy liên hệ hỗ trợ phù hợp.");
  sections.get("alerts").appendChild(help);

  // Thay menu dài bằng sáu nhóm chức năng; menu ngang vẫn hiện trên điện thoại.
  navigation.replaceChildren();
  navigation.classList.add("cg-navigation");
  navigation.setAttribute("aria-label", "Các mục của Dashboard caregiver");
  const navLinks = new Map();
  for (const page of pages) {
    const a = node("a", "cg-nav-link");
    a.href = `#cg-${page.id}`;
    a.append(node("span", "cg-nav-icon", page.icon), node("span", "cg-nav-label", page.label));
    if (page.id === "alerts") {
      const badge = node("span", "cg-nav-count");
      badge.hidden = true;
      badge.id = "cg-nav-unread";
      a.append(badge);
    }
    a.addEventListener("click", (event) => {
      event.preventDefault();
      navigate(page.id, true);
    });
    navLinks.set(page.id, a);
    navigation.appendChild(a);
  }

  // Nút xem tất cả sự kiện cũ vừa bỏ lọc thiết bị vừa mở trang lịch sử.
  document.getElementById("view-all-button")?.addEventListener("click", () => navigate("history"));

  function navigate(name, updateHash = false) {
    const next = pages.find((item) => item.id === name) || pages[0];
    for (const page of pages) {
      sections.get(page.id).hidden = page.id !== next.id;
      const link = navLinks.get(page.id);
      link.classList.toggle("active", page.id === next.id);
      if (page.id === next.id) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    }
    title.textContent = next.title;
    description.textContent = next.description;
    tag.textContent = next.id === "home" ? "TỔNG QUAN" : "KHÔNG GIAN NGƯỜI CHĂM SÓC";
    if (updateHash && window.location.hash !== `#cg-${next.id}`) {
      history.replaceState(null, "", `#cg-${next.id}`);
    }
    // Chỉ cuộn trang sau thao tác, tránh đưa màn hình login về đầu ngoài ý muốn.
    if (!dashboard.hidden) window.scrollTo({ top: 0, behavior: "instant" });
  }

  const currentFromHash = () => {
    const value = window.location.hash.replace(/^#cg-/, "");
    return pages.some((page) => `#cg-${page.id}` === window.location.hash) ? value : null;
  };
  navigate(currentFromHash() || "home");
  window.addEventListener("hashchange", () => {
    const page = currentFromHash();
    if (page) navigate(page);
  });

  // Đồng bộ nhãn từ những thành phần đang được Backend cập nhật.
  function refreshIndicators() {
    const raw = document.getElementById("alert-unread-count")?.textContent?.trim() || "0";
    const unread = Number(raw);
    const badge = document.getElementById("cg-nav-unread");
    const num = Number.isFinite(unread) && unread > 0 ? unread : 0;
    if (badge) {
      badge.textContent = num > 99 ? "99+" : String(num);
      badge.hidden = num === 0;
    }
    attentionTitle.textContent = num ? `Có ${num} cảnh báo chưa xem` : "Chưa có cảnh báo chưa xem";
    summary.classList.toggle("has-alert", num > 0);
    attentionDetail.textContent = num
      ? "Hãy mở mục Cảnh báo để kiểm tra. Đã xem và đã xử lý là hai trạng thái khác nhau."
      : "Bạn có thể mở mục Cảnh báo để xem lại những thông báo trước đó.";

    const offline = document.getElementById("offline-devices")?.textContent?.trim() || "—";
    const offlineCount = Number(offline);
    welcome.classList.toggle("has-offline", Number.isFinite(offlineCount) && offlineCount > 0);
  }
  ["alert-unread-count", "offline-devices"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) new MutationObserver(refreshIndicators).observe(el, { childList: true, characterData: true, subtree: true });
  });
  refreshIndicators();

  // Phím tắt Escape không xóa biểu mẫu, không thay đổi quyền hoặc phiên đăng nhập.
  dashboard.dataset.caregiverUi = "ready";
  console.info("FallGuard: giao diện caregiver mới đã được khởi tạo.");
})();
