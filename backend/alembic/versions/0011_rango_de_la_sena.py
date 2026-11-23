"""Rango de la seña (0 a 100 %) en publicación y prestador.

La API ya lo valida, pero el porcentaje decide cuánto se cobra online: la base
tiene que rechazar un valor fuera de rango venga por donde venga.

Revision ID: 0011
Revises: 0010
"""

from collections.abc import Sequence

from alembic import op

revision: str = '0011'
down_revision: str | None = '0010'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONDICION = "porcentaje_sena IS NULL OR porcentaje_sena BETWEEN 0 AND 100"


def upgrade() -> None:
    op.create_check_constraint('porcentaje_sena_rango', 'publicacion', CONDICION)
    op.create_check_constraint('porcentaje_sena_rango', 'prestador', CONDICION)


def downgrade() -> None:
    op.drop_constraint(op.f('ck_prestador_porcentaje_sena_rango'), 'prestador', type_='check')
    op.drop_constraint(op.f('ck_publicacion_porcentaje_sena_rango'), 'publicacion', type_='check')
