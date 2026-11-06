"""pedidos a proveedor

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-06 17:40:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0011'
down_revision: Union[str, None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'pedidos_proveedor',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('proveedor', sa.String(), nullable=False),
        sa.Column('estado', sa.String(), nullable=False),
        sa.Column('notas', sa.Text(), nullable=True),
        sa.Column('fecha_creacion', sa.DateTime(), nullable=True),
        sa.Column('fecha_envio', sa.DateTime(), nullable=True),
        sa.Column('fecha_recepcion', sa.DateTime(), nullable=True),
        sa.Column('creado_por', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['creado_por'], ['usuarios.id'], name='fk_pedidos_proveedor_creado_por'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('pedidos_proveedor', schema=None) as batch_op:
        batch_op.create_index('ix_pedidos_proveedor_id', ['id'], unique=False)
        batch_op.create_index('ix_pedidos_proveedor_proveedor', ['proveedor'], unique=False)
        batch_op.create_index('ix_pedidos_proveedor_estado', ['estado'], unique=False)
    op.create_table(
        'pedido_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pedido_id', sa.Integer(), nullable=False),
        sa.Column('repuesto_id', sa.Integer(), nullable=False),
        sa.Column('cantidad', sa.Integer(), nullable=False),
        sa.Column('recibido', sa.Integer(), server_default='0', nullable=False),
        sa.Column('precio', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['pedido_id'], ['pedidos_proveedor.id'], name='fk_pedido_items_pedido_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['repuesto_id'], ['repuestos.id'], name='fk_pedido_items_repuesto_id'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('pedido_items', schema=None) as batch_op:
        batch_op.create_index('ix_pedido_items_id', ['id'], unique=False)
        batch_op.create_index('ix_pedido_items_pedido_id', ['pedido_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('pedido_items', schema=None) as batch_op:
        batch_op.drop_index('ix_pedido_items_pedido_id')
        batch_op.drop_index('ix_pedido_items_id')
    op.drop_table('pedido_items')
    with op.batch_alter_table('pedidos_proveedor', schema=None) as batch_op:
        batch_op.drop_index('ix_pedidos_proveedor_estado')
        batch_op.drop_index('ix_pedidos_proveedor_proveedor')
        batch_op.drop_index('ix_pedidos_proveedor_id')
    op.drop_table('pedidos_proveedor')
