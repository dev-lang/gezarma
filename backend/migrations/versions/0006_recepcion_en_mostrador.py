"""recepción en mostrador

tickets.checklist_ingreso: accesorios, estado físico, si enciende y si tiene
bloqueo. adjuntos.categoria: marca las fotos del estado al ingresar.
firmas: firma del cliente en pantalla al ingreso y a la entrega.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-06 16:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('tickets', schema=None) as batch_op:
        batch_op.add_column(sa.Column('checklist_ingreso', sa.JSON(), nullable=True))
    with op.batch_alter_table('adjuntos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('categoria', sa.String(), nullable=True))
    op.create_table(
        'firmas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ticket_id', sa.Integer(), nullable=False),
        sa.Column('momento', sa.String(), nullable=False),
        sa.Column('imagen', sa.LargeBinary(), nullable=False),
        sa.Column('ancho', sa.Integer(), nullable=False),
        sa.Column('alto', sa.Integer(), nullable=False),
        sa.Column('aclaracion', sa.String(), nullable=True),
        sa.Column('fecha', sa.DateTime(), nullable=True),
        sa.Column('registrado_por', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id'], name='fk_firmas_ticket_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['registrado_por'], ['usuarios.id'], name='fk_firmas_registrado_por'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ticket_id', 'momento', name='uq_firmas_ticket_momento'),
    )
    with op.batch_alter_table('firmas', schema=None) as batch_op:
        batch_op.create_index('ix_firmas_id', ['id'], unique=False)
        batch_op.create_index('ix_firmas_ticket_id', ['ticket_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('firmas', schema=None) as batch_op:
        batch_op.drop_index('ix_firmas_ticket_id')
        batch_op.drop_index('ix_firmas_id')
    op.drop_table('firmas')
    with op.batch_alter_table('adjuntos', schema=None) as batch_op:
        batch_op.drop_column('categoria')
    with op.batch_alter_table('tickets', schema=None) as batch_op:
        batch_op.drop_column('checklist_ingreso')
