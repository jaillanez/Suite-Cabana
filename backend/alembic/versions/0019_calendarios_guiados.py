"""Calendarios guiados: quién lee nuestro calendario (Airbnb, Booking…) y desde
cuándo falla un calendario importado, para avisarle al anfitrión una sola vez.

Revision ID: 0019
Revises: 0018
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0019'
down_revision: str | None = '0018'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'lectura_calendario',
        sa.Column('unidad_id', sa.Uuid(), nullable=False),
        sa.Column('plataforma', sa.String(length=30), nullable=False),
        sa.Column('leido_en', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ['unidad_id'], ['unidad.id'], name=op.f('fk_lectura_calendario_unidad_id_unidad')
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_lectura_calendario')),
        sa.UniqueConstraint('unidad_id', 'plataforma', name='uq_lectura_calendario'),
    )
    op.create_index(
        op.f('ix_lectura_calendario_unidad_id'), 'lectura_calendario', ['unidad_id'], unique=False
    )
    op.add_column(
        'calendario_externo', sa.Column('error_desde', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        'calendario_externo',
        sa.Column('aviso_error_en', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('calendario_externo', 'aviso_error_en')
    op.drop_column('calendario_externo', 'error_desde')
    op.drop_index(op.f('ix_lectura_calendario_unidad_id'), table_name='lectura_calendario')
    op.drop_table('lectura_calendario')
