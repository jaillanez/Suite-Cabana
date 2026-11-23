"""Tareas periódicas: lo que no espera a que alguien entre a la página.

    python -m app.tareas            # corre para siempre, cada INTERVALO segundos
    python -m app.tareas --una-vez  # una pasada y sale

- Libera las reservas que no se pagaron a tiempo (docs/01 §5 R5), y los lugares
  de excursión retenidos que vencieron (docs/05).
- Vacía el buzón de notificaciones: confirmaciones, avisos al anfitrión.
- Trae de nuevo los calendarios de Airbnb, Booking, etc. cada una hora.

Una sola instancia: si corrieran dos, las dos tomarían los mismos pendientes.
Cuando haya cola de trabajos (docs/00 §9) esto pasa a ser un par de tareas de ella.
"""

from __future__ import annotations

import argparse
import logging
import time

from app.core.database import SessionLocal
from app.services import calendario, horarios, notificaciones, reservas, salidas

INTERVALO = 60
registro = logging.getLogger("tareas")


def una_pasada() -> dict[str, int]:
    resultado: dict[str, int] = {}
    with SessionLocal() as db:
        resultado["liberadas"] = reservas.liberar_vencidas(db)
        resultado["horas_liberadas"] = horarios.soltar_vencidos(db)
        resultado["lugares_liberados"] = salidas.soltar_vencidos(db)
        db.commit()
    with SessionLocal() as db:
        resultado.update(notificaciones.enviar_pendientes(db))
        db.commit()
    # Al final: es lo único que sale a internet y puede tardar.
    with SessionLocal() as db:
        resultado.update(calendario.sincronizar_vencidos(db))
        db.commit()
    return resultado


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m app.tareas")
    ap.add_argument("--una-vez", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    while True:
        try:
            resultado = una_pasada()
            if any(resultado.values()):
                registro.info("pasada: %s", resultado)
        except Exception:  # noqa: BLE001 - una pasada fallida no frena las siguientes
            registro.exception("falló una pasada")
            if args.una_vez:
                return 1
        if args.una_vez:
            return 0
        time.sleep(INTERVALO)


if __name__ == "__main__":
    raise SystemExit(main())
