"""
Capa de acceso a datos para el sistema de licencias.
"""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from .connection import session_scope

DEMO_USER_EMAIL = "demo@reto-tendencias.local"


def ensure_demo_user() -> int:
    with session_scope() as s:
        row = s.execute(
            text("SELECT id_usuario FROM usuarios WHERE correo = :correo"),
            {"correo": DEMO_USER_EMAIL},
        ).fetchone()
        if row:
            return row[0]
        tipo = s.execute(
            text("SELECT id_tipo_usuario FROM tipo_de_usuario WHERE nombre_rol = 'Individual'")
        ).fetchone()
        result = s.execute(
            text(
                """
                INSERT INTO usuarios (id_tipo_usuario, nombre_completo, correo, contrasena_hash, estado)
                VALUES (:tipo, :nombre, :correo, :hash, 'activo')
                RETURNING id_usuario
                """
            ),
            {"tipo": tipo[0], "nombre": "Usuario Demo Reto", "correo": DEMO_USER_EMAIL, "hash": "no-aplica-demo"},
        )
        return result.fetchone()[0]


def get_user_id_by_correo(correo: str) -> Optional[int]:
    """Busca el id_usuario real a partir de su correo. None si no existe."""
    if not correo:
        return None
    with session_scope() as s:
        row = s.execute(
            text("SELECT id_usuario FROM usuarios WHERE correo = :correo"),
            {"correo": correo},
        ).fetchone()
        return row[0] if row else None


def set_license_owner(codigo_licencia: str, id_usuario: int) -> bool:
    """Reasigna el dueno de una licencia. Se usa al 'activar' una licencia con
    un usuario logueado: si la licencia estaba libre (usuario demo), pasa a ser suya."""
    with session_scope() as s:
        result = s.execute(
            text("UPDATE licencias SET id_usuario = :id_usuario WHERE codigo_licencia = :codigo"),
            {"id_usuario": id_usuario, "codigo": codigo_licencia},
        )
        return result.rowcount > 0


def insert_license(*, codigo_licencia: str, id_usuario: int, fecha_expiracion: datetime,
                   firma_postcuantica: Dict[str, Any], firma_clasica: Optional[Dict[str, Any]],
                   license_doc: Optional[Dict[str, Any]] = None) -> int:
    """license_doc: el documento COMPLETO devuelto por LicenseService.generate_license()
    (incluye schema/payload/signatures tal cual). Se guarda integro para poder revalidar
    despues sin tener que reconstruir su estructura a mano."""
    with session_scope() as s:
        result = s.execute(
            text(
                """
                INSERT INTO licencias (id_usuario, codigo_licencia, firma_postcuantica, firma_clasica, fecha_expiracion, estado, payload)
                VALUES (:id_usuario, :codigo, CAST(:pq AS JSON), CAST(:clasica AS JSON), :expira, 'activa', CAST(:doc AS JSON))
                RETURNING id_licencia
                """
            ),
            {
                "id_usuario": id_usuario, "codigo": codigo_licencia,
                "pq": json.dumps(firma_postcuantica),
                "clasica": json.dumps(firma_clasica) if firma_clasica else None,
                "expira": fecha_expiracion,
                "doc": json.dumps(license_doc) if license_doc else None,
            },
        )
        return result.fetchone()[0]


def get_license_id_by_code(codigo_licencia: str) -> Optional[int]:
    with session_scope() as s:
        row = s.execute(
            text("SELECT id_licencia FROM licencias WHERE codigo_licencia = :codigo"),
            {"codigo": codigo_licencia},
        ).fetchone()
        return row[0] if row else None


def get_full_license_by_code(codigo_licencia: str) -> Optional[Dict[str, Any]]:
    """Trae el documento completo de la licencia (para revalidar/activar) mas su
    id interno, dueno y estado."""
    with session_scope() as s:
        row = s.execute(
            text(
                """
                SELECT id_licencia, id_usuario, payload, estado
                FROM licencias
                WHERE codigo_licencia = :codigo
                """
            ),
            {"codigo": codigo_licencia},
        ).fetchone()
        if not row:
            return None
        license_doc = row[2]
        if isinstance(license_doc, str):
            license_doc = json.loads(license_doc)
        return {
            "id_licencia": row[0],
            "id_usuario": row[1],
            "license_doc": license_doc,
            "estado": row[3],
        }


def list_licenses() -> List[Dict[str, Any]]:
    with session_scope() as s:
        rows = s.execute(
            text(
                """
                SELECT l.codigo_licencia, u.nombre_completo, l.fecha_expiracion, l.estado
                FROM licencias l
                JOIN usuarios u ON u.id_usuario = l.id_usuario
                ORDER BY l.fecha_emision DESC
                """
            )
        ).fetchall()
        return [
            {
                "license_id": r[0], "customer_id": r[1], "plan": "professional",
                "validation_mode": "hybrid",
                "expires_at": r[2].isoformat() if r[2] else None,
                "estado": r[3],
            }
            for r in rows
        ]


def list_licenses_by_user(id_usuario: int) -> List[Dict[str, Any]]:
    """Licencias que pertenecen a un usuario especifico (vista de cliente final)."""
    with session_scope() as s:
        rows = s.execute(
            text(
                """
                SELECT l.codigo_licencia, l.fecha_emision, l.fecha_expiracion, l.estado
                FROM licencias l
                WHERE l.id_usuario = :id_usuario
                ORDER BY l.fecha_emision DESC
                """
            ),
            {"id_usuario": id_usuario},
        ).fetchall()
        return [
            {
                "license_id": r[0],
                "issued_at": r[1].isoformat() if r[1] else None,
                "expires_at": r[2].isoformat() if r[2] else None,
                "estado": r[3],
            }
            for r in rows
        ]


def record_validation(*, id_licencia: int, modo: str, resultado: str) -> None:
    with session_scope() as s:
        s.execute(
            text("INSERT INTO historial_validaciones (id_licencia, modo, resultado) VALUES (:id_licencia, :modo, :resultado)"),
            {"id_licencia": id_licencia, "modo": modo, "resultado": resultado},
        )


def cancel_license(*, id_licencia: int, motivo: str, tipo: str = "manual", id_usuario_responsable: Optional[int] = None) -> None:
    with session_scope() as s:
        s.execute(text("UPDATE licencias SET estado = 'revocada' WHERE id_licencia = :id"), {"id": id_licencia})
        s.execute(
            text(
                """
                INSERT INTO cancelaciones (id_licencia, id_usuario_responsable, tipo_cancelacion, motivo)
                VALUES (:id_licencia, :responsable, :tipo, :motivo)
                """
            ),
            {"id_licencia": id_licencia, "responsable": id_usuario_responsable, "tipo": tipo, "motivo": motivo},
        )


def append_offline_revocation(*, id_licencia: int, codigo_licencia: str, version_lista: int) -> None:
    with session_scope() as s:
        s.execute(
            text("INSERT INTO revocaciones_offline (id_licencia, codigo_licencia, version_lista) VALUES (:id_licencia, :codigo, :version)"),
            {"id_licencia": id_licencia, "codigo": codigo_licencia, "version": version_lista},
        )


def list_offline_revocations() -> List[Dict[str, Any]]:
    with session_scope() as s:
        rows = s.execute(
            text("SELECT codigo_licencia, fecha_revocacion, version_lista FROM revocaciones_offline ORDER BY fecha_revocacion DESC")
        ).fetchall()
        return [
            {"codigo_licencia": r[0], "fecha_revocacion": r[1].isoformat() if r[1] else None, "version_lista": r[2]}
            for r in rows
        ]


def list_historial() -> List[Dict[str, Any]]:
    with session_scope() as s:
        rows = s.execute(
            text(
                """
                SELECT h.id_validacion, l.codigo_licencia, h.fecha_validacion, h.modo, h.resultado
                FROM historial_validaciones h
                JOIN licencias l ON l.id_licencia = h.id_licencia
                ORDER BY h.fecha_validacion DESC
                LIMIT 100
                """
            )
        ).fetchall()
        return [
            {
                "id": r[0], "codigo_licencia": r[1],
                "fecha_validacion": r[2].isoformat() if r[2] else None,
                "modo": r[3], "resultado": r[4],
            }
            for r in rows
        ]


def list_cancelaciones() -> List[Dict[str, Any]]:
    with session_scope() as s:
        rows = s.execute(
            text(
                """
                SELECT c.id_cancelacion, l.codigo_licencia, c.fecha_cancelacion, c.tipo_cancelacion, c.motivo
                FROM cancelaciones c
                JOIN licencias l ON l.id_licencia = c.id_licencia
                ORDER BY c.fecha_cancelacion DESC
                """
            )
        ).fetchall()
        return [
            {
                "id": r[0], "codigo_licencia": r[1],
                "fecha_cancelacion": r[2].isoformat() if r[2] else None,
                "tipo_cancelacion": r[3], "motivo": r[4],
            }
            for r in rows
        ]


def register_device_activation(*, id_licencia: int, huella_hardware: str) -> None:
    with session_scope() as s:
        existing = s.execute(
            text("SELECT id_dispositivo FROM dispositivo_activacion WHERE id_licencia = :id_licencia AND huella_hardware = :huella"),
            {"id_licencia": id_licencia, "huella": huella_hardware},
        ).fetchone()
        if existing:
            return
        s.execute(
            text("INSERT INTO dispositivo_activacion (id_licencia, huella_hardware, estado) VALUES (:id_licencia, :huella, 'activo')"),
            {"id_licencia": id_licencia, "huella": huella_hardware},
        )