"""Guardado y optimización de fotos de publicaciones (docs/01 §5 R2).

El prestador sube lo que tiene: una foto de 8 MB salida del teléfono, a veces
rotada. Acá se normaliza una sola vez, al subirla, y no en cada visita: se corrige
la orientación EXIF, se achica al ancho máximo, se convierte a WebP y se le saca
la metadata, que puede traer la ubicación exacta de la casa.

El almacenamiento es el disco local. Cuando haya almacenamiento de objetos con CDN
(docs/00 §9) cambia `guardar`, no el resto del sistema.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps

from app.core.config import get_settings

FORMATOS = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
CALIDAD = 82


class FotoInvalida(Exception):
    """El archivo no es una imagen que podamos usar."""


@dataclass(frozen=True)
class FotoGuardada:
    url: str
    ruta: Path
    ancho: int
    alto: int
    bytes: int


def _carpeta(publicacion_id: uuid.UUID) -> Path:
    s = get_settings()
    carpeta = Path(s.media_dir) / "publicaciones" / str(publicacion_id)
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def guardar(publicacion_id: uuid.UUID, contenido: bytes, content_type: str | None) -> FotoGuardada:
    s = get_settings()
    if content_type and content_type.lower() not in FORMATOS:
        raise FotoInvalida(f"No podemos usar archivos {content_type}")
    if len(contenido) > s.foto_peso_maximo_mb * 1024 * 1024:
        raise FotoInvalida(f"La foto supera los {s.foto_peso_maximo_mb} MB")

    try:
        imagen = Image.open(BytesIO(contenido))
        imagen.load()
    except Exception as e:  # noqa: BLE001 - Pillow levanta de todo ante un archivo roto
        raise FotoInvalida("El archivo no es una imagen válida") from e

    # La orientación viene en EXIF: sin esto, media galería sale acostada.
    imagen = ImageOps.exif_transpose(imagen)
    if imagen.mode not in ("RGB", "L"):
        imagen = imagen.convert("RGB")
    if imagen.width > s.foto_ancho_maximo:
        alto = round(imagen.height * s.foto_ancho_maximo / imagen.width)
        imagen = imagen.resize((s.foto_ancho_maximo, alto), Image.LANCZOS)

    nombre = f"{uuid.uuid4().hex}.webp"
    ruta = _carpeta(publicacion_id) / nombre
    # `Image.save` sin exif: la metadata puede traer la ubicación exacta de la casa.
    imagen.save(ruta, format="WEBP", quality=CALIDAD, method=5)

    return FotoGuardada(
        url=f"{s.media_url}/publicaciones/{publicacion_id}/{nombre}",
        ruta=ruta,
        ancho=imagen.width,
        alto=imagen.height,
        bytes=ruta.stat().st_size,
    )


def borrar(url: str) -> None:
    """Borra el archivo de una foto. No falla si ya no está."""
    s = get_settings()
    if not url.startswith(s.media_url + "/"):
        return  # una url externa (la semilla usa fotos del frontend) no se toca
    relativa = url[len(s.media_url) + 1 :]
    (Path(s.media_dir) / relativa).unlink(missing_ok=True)
