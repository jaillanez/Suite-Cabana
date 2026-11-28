"""Mercado Pago con un botón (OAuth): cómo se conectó la cuenta del anfitrión,
cuándo vence su credencial, y cuánta comisión retuvo Mercado Pago en cada pago.

Revision ID: 0018
Revises: 0017
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0018'
down_revision: str | None = '0017'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'prestador',
        sa.Column('mp_oauth', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'prestador', sa.Column('mp_token_vence_en', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        'pago',
        sa.Column(
            'comision_retenida', sa.Numeric(precision=14, scale=2), nullable=False,
            server_default='0',
        ),
    )


def downgrade() -> None:
    op.drop_column('pago', 'comision_retenida')
    op.drop_column('prestador', 'mp_token_vence_en')
    op.drop_column('prestador', 'mp_oauth')
