"""Cuenta de cobro propia del prestador: nombre visible de la cuenta vinculada.

La credencial ya tenía columna (`mp_access_token`); desde acá se guarda cifrada.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0008'
down_revision: str | None = '0007'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('prestador', sa.Column('mp_cuenta', sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column('prestador', 'mp_cuenta')
