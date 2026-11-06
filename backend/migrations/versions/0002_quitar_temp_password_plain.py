"""quitar usuarios.temp_password_plain

La contraseña temporal ya no se guarda (se devuelve una sola vez al generarla).
Se borra la columna, que en bases viejas podía tener claves en texto plano.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("usuarios") as batch_op:
        batch_op.drop_column("temp_password_plain")


def downgrade() -> None:
    # Se recrea vacía: los valores borrados no se recuperan (y no deberían).
    with op.batch_alter_table("usuarios") as batch_op:
        batch_op.add_column(sa.Column("temp_password_plain", sa.String(), nullable=True))
