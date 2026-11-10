"""setup inicial: marca de datos de ejemplo y las instalaciones existentes quedan configuradas

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-10 14:10:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0018'
down_revision: Union[str, None] = '0017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLAS = ("usuarios", "productos", "repuestos", "tickets", "ubicaciones")


def upgrade() -> None:
    for tabla in TABLAS:
        with op.batch_alter_table(tabla) as b:
            b.add_column(sa.Column("demo", sa.Boolean(), nullable=False, server_default="0"))
    # Un taller que ya tiene tickets no necesita el asistente de configuración inicial
    con = op.get_bind()
    hay_tickets = con.execute(sa.text("SELECT 1 FROM tickets LIMIT 1")).first()
    ya = con.execute(sa.text("SELECT 1 FROM config_sistema WHERE clave = 'setup_terminado'")).first()
    if hay_tickets and not ya:
        con.execute(sa.text("INSERT INTO config_sistema (clave, valor) VALUES ('setup_terminado', '1')"))


def downgrade() -> None:
    op.execute("DELETE FROM config_sistema WHERE clave IN ('setup_terminado', 'setup_pospuesto', 'setup_pasos', 'setup_rubros')")
    for tabla in reversed(TABLAS):
        with op.batch_alter_table(tabla) as b:
            b.drop_column("demo")
