"""Descarga fotos de licencia libre para la semilla de desarrollo.

Fuente: Wikimedia Commons, **por categoría**, no por búsqueda de texto. La búsqueda
de texto, ante "swimming pool house", devuelve grabados del siglo XIX, actos
políticos y recitales. Las categorías las curan personas: `Category:Log cabins`
tiene cabañas de troncos y nada más.

Son fotos reales, con licencia verificada y crédito guardado. NO son fotos de los
alojamientos: la semilla carga alojamientos de ejemplo y estas imágenes los ilustran.
Cuando haya material de prestadores reales, se reemplazan y este directorio se borra.

Uso:  python scripts/fotos_demo.py [--cantidad 120]
"""

from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
from pathlib import Path

import httpx

API = "https://commons.wikimedia.org/w/api.php"
# Wikimedia exige un User-Agent descriptivo con forma de contacto.
AGENTE = "SuiteCabana-dev/0.1 (semilla de desarrollo; contacto: equipo@ejemplo.test) httpx"
RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "frontend" / "public" / "fotos" / "demo"
ANCHO = 1400
SEMILLA = 20260916

CLIENTE = httpx.Client(headers={"User-Agent": AGENTE}, timeout=90.0, follow_redirects=True)

LICENCIAS_OK = re.compile(r"^(cc0|cc by(-sa)?[\s-]*[\d.]*|public domain|pd-?.*)$", re.I)

# Aun dentro de una categoría buena se cuela material que no ilustra un alojamiento.
EXCLUIR = re.compile(
    r"engrav|lithograph|etching|woodcut|drawing|sketch|illustration|painting|postcard"
    r"|\bmap\b|floor ?plan|diagram|blueprint|portrait|wedding|funeral|protest|concert"
    r"|president|minist|politic|ceremony|award|museum|ruins?\b|abandoned|derelict"
    r"|1[6-9]\d{2}|19[0-4]\d|LCCN|HABS|archive",
    re.I,
)

# Una proporción rara rompe la grilla de tarjetas.
PROPORCION = (1.2, 2.0)

# Distinguir un grabado de una fotografía mirando los píxeles no funciona: un
# aguafuerte en sepia da la misma saturación que una foto, y el conteo de colores
# se arruina con la compresión JPEG. Lo que sí es confiable son las categorías que
# Commons ya le asignó al archivo, que están curadas por personas.
CATEGORIAS_VETADAS = re.compile(
    r"painting|drawing|engrav|lithograph|etching|watercolou?r|woodcut|print|artwork"
    r"|illustration|postcard|poster|\bmaps?\b|plans of|diagram|sculpture"
    r"|black[- ]and[- ]white photograph|1[6-9]\d{2}|\d{2}th[- ]century|photochrom"
    r"|portrait|people|men|women|children",
    re.I,
)

# (categoría propia, categoría de Commons, cuántas tomar)
CATEGORIAS = [
    ("cabana", "Log cabins", 8),
    ("cabana", "Wooden houses", 8),
    ("cabana", "Chalets", 6),
    ("casa", "Cottages", 8),
    ("casa", "Country houses", 6),
    ("casa", "Houses in Argentina", 8),
    ("departamento", "Apartments", 6),
    ("departamento", "Living rooms", 8),
    ("interior", "Bedrooms", 8),
    ("interior", "Kitchens", 6),
    ("interior", "Dining rooms", 6),
    ("interior", "Bathrooms", 5),
    ("pileta", "Outdoor swimming pools", 10),
    # San Juan de verdad, por departamento.
    ("entorno", "Rivadavia Department, San Juan", 8),
    ("entorno", "Calingasta Department", 6),
    ("entorno", "Valle Fértil Department", 6),
    ("entorno", "Barreal", 5),
    ("entorno", "Quebrada de Zonda", 4),
    ("entorno", "Vineyards in Argentina", 5),
]


def pedir(params: dict) -> dict:
    r = CLIENTE.get(API, params={**params, "format": "json"})
    r.raise_for_status()
    return r.json()


def archivos_de(categoria: str, limite: int = 200) -> list[str]:
    datos = pedir(
        {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": f"Category:{categoria}",
            "cmtype": "file",
            "cmlimit": str(limite),
        }
    )
    return [f["title"] for f in datos.get("query", {}).get("categorymembers", [])]


def limpiar(html: str | None) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html or "").split())[:160]


