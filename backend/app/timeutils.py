"""Helpers de fecha/hora.

Convención de la app:
- Los instantes (creación, cierre, comentarios, historial, SLA...) se guardan en la
  base como UTC *naive* (sin tzinfo).
- La API los devuelve en UTC con zona explícita ("...Z"), y el navegador los
  muestra en la hora local de cada usuario.
- `fecha_compra` es una fecha de calendario que carga el usuario: no se convierte.
- Lo que formatea el propio servidor (exportaciones) usa config.TIMEZONE.
"""
from datetime import datetime, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

from . import config


def utcnow() -> datetime:
    """Hora actual en UTC, naive (reemplaza a datetime.utcnow(), deprecado)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


@lru_cache(maxsize=None)
def tz(name: str = None) -> ZoneInfo:
    return ZoneInfo(name or config.TIMEZONE)


def now_local() -> datetime:
    """Hora actual en la zona del negocio, naive (año del RMA, fechas de calendario)."""
    return datetime.now(tz()).replace(tzinfo=None)


def to_utc_naive(dt: datetime, tz_name: str = None) -> datetime:
    """Normaliza un instante a UTC naive. Si viene sin zona, se toma como hora local
    de TIMEZONE (o de tz_name)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz(tz_name))
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def utc_to_local(dt: datetime, tz_name: str = None) -> datetime:
    """UTC naive (como está en la base) → hora local naive, para mostrar."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz(tz_name)).replace(tzinfo=None)


def iso_utc(dt: datetime) -> str:
    """UTC naive → '2026-11-06T16:27:00Z' (ISO 8601 con zona explícita)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
