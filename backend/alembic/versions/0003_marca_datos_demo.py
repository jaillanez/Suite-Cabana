"""marca de datos de ejemplo en prestador y publicacion

Los datos de la semilla de desarrollo tienen que ser distinguibles de los reales
dentro de la propia base: sin esta marca, un alojamiento de ejemplo es
indistinguible de uno cargado por un prestador de verdad.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for tabla in ("prestador", "publicacion"):
        op.add_column(
            tabla,
            sa.Column("es_demo", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    op.create_index("ix_publicacion_es_demo", "publicacion", ["es_demo"])


def downgrade() -> None:
    op.drop_index("ix_publicacion_es_demo", table_name="publicacion")
    for tabla in ("publicacion", "prestador"):
        op.drop_column(tabla, "es_demo")
