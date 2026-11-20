"""pagos con varias pasarelas, no solo Mercado Pago

El producto no se ata a una billetera (docs/00 §8). Las notificaciones y los
pagos pasan a identificar de qué pasarela vienen, y la unicidad de una
notificación es por (pasarela, id_externo): dos billeteras pueden usar el mismo
id sin pisarse.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.rename_table("notificacion_mp", "notificacion_pago")
    op.add_column(
        "notificacion_pago",
        sa.Column("pasarela", sa.String(length=40), nullable=False, server_default="mercadopago"),
    )
    op.drop_constraint("uq_notificacion_mp_id_externo", "notificacion_pago", type_="unique")
    op.create_index(
        op.f("ix_notificacion_pago_pasarela"), "notificacion_pago", ["pasarela"], unique=False
    )
    op.create_unique_constraint(
        "uq_notificacion_pago_pasarela", "notificacion_pago", ["pasarela", "id_externo"]
    )

    op.add_column(
        "pago",
        sa.Column("pasarela", sa.String(length=40), nullable=False, server_default="mercadopago"),
    )
    op.alter_column("pago", "mp_payment_id", new_column_name="id_externo")
    op.alter_column("pago", "mp_preference_id", new_column_name="id_preferencia")
    op.alter_column("pago", "datos_mp", new_column_name="datos")
    # El id externo solo tiene que ser único dentro de su pasarela.
    op.drop_constraint("uq_pago_mp_payment_id", "pago", type_="unique")
    op.create_unique_constraint("uq_pago_pasarela", "pago", ["pasarela", "id_externo"])


def downgrade() -> None:
    op.drop_constraint("uq_pago_pasarela", "pago", type_="unique")
    op.create_unique_constraint("uq_pago_mp_payment_id", "pago", ["id_externo"])
    op.alter_column("pago", "datos", new_column_name="datos_mp")
    op.alter_column("pago", "id_preferencia", new_column_name="mp_preference_id")
    op.alter_column("pago", "id_externo", new_column_name="mp_payment_id")
    op.drop_column("pago", "pasarela")

    op.drop_constraint("uq_notificacion_pago_pasarela", "notificacion_pago", type_="unique")
    op.drop_index(op.f("ix_notificacion_pago_pasarela"), table_name="notificacion_pago")
    op.create_unique_constraint(
        "uq_notificacion_mp_id_externo", "notificacion_pago", ["id_externo"]
    )
    op.drop_column("notificacion_pago", "pasarela")
    op.rename_table("notificacion_pago", "notificacion_mp")
