"""encuestas de satisfacción

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-06 16:40:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0008'
down_revision: Union[str, None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'encuestas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ticket_id', sa.Integer(), nullable=False),
        sa.Column('puntaje', sa.Integer(), nullable=False),
        sa.Column('comentario', sa.Text(), nullable=True),
        sa.Column('fecha', sa.DateTime(), nullable=True),
        sa.Column('origen', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id'], name='fk_encuestas_ticket_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ticket_id', name='uq_encuestas_ticket_id'),
    )
    with op.batch_alter_table('encuestas', schema=None) as batch_op:
        batch_op.create_index('ix_encuestas_id', ['id'], unique=False)
        batch_op.create_index('ix_encuestas_fecha', ['fecha'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('encuestas', schema=None) as batch_op:
        batch_op.drop_index('ix_encuestas_fecha')
        batch_op.drop_index('ix_encuestas_id')
    op.drop_table('encuestas')
