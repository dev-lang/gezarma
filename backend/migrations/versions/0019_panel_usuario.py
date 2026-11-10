"""panel de control personalizable por usuario

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-10 17:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0019'
down_revision: Union[str, None] = '0018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("usuarios") as b:
        b.add_column(sa.Column("panel_config", sa.Text(), nullable=True))


def downgrade() -> None:
    op.execute("DELETE FROM config_sistema WHERE clave = 'panel_predeterminado'")
    with op.batch_alter_table("usuarios") as b:
        b.drop_column("panel_config")
