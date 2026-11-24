"""Traslados, etapa 1 (docs/06): lugares, tramos fijos, tarifa de cada vehículo y
las valijas que entran.

El tipo "Traslado" ya existe desde el esquema inicial; sus subtipos los carga el
catálogo (`python -m app.semilla catalogo`), que corre en cada despliegue.

Revision ID: 0016
Revises: 0015
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision: str = '0016'
down_revision: str | None = '0015'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('lugar_traslado',
    sa.Column('publicacion_id', sa.Uuid(), nullable=False),
    sa.Column('nombre', sa.String(length=120), nullable=False),
    sa.Column('ubicacion', geoalchemy2.types.Geography(geometry_type='POINT', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeogFromText', name='geography'), nullable=True),
    sa.Column('es_base', sa.Boolean(), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['publicacion_id'], ['publicacion.id'], name=op.f('fk_lugar_traslado_publicacion_id_publicacion')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_lugar_traslado')),
    sa.UniqueConstraint('publicacion_id', 'nombre', name='uq_lugar_traslado_nombre')
    )
    op.create_index(op.f('ix_lugar_traslado_publicacion_id'), 'lugar_traslado', ['publicacion_id'], unique=False)
    op.create_table('tarifa_traslado',
    sa.Column('unidad_id', sa.Uuid(), nullable=False),
    sa.Column('precio_km', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('bajada', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('minimo', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('radio_km', sa.SmallInteger(), nullable=True),
    sa.Column('factor_ruta', sa.Numeric(precision=7, scale=4), nullable=False),
    sa.Column('velocidad_kmh', sa.SmallInteger(), nullable=False),
    sa.Column('recargo_nocturno_desde', sa.Time(), nullable=True),
    sa.Column('recargo_nocturno_hasta', sa.Time(), nullable=True),
    sa.Column('recargo_nocturno_porcentaje', sa.Numeric(precision=7, scale=4), nullable=False),
    sa.Column('vuelve_a_base', sa.Boolean(), nullable=False),
    sa.Column('anticipacion_minima_horas', sa.SmallInteger(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint('anticipacion_minima_horas BETWEEN 0 AND 720', name=op.f('ck_tarifa_traslado_anticipacion_rango')),
    sa.CheckConstraint('bajada >= 0 AND minimo >= 0', name=op.f('ck_tarifa_traslado_montos_no_negativos')),
    sa.CheckConstraint('factor_ruta BETWEEN 1 AND 3', name=op.f('ck_tarifa_traslado_factor_ruta_rango')),
    sa.CheckConstraint('precio_km IS NULL OR precio_km > 0', name=op.f('ck_tarifa_traslado_precio_km_positivo')),
    sa.CheckConstraint('radio_km IS NULL OR radio_km > 0', name=op.f('ck_tarifa_traslado_radio_positivo')),
    sa.CheckConstraint('recargo_nocturno_porcentaje BETWEEN 0 AND 200', name=op.f('ck_tarifa_traslado_recargo_rango')),
    sa.CheckConstraint('velocidad_kmh BETWEEN 10 AND 150', name=op.f('ck_tarifa_traslado_velocidad_rango')),
    sa.ForeignKeyConstraint(['unidad_id'], ['unidad.id'], name=op.f('fk_tarifa_traslado_unidad_id_unidad')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_tarifa_traslado')),
    sa.UniqueConstraint('unidad_id', name=op.f('uq_tarifa_traslado_unidad_id'))
    )
    op.create_table('tramo_traslado',
    sa.Column('unidad_id', sa.Uuid(), nullable=False),
    sa.Column('origen_id', sa.Uuid(), nullable=False),
    sa.Column('destino_id', sa.Uuid(), nullable=False),
    sa.Column('precio', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('por_persona', sa.Boolean(), nullable=False),
    sa.Column('duracion_minutos', sa.SmallInteger(), nullable=False),
    sa.Column('ambos_sentidos', sa.Boolean(), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint('duracion_minutos BETWEEN 5 AND 2880', name=op.f('ck_tramo_traslado_duracion_rango')),
    sa.CheckConstraint('origen_id <> destino_id', name=op.f('ck_tramo_traslado_origen_distinto_destino')),
    sa.CheckConstraint('precio > 0', name=op.f('ck_tramo_traslado_precio_positivo')),
    sa.ForeignKeyConstraint(['destino_id'], ['lugar_traslado.id'], name=op.f('fk_tramo_traslado_destino_id_lugar_traslado')),
    sa.ForeignKeyConstraint(['origen_id'], ['lugar_traslado.id'], name=op.f('fk_tramo_traslado_origen_id_lugar_traslado')),
    sa.ForeignKeyConstraint(['unidad_id'], ['unidad.id'], name=op.f('fk_tramo_traslado_unidad_id_unidad')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_tramo_traslado')),
    sa.UniqueConstraint('unidad_id', 'origen_id', 'destino_id', name='uq_tramo_traslado')
    )
    op.create_index(op.f('ix_tramo_traslado_unidad_id'), 'tramo_traslado', ['unidad_id'], unique=False)
    op.add_column('unidad', sa.Column('equipaje', sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column('unidad', 'equipaje')
    op.drop_index(op.f('ix_tramo_traslado_unidad_id'), table_name='tramo_traslado')
    op.drop_table('tramo_traslado')
    op.drop_table('tarifa_traslado')
    op.drop_index(op.f('ix_lugar_traslado_publicacion_id'), table_name='lugar_traslado')
    op.drop_table('lugar_traslado')
