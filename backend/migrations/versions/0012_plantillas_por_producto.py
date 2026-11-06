"""plantillas de presupuesto por producto

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-06 18:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0012'
down_revision: Union[str, None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('plantillas_presupuesto', schema=None) as batch_op:
        batch_op.add_column(sa.Column('producto_id', sa.Integer(), nullable=True))
        batch_op.create_index('ix_plantillas_presupuesto_producto_id', ['producto_id'], unique=False)
        batch_op.create_foreign_key('fk_plantillas_presupuesto_producto_id', 'productos', ['producto_id'], ['id'],
                                    ondelete='SET NULL')


def downgrade() -> None:
    with op.batch_alter_table('plantillas_presupuesto', schema=None) as batch_op:
        batch_op.drop_constraint('fk_plantillas_presupuesto_producto_id', type_='foreignkey')
        batch_op.drop_index('ix_plantillas_presupuesto_producto_id')
        batch_op.drop_column('producto_id')
