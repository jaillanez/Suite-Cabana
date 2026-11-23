"""Excursiones, etapa 1 (docs/05): turnos que se repiten, salidas por día y lugares
tomados, con el cupo cuidado por una restricción de la base.

El tipo "Excursión" ya existe desde el esquema inicial; sus subtipos los carga el
catálogo (`python -m app.semilla catalogo`), que corre en cada despliegue.

Revision ID: 0014
Revises: 0013
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0014'
down_revision: str | None = '0013'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('turno_excursion',
    sa.Column('unidad_id', sa.Uuid(), nullable=False),
    sa.Column('nombre', sa.String(length=80), nullable=False),
    sa.Column('dias_semana', postgresql.ARRAY(sa.SmallInteger()), nullable=False),
    sa.Column('hora_inicio', sa.Time(), nullable=False),
    sa.Column('duracion_minutos', sa.Integer(), nullable=False),
    sa.Column('cupo', sa.SmallInteger(), nullable=False),
    sa.Column('desde', sa.Date(), nullable=True),
    sa.Column('hasta', sa.Date(), nullable=True),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('actualizado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('cardinality(dias_semana) > 0 AND dias_semana <@ ARRAY[0,1,2,3,4,5,6]::smallint[]', name=op.f('ck_turno_excursion_dias_validos')),
    sa.CheckConstraint('cupo > 0', name=op.f('ck_turno_excursion_cupo_positivo')),
    sa.CheckConstraint('duracion_minutos BETWEEN 15 AND 20160', name=op.f('ck_turno_excursion_duracion_rango')),
    sa.CheckConstraint('hasta IS NULL OR desde IS NULL OR hasta >= desde', name=op.f('ck_turno_excursion_temporada')),
    sa.ForeignKeyConstraint(['unidad_id'], ['unidad.id'], name=op.f('fk_turno_excursion_unidad_id_unidad')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_turno_excursion'))
    )
    op.create_index(op.f('ix_turno_excursion_unidad_id'), 'turno_excursion', ['unidad_id'], unique=False)
    op.create_table('salida_excursion',
    sa.Column('unidad_id', sa.Uuid(), nullable=False),
    sa.Column('turno_id', sa.Uuid(), nullable=True),
    sa.Column('fecha', sa.Date(), nullable=False),
    sa.Column('inicio_en', sa.DateTime(timezone=True), nullable=False),
    sa.Column('fin_en', sa.DateTime(timezone=True), nullable=False),
    sa.Column('cupo', sa.SmallInteger(), nullable=False),
    sa.Column('ocupados', sa.SmallInteger(), nullable=False),
    sa.Column('suspendida', sa.Boolean(), nullable=False),
    sa.Column('motivo', sa.String(length=200), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('actualizado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('cupo > 0', name=op.f('ck_salida_excursion_cupo_positivo')),
    sa.CheckConstraint('fin_en > inicio_en', name=op.f('ck_salida_excursion_horario_valido')),
    sa.CheckConstraint('ocupados >= 0 AND ocupados <= cupo', name=op.f('ck_salida_excursion_cupo_no_se_pasa')),
    sa.ForeignKeyConstraint(['turno_id'], ['turno_excursion.id'], name=op.f('fk_salida_excursion_turno_id_turno_excursion')),
    sa.ForeignKeyConstraint(['unidad_id'], ['unidad.id'], name=op.f('fk_salida_excursion_unidad_id_unidad')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_salida_excursion')),
    sa.UniqueConstraint('turno_id', 'fecha', name='uq_salida_excursion_turno_fecha')
    )
    op.create_index('ix_salida_excursion_unidad_fecha', 'salida_excursion', ['unidad_id', 'fecha'], unique=False)
    op.create_table('cupo_tomado',
    sa.Column('salida_id', sa.Uuid(), nullable=False),
    sa.Column('personas', sa.SmallInteger(), nullable=False),
    sa.Column('origen', postgresql.ENUM(name='origen_bloqueo', create_type=False), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('vence_en', sa.DateTime(timezone=True), nullable=True),
    sa.Column('item_reserva_id', sa.Uuid(), nullable=True),
    sa.Column('nota', sa.String(length=200), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('actualizado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('personas > 0', name=op.f('ck_cupo_tomado_personas_positivas')),
    sa.ForeignKeyConstraint(['item_reserva_id'], ['item_reserva.id'], name=op.f('fk_cupo_tomado_item_reserva_id_item_reserva')),
    sa.ForeignKeyConstraint(['salida_id'], ['salida_excursion.id'], name=op.f('fk_cupo_tomado_salida_id_salida_excursion')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_cupo_tomado'))
    )
    op.create_index(op.f('ix_cupo_tomado_salida_id'), 'cupo_tomado', ['salida_id'], unique=False)
    op.create_index('ix_cupo_tomado_vence', 'cupo_tomado', ['vence_en'], unique=False, postgresql_where=sa.text('activo'))


def downgrade() -> None:
    op.drop_index('ix_cupo_tomado_vence', table_name='cupo_tomado', postgresql_where=sa.text('activo'))
    op.drop_index(op.f('ix_cupo_tomado_salida_id'), table_name='cupo_tomado')
    op.drop_table('cupo_tomado')
    op.drop_index('ix_salida_excursion_unidad_fecha', table_name='salida_excursion')
    op.drop_table('salida_excursion')
    op.drop_index(op.f('ix_turno_excursion_unidad_id'), table_name='turno_excursion')
    op.drop_table('turno_excursion')
