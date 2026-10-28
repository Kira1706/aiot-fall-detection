"""Tổ chức tài liệu Swagger cho FallGuard mà không thay đổi API nghiệp vụ.

Cài đặt ở CUỐI main.py sau khi đăng ký tất cả router:
    from swagger_presentation import install_swagger_presentation
    install_swagger_presentation(app)

FastAPI(...) phải đặt docs_url=None và redoc_url=None để tránh trùng /docs.
"""

from copy import deepcopy
from functools import lru_cache
from ipaddress import ip_address
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.openapi.docs import get_swagger_ui_html


# Thứ tự nhóm được chọn theo quy trình demo thực tế.
GROUPS = [
    ("01 · Tài khoản", "Đăng ký, đăng nhập và kiểm tra người dùng đang đăng nhập."),
    ("02 · Bảo mật tài khoản", "Xác minh email, mật khẩu, liên kết Google và phiên đăng nhập."),
    ("03 · Thiết bị", "Xem những thiết bị mà caregiver có quyền truy cập và tình trạng kết nối."),
    ("04 · Ghép nối & chia sẻ", "Nhận quyền sở hữu, mời và thu hồi quyền caregiver."),
    ("05 · Dữ liệu ESP32", "Heartbeat, sự kiện té ngã và tải model; thường cần Device Key."),
    ("06 · Sự kiện té ngã", "Tra cứu lịch sử FallEvent và bộ lọc theo quyền caregiver."),
    ("07 · Cảnh báo & sự cố", "Thông báo, xác nhận đã xem, xử lý sự cố và replay."),
    ("08 · Thống kê & giám sát", "Bảng tổng quan, lịch sử thông báo và theo dõi độ sẵn sàng."),
    ("09 · Quản lý model", "Tải lên, phát hành và phân phối model cho thiết bị."),
    ("10 · Admin & demo", "Quản trị hệ thống và mô phỏng FallEvent; cần tài khoản Admin."),
    ("11 · Khác", "Các API kỹ thuật hoặc chưa được phân nhóm."),
]

# Chỉ hiện các API cần cho kịch bản trên /docs. Endpoint không tồn tại sẽ tự bỏ qua.
DEMO_ENDPOINTS = {
    ("post", "/auth/register"),
    ("post", "/auth/login"),
    ("get", "/auth/me"),
    ("get", "/devices"),
    ("get", "/devices/{device_id}"),
    ("get", "/devices/{device_id}/status"),
    ("post", "/pairing/claim"),
    ("post", "/shares/accept"),
    ("post", "/devices/{device_id}/shares/invitations"),
    ("get", "/management/summary"),
    ("get", "/management/fall-events"),
    ("get", "/management/alerts"),
    ("get", "/reliability/alerts/replay"),
    ("get", "/reliability/incidents/{event_id}"),
    ("put", "/reliability/incidents/{event_id}"),
    ("post", "/admin/api/demo/fall"),
}

# Ví dụ khớp các request model đã kiểm tra trong source tham chiếu.
# Tài khoản, mã ghép nối và email người được mời vẫn phải là dữ liệu THẬT.
REQUEST_EXAMPLES = {
    ("post", "/auth/login"): {
        "email": "demo.caregiver@example.com", "password": "THAY_BANG_MAT_KHAU_THAT"
    },
    ("post", "/auth/register"): None,  # Schema đăng ký có thể khác giữa các milestone.
    ("post", "/admin/api/demo/fall"): {
        "device_id": "DEV-001", "confidence": 0.95
    },
    ("post", "/devices/{device_id}/shares/invitations"): {
        "invitee_email": "caregiver.test@example.com"
    },
    ("put", "/reliability/incidents/{event_id}"): {
        "status": "acknowledged", "note": "Đã liên hệ người thân"
    },
}

SPECIFIC_DETAILS = {
    ("post", "/auth/login"): (
        "Đăng nhập caregiver",
        "Nhập email và **mật khẩu thật**. Phản hồi thành công chứa JWT để gọi API cần đăng nhập. "
        "Không đưa JWT vào ảnh chụp màn hình."
    ),
    ("get", "/devices"): (
        "Danh sách thiết bị đang theo dõi",
        "Chỉ hiện thiết bị mà caregiver hiện có quyền truy cập. Cần JWT hợp lệ."
    ),
    ("get", "/devices/{device_id}/status"): (
        "Xem trạng thái Online/Offline",
        "Chọn DEV-001 hoặc DEV-002 nếu tài khoản có quyền. Cần JWT hợp lệ."
    ),
    ("post", "/pairing/claim"): (
        "Nhận quyền Owner bằng mã ghép nối",
        "Cần mã ghép nối **mới, thật, còn hạn** do Admin cấp; không thể dùng Device ID thay cho mã."
    ),
    ("post", "/shares/accept"): (
        "Chấp nhận lời mời theo dõi",
        "Cần mã mời thật, còn hạn và được cấp đúng email của tài khoản hiện tại."
    ),
    ("get", "/management/fall-events"): (
        "Lọc lịch sử té ngã",
        "Xem FallEvent theo quyền caregiver; có bộ lọc và phân trang."
    ),
    ("get", "/management/alerts"): (
        "Xem lịch sử thông báo",
        "Lọc thông báo đã xem/chưa xem và phân trang. Cần JWT."
    ),
    ("get", "/reliability/alerts/replay"): (
        "Nhận lại cảnh báo sau mất kết nối",
        "Bắt đầu với after_id=0, limit=10, sau đó dùng next_cursor trả về ở lần gọi trước."
    ),
    ("put", "/reliability/incidents/{event_id}"): (
        "Cập nhật tình trạng xử lý sự cố",
        "Sử dụng event_id đang có trong Database. Ví dụ chuyển sang acknowledged; "
        "sự cố đã resolved không được chuyển lùi."
    ),
    ("post", "/admin/api/demo/fall"): (
        "Mô phỏng một lần té ngã",
        "**Lối demo ưu tiên.** Chỉ dùng trên môi trường phát triển, với tài khoản Admin. "
        "Nhập Device ID có thật (mặc định DEV-001), Backend **tự sinh UUIDv4 và thời gian UTC**; "
        "không cần nhập Device Key trên trình duyệt. Tạo dữ liệu và thông báo giả lập."
    ),
}


def _group_for(path: str) -> str:
    """Nhận diện nhóm theo tiền tố đường dẫn, không phụ thuộc router tags cũ."""
    if path.startswith("/admin/api/"):
        return GROUPS[9][0]
    if path.startswith("/auth/google") or path.startswith("/security/") or path.startswith("/account/"):
        return GROUPS[1][0]
    if path.startswith("/auth/"):
        return GROUPS[0][0]
    if path.startswith("/pairing") or path.startswith("/shares") or "/shares" in path or path.endswith("/pairing-role"):
        return GROUPS[3][0]
    if path.startswith("/model"):
        return GROUPS[8][0]
    if path.startswith("/device-ingest") or path.startswith("/edge"):
        return GROUPS[4][0]
    if path.startswith("/reliability/incidents") or path.startswith("/reliability/alerts") or path.startswith("/alerts"):
        return GROUPS[6][0]
    if path.startswith("/management/fall-events") or "/fall-events" in path or path.startswith("/fall-events"):
        return GROUPS[5][0]
    if path.startswith("/management/") or path.startswith("/reliability/") or path in ("/health", "/ready"):
        return GROUPS[7][0]
    if path.startswith("/devices/") or path == "/devices":
        return GROUPS[2][0]
    return GROUPS[10][0]


def _add_example(operation: dict, method: str, path: str) -> None:
    """Đính kèm JSON mẫu ở mức OpenAPI; không thay đổi validation của Backend."""
    example = REQUEST_EXAMPLES.get((method, path))
    if example is None:
        return
    media = operation.get("requestBody", {}).get("content", {}).get("application/json")
    if not isinstance(media, dict):
        return
    # Không phá ví dụ đã khai báo chính xác trong API gốc.
    if "example" not in media and "examples" not in media:
        media["example"] = deepcopy(example)


