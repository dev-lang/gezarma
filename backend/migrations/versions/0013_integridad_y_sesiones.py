"""integridad y sesiones

- usuarios.token_version: invalida los tokens al cambiar o resetear la clave.
- rma_counters: un solo contador por (año, prefijo); si hubiera duplicados se
  conserva el más avanzado.
- stock_movimientos: vínculo con el ítem de pedido y anulación (en lugar de
  borrar movimientos).

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-06 18:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0013'
down_revision: Union[str, None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.add_column(sa.Column('token_version', sa.Integer(), server_default='0', nullable=False))

    # Contadores duplicados (posibles con altas simultáneas): queda el más avanzado
    conn = op.get_bind()
    filas = conn.execute(sa.text("SELECT id, year, rol_prefix, serie, last_seq FROM rma_counters")).fetchall()
    mejor = {}
    for f in filas:
        k = (f.year, f.rol_prefix)
        if k not in mejor or (f.serie, f.last_seq) > (mejor[k].serie, mejor[k].last_seq):
            mejor[k] = f
    conservar = {f.id for f in mejor.values()}
    for f in filas:
        if f.id not in conservar:
            conn.execute(sa.text("DELETE FROM rma_counters WHERE id = :id"), {"id": f.id})
    with op.batch_alter_table('rma_counters', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_rma_counters_year_prefix', ['year', 'rol_prefix'])

    with op.batch_alter_table('stock_movimientos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('pedido_item_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('anula_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('anulado', sa.Boolean(), server_default='0', nullable=False))
        batch_op.create_foreign_key('fk_stock_movimientos_pedido_item_id', 'pedido_items', ['pedido_item_id'], ['id'])
        batch_op.create_foreign_key('fk_stock_movimientos_anula_id', 'stock_movimientos', ['anula_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('stock_movimientos', schema=None) as batch_op:
        batch_op.drop_constraint('fk_stock_movimientos_anula_id', type_='foreignkey')
        batch_op.drop_constraint('fk_stock_movimientos_pedido_item_id', type_='foreignkey')
        batch_op.drop_column('anulado')
        batch_op.drop_column('anula_id')
        batch_op.drop_column('pedido_item_id')
    with op.batch_alter_table('rma_counters', schema=None) as batch_op:
        batch_op.drop_constraint('uq_rma_counters_year_prefix', type_='unique')
    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.drop_column('token_version')
