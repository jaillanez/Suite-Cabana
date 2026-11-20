#!/usr/bin/env python3
"""Carga las fotos reales de Los Búhos desde `fotos/los-buhos/`.

Pasan por el mismo procesamiento que una foto subida desde la web: WebP,
orientación corregida y **EXIF borrado**. Eso último no es un detalle: la foto de
un teléfono lleva adentro la ubicación GPS de dónde se sacó, y publicarla cruda
sería publicar la dirección de la casa.

El orden lo da el nombre del archivo, así que conviene numerarlas.

    python scripts/fotos_los_buhos.py            # carga lo que haya
    python scripts/fotos_los_buhos.py --listar   # solo dice qué encontró
"""

from __future__ import annotations

import argparse
import mimetypes
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "backend"))

from sqlalchemy import delete, select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.models import Foto, Publicacion  # noqa: E402
from app.semilla.datos import LOS_BUHOS  # noqa: E402
from app.services import fotos as procesador  # noqa: E402

CARPETA = RAIZ / "fotos" / "los-buhos"
EXTENSIONES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}


def encontradas() -> list[Path]:
    if not CARPETA.is_dir():
        return []
    return sorted(p for p in CARPETA.iterdir() if p.suffix.lower() in EXTENSIONES)


def cargar(db, publicacion: Publicacion, archivos: list[Path]) -> int:
    """Reemplaza las fotos de la publicación por las de la carpeta.

    Reemplaza y no agrega: así volver a correr esto después de sacar o reordenar
    archivos deja la ficha igual a la carpeta, sin duplicados ni sobras.
    """
    for vieja in db.scalars(select(Foto).where(Foto.publicacion_id == publicacion.id)):
        procesador.borrar(vieja.url)
    db.execute(delete(Foto).where(Foto.publicacion_id == publicacion.id))
    db.flush()

    puestas = 0
    for orden, archivo in enumerate(archivos):
        tipo = mimetypes.guess_type(archivo.name)[0]
        try:
            guardada = procesador.guardar(publicacion.id, archivo.read_bytes(), tipo)
        except procesador.FotoInvalida as e:
            print(f"  ✗ {archivo.name}: {e}")
            continue
        db.add(Foto(publicacion_id=publicacion.id, url=guardada.url, orden=orden))
        puestas += 1
        print(f"  ✓ {archivo.name} → {guardada.url}")
    db.flush()
    return puestas


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--listar", action="store_true", help="Solo mostrar qué hay en la carpeta")
    args = ap.parse_args()

    archivos = encontradas()
    if not archivos:
        print(f"No hay fotos en {CARPETA.relative_to(RAIZ)}/")
        print("Copiá ahí las fotos del lugar, numeradas: 01-frente.jpg, 02-pileta.jpg…")
        print("Las instrucciones completas están en su LEEME.md.")
        return 0

    print(f"{len(archivos)} foto(s) en {CARPETA.relative_to(RAIZ)}/, en este orden:")
    for i, a in enumerate(archivos, 1):
        print(f"  {i:2}. {a.name}  ({a.stat().st_size / 1024:.0f} KB)")
    if args.listar:
        return 0

    with SessionLocal() as db:
        publicacion = db.scalar(
            select(Publicacion).where(Publicacion.slug == LOS_BUHOS["slug"])
        )
        if publicacion is None:
            print("\nLos Búhos no está en la base. Corré primero: python -m app.semilla")
            return 1
        print()
        puestas = cargar(db, publicacion, archivos)
        db.commit()

    print(f"\nListo: {puestas} foto(s) en la ficha.")
    print(f"Miralas en http://localhost:3001/alojamiento/{LOS_BUHOS['slug']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
