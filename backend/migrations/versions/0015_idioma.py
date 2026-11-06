"""idioma de cada usuario

Vacío = el idioma predeterminado del taller (ajuste idioma_predeterminado).

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-06 21:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0015'
down_revision: Union[str, None] = '0014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("usuarios") as b:
        b.add_column(sa.Column("idioma", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("usuarios") as b:
        b.drop_column("idioma")
