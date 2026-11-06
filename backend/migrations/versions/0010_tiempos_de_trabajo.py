"""tiempos de trabajo por técnico

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-06 17:20:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0010'
down_revision: Union[str, None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tiempos_trabajo',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ticket_id', sa.Integer(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('inicio', sa.DateTime(), nullable=False),
        sa.Column('fin', sa.DateTime(), nullable=True),
        sa.Column('nota', sa.String(), nullable=True),
        sa.Column('manual', sa.Boolean(), server_default='0', nullable=False),
        sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id'], name='fk_tiempos_trabajo_ticket_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], name='fk_tiempos_trabajo_usuario_id'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('tiempos_trabajo', schema=None) as batch_op:
        batch_op.create_index('ix_tiempos_trabajo_id', ['id'], unique=False)
        batch_op.create_index('ix_tiempos_trabajo_ticket_id', ['ticket_id'], unique=False)
        batch_op.create_index('ix_tiempos_trabajo_usuario_id', ['usuario_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('tiempos_trabajo', schema=None) as batch_op:
        batch_op.drop_index('ix_tiempos_trabajo_usuario_id')
        batch_op.drop_index('ix_tiempos_trabajo_ticket_id')
        batch_op.drop_index('ix_tiempos_trabajo_id')
    op.drop_table('tiempos_trabajo')
