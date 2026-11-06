"""retiro de equipos

tickets.fecha_listo / retiro_*: desde cuándo el equipo está listo para
retirar, recordatorios al cliente y aviso de plazo de guarda vencido.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-06 16:20:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0007'
down_revision: Union[str, None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('tickets', schema=None) as batch_op:
        batch_op.add_column(sa.Column('fecha_listo', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('retiro_ultimo_aviso', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('retiro_recordatorios', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('retiro_vencido_avisado', sa.Boolean(), server_default='0', nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('tickets', schema=None) as batch_op:
        batch_op.drop_column('retiro_vencido_avisado')
        batch_op.drop_column('retiro_recordatorios')
        batch_op.drop_column('retiro_ultimo_aviso')
        batch_op.drop_column('fecha_listo')
