import json
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib import request


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from pqlicense.core import create_key_bundle  # noqa: E402
from pqlicense.server import make_handler  # noqa: E402


class WebFrontendTests(unittest.TestCase):
    def setUp(self):
        self.keys = create_key_bundle()
        handler = make_handler(
            keys=self.keys,
            revocations=None,
            product_id="app-pro",
            revocations_path=None,
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()

    def get_text(self, path):
        with request.urlopen(self.base_url + path, timeout=5) as response:
            return response.read().decode("utf-8")

    def post_json(self, path, payload, token=None):
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self.base_url + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with request.urlopen(req, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    def admin_token(self):
        return self.post_json("/api/admin/login", {"username": "admin", "password": "admin123"})["token"]

    def test_frontend_is_served(self):
        html = self.get_text("/")

        self.assertIn("Sistema de Licencias", html)
        self.assertIn("app.js", html)
        self.assertIn("styles.css", html)
        self.assertIn("Modo de firma", html)
        self.assertIn("Plan", html)
        self.assertIn("Huella de dispositivo", html)
        self.assertIn("Detalles de verificacion", html)
        self.assertIn("Acceso administrador", html)
        self.assertIn("Licencias emitidas", html)
        self.assertIn("Revocaciones", html)

    def test_frontend_api_generates_validates_and_revokes_license(self):
        token = self.admin_token()
        created = self.post_json(
            "/api/create-license",
            {
                "license_id": "LIC-WEB-1",
                "customer_id": "cliente-web",
                "product_id": "app-pro",
                "days": 90,
                "features": ["offline", "reports"],
                "device_limit": 2,
                "redirect_url": "https://app.example.com/start",
                "error_url": "https://app.example.com/license-error",
            },
            token=token,
        )
        license_doc = created["license"]

        valid = self.post_json("/api/validate", {"license": license_doc})
        self.assertEqual(valid["status"], "valid")
        self.assertIn("LIC-WEB-1", valid["redirect_url"])

        revoked = self.post_json(
            "/api/revoke",
            {"license_id": "LIC-WEB-1", "reason": "demo cancellation"},
            token=token,
        )
        self.assertEqual(revoked["status"], "revoked")

        invalid = self.post_json("/api/validate", {"license": license_doc})
        self.assertEqual(invalid["status"], "revoked")


if __name__ == "__main__":
    unittest.main()
