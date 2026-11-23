"""Política de cancelación por ítem (docs/04 §5 S11, paquete salón + cabañas).

En un paquete cada ítem cancela con su propia política (el salón con la de
eventos, la cabaña con la suya): el snapshot pasa a guardarse también por ítem.
Las reservas existentes se completan con el de la reserva, que era el único.

Revision ID: 0012
Revises: 0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0012'
down_revision: str | None = '0011'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'item_reserva',
        sa.Column('politica_cancelacion', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.execute(
        "UPDATE item_reserva i SET politica_cancelacion = r.politica_cancelacion "
        "FROM reserva r WHERE r.id = i.reserva_id"
    )


def downgrade() -> None:
    op.drop_column('item_reserva', 'politica_cancelacion')
