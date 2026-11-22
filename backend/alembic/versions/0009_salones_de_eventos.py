"""Salones de eventos, etapa 1 (docs/04): reserva por horario, comodidades por tipo
de servicio, capacidad sentados y bloqueos por rango de hora.

El tipo "Salón de eventos" y sus subtipos no se insertan acá: un valor nuevo de un
enum no se puede usar en la misma transacción que lo crea. Los carga el catálogo
(`python -m app.semilla catalogo`), que es idempotente y corre en cada despliegue.

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0009'
down_revision: str | None = '0008'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE modo_reserva ADD VALUE IF NOT EXISTS 'horas'")

    op.create_table(
        'comodidad_tipo_servicio',
        sa.Column('comodidad_id', sa.Uuid(), nullable=False),
        sa.Column('tipo_servicio_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ['comodidad_id'], ['comodidad.id'],
            name=op.f('fk_comodidad_tipo_servicio_comodidad_id_comodidad'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['tipo_servicio_id'], ['tipo_servicio.id'],
            name=op.f('fk_comodidad_tipo_servicio_tipo_servicio_id_tipo_servicio'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint(
            'comodidad_id', 'tipo_servicio_id', name=op.f('pk_comodidad_tipo_servicio')
        ),
    )
    # Hasta acá todas las comodidades eran de alojamiento: lo siguen siendo.
    op.execute(
        """
        INSERT INTO comodidad_tipo_servicio (comodidad_id, tipo_servicio_id)
        SELECT c.id, t.id FROM comodidad c CROSS JOIN tipo_servicio t
        WHERE t.codigo = 'alojamiento'
        """
    )

    op.add_column('unidad', sa.Column('capacidad_sentados', sa.SmallInteger(), nullable=True))

    op.create_table(
        'bloqueo_horario',
        sa.Column('unidad_id', sa.Uuid(), nullable=False),
        sa.Column('rango', postgresql.TSTZRANGE(), nullable=False),
        sa.Column(
            'origen',
            postgresql.ENUM(name='origen_bloqueo', create_type=False),
            nullable=False,
        ),
        sa.Column('activo', sa.Boolean(), nullable=False),
        sa.Column('vence_en', sa.DateTime(timezone=True), nullable=True),
        sa.Column('item_reserva_id', sa.Uuid(), nullable=True),
        sa.Column('nota', sa.String(length=200), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column(
            'creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'actualizado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'),
            nullable=False,
        ),
        postgresql.ExcludeConstraint(
            (sa.column('unidad_id'), '='),
            (sa.column('rango'), '&&'),
            where=sa.text('activo'),
            using='gist',
            name='ex_bloqueo_horario_sin_superposicion',
        ),
        sa.ForeignKeyConstraint(
            ['item_reserva_id'], ['item_reserva.id'],
            name=op.f('fk_bloqueo_horario_item_reserva_id_item_reserva'),
        ),
        sa.ForeignKeyConstraint(
            ['unidad_id'], ['unidad.id'], name=op.f('fk_bloqueo_horario_unidad_id_unidad')
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_bloqueo_horario')),
    )
    op.create_index(
        op.f('ix_bloqueo_horario_unidad_id'), 'bloqueo_horario', ['unidad_id'], unique=False
    )
    op.create_index(
        'ix_bloqueo_horario_vence', 'bloqueo_horario', ['vence_en'], unique=False,
        postgresql_where=sa.text('vence_en IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index('ix_bloqueo_horario_vence', table_name='bloqueo_horario')
    op.drop_index(op.f('ix_bloqueo_horario_unidad_id'), table_name='bloqueo_horario')
    op.drop_table('bloqueo_horario')
    op.drop_column('unidad', 'capacidad_sentados')
    op.drop_table('comodidad_tipo_servicio')
    # El valor 'horas' de modo_reserva queda: PostgreSQL no permite quitarlo.
