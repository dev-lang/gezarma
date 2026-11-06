"""fechas de tickets en UTC

Hasta esta versión, algunas fechas de los tickets se guardaban en hora local
del servidor y el resto en UTC. Desde ahora todo se guarda en UTC; esta
migración corrige los datos existentes:

- fecha_cierre, deadline_sla, fecha_envio: siempre se guardaron en hora local
  → se convierten a UTC usando TIMEZONE (por defecto America/Argentina/Buenos_Aires;
  si el servidor viejo estaba en otra zona, definir TIMEZONE antes de migrar).
- fecha_actualizacion: quedaba en UTC o en hora local según qué acción la tocó
  por última vez, así que no se puede convertir fila por fila. Se reconstruye
  como el último momento conocido del ticket: el evento más reciente del
  historial, comentarios y adjuntos (siempre en UTC), o el cierre/envío.
- fecha_creacion y las demás tablas ya estaban en UTC: no cambian.
- fecha_compra es una fecha de calendario: no cambia.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from backend.app.timeutils import to_utc_naive, utc_to_local

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNAS_LOCALES = ("fecha_cierre", "deadline_sla", "fecha_envio")

tickets = sa.table(
    "tickets",
    sa.column("id", sa.Integer),
    sa.column("fecha_creacion", sa.DateTime),
    sa.column("fecha_actualizacion", sa.DateTime),
    *(sa.column(c, sa.DateTime) for c in COLUMNAS_LOCALES),
)
# Tablas cuyas fechas siempre estuvieron en UTC: sirven para reconstruir fecha_actualizacion
EVENTOS = [sa.table(t, sa.column("ticket_id", sa.Integer), sa.column("fecha", sa.DateTime))
           for t in ("historial_estados", "comentarios", "adjuntos")]


def _convertir(convert) -> list:
    bind = op.get_bind()
    filas = bind.execute(sa.select(tickets)).mappings().all()
    for f in filas:
        nuevos = {c: convert(f[c]) for c in COLUMNAS_LOCALES if f[c] is not None}
        if nuevos:
            bind.execute(tickets.update().where(tickets.c.id == f["id"]).values(**nuevos))
    return filas


def upgrade() -> None:
    bind = op.get_bind()
    filas = _convertir(to_utc_naive)

    ultimos = {}
    for ev in EVENTOS:
        q = sa.select(ev.c.ticket_id, sa.func.max(ev.c.fecha)).group_by(ev.c.ticket_id)
        for ticket_id, fecha in bind.execute(q):
            if fecha is not None:
                ultimos[ticket_id] = max(fecha, ultimos.get(ticket_id, fecha))

    for f in bind.execute(sa.select(tickets)).mappings().all():
        candidatos = [f["fecha_creacion"], f["fecha_cierre"], f["fecha_envio"], ultimos.get(f["id"])]
        candidatos = [c for c in candidatos if c is not None]
        if candidatos:
            bind.execute(tickets.update().where(tickets.c.id == f["id"])
                         .values(fecha_actualizacion=max(candidatos)))


def downgrade() -> None:
    # Vuelve fecha_cierre, deadline_sla y fecha_envio a hora local.
    # fecha_actualizacion queda en UTC (su valor mezclado original no se puede recuperar).
    _convertir(utc_to_local)
