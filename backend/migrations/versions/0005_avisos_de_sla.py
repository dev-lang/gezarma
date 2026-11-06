"""avisos de sla

tickets.sla_aviso_deadline / sla_aviso_nivel: qué aviso de SLA ya se mandó y
para qué vencimiento, así cada aviso sale una sola vez.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-06 17:31:20.301161

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('tickets', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sla_aviso_deadline', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('sla_aviso_nivel', sa.String(), nullable=True))



def downgrade() -> None:
    with op.batch_alter_table('tickets', schema=None) as batch_op:
        batch_op.drop_column('sla_aviso_nivel')
        batch_op.drop_column('sla_aviso_deadline')

