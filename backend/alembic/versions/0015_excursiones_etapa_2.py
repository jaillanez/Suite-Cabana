"""Excursiones, etapa 2 (docs/05): lo que decide cada prestador.

- Precios por tipo de pasajero (`precio_pasajero`), con las edades que él elija.
- Mínimo de personas por turno y con cuántas horas se decide; la salida los copia.
- Tramos de cancelación propios de la publicación, sobre la plantilla.
- Cuánto se devuelve si la salida no sale por el prestador (por defecto, todo).

Revision ID: 0015
Revises: 0014
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0015'
down_revision: str | None = '0014'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('precio_pasajero',
    sa.Column('unidad_id', sa.Uuid(), nullable=False),
    sa.Column('nombre', sa.String(length=60), nullable=False),
    sa.Column('descripcion', sa.String(length=200), nullable=True),
    sa.Column('edad_desde', sa.SmallInteger(), nullable=True),
    sa.Column('edad_hasta', sa.SmallInteger(), nullable=True),
    sa.Column('precio', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('ocupa_lugar', sa.Boolean(), nullable=False),
    sa.Column('orden', sa.SmallInteger(), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint('edad_desde IS NULL OR edad_hasta IS NULL OR edad_hasta >= edad_desde', name=op.f('ck_precio_pasajero_edades')),
    sa.CheckConstraint('precio >= 0', name=op.f('ck_precio_pasajero_precio_no_negativo')),
    sa.ForeignKeyConstraint(['unidad_id'], ['unidad.id'], name=op.f('fk_precio_pasajero_unidad_id_unidad')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_precio_pasajero'))
    )
    op.create_index(op.f('ix_precio_pasajero_unidad_id'), 'precio_pasajero', ['unidad_id'], unique=False)
    op.add_column('publicacion', sa.Column('tramos_cancelacion', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('publicacion', sa.Column('reintegro_si_no_sale', sa.SmallInteger(), nullable=False, server_default='100'))
    op.add_column('salida_excursion', sa.Column('minimo_personas', sa.SmallInteger(), nullable=False, server_default='1'))
    op.add_column('salida_excursion', sa.Column('aviso_minimo_horas', sa.SmallInteger(), nullable=False, server_default='24'))
    op.add_column('salida_excursion', sa.Column('sale_confirmada', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('turno_excursion', sa.Column('minimo_personas', sa.SmallInteger(), nullable=False, server_default='1'))
    op.add_column('turno_excursion', sa.Column('aviso_minimo_horas', sa.SmallInteger(), nullable=False, server_default='24'))
    op.create_check_constraint(
        'reintegro_si_no_sale_rango', 'publicacion', 'reintegro_si_no_sale BETWEEN 0 AND 100'
    )
    op.create_check_constraint(
        'minimo_rango', 'turno_excursion', 'minimo_personas BETWEEN 1 AND cupo'
    )
    op.create_check_constraint(
        'aviso_rango', 'turno_excursion', 'aviso_minimo_horas BETWEEN 0 AND 720'
    )
    op.create_check_constraint('minimo_positivo', 'salida_excursion', 'minimo_personas >= 1')


def downgrade() -> None:
    op.drop_constraint('minimo_positivo', 'salida_excursion', type_='check')
    op.drop_constraint('aviso_rango', 'turno_excursion', type_='check')
    op.drop_constraint('minimo_rango', 'turno_excursion', type_='check')
    op.drop_constraint('reintegro_si_no_sale_rango', 'publicacion', type_='check')
    op.drop_column('turno_excursion', 'aviso_minimo_horas')
    op.drop_column('turno_excursion', 'minimo_personas')
    op.drop_column('salida_excursion', 'sale_confirmada')
    op.drop_column('salida_excursion', 'aviso_minimo_horas')
    op.drop_column('salida_excursion', 'minimo_personas')
    op.drop_column('publicacion', 'reintegro_si_no_sale')
    op.drop_column('publicacion', 'tramos_cancelacion')
    op.drop_index(op.f('ix_precio_pasajero_unidad_id'), table_name='precio_pasajero')
    op.drop_table('precio_pasajero')
