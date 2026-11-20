"""Reservas que entraron por fuera: por mail de la plataforma o vendidas a mano.

Despegar no publica iCal, y una venta por WhatsApp no tiene calendario ninguno.
Las dos terminan acá: una fila con nombre y fechas, y el bloqueo que produce.
"""
from collections.abc import Sequence

import geoalchemy2  # noqa: F401
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0007'
down_revision: str | None = '0006'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Un valor nuevo de enum no lo detecta autogenerate: va a mano. Fuera de
    # transacción porque Postgres no deja usar el valor en la misma que lo crea.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE origen_bloqueo ADD VALUE IF NOT EXISTS 'externa'")

    op.create_table('reserva_externa',
    sa.Column('prestador_id', sa.Uuid(), nullable=False),
    sa.Column('unidad_id', sa.Uuid(), nullable=True),
    sa.Column('origen', sa.Enum('particular', 'correo', name='origen_reserva_externa'), nullable=False),
    sa.Column('estado', sa.Enum('confirmada', 'por_revisar', 'descartada', name='estado_reserva_externa'), nullable=False),
    sa.Column('plataforma', sa.String(length=30), nullable=False),
    sa.Column('fecha_inicio', sa.Date(), nullable=True),
    sa.Column('fecha_fin', sa.Date(), nullable=True),
    sa.Column('huesped', sa.String(length=120), nullable=True),
    sa.Column('contacto', sa.String(length=120), nullable=True),
    sa.Column('personas', sa.SmallInteger(), nullable=True),
    sa.Column('monto', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('codigo_externo', sa.String(length=80), nullable=True),
    sa.Column('nota', sa.String(length=400), nullable=True),
    sa.Column('faltantes', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('huella', sa.String(length=120), nullable=True),
    sa.Column('mensaje', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('actualizado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['prestador_id'], ['prestador.id'], name=op.f('fk_reserva_externa_prestador_id_prestador')),
    sa.ForeignKeyConstraint(['unidad_id'], ['unidad.id'], name=op.f('fk_reserva_externa_unidad_id_unidad')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reserva_externa')),
    sa.UniqueConstraint('prestador_id', 'huella', name='uq_reserva_externa_huella')
    )
    op.create_index(op.f('ix_reserva_externa_prestador_id'), 'reserva_externa', ['prestador_id'], unique=False)
    op.create_index(op.f('ix_reserva_externa_unidad_id'), 'reserva_externa', ['unidad_id'], unique=False)
    op.add_column('bloqueo_fecha', sa.Column('reserva_externa_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(op.f('fk_bloqueo_fecha_reserva_externa_id_reserva_externa'), 'bloqueo_fecha', 'reserva_externa', ['reserva_externa_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    # El valor del enum no se saca: Postgres no lo permite sin recrear el tipo,
    # y dejarlo de más no rompe nada.
    op.drop_constraint(op.f('fk_bloqueo_fecha_reserva_externa_id_reserva_externa'), 'bloqueo_fecha', type_='foreignkey')
    op.drop_column('bloqueo_fecha', 'reserva_externa_id')
    op.drop_index(op.f('ix_reserva_externa_unidad_id'), table_name='reserva_externa')
    op.drop_index(op.f('ix_reserva_externa_prestador_id'), table_name='reserva_externa')
    op.drop_table('reserva_externa')
    sa.Enum(name='estado_reserva_externa').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='origen_reserva_externa').drop(op.get_bind(), checkfirst=True)
