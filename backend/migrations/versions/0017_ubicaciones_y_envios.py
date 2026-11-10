"""ubicaciones (dónde se guarda cada equipo y repuesto) y envíos a garantía del fabricante

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-10 11:40:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0017'
down_revision: Union[str, None] = '0016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ubicaciones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nombre", sa.String(60), nullable=False),
        sa.Column("padre_id", sa.Integer(), nullable=True),
        sa.Column("codigo", sa.String(20), nullable=True),
        sa.Column("tipo", sa.String(10), nullable=False, server_default="taller"),
        sa.Column("nota", sa.String(200), nullable=True),
        sa.Column("activa", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["padre_id"], ["ubicaciones.id"], name="fk_ubicaciones_padre_id", ondelete="RESTRICT"),
    )
    op.create_index("ix_ubicaciones_id", "ubicaciones", ["id"])
    op.create_index("ix_ubicaciones_padre_id", "ubicaciones", ["padre_id"])
    op.create_index("ix_ubicaciones_codigo", "ubicaciones", ["codigo"], unique=True)

    op.create_table(
        "ubicacion_movimientos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticket_id", sa.Integer(), nullable=True),
        sa.Column("repuesto_id", sa.Integer(), nullable=True),
        sa.Column("desde_id", sa.Integer(), nullable=True),
        sa.Column("hacia_id", sa.Integer(), nullable=True),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("motivo", sa.String(30), nullable=True),
        sa.Column("fecha", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], name="fk_ubicacion_movimientos_ticket_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["repuesto_id"], ["repuestos.id"], name="fk_ubicacion_movimientos_repuesto_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["desde_id"], ["ubicaciones.id"], name="fk_ubicacion_movimientos_desde_id", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["hacia_id"], ["ubicaciones.id"], name="fk_ubicacion_movimientos_hacia_id", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], name="fk_ubicacion_movimientos_usuario_id"),
    )
    op.create_index("ix_ubicacion_movimientos_id", "ubicacion_movimientos", ["id"])
    op.create_index("ix_ubicacion_movimientos_ticket_id", "ubicacion_movimientos", ["ticket_id"])
    op.create_index("ix_ubicacion_movimientos_repuesto_id", "ubicacion_movimientos", ["repuesto_id"])
    op.create_index("ix_ubicacion_movimientos_fecha", "ubicacion_movimientos", ["fecha"])

    op.create_table(
        "envios_externos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("destino", sa.String(120), nullable=False),
        sa.Column("numero_caso", sa.String(60), nullable=True),
        sa.Column("fecha_envio", sa.DateTime(), nullable=False),
        sa.Column("transportista", sa.String(80), nullable=True),
        sa.Column("guia", sa.String(80), nullable=True),
        sa.Column("contenido", sa.String(120), nullable=True),
        sa.Column("accesorios", sa.String(300), nullable=True),
        sa.Column("fecha_estimada", sa.DateTime(), nullable=True),
        sa.Column("nota", sa.Text(), nullable=True),
        sa.Column("estado", sa.String(10), nullable=False, server_default="enviado"),
        sa.Column("fecha_recepcion", sa.DateTime(), nullable=True),
        sa.Column("resultado", sa.String(15), nullable=True),
        sa.Column("serie_nueva", sa.String(80), nullable=True),
        sa.Column("comprobante", sa.String(80), nullable=True),
        sa.Column("nota_recepcion", sa.Text(), nullable=True),
        sa.Column("usuario_envio_id", sa.Integer(), nullable=True),
        sa.Column("usuario_recepcion_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], name="fk_envios_externos_ticket_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["usuario_envio_id"], ["usuarios.id"], name="fk_envios_externos_usuario_envio_id"),
        sa.ForeignKeyConstraint(["usuario_recepcion_id"], ["usuarios.id"], name="fk_envios_externos_usuario_recepcion_id"),
    )
    op.create_index("ix_envios_externos_id", "envios_externos", ["id"])
    op.create_index("ix_envios_externos_ticket_id", "envios_externos", ["ticket_id"])
    op.create_index("ix_envios_externos_estado", "envios_externos", ["estado"])

    with op.batch_alter_table("tickets") as b:
        b.add_column(sa.Column("ubicacion_id", sa.Integer(), nullable=True))
        b.add_column(sa.Column("ubicacion_fecha", sa.DateTime(), nullable=True))
        b.create_foreign_key("fk_tickets_ubicacion_id", "ubicaciones", ["ubicacion_id"], ["id"], ondelete="SET NULL")
        b.create_index("ix_tickets_ubicacion_id", ["ubicacion_id"])
    with op.batch_alter_table("repuestos") as b:
        b.add_column(sa.Column("ubicacion_id", sa.Integer(), nullable=True))
        b.create_foreign_key("fk_repuestos_ubicacion_id", "ubicaciones", ["ubicacion_id"], ["id"], ondelete="SET NULL")
        b.create_index("ix_repuestos_ubicacion_id", ["ubicacion_id"])


def downgrade() -> None:
    with op.batch_alter_table("repuestos") as b:
        b.drop_index("ix_repuestos_ubicacion_id")
        b.drop_constraint("fk_repuestos_ubicacion_id", type_="foreignkey")
        b.drop_column("ubicacion_id")
    with op.batch_alter_table("tickets") as b:
        b.drop_index("ix_tickets_ubicacion_id")
        b.drop_constraint("fk_tickets_ubicacion_id", type_="foreignkey")
        b.drop_column("ubicacion_fecha")
        b.drop_column("ubicacion_id")
    op.drop_table("envios_externos")
    op.drop_table("ubicacion_movimientos")
    op.drop_table("ubicaciones")
