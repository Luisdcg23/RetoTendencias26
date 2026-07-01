import json
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .core import create_key_bundle
from .crypto_service import CryptoService
from .license_service import LicenseService
from .offline_validation_service import OfflineValidationService
from .revocation_service import RevocationService

# Habilita importar el paquete db/ que vive en la raiz del proyecto
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
try:
    from db import repository as db_repo
    from db import auth as db_auth
    from db.connection import check_connection
    DB_AVAILABLE = check_connection()
except Exception:  # noqa: BLE001
    DB_AVAILABLE = False
    db_repo = None
    db_auth = None


class LicenseController:
    def __init__(self, *, keys, revocations: Optional[Dict[str, Any]], product_id: str, revocations_path: Optional[str]):
        self.keys = keys
        self.revocations = self._trusted_revocations(revocations, keys)
        self.product_id = product_id
        self.revocations_path = revocations_path
        self.revocation_epoch = self._current_revocation_epoch()
        self.licenses = []
        self.admin_username = os.environ.get("PQLICENSE_ADMIN_USER", "admin")
        self.admin_password = os.environ.get("PQLICENSE_ADMIN_PASSWORD", "admin123")
        self.demo_admin_username = "admin"
        self.demo_admin_password = "admin123"
        self.admin_tokens = set()
        self.db_enabled = DB_AVAILABLE
        self.demo_user_id = db_repo.ensure_demo_user() if self.db_enabled else None
        if self.db_enabled:
            print("[db] Conectado a PostgreSQL — las licencias se persistiran en la base de datos.")
        else:
            print("[db] PostgreSQL no disponible — usando almacenamiento en memoria (no persistente).")

    def login(self, body: Dict[str, Any]) -> Dict[str, Any]:
        correo = body.get("username") or body.get("correo")
        password = body.get("password")
        if not self.db_enabled:
            return {"status": "denied", "error": "database_unavailable"}
        if not correo or not password:
            return {"status": "denied", "error": "missing_credentials"}
        user = db_auth.authenticate_user(correo=correo, password=password)
        if not user:
            return {"status": "denied", "error": "invalid_credentials"}
        token = db_auth.generate_token(user)
        return {"status": "authenticated", "token": token, "rol": user["rol"], "nombre_completo": user["nombre_completo"]}

    def register(self, body: Dict[str, Any]) -> Dict[str, Any]:
        if not self.db_enabled:
            return {"status": "error", "error": "database_unavailable"}
        try:
            user = db_auth.register_user(
                nombre_completo=body["nombre_completo"],
                correo=body["correo"],
                password=body["password"],
                tipo_usuario=body.get("tipo_usuario", "Individual"),
            )
            return {"status": "registered", "user": user}
        except (KeyError, ValueError) as exc:
            return {"status": "error", "error": str(exc)}

    def is_admin_token(self, token: str) -> bool:
        if not self.db_enabled or not token:
            return False
        payload = db_auth.decode_token(token)
        return db_auth.is_admin_payload(payload)

    def identify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Decodifica un JWT valido de cualquier rol (admin o cliente). None si es invalido/expirado."""
        if not self.db_enabled or not token:
            return None
        return db_auth.decode_token(token)

    def my_licenses(self, token: str) -> Dict[str, Any]:
        """Licencias del usuario autenticado (vista de cliente final, no admin)."""
        payload = self.identify_token(token)
        if not payload:
            return {"error": "auth_required"}
        if not self.db_enabled:
            return {"licenses": [], "nombre_completo": payload.get("nombre_completo", ""), "rol": payload.get("rol", "")}
        id_usuario = int(payload["sub"])
        return {
            "licenses": db_repo.list_licenses_by_user(id_usuario),
            "nombre_completo": payload.get("nombre_completo", ""),
            "rol": payload.get("rol", ""),
        }

    def validate_owned_license(self, token: str, license_id: str) -> Dict[str, Any]:
        """Revalida una licencia propia (o cualquiera, si es Admin) a partir de su codigo,
        usando el documento completo guardado en la BD al momento de generarla."""
        payload_token = self.identify_token(token)
        if not payload_token:
            return {"error": "auth_required"}
        if not self.db_enabled:
            return {"error": "database_unavailable"}
        if not license_id:
            return {"error": "missing_license_id"}

        record = db_repo.get_full_license_by_code(license_id)
        if not record:
            return {"error": "license_not_found"}

        is_admin = payload_token.get("rol") == "Admin"
        if not is_admin and record["id_usuario"] != int(payload_token["sub"]):
            return {"error": "forbidden"}

        license_doc = record.get("license_doc")
        if not license_doc:
            return {"error": "license_missing_payload"}

        inner_payload = license_doc.get("payload", {})
        body = {
            "license": license_doc,
            "product_id": inner_payload.get("product_id", self.product_id),
            "device_fingerprint": inner_payload.get("device_fingerprint", ""),
        }
        return self.validate(body)

    def revoke_owned_license(self, token: str, license_id: str, reason: str) -> Dict[str, Any]:
        """Permite que un usuario cancele su propia licencia (o cualquiera, si es Admin).
        Verifica dueno antes de tocar la BD, luego reusa la misma logica de cancel()."""
        payload_token = self.identify_token(token)
        if not payload_token:
            return {"error": "auth_required"}
        if not self.db_enabled:
            return {"error": "database_unavailable"}
        if not license_id:
            return {"error": "missing_license_id"}

        record = db_repo.get_full_license_by_code(license_id)
        if not record:
            return {"error": "license_not_found"}

        is_admin = payload_token.get("rol") == "Admin"
        if not is_admin and record["id_usuario"] != int(payload_token["sub"]):
            return {"error": "forbidden"}

        if record.get("estado") == "revocada":
            return {"error": "already_revoked"}

        actor_id = int(payload_token["sub"])
        result = self.cancel(license_id, {"reason": reason or "cancelacion solicitada por el usuario"}, actor_id=actor_id)
        return result

    def activate_license(self, token: str, code: str, device_fingerprint: str) -> Dict[str, Any]:
        """Permite a un usuario final activar una licencia que compro, ingresando su codigo.
        Si la licencia esta libre (aun en el usuario demo) la vincula a su cuenta; si ya es
        suya, no hace nada especial; si es de OTRO usuario real, rechaza la operacion.
        Registra este dispositivo como activacion y reusa validate() para devolver el mismo
        resultado (valid/expired/revoked/etc.) que usan las pantallas de resultado."""
        payload_token = self.identify_token(token)
        if not payload_token:
            return {"error": "auth_required"}
        if not self.db_enabled:
            return {"error": "database_unavailable"}

        normalized_code = (code or "").strip().upper()
        if not normalized_code:
            return {"error": "missing_license_id"}

        record = db_repo.get_full_license_by_code(normalized_code)
        if not record:
            return {"error": "license_not_found"}

        requester_id = int(payload_token["sub"])
        owner_id = record.get("id_usuario")
        if owner_id not in (self.demo_user_id, requester_id):
            return {"error": "license_owned_by_other"}

        if owner_id != requester_id:
            db_repo.set_license_owner(normalized_code, requester_id)

        if device_fingerprint:
            db_repo.register_device_activation(
                id_licencia=record["id_licencia"],
                huella_hardware=device_fingerprint,
            )

        license_doc = record.get("license_doc")
        if not license_doc:
            return {"error": "license_missing_payload"}

        inner_payload = license_doc.get("payload", {})
        body = {
            "license": license_doc,
            "product_id": inner_payload.get("product_id", self.product_id),
            "device_fingerprint": device_fingerprint or inner_payload.get("device_fingerprint", ""),
        }
        result = self.validate(body)
        result["activated"] = True
        result["license_id"] = normalized_code
        return result

    def reset_keys(self) -> Dict[str, Any]:
        self.keys = create_key_bundle()
        self.revocations = None
        self.revocation_epoch = 1
        return {"status": "keys_ready", "public_keys": self.keys.public_bundle().to_dict()}

    def state(self) -> Dict[str, Any]:
        revoked = self.revocations.get("payload", {}).get("revoked", []) if self.revocations else []
        return {
            "classic_algorithm": self.keys.classic_algorithm,
            "pq_algorithm": self.keys.pq_algorithm,
            "revoked_count": len(revoked),
            "revocation_epoch": self.revocation_epoch,
            "signature_modes": ["hybrid", "classical_only", "post_quantum_only"],
            "public_keys": self.keys.public_bundle().to_dict(),
        }

    def generate(self, body: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        features = body.get("features", body.get("feature", []))
        if isinstance(features, str):
            features = [item.strip() for item in features.split(",") if item.strip()]
        allowed_devices = body.get("allowed_devices", body.get("device_limit", 1))
        metadata = {
            "redirect_url": body["redirect_url"],
            "error_url": body["error_url"],
        }
        license_doc = LicenseService(self.keys).generate_license(
            license_id=body["license_id"],
            customer_id=body["customer_id"],
            product_id=body.get("product_id", self.product_id),
            plan=body.get("plan", "professional"),
            issued_at=now,
            expires_at=now + timedelta(days=int(body.get("days", 365))),
            allowed_devices=int(allowed_devices),
            device_fingerprint=body.get("device_fingerprint", ""),
            features=features,
            validation_mode=body.get("validation_mode", "hybrid"),
            revocation_epoch=self.revocation_epoch,
            metadata=metadata,
        )
        self.licenses.append(license_doc)

        if self.db_enabled:
            payload = license_doc["payload"]
            signatures = license_doc.get("signatures", {})
            # Intenta ligar la licencia al usuario real buscando por correo.
            # Si el campo "cliente" no coincide con ningun correo registrado,
            # cae de vuelta al usuario demo (comportamiento anterior).
            id_usuario_real = db_repo.get_user_id_by_correo(body.get("customer_id", ""))
            id_usuario_final = id_usuario_real if id_usuario_real else self.demo_user_id

            db_license_id = db_repo.insert_license(
                codigo_licencia=payload["license_id"],
                id_usuario=id_usuario_final,
                fecha_expiracion=now + timedelta(days=int(body.get("days", 365))),
                firma_postcuantica=signatures.get("post_quantum", {}),
                firma_clasica=signatures.get("classical"),
                license_doc=license_doc,
            )
            if payload.get("device_fingerprint"):
                db_repo.register_device_activation(
                    id_licencia=db_license_id,
                    huella_hardware=payload["device_fingerprint"],
                )

        return {"status": "created", "license": license_doc}

    def list_licenses(self) -> Dict[str, Any]:
        if self.db_enabled:
            return {"licenses": db_repo.list_licenses()}
        return {"licenses": [self._license_summary(license_doc) for license_doc in self.licenses]}

    def validate(self, body: Dict[str, Any]) -> Dict[str, Any]:
        result = OfflineValidationService(self.keys.public_bundle()).validate(
            body.get("license", body),
            expected_product_id=body.get("product_id", self.product_id),
            revocation_list=self.revocations,
            device_fingerprint=body.get("device_fingerprint", ""),
        )
        result_dict = result.to_dict()

        if self.db_enabled:
            license_payload = body.get("license", body)
            inner_payload = license_payload.get("payload", license_payload)
            license_code = inner_payload.get("license_id") if isinstance(inner_payload, dict) else None
            if license_code:
                db_license_id = db_repo.get_license_id_by_code(license_code)
                if db_license_id:
                    status = result_dict.get("status", "invalida")
                    resultado_map = {
                        "valid": "valida",
                        "expired": "vencida",
                        "revoked": "revocada",
                    }
                    resultado = resultado_map.get(status, "invalida")
                    modo = "online" if body.get("online", True) else "offline"
                    db_repo.record_validation(id_licencia=db_license_id, modo=modo, resultado=resultado)

        return result_dict

    def cancel(self, license_id: str, body: Dict[str, Any], actor_id: Optional[int] = None) -> Dict[str, Any]:
        current = []
        if self.revocations:
            current = list(self.revocations.get("payload", {}).get("revoked", []))
        current.append(
            {
                "license_id": license_id,
                "reason": body.get("reason", "manual cancellation"),
                "revoked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
        )
        self.revocation_epoch += 1
        self.revocations = RevocationService(self.keys).create_revocation_list(
            revoked=current,
            generated_at=datetime.now(timezone.utc),
            revocation_epoch=self.revocation_epoch,
            grace_period_days=int(body.get("grace_period_days", 0)),
        )
        self._persist_revocations()

        if self.db_enabled:
            db_license_id = db_repo.get_license_id_by_code(license_id)
            if db_license_id:
                reason = body.get("reason", "manual cancellation")
                db_repo.cancel_license(
                    id_licencia=db_license_id,
                    motivo=reason,
                    tipo="manual",
                    id_usuario_responsable=actor_id,
                )
                db_repo.append_offline_revocation(
                    id_licencia=db_license_id,
                    codigo_licencia=license_id,
                    version_lista=self.revocation_epoch,
                )

        return {"status": "revoked", "license_id": license_id, "revocation_epoch": self.revocation_epoch}

    def historial(self) -> Dict[str, Any]:
        if self.db_enabled:
            return {"historial": db_repo.list_historial()}
        return {"historial": []}

    def cancelaciones(self) -> Dict[str, Any]:
        if self.db_enabled:
            return {"cancelaciones": db_repo.list_cancelaciones()}
        return {"cancelaciones": []}

    def revocation_list(self) -> Dict[str, Any]:
        if self.db_enabled:
            revoked = db_repo.list_offline_revocations()
            return {
                "schema": "pqlicense-revocations/v2",
                "payload": {
                    "revoked": [
                        {
                            "license_id": item["codigo_licencia"],
                            "reason": "revocada",
                            "revoked_at": item["fecha_revocacion"],
                        }
                        for item in revoked
                    ],
                    "revocation_epoch": self.revocation_epoch,
                },
            }
        return self.revocations or {
            "schema": "pqlicense-revocations/v2",
            "payload": {
                "revoked": [],
                "revocation_epoch": self.revocation_epoch,
            },
        }

    def _license_summary(self, license_doc: Dict[str, Any]) -> Dict[str, Any]:
        payload = license_doc.get("payload", {})
        return {
            "license_id": payload.get("license_id", ""),
            "customer_id": payload.get("customer_id", ""),
            "product_id": payload.get("product_id", ""),
            "plan": payload.get("plan", ""),
            "expires_at": payload.get("expires_at", ""),
            "validation_mode": payload.get("validation_mode", ""),
            "revocation_epoch": payload.get("revocation_epoch", 1),
            "features": payload.get("features", []),
        }

    def _current_revocation_epoch(self) -> int:
        if not self.revocations:
            return 1
        return int(self.revocations.get("payload", {}).get("revocation_epoch", 1))

    def _trusted_revocations(self, revocations: Optional[Dict[str, Any]], keys) -> Optional[Dict[str, Any]]:
        if not revocations:
            return None
        payload = revocations.get("payload")
        signatures = revocations.get("signatures")
        if not isinstance(payload, dict) or not isinstance(signatures, dict):
            return None
        mode = payload.get("validation_mode", "hybrid")
        _verification, ok = CryptoService().verify_payload(payload, signatures, keys.public_bundle(), mode)
        return revocations if ok else None

    def _persist_revocations(self) -> None:
        if self.revocations_path:
            Path(self.revocations_path).write_text(
                json.dumps(self.revocations, indent=2, sort_keys=True),
                encoding="utf-8",
            )