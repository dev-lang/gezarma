"""stock minimo y repuestos en presupuesto

- repuestos.stock_minimo: 0 = sin alerta.
- presupuesto_items.repuesto_id: ítem vinculado a un repuesto del catálogo; se
  descuenta del stock cuando se aprueba el presupuesto.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-06 17:05:30.898912

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('presupuesto_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('repuesto_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_presupuesto_items_repuesto_id', 'repuestos', ['repuesto_id'], ['id'])

    with op.batch_alter_table('repuestos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('stock_minimo', sa.Integer(), server_default='0', nullable=False))



def downgrade() -> None:
    with op.batch_alter_table('repuestos', schema=None) as batch_op:
        batch_op.drop_column('stock_minimo')

    with op.batch_alter_table('presupuesto_items', schema=None) as batch_op:
        batch_op.drop_constraint('fk_presupuesto_items_repuesto_id', type_='foreignkey')
        batch_op.drop_column('repuesto_id')

