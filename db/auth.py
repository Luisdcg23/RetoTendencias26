"""
Autenticacion real para el sistema de licencias postcuantico.

Reemplaza el login hardcodeado (admin/admin123) por:
  - Registro de usuarios (admin y clientes) en la tabla 'usuarios'
  - Contrasenas hasheadas con bcrypt (nunca texto plano)
  - Tokens JWT firmados con expiracion, en vez de tokens aleatorios en memoria

Variables de entorno usadas (ver .env):
  PQLICENSE_JWT_SECRET  (clave secreta para firmar JWT, obligatoria en produccion)
  PQLICENSE_JWT_EXPIRES_MINUTES (default: 120)
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
import jwt
from sqlalchemy import text

from .connection import session_scope

JWT_ALGORITHM = "HS256"


def _jwt_secret() -> str:
    secret = os.environ.get("PQLICENSE_JWT_SECRET")
    if not secret:
        # Respaldo solo para desarrollo local; en produccion siempre configurar PQLICENSE_JWT_SECRET
        secret = "dev-secret-cambia-esto-en-produccion"
    return secret


def _jwt_expires_minutes() -> int:
    return int(os.environ.get("PQLICENSE_JWT_EXPIRES_MINUTES", "120"))


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def register_user(
    *, nombre_completo: str, correo: str, password: str, tipo_usuario: str = "Individual"
) -> Dict[str, Any]:
    """Crea un nuevo usuario (admin o cliente). tipo_usuario: 'Individual', 'Empresa' o 'Admin'."""
    with session_scope() as s:
        existing = s.execute(
            text("SELECT id_usuario FROM usuarios WHERE correo = :correo"),
            {"correo": correo},
        ).fetchone()
        if existing:
            raise ValueError("correo_ya_registrado")

        tipo_row = s.execute(
            text("SELECT id_tipo_usuario FROM tipo_de_usuario WHERE nombre_rol = :rol"),
            {"rol": tipo_usuario},
        ).fetchone()
        if not tipo_row:
            raise ValueError("tipo_usuario_invalido")

        password_hash = hash_password(password)
        result = s.execute(
            text(
                """
                INSERT INTO usuarios (id_tipo_usuario, nombre_completo, correo, contrasena_hash, estado)
                VALUES (:tipo, :nombre, :correo, :hash, 'activo')
                RETURNING id_usuario
                """
            ),
            {
                "tipo": tipo_row[0],
                "nombre": nombre_completo,
                "correo": correo,
                "hash": password_hash,
            },
        )
        id_usuario = result.fetchone()[0]
        return {"id_usuario": id_usuario, "correo": correo, "tipo_usuario": tipo_usuario}


def authenticate_user(*, correo: str, password: str) -> Optional[Dict[str, Any]]:
    """Verifica credenciales contra la BD. Devuelve datos del usuario si son correctas, None si no."""
    with session_scope() as s:
        row = s.execute(
            text(
                """
                SELECT u.id_usuario, u.nombre_completo, u.correo, u.contrasena_hash,
                       u.estado, t.nombre_rol
                FROM usuarios u
                JOIN tipo_de_usuario t ON t.id_tipo_usuario = u.id_tipo_usuario
                WHERE u.correo = :correo
                """
            ),
            {"correo": correo},
        ).fetchone()
        if not row:
            return None
        id_usuario, nombre_completo, correo_db, password_hash, estado, rol = row
        if estado != "activo":
            return None
        if not verify_password(password, password_hash):
            return None
        return {
            "id_usuario": id_usuario,
            "nombre_completo": nombre_completo,
            "correo": correo_db,
            "rol": rol,
        }


def generate_token(user: Dict[str, Any]) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user["id_usuario"]),
        "correo": user["correo"],
        "rol": user["rol"],
        "nombre_completo": user.get("nombre_completo", ""),
        "iat": now,
        "exp": now + timedelta(minutes=_jwt_expires_minutes()),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """Verifica la firma y expiracion del JWT. Devuelve el payload si es valido, None si no."""
    try:
        return jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


def is_admin_payload(payload: Optional[Dict[str, Any]]) -> bool:
    return bool(payload and payload.get("rol") == "Admin")