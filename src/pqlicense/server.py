import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

from .license_controller import LicenseController
from .signers import KeyBundle

WEB_ROOT = Path(__file__).resolve().parents[2] / "web"


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: Dict[str, Any]) -> None:
    data = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _bearer_token(handler: BaseHTTPRequestHandler) -> str:
    authorization = handler.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip()
    return ""


def _require_admin(handler: BaseHTTPRequestHandler, controller: LicenseController) -> bool:
    if controller.is_admin_token(_bearer_token(handler)):
        return True
    _json_response(handler, 401, {"error": "admin_auth_required"})
    return False


def _read_json_body(handler: BaseHTTPRequestHandler) -> Dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(length) if length else b"{}"
    return json.loads(raw.decode("utf-8"))


def _static_response(handler: BaseHTTPRequestHandler, path: Path, content_type: str) -> None:
    data = path.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def make_handler(
    *,
    keys: KeyBundle,
    revocations: Optional[Dict[str, Any]],
    product_id: str,
    revocations_path: Optional[str],
):
    controller = LicenseController(
        keys=keys,
        revocations=revocations,
        product_id=product_id,
        revocations_path=revocations_path,
    )

    class LicenseHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            try:
                body = _read_json_body(self)
            except json.JSONDecodeError:
                _json_response(self, 400, {"error": "invalid_json"})
                return

            if self.path == "/api/auth/register":
                response = controller.register(body)
                if response.get("status") != "registered":
                    _json_response(self, 400, response)
                    return
                _json_response(self, 200, response)
                return

            if self.path == "/api/admin/login":
                response = controller.login(body)
                if response.get("status") != "authenticated":
                    _json_response(self, 401, response)
                    return
                _json_response(self, 200, response)
                return

            if self.path == "/api/my-licenses/validate":
                token = _bearer_token(self)
                result = controller.validate_owned_license(token, body.get("license_id", ""))
                error = result.get("error")
                if error == "auth_required":
                    _json_response(self, 401, result)
                    return
                if error == "forbidden":
                    _json_response(self, 403, result)
                    return
                if error == "license_not_found":
                    _json_response(self, 404, result)
                    return
                if error:
                    _json_response(self, 400, result)
                    return
                _json_response(self, 200, result)
                return

            if self.path == "/api/my-licenses/cancel":
                token = _bearer_token(self)
                result = controller.revoke_owned_license(
                    token, body.get("license_id", ""), body.get("reason", "")
                )
                error = result.get("error")
                if error == "auth_required":
                    _json_response(self, 401, result)
                    return
                if error == "forbidden":
                    _json_response(self, 403, result)
                    return
                if error == "license_not_found":
                    _json_response(self, 404, result)
                    return
                if error:
                    _json_response(self, 400, result)
                    return
                _json_response(self, 200, result)
                return

            if self.path == "/api/my-licenses/activate":
                token = _bearer_token(self)
                result = controller.activate_license(
                    token, body.get("license_id", ""), body.get("device_fingerprint", "")
                )
                error = result.get("error")
                if error == "auth_required":
                    _json_response(self, 401, result)
                    return
                if error == "license_owned_by_other":
                    _json_response(self, 403, result)
                    return
                if error == "license_not_found":
                    _json_response(self, 404, result)
                    return
                if error:
                    _json_response(self, 400, result)
                    return
                _json_response(self, 200, result)
                return

            if self.path in ("/api/reset-keys", "/api/licenses/reset-keys"):
                if not _require_admin(self, controller):
                    return
                _json_response(self, 200, controller.reset_keys())
                return

            if self.path in ("/api/create-license", "/api/licenses/generate"):
                if not _require_admin(self, controller):
                    return
                try:
                    response = controller.generate(body)
                except (KeyError, TypeError, ValueError) as exc:
                    _json_response(self, 400, {"error": "invalid_license_request", "details": str(exc)})
                    return
                _json_response(self, 200, response)
                return

            if self.path in ("/validate", "/api/validate", "/api/licenses/validate"):
                _json_response(self, 200, controller.validate(body))
                return

            if self.path in ("/revoke", "/api/revoke"):
                if not _require_admin(self, controller):
                    return
                _json_response(self, 200, controller.cancel(body["license_id"], body))
                return

            if self.path.startswith("/api/licenses/") and self.path.endswith("/cancel"):
                if not _require_admin(self, controller):
                    return
                license_id = self.path.removeprefix("/api/licenses/").removesuffix("/cancel")
                _json_response(self, 200, controller.cancel(license_id, body))
                return

            _json_response(self, 404, {"error": "not_found"})

        def do_GET(self) -> None:
            if self.path == "/" or self.path == "/login":
                _static_response(self, WEB_ROOT / "login.html", "text/html; charset=utf-8")
                return
            if self.path == "/app":
                _static_response(self, WEB_ROOT / "index.html", "text/html; charset=utf-8")
                return
            if self.path == "/user":
                _static_response(self, WEB_ROOT / "user.html", "text/html; charset=utf-8")
                return
            if self.path == "/styles.css":
                _static_response(self, WEB_ROOT / "styles.css", "text/css; charset=utf-8")
                return
            if self.path == "/app.js":
                _static_response(self, WEB_ROOT / "app.js", "text/javascript; charset=utf-8")
                return
            if self.path == "/login.js":
                _static_response(self, WEB_ROOT / "login.js", "text/javascript; charset=utf-8")
                return
            if self.path == "/user.js":
                _static_response(self, WEB_ROOT / "user.js", "text/javascript; charset=utf-8")
                return
            if self.path == "/logo.png":
                _static_response(self, WEB_ROOT / "logo.png", "image/png")
                return
            if self.path == "/theme.js":
                _static_response(self, WEB_ROOT / "theme.js", "text/javascript; charset=utf-8")
                return
            if self.path in ("/api/state", "/api/licenses/state"):
                _json_response(self, 200, controller.state())
                return
            if self.path == "/api/my-licenses":
                result = controller.my_licenses(_bearer_token(self))
                if result.get("error"):
                    _json_response(self, 401, result)
                    return
                _json_response(self, 200, result)
                return
            if self.path == "/api/licenses":
                if not _require_admin(self, controller):
                    return
                _json_response(self, 200, controller.list_licenses())
                return
            if self.path == "/api/historial":
                if not _require_admin(self, controller):
                    return
                _json_response(self, 200, controller.historial())
                return
            if self.path == "/api/cancelaciones":
                if not _require_admin(self, controller):
                    return
                _json_response(self, 200, controller.cancelaciones())
                return
            if self.path in ("/revocations", "/api/revocations", "/api/licenses/revocations"):
                if not _require_admin(self, controller):
                    return
                _json_response(self, 200, controller.revocation_list())
                return
            _json_response(self, 404, {"error": "not_found"})

        def log_message(self, format: str, *args: Any) -> None:
            return

    return LicenseHandler


def serve(
    *,
    keys: KeyBundle,
    revocations: Optional[Dict[str, Any]],
    product_id: str,
    host: str,
    port: int,
    revocations_path: Optional[str],
) -> None:
    handler = make_handler(
        keys=keys,
        revocations=revocations,
        product_id=product_id,
        revocations_path=revocations_path,
    )
    server = ThreadingHTTPServer((host, port), handler)
    print(f"license API listening on http://{host}:{port}")
    server.serve_forever()