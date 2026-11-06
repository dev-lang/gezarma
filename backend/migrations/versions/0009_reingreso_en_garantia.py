"""reingreso en garantía de la reparación

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-06 17:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0009'
down_revision: Union[str, None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('tickets', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reingreso_de', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('reingreso_garantia', sa.Boolean(), server_default='0', nullable=False))
        batch_op.create_foreign_key('fk_tickets_reingreso_de', 'tickets', ['reingreso_de'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('tickets', schema=None) as batch_op:
        batch_op.drop_constraint('fk_tickets_reingreso_de', type_='foreignkey')
        batch_op.drop_column('reingreso_garantia')
        batch_op.drop_column('reingreso_de')
