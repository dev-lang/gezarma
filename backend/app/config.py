"""
config.py — Configuración de la app, leída de variables de entorno.

Los valores pueden venir del entorno (p. ej. Docker) o de un archivo `.env`
en la raíz del repo (ver `.env.example`). Si no se define nada, se usan los
mismos valores que tenía la app antes de esta configuración, así que una
instalación existente sigue funcionando igual.
"""
import logging
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
# Las variables ya definidas en el entorno tienen prioridad sobre el .env
load_dotenv(ROOT_DIR / ".env", override=False)

log = logging.getLogger("uvicorn.error")  # sale junto con los logs de uvicorn

_DEFAULT_SECRET_KEY = "gezatek_super_secret_key_123"  # clave histórica publicada en el repo: nunca se usa
_DEFAULT_ADMIN_PASSWORD = "admin123"


def _list(value: str) -> list:
    return [v.strip() for v in value.split(",") if v.strip()]


# ── Datos ────────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./rma_system.db")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")


def _carpeta_de_datos() -> Path:
    """Donde vive la base SQLite (en Docker, /data); si no es SQLite, la raíz del repo."""
    if DATABASE_URL.startswith("sqlite:///"):
        ruta = DATABASE_URL[len("sqlite:///"):]
        if ruta and ruta != ":memory:":
            return Path(ruta).expanduser().resolve().parent
    return ROOT_DIR


def _secret_key():
    """SECRET_KEY del entorno; si no hay (o es la clave histórica del repo), una
    clave aleatoria guardada junto a la base, que se genera la primera vez.
    Devuelve (clave, origen)."""
    valor = os.getenv("SECRET_KEY")
    if valor and valor != _DEFAULT_SECRET_KEY:
        return valor, "env"
    archivo = Path(os.getenv("SECRET_KEY_FILE") or (_carpeta_de_datos() / "secret_key"))
    try:
        if archivo.exists() and archivo.read_text().strip():
            return archivo.read_text().strip(), "archivo"
        archivo.parent.mkdir(parents=True, exist_ok=True)
        clave = secrets.token_urlsafe(48)
        archivo.write_text(clave + "\n")
        try:
            archivo.chmod(0o600)
        except OSError:
            pass
        return clave, "generada"
    except OSError as exc:
        raise RuntimeError(f"No hay SECRET_KEY y no se pudo guardar una nueva en {archivo}: {exc}. "
                           "Definí SECRET_KEY en el .env (o SECRET_KEY_FILE con una ruta escribible).") from exc


# ── Seguridad ────────────────────────────────────────────────────────────────
SECRET_KEY, SECRET_KEY_ORIGEN = _secret_key()
SECRET_KEY_LEGADA = os.getenv("SECRET_KEY") == _DEFAULT_SECRET_KEY
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 24))
CORS_ORIGINS = _list(os.getenv("CORS_ORIGINS", "*"))

# ── Admin inicial (usuario "admin"; solo se usa al crear una base nueva) ─────
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD") or _DEFAULT_ADMIN_PASSWORD
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@gezarma.local")

# ── Zona horaria ─────────────────────────────────────────────────────────────
# Las fechas se guardan en UTC. TIMEZONE es la zona del negocio: se usa para lo
# que el servidor muestra formateado (exportaciones) y para convertir a UTC los
# datos viejos que se guardaron en hora local (migración 0003).
TIMEZONE = os.getenv("TIMEZONE") or "America/Argentina/Buenos_Aires"
try:
    from zoneinfo import ZoneInfo
    ZoneInfo(TIMEZONE)
except Exception as exc:  # nombre inválido o falta la base de zonas (pip install tzdata)
    raise RuntimeError(f"TIMEZONE inválida: {TIMEZONE!r}. Usá un nombre IANA, "
                       f"p. ej. America/Argentina/Buenos_Aires") from exc

# ── URL pública y email ──────────────────────────────────────────────────────
# Ambas cosas también se pueden configurar desde el panel de administración.
PUBLIC_URL = (os.getenv("PUBLIC_URL") or "").rstrip("/")
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT") or 587)
SMTP_SECURITY = os.getenv("SMTP_SECURITY", "starttls")   # starttls | ssl | ninguna
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "")

# Tareas periódicas (revisión de SLA). Se pueden apagar, p. ej. en los tests
# o si se corre más de un proceso de la app (para que no avisen dos veces).
TAREAS_PERIODICAS = (os.getenv("TAREAS_PERIODICAS", "1").strip().lower() not in ("0", "false", "no"))

USING_DEFAULT_ADMIN_PASSWORD = ADMIN_PASSWORD == _DEFAULT_ADMIN_PASSWORD


def warn_insecure_defaults() -> None:
    if SECRET_KEY_LEGADA:
        log.warning("SECRET_KEY tiene la clave de ejemplo publicada en el repo: se ignora y se usa una "
                    "clave propia. Cambiala en el .env (las sesiones abiertas se cierran y, si la "
                    "contraseña SMTP estaba cargada en el panel, hay que volver a cargarla).")
    if SECRET_KEY_ORIGEN == "generada":
        log.warning("No había SECRET_KEY: se generó una aleatoria y se guardó junto a la base. "
                    "Incluila en los backups (sin ella se cierran las sesiones y hay que volver a "
                    "cargar la contraseña SMTP del panel).")
    if "*" in CORS_ORIGINS:
        log.warning("CORS_ORIGINS='*': cualquier sitio puede llamar a la API. "
                    "Si el frontend se sirve desde la misma app, podés dejarlo vacío.")
