"""horas: tramos sin ticket (categoría), marca de editado y registro de cambios

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-06 23:10:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0016'
down_revision: Union[str, None] = '0015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("tiempos_trabajo") as b:
        b.alter_column("ticket_id", existing_type=sa.Integer(), nullable=True)
        b.add_column(sa.Column("categoria", sa.String(), nullable=True))
        b.add_column(sa.Column("editado", sa.Boolean(), nullable=False, server_default="0"))
        b.create_index("ix_tiempos_trabajo_inicio", ["inicio"])
    op.create_table(
        "tiempo_cambios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("registro_id", sa.Integer(), sa.ForeignKey("tiempos_trabajo.id", ondelete="SET NULL"), nullable=True),
        sa.Column("tecnico_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("fecha", sa.DateTime(), nullable=False),
        sa.Column("accion", sa.String(), nullable=False),
        sa.Column("antes", sa.JSON(), nullable=True),
        sa.Column("despues", sa.JSON(), nullable=True),
    )
    op.create_index("ix_tiempo_cambios_id", "tiempo_cambios", ["id"])
    op.create_index("ix_tiempo_cambios_registro_id", "tiempo_cambios", ["registro_id"])
    op.create_index("ix_tiempo_cambios_tecnico_id", "tiempo_cambios", ["tecnico_id"])


def downgrade() -> None:
    op.drop_table("tiempo_cambios")
    with op.batch_alter_table("tiempos_trabajo") as b:
        b.drop_index("ix_tiempos_trabajo_inicio")
        b.drop_column("editado")
        b.drop_column("categoria")
        b.alter_column("ticket_id", existing_type=sa.Integer(), nullable=False)