def metadatos(titulos: list[str]) -> list[dict]:
    """Commons acepta hasta 50 títulos por consulta."""
    salida: list[dict] = []
    for i in range(0, len(titulos), 50):
        datos = pedir(
            {
                "action": "query",
                "titles": "|".join(titulos[i : i + 50]),
                "prop": "imageinfo|categories",
                "iiprop": "url|extmetadata|mime|size",
                "iiurlwidth": str(ANCHO),
                "cllimit": "max",
            }
        )
        for pagina in datos.get("query", {}).get("pages", {}).values():
            info = (pagina.get("imageinfo") or [{}])[0]
            if not info or info.get("mime") not in ("image/jpeg", "image/png"):
                continue
            meta = info.get("extmetadata", {})
            lic = limpiar(meta.get("LicenseShortName", {}).get("value"))
            if not LICENCIAS_OK.match(lic.strip()):
                continue
            if (info.get("width") or 0) < 1000:
                continue
            categorias = [
                c["title"].removeprefix("Category:") for c in pagina.get("categories", [])
            ]
            vetada = next((c for c in categorias if CATEGORIAS_VETADAS.search(c)), None)
            if vetada:
                continue
            salida.append(
                {
                    "titulo": pagina["title"],
                    "descarga": info.get("thumburl") or info.get("url"),
                    "pagina": info.get("descriptionurl"),
                    "autor": limpiar(meta.get("Artist", {}).get("value")) or "Autor no indicado",
                    "licencia": lic,
                    "descripcion": limpiar(meta.get("ImageDescription", {}).get("value")),
                }
            )
    return salida


def nombre_archivo(titulo: str, indice: int) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", titulo.removeprefix("File:").lower()).strip("-")
    return f"{indice:03d}-{base[:44].strip('-') or 'foto'}.jpg"


def _medida(ruta: Path, formula: str) -> float | None:
    """Lee una métrica de la imagen con ImageMagick; None si no está disponible."""
    try:
        r = subprocess.run(
            ["magick", str(ruta), "-format", formula, "info:"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return float(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def aceptable(ruta: Path) -> str | None:
    """None si la foto sirve; si no, el motivo del descarte."""
    ancho, alto = _medida(ruta, "%w"), _medida(ruta, "%h")
    if ancho and alto:
        proporcion = ancho / alto
        if not PROPORCION[0] <= proporcion <= PROPORCION[1]:
            return f"proporción {proporcion:.2f}"
    return None


def descargar(item: dict, ruta: Path) -> bool:
    try:
        r = CLIENTE.get(item["descarga"])
        r.raise_for_status()
        ruta.write_bytes(r.content)
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ {item['titulo'][:48]}: {type(e).__name__}", file=sys.stderr)
        return False
    if ruta.stat().st_size < 8000:
        ruta.unlink(missing_ok=True)
        return False
    subprocess.run(
        ["sips", "-s", "format", "jpeg", "-s", "formatOptions", "72",
         "-Z", str(ANCHO), str(ruta), "--out", str(ruta)],
        capture_output=True,
    )
    return ruta.exists() and ruta.stat().st_size > 5000


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cantidad", type=int, default=120)
    args = ap.parse_args()

    az = random.Random(SEMILLA)
    DESTINO.mkdir(parents=True, exist_ok=True)
    creditos: list[dict] = []
    vistos: set[str] = set()
    indice = 0

    for categoria, commons, cupo in CATEGORIAS:
        if indice >= args.cantidad:
            break
        try:
            titulos = archivos_de(commons)
        except Exception as e:  # noqa: BLE001
            print(f"✗ {commons}: {type(e).__name__}", file=sys.stderr)
            continue
        if not titulos:
            print(f"✗ {commons}: categoría vacía", file=sys.stderr)
            continue

        # Las categorías vienen alfabéticas: sin mezclar, siempre saldrían las mismas.
        az.shuffle(titulos)
        candidatos = [m for m in metadatos(titulos[:60]) if not EXCLUIR.search(m["titulo"])]
        print(f"→ {categoria} · {commons}: {len(candidatos)} candidatas")

        tomados = 0
        for item in candidatos:
            if tomados >= cupo or indice >= args.cantidad or item["titulo"] in vistos:
                continue
            archivo = nombre_archivo(item["titulo"], indice)
            ruta = DESTINO / archivo
            if not descargar(item, ruta):
                continue
            motivo = aceptable(ruta)
            if motivo:
                ruta.unlink(missing_ok=True)
                continue

            vistos.add(item["titulo"])
            creditos.append(
                {
                    "archivo": archivo,
                    "url": f"/fotos/demo/{archivo}",
                    "categoria": categoria,
                    "titulo": item["titulo"].removeprefix("File:"),
                    "autor": item["autor"],
                    "licencia": item["licencia"],
                    "origen": item["pagina"],
                    "categoria_commons": commons,
                }
            )
            indice += 1
            tomados += 1

    (DESTINO / "creditos.json").write_text(
        json.dumps(
            {
                "nota": (
                    "Fotos de Wikimedia Commons con licencia libre, tomadas de categorías "
                    "curadas y usadas solo como material provisorio de desarrollo. No "
                    "corresponden a los alojamientos de la semilla, que son ficticios. "
                    "Reemplazar por fotos reales de los prestadores antes de cualquier uso "
                    "público."
                ),
                "fotos": creditos,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n{len(creditos)} fotos en {DESTINO}")
    return 0 if creditos else 1


if __name__ == "__main__":
    raise SystemExit(main())
