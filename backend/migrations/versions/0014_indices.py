"""índices para los filtros más usados y PK de ticket_tags

- Índices en las columnas por las que se filtra u ordena siempre (estado,
  cliente, técnico, fechas, y las FK de comentarios/historial/adjuntos/stock).
- ticket_tags no tenía clave primaria: admitía la misma etiqueta repetida en
  un ticket. Se eliminan los duplicados y se agrega (ticket_id, tag_id).

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-06 19:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0014'
down_revision: Union[str, None] = '0013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDICES = [
    ("tickets", "usuario_id"), ("tickets", "estado"), ("tickets", "tecnico_asignado"),
    ("tickets", "fecha_creacion"), ("tickets", "deadline_sla"),
    ("comentarios", "ticket_id"), ("historial_estados", "ticket_id"), ("adjuntos", "ticket_id"),
    ("stock_movimientos", "repuesto_id"), ("stock_movimientos", "ticket_id"),
    ("login_attempts", "username"), ("presupuestos", "ticket_id"), ("presupuesto_items", "presupuesto_id"),
]


def upgrade() -> None:
    for tabla, columna in INDICES:
        with op.batch_alter_table(tabla, schema=None) as batch_op:
            batch_op.create_index(f"ix_{tabla}_{columna}", [columna], unique=False)

    # ticket_tags: sacar duplicados (y filas a medias) y agregar la clave primaria
    conn = op.get_bind()
    filas = conn.execute(sa.text("SELECT DISTINCT ticket_id, tag_id FROM ticket_tags "
                                 "WHERE ticket_id IS NOT NULL AND tag_id IS NOT NULL")).fetchall()
    conn.execute(sa.text("DELETE FROM ticket_tags"))
    for ticket_id, tag_id in filas:
        conn.execute(sa.text("INSERT INTO ticket_tags (ticket_id, tag_id) VALUES (:a, :b)"), {"a": ticket_id, "b": tag_id})
    with op.batch_alter_table("ticket_tags", schema=None) as batch_op:
        batch_op.alter_column("ticket_id", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("tag_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_primary_key("pk_ticket_tags", ["ticket_id", "tag_id"])


def downgrade() -> None:
    with op.batch_alter_table("ticket_tags", schema=None) as batch_op:
        batch_op.drop_constraint("pk_ticket_tags", type_="primary")
        batch_op.alter_column("tag_id", existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column("ticket_id", existing_type=sa.Integer(), nullable=True)
    for tabla, columna in reversed(INDICES):
        with op.batch_alter_table(tabla, schema=None) as batch_op:
            batch_op.drop_index(f"ix_{tabla}_{columna}")
