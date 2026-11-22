"""CLI de la semilla. Ver el docstring de app.semilla."""

from __future__ import annotations

import argparse
from decimal import Decimal

from app.core.database import SessionLocal
from app.models.enums import QuienPaga
from app.semilla import (
    cargar_catalogo,
    cargar_los_buhos,
    cargar_oferta,
    cargar_reservas,
    configurar_comision,
    fotos_de_los_buhos,
    limpiar_demo,
    resumen,
)
from app.semilla.datos import PENDIENTES_LOS_BUHOS


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m app.semilla")
    sub = ap.add_subparsers(dest="comando")

    ap.add_argument("--solo-catalogo", action="store_true", help="No cargar oferta de ejemplo")
    ap.add_argument("--limpiar", action="store_true", help="Borrar la oferta de ejemplo y salir")

    sub.add_parser(
        "catalogo",
        help="Solo el catálogo real (idempotente; no toca la comisión ni la oferta)",
    )

    com = sub.add_parser("comision", help="Configurar la regla de comisión por defecto")
    com.add_argument("--porcentaje", type=Decimal, default=Decimal(10))
    com.add_argument(
        "--quien-paga",
        choices=[q.value for q in QuienPaga],
        default=QuienPaga.PRESTADOR.value,
        help="prestador: la absorbe el prestador · viajero: cargo de servicio · dividido",
    )
    com.add_argument(
        "--porcentaje-viajero",
        type=Decimal,
        default=Decimal(0),
        help="Solo con --quien-paga dividido: qué parte del total paga el viajero",
    )
    com.add_argument("--iva-incluido", action="store_true")

    args = ap.parse_args()

    with SessionLocal() as db:
        if args.comando == "catalogo":
            cargar_catalogo(db)
            db.commit()
            print("Catálogo al día:", resumen(db))
            return 0

        if args.comando == "comision":
            regla = configurar_comision(
                db,
                porcentaje=args.porcentaje,
                quien_paga=QuienPaga(args.quien_paga),
                porcentaje_viajero=args.porcentaje_viajero,
                iva_incluido=args.iva_incluido,
            )
            db.commit()
            print(
                f"Regla por defecto: {regla.porcentaje}% · paga: {regla.quien_paga.value}"
                + (
                    f" ({regla.porcentaje_viajero}% al viajero)"
                    if regla.quien_paga is QuienPaga.DIVIDIDO
                    else ""
                )
            )
            return 0

        if args.limpiar:
            borradas = limpiar_demo(db)
            db.commit()
            print(f"Oferta de ejemplo borrada: {borradas} publicaciones.")
            return 0

        cargar_catalogo(db)
        configurar_comision(db)
        if not args.solo_catalogo:
            limpiar_demo(db)
            conteo = cargar_oferta(db)
            cargar_los_buhos(db)
            print(
                f"Oferta de ejemplo: {conteo['publicaciones']} publicaciones, "
                f"{conteo['unidades']} unidades, {conteo['bloqueos']} bloqueos, "
                f"{conteo['prestadores']} prestadores."
            )
            reservas = cargar_reservas(db)
            print(
                f"Reservas de ejemplo: {reservas['reservas']} "
                f"({reservas.get('confirmada', 0)} confirmadas, "
                f"{reservas.get('pendiente_pago', 0)} esperando el pago, "
                f"{reservas.get('pendiente_aprobacion', 0)} esperando aprobación)."
            )
        db.commit()
        print("En la base:", resumen(db))
        if not args.solo_catalogo:
            con_fotos = len(fotos_de_los_buhos())
            print(
                f"\nLos Búhos: {con_fotos} foto(s) reales cargadas."
                if con_fotos
                else "\nLos Búhos todavía no tiene fotos "
                "(dejalas en fotos/los-buhos/, ver su LEEME.md)."
            )
            faltan = [
                p
                for p in PENDIENTES_LOS_BUHOS
                if not (con_fotos and p.lower().startswith("fotos"))
            ]
            if faltan:
                print("Sigue con datos PROVISORIOS. Falta:")
                for pendiente in faltan:
                    print(f"  · {pendiente}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