def _prepare_schema(source: dict, demo: bool) -> dict:
    """Tạo tài liệu tách biệt từ schema gốc, không làm thay đổi đường dẫn thực tế."""
    schema = deepcopy(source)
    schema["info"]["title"] = "FallGuard · API Demo" if demo else "FallGuard · API Developer"
    schema["info"]["description"] = (
        "Các API chính cho bài demo FallGuard. Thứ tự gợi ý: Login → Thiết bị → "
        "Giám sát → Mô phỏng FallEvent → Cảnh báo. Không nhập mã bí mật lên ảnh hoặc chat."
        if demo else
        "Danh sách API đầy đủ, được sắp xếp theo nghiệp vụ. Các endpoint vẫn giữ nguyên chức năng và phân quyền."
    )
    paths = {}
    used_groups = set()
    for path, operations in schema.get("paths", {}).items():
        if not isinstance(operations, dict):
            continue
        selected = {}
        for method, operation in operations.items():
            method_lower = method.lower()
            if method_lower not in {"get", "post", "put", "delete", "patch", "head", "options"}:
                continue
            if demo and (method_lower, path) not in DEMO_ENDPOINTS:
                continue
            group = _group_for(path)
            used_groups.add(group)
            operation["tags"] = [group]
            details = SPECIFIC_DETAILS.get((method_lower, path))
            if details:
                operation["summary"] = details[0]
                old = operation.get("description", "")
                operation["description"] = details[1] + ("\n\n**Chi tiết kỹ thuật:** " + old if old else "")
            _add_example(operation, method_lower, path)
            # Hiển thị Device ID minh họa nhưng không đụng các trường khác.
            for param in operation.get("parameters", []):
                if isinstance(param, dict) and param.get("in") == "path" and param.get("name") == "device_id":
                    param.setdefault("example", "DEV-001")
            selected[method] = operation
        if selected:
            paths[path] = selected
    schema["paths"] = paths
    schema["tags"] = [{"name": name, "description": desc} for name, desc in GROUPS if name in used_groups]
    return schema


def install_swagger_presentation(app: FastAPI) -> None:
    """Lắp hai bộ Swagger. Phải gọi sau khi đã include tất cả router.

    Tài liệu chỉ dành cho phát triển tại localhost, không phải cơ chế cấp quyền Admin.
    Các API nghiệp vụ vẫn xác thực JWT, Device Key hoặc Admin Key như trước.
    """

    @lru_cache(maxsize=1)
    def get_original() -> dict:
        """Tạo schema sau khi mọi API đã được đăng ký."""
        return app.openapi()

    def assert_docs_allowed(request: Request) -> None:
        """Không cho truy cập trang docs từ production hoặc IP ngoài localhost."""
        if os.getenv("APP_ENV", "development").lower() not in {"development", "test"}:
            raise HTTPException(status_code=404, detail="Tài liệu thử nghiệm không được bật.")
        address = request.client.host if request.client else ""
        try:
            local = ip_address(address).is_loopback
        except ValueError:
            local = False
        if not local:
            raise HTTPException(status_code=403, detail="Swagger chỉ cho phép truy cập từ localhost.")

    @app.get("/openapi-demo.json", include_in_schema=False)
    def demo_openapi(request: Request):
        """Trả OpenAPI đã lọc cho buổi demo."""
        assert_docs_allowed(request)
        return _prepare_schema(get_original(), demo=True)

    @app.get("/openapi-full.json", include_in_schema=False)
    def full_openapi(request: Request):
        """Trả OpenAPI đầy đủ, đã phân nhóm và có ví dụ."""
        assert_docs_allowed(request)
        return _prepare_schema(get_original(), demo=False)

    @app.get("/docs", include_in_schema=False)
    def demo_swagger(request: Request):
        """Mở Swagger rút gọn cho buổi thuyết trình."""
        assert_docs_allowed(request)
        return get_swagger_ui_html(
            openapi_url="/openapi-demo.json",
            title="FallGuard | Swagger Demo",
            swagger_ui_parameters={
                "docExpansion": "list", "filter": True,
                "displayRequestDuration": True, "persistAuthorization": False,
            },
        )

    @app.get("/docs/full", include_in_schema=False)
    def developer_swagger(request: Request):
        """Mở Swagger kỹ thuật đầy đủ."""
        assert_docs_allowed(request)
        return get_swagger_ui_html(
            openapi_url="/openapi-full.json",
            title="FallGuard | API Developer",
            swagger_ui_parameters={
                "docExpansion": "none", "filter": True,
                "displayRequestDuration": True, "persistAuthorization": False,
            },
        )
