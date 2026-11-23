"""Sincronización automática de calendarios externos, cada una hora.

`ultimo_intento` registra cada intento, salga bien o mal. `ultima_sincronizacion`
solo cambia cuando sale bien: si la tarea mirara esa, un calendario con la
dirección vencida se reintentaría cada minuto para siempre.

Revision ID: 0013
Revises: 0012
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0013'
down_revision: str | None = '0012'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'calendario_externo',
        sa.Column('ultimo_intento', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('calendario_externo', 'ultimo_intento')
