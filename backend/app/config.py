"""
config.py — Configuración de la app, leída de variables de entorno.

Los valores pueden venir del entorno (p. ej. Docker) o de un archivo `.env`
en la raíz del repo (ver `.env.example`). Si no se define nada, se usan los
mismos valores que tenía la app antes de esta configuración, así que una
instalación existente sigue funcionando igual.
"""
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
# Las variables ya definidas en el entorno tienen prioridad sobre el .env
load_dotenv(ROOT_DIR / ".env", override=False)

log = logging.getLogger("uvicorn.error")  # sale junto con los logs de uvicorn

_DEFAULT_SECRET_KEY = "gezatek_super_secret_key_123"
_DEFAULT_ADMIN_PASSWORD = "admin123"


def _list(value: str) -> list:
    return [v.strip() for v in value.split(",") if v.strip()]


# ── Seguridad ────────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY") or _DEFAULT_SECRET_KEY
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 24))
CORS_ORIGINS = _list(os.getenv("CORS_ORIGINS", "*"))

# ── Admin inicial (usuario "admin"; solo se usa al crear una base nueva) ─────
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD") or _DEFAULT_ADMIN_PASSWORD
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@gezatek.com.ar")

# ── Datos ────────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./rma_system.db")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")

USING_DEFAULT_SECRET_KEY = SECRET_KEY == _DEFAULT_SECRET_KEY
USING_DEFAULT_ADMIN_PASSWORD = ADMIN_PASSWORD == _DEFAULT_ADMIN_PASSWORD


def warn_insecure_defaults() -> None:
    if USING_DEFAULT_SECRET_KEY:
        log.warning("SECRET_KEY no está configurada: se usa la clave por defecto del repo. "
                    "Definila en .env antes de usar la app en producción.")
    if "*" in CORS_ORIGINS:
        log.warning("CORS_ORIGINS='*': cualquier sitio puede llamar a la API. "
                    "Si el frontend se sirve desde la misma app, podés dejarlo vacío.")
