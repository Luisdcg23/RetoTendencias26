"""
Conexion a PostgreSQL para el sistema de licencias postcuantico.

Usa variables de entorno (ver .env) para la cadena de conexion:
  PQLICENSE_DB_HOST  (default: localhost)
  PQLICENSE_DB_PORT  (default: 5432)
  PQLICENSE_DB_NAME  (default: reto_tendencias)
  PQLICENSE_DB_USER  (default: postgres)
  PQLICENSE_DB_PASSWORD (sin default, debe configurarse)
"""
import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def build_database_url() -> str:
    host = os.environ.get("PQLICENSE_DB_HOST", "localhost")
    port = os.environ.get("PQLICENSE_DB_PORT", "5432")
    name = os.environ.get("PQLICENSE_DB_NAME", "reto_tendencias")
    user = os.environ.get("PQLICENSE_DB_USER", "postgres")
    password = os.environ.get("PQLICENSE_DB_PASSWORD", "")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"


_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(build_database_url(), pool_pre_ping=True)
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)
    return _SessionLocal


@contextmanager
def session_scope():
    """Provee una sesion transaccional: usar con 'with session_scope() as s:'"""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_connection() -> bool:
    """Verifica que la conexion a PostgreSQL funciona. Util para diagnostico."""
    try:
        with get_engine().connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[db] No se pudo conectar a PostgreSQL: {exc}")
        return False