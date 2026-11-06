"""Helpers de fecha/hora."""
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Hora actual en UTC, *naive* (sin tzinfo).

    Reemplaza a datetime.utcnow(), deprecado desde Python 3.12, devolviendo
    exactamente lo mismo: las fechas ya guardadas en la base son naive, y
    mezclar naive con aware rompería las comparaciones.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
