"""Semilla de desarrollo: carga catálogos reales y oferta de ejemplo en la base.

No hay datos falsos en el código de la aplicación. Lo que la búsqueda devuelve sale
siempre de la base; esto es lo que la llena mientras no haya prestadores cargando
su propia oferta.

- Provincias, localidades, tipos, comodidades y políticas son catálogo real y quedan
  aunque se borre la oferta de ejemplo.
- Prestadores, publicaciones, unidades, tarifas y bloqueos son ficticios y quedan
  marcados con `es_demo = true`.
- Las fotos son reales, de Wikimedia Commons, con licencia libre y crédito guardado
  en `frontend/public/fotos/demo/creditos.json` (ver `scripts/fotos_demo.py`).

Uso:
    python -m app.semilla                      # carga catálogo + oferta de ejemplo
    python -m app.semilla --solo-catalogo      # solo catálogo real
    python -m app.semilla --limpiar            # borra la oferta de ejemplo
    python -m app.semilla comision --porcentaje 12 --quien-paga viajero
"""

from __future__ import annotations

import json
import mimetypes
import random
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hashear_password
from app.models import (
    BloqueoFecha,
    CalendarioExterno,
    Comodidad,
    Favorito,
    Foto,
    ItemReserva,
    Localidad,
    Notificacion,
    Pago,
    PoliticaCancelacion,
    Prestador,
    Provincia,
    Publicacion,
    ReglaComision,
    Resena,
    Reserva,
    ReservaExterna,
    SubtipoServicio,
    Tarifa,
    TipoServicio,
    Unidad,
    Usuario,
    Zona,
)
from app.models.enums import EstadoPublicacion, ModoReserva, OrigenBloqueo, QuienPaga
from app.semilla import datos

#: Los anfitriones de ejemplo se usan para entrar al panel y mirarlo por dentro.
#: `example.com` está reservado justamente para esto; `.test`, en cambio, lo
#: rechaza el validador de correos, y las cuentas quedaban sin poder ingresar.
DOMINIO_DEMO = "demo.example.com"
CLAVE_DEMO = "demo12345"

SEMILLA_ALEATORIA = 20260916
HOY = date(2026, 9, 16)
FOTOS_JSON = (
    Path(__file__).resolve().parents[3] / "frontend" / "public" / "fotos" / "demo" / "creditos.json"
)


def _r(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _punto(lat: float, lon: float) -> str:
    return f"SRID=4326;POINT({lon} {lat})"


def cargar_catalogo(db: Session) -> None:
    """Catálogo real. Idempotente: solo agrega lo que falta."""
    provincias = {p.slug: p for p in db.scalars(select(Provincia))}
    for nombre, slug in datos.PROVINCIAS:
        if slug not in provincias:
            provincias[slug] = Provincia(nombre=nombre, slug=slug)
            db.add(provincias[slug])
    db.flush()

    localidades = {loc.slug: loc for loc in db.scalars(select(Localidad))}
    for prov_slug, nombre, slug, lat, lon, _cant, _perfil, _zonas in datos.LOCALIDADES:
        if slug not in localidades:
            localidades[slug] = Localidad(
                provincia_id=provincias[prov_slug].id,
                nombre=nombre,
                slug=slug,
                ubicacion=_punto(lat, lon),
            )
            db.add(localidades[slug])
    db.flush()

    # Distritos y villas dentro de cada departamento.
    existentes = {(z.localidad_id, z.nombre) for z in db.scalars(select(Zona))}
    for _prov, _nombre, slug, _lat, _lon, _cant, _perfil, zonas in datos.LOCALIDADES:
        localidad = localidades[slug]
        for zona in zonas:
            if (localidad.id, zona) not in existentes:
                db.add(Zona(localidad_id=localidad.id, nombre=zona))
    db.flush()

    tipos = {t.codigo: t for t in db.scalars(select(TipoServicio))}
    for codigo, nombre, modo in datos.TIPOS_SERVICIO:
        if codigo not in tipos:
            tipos[codigo] = TipoServicio(
                codigo=codigo, nombre=nombre, modo_reserva=ModoReserva(modo)
            )
            db.add(tipos[codigo])
    db.flush()

    subtipos = {s.codigo for s in db.scalars(select(SubtipoServicio))}
    for tipo, codigo, nombre in datos.SUBTIPOS:
        if codigo not in subtipos:
            db.add(SubtipoServicio(tipo_id=tipos[tipo].id, codigo=codigo, nombre=nombre))

    # Las comodidades se agregan y se completan sus tipos; nunca se les quita uno
    # (alguien pudo haberlo asignado a mano).
    comodidades = {c.codigo: c for c in db.scalars(select(Comodidad))}
    for codigo, nombre, icono, de_tipos in datos.COMODIDADES:
        comodidad = comodidades.get(codigo)
        if comodidad is None:
            comodidad = Comodidad(codigo=codigo, nombre=nombre, icono=icono)
            db.add(comodidad)
        for tipo in de_tipos:
            if tipos[tipo] not in comodidad.tipos:
                comodidad.tipos.append(tipos[tipo])

    politicas = {p.codigo for p in db.scalars(select(PoliticaCancelacion))}
    for codigo, nombre, descripcion, tramos in datos.POLITICAS:
        if codigo not in politicas:
            db.add(
                PoliticaCancelacion(
                    codigo=codigo, nombre=nombre, descripcion=descripcion, tramos=tramos
                )
            )
    db.flush()


def configurar_comision(
    db: Session,
    porcentaje: Decimal = Decimal(10),
    quien_paga: QuienPaga = QuienPaga.PRESTADOR,
    porcentaje_viajero: Decimal = Decimal(0),
    iva_incluido: bool = False,
) -> ReglaComision:
    """Crea o actualiza la regla por defecto (docs/00 §7).

    Es el único lugar donde se decide cuánto cobra la plataforma y quién lo paga.
    `porcentaje=0` deja el marketplace sin comisión sin romper nada: la regla
    sigue existiendo, el desglose sigue nombrando el cargo y vale cero.
    """
    regla = db.scalar(select(ReglaComision).where(ReglaComision.es_default))
    if regla is None:
        regla = ReglaComision(nombre="Comisión general", es_default=True)
        db.add(regla)
    regla.descripcion = (
        "Regla por defecto: se aplica cuando ninguna regla más específica coincide. "
        "Cambiar `quien_paga` decide si el cargo lo absorbe el prestador, lo paga el "
        "viajero como cargo de servicio, o se reparte."
    )
    regla.activa = True
    regla.porcentaje = porcentaje
    regla.monto_fijo = Decimal(0)
    regla.quien_paga = quien_paga
    regla.porcentaje_viajero = porcentaje_viajero
    regla.iva_incluido = iva_incluido
    db.flush()
    return regla


def _fotos_por_categoria() -> dict[str, list[dict]]:
    if not FOTOS_JSON.exists():
        return {}
    catalogo = json.loads(FOTOS_JSON.read_text(encoding="utf-8"))
    agrupadas: dict[str, list[dict]] = {}
    for foto in catalogo["fotos"]:
        agrupadas.setdefault(foto["categoria"], []).append(foto)
    return agrupadas


def limpiar_demo(db: Session) -> int:
    """Borra toda la oferta de ejemplo. El catálogo real no se toca."""
    ids = list(db.scalars(select(Publicacion.id).where(Publicacion.es_demo)))
    if ids:
        unidades = list(db.scalars(select(Unidad.id).where(Unidad.publicacion_id.in_(ids))))
        if unidades:
            # El orden lo manda el grafo de claves foráneas, de la hoja a la raíz:
            # un bloqueo apunta al calendario que lo trajo y al ítem que lo retuvo,
            # así que los bloqueos se van antes que ambos.
            reservas = list(
                db.scalars(
                    select(ItemReserva.reserva_id).where(ItemReserva.unidad_id.in_(unidades))
                )
            )
            db.execute(
                delete(CalendarioExterno).where(CalendarioExterno.unidad_id.in_(unidades))
            )
            db.execute(delete(BloqueoFecha).where(BloqueoFecha.unidad_id.in_(unidades)))
            # Las ventas que entraron por fuera cuelgan del prestador, no de la
            # unidad: las que quedaron «por revisar» todavía no tienen unidad.
            db.execute(
                delete(ReservaExterna).where(
                    ReservaExterna.prestador_id.in_(
                        select(Prestador.id).where(Prestador.es_demo)
                    )
                )
            )
            if reservas:
                db.execute(delete(Resena).where(Resena.reserva_id.in_(reservas)))
                db.execute(delete(Pago).where(Pago.reserva_id.in_(reservas)))
                db.execute(
                    Notificacion.__table__.update()
                    .where(Notificacion.reserva_id.in_(reservas))
                    .values(reserva_id=None)
                )
                db.execute(delete(ItemReserva).where(ItemReserva.reserva_id.in_(reservas)))
                db.execute(delete(Reserva).where(Reserva.id.in_(reservas)))
            db.execute(delete(Tarifa).where(Tarifa.unidad_id.in_(unidades)))
            db.execute(delete(Unidad).where(Unidad.id.in_(unidades)))
        db.execute(delete(Foto).where(Foto.publicacion_id.in_(ids)))
        db.execute(
            Publicacion.__table__.delete().where(Publicacion.id.in_(ids))
        )
    # Las cuentas de ejemplo son dos familias: los anfitriones, que cuelgan de un
    # prestador `es_demo`, y los viajeros, que solo se reconocen por su correo.
    prestadores = list(db.scalars(select(Prestador.id).where(Prestador.es_demo)))
    cuentas = list(
        db.scalars(select(Usuario.id).where(Usuario.email.like(f"viajero%@{DOMINIO_DEMO}")))
    )
    if prestadores:
        cuentas += list(
            db.scalars(select(Prestador.usuario_id).where(Prestador.id.in_(prestadores)))
        )
    if cuentas:
        db.execute(delete(Favorito).where(Favorito.usuario_id.in_(cuentas)))
        # La notificación es un registro de lo que se mandó: se le suelta el
        # destinatario en vez de borrarla.
        db.execute(
            Notificacion.__table__.update()
            .where(Notificacion.usuario_id.in_(cuentas))
            .values(usuario_id=None)
        )
    if prestadores:
        db.execute(delete(Prestador).where(Prestador.id.in_(prestadores)))
    if cuentas:
        db.execute(delete(Usuario).where(Usuario.id.in_(cuentas)))
    db.flush()
    return len(ids)


def cargar_oferta(db: Session) -> dict[str, int]:
    """Oferta de ejemplo, determinista: la misma semilla produce siempre lo mismo."""
    az = random.Random(SEMILLA_ALEATORIA)
    fotos = _fotos_por_categoria()
    exteriores = fotos.get("cabana", []) + fotos.get("casa", []) + fotos.get("departamento", [])
    interiores = fotos.get("interior", []) or exteriores
    entornos = fotos.get("entorno", []) or exteriores
    piletas = fotos.get("pileta", [])

    localidades = {loc.slug: loc for loc in db.scalars(select(Localidad))}
    zonas_por_localidad: dict = {}
    for z in db.scalars(select(Zona)):
        zonas_por_localidad.setdefault(z.localidad_id, []).append(z)
    subtipos = {s.codigo: s for s in db.scalars(select(SubtipoServicio))}
    comodidades = list(db.scalars(select(Comodidad)))
    politicas = list(db.scalars(select(PoliticaCancelacion)))
    tipo_alojamiento = db.scalar(select(TipoServicio).where(TipoServicio.codigo == "alojamiento"))

    prestadores: list[Prestador] = []
    for i, razon in enumerate(datos.PRESTADORES):
        usuario = Usuario(
            email=f"prestador{i + 1}@{DOMINIO_DEMO}",
            nombre="Prestador",
            apellido=f"de ejemplo {i + 1}",
            hash_password=hashear_password(CLAVE_DEMO),
            email_verificado=True,
            es_prestador=True,
        )
        db.add(usuario)
        db.flush()
        prestador = Prestador(
            usuario_id=usuario.id,
            razon_social=razon,
            cuit=f"30-{50000000 + i * 1117:08d}-{i % 10}",
            condicion_iva="Responsable inscripto" if i % 3 else "Monotributo",
            categoria="nuevo" if i % 4 == 0 else None,
            fecha_alta=HOY - timedelta(days=az.randint(30, 900)),
            verificado=i % 3 != 0,
            mp_user_id=f"DEMO{100000 + i}",
            porcentaje_sena=az.choice([None, 30, 50]),
            es_demo=True,
        )
        db.add(prestador)
        prestadores.append(prestador)
    db.flush()

    nombres_usados: set[str] = set()
    total_publicaciones = total_unidades = total_bloqueos = 0
    indice_prestador = 0

    for _prov_slug, _nombre, slug, lat, lon, cantidad, perfil, _zonas in datos.LOCALIDADES:
        localidad = localidades[slug]
        zonas = zonas_por_localidad.get(localidad.id, [])
        piso, techo = datos.PRECIO_BASE[perfil]
        for _ in range(cantidad):
            prestador = prestadores[indice_prestador % len(prestadores)]
            indice_prestador += 1

            while True:
                titulo = f"{az.choice(datos.PREFIJOS)} {az.choice(datos.NOMBRES)}"
                if titulo not in nombres_usados:
                    nombres_usados.add(titulo)
                    break
            slug_pub = (
                titulo.lower()
                .replace(" ", "-")
                .replace("ñ", "n")
                .replace("á", "a")
                .replace("é", "e")
                .replace("í", "i")
                .replace("ó", "o")
                .replace("ú", "u")
                + f"-{slug}"
            )
            subtipo = subtipos[az.choice(["cabana", "cabana", "casa", "departamento", "hosteria"])]
            elegidas = az.sample(comodidades, az.randint(4, 8))
            codigos = {c.codigo for c in elegidas}
            tiene_pileta = "pileta" in codigos
            acepta_mascotas = "mascotas" in codigos

            publicacion = Publicacion(
                prestador_id=prestador.id,
                tipo_servicio_id=tipo_alojamiento.id,
                subtipo_servicio_id=subtipo.id,
                titulo=titulo,
                slug=slug_pub,
                descripcion=az.choice(datos.DESCRIPCIONES),
                reglas_casa=az.choice(datos.REGLAS_CASA),
                estado=EstadoPublicacion.APROBADA,
                localidad_id=localidad.id,
                zona_id=az.choice(zonas).id if zonas else None,
                direccion=f"Calle {az.randint(1, 40)} N° {az.randint(100, 2500)}",
                ubicacion=_punto(
                    lat + az.uniform(-0.05, 0.05), lon + az.uniform(-0.05, 0.05)
                ),
                confirmacion_inmediata=az.random() < 0.7,
                politica_cancelacion_id=az.choice(politicas).id,
                es_demo=True,
            )
            publicacion.comodidades = elegidas
            db.add(publicacion)
            db.flush()
            total_publicaciones += 1

            seleccion = (
                az.sample(exteriores, min(2, len(exteriores)))
                + az.sample(interiores, min(2, len(interiores)))
                + az.sample(entornos, min(1, len(entornos)))
                + (az.sample(piletas, 1) if tiene_pileta and piletas else [])
            )
            for orden, foto in enumerate(seleccion):
                db.add(
                    Foto(
                        publicacion_id=publicacion.id,
                        url=foto["url"],
                        orden=orden,
                        descripcion=f"Foto de referencia · {foto['autor']} ({foto['licencia']})",
                    )
                )

            for nombre_unidad, capacidad in az.sample(datos.UNIDADES, az.randint(1, 4)):
                base = _r(Decimal(az.randint(int(piso), int(techo))) / 1000) * 1000
                unidad = Unidad(
                    publicacion_id=publicacion.id,
                    nombre=nombre_unidad,
                    capacidad=capacidad,
                    capacidad_base=max(2, capacidad - az.choice([0, 1, 2])),
                    cargo_limpieza=_r(base * Decimal("0.12")),
                    cargo_persona_extra=_r(base * Decimal("0.10")),
                    cargo_mascota=(
                        _r(base * Decimal("0.08")) if acepta_mascotas else Decimal(0)
                    ),
                    descuento_semanal=Decimal(az.choice([0, 5, 10])),
                    descuento_mensual=Decimal(az.choice([0, 15, 25])),
                )
                db.add(unidad)
                db.flush()
                total_unidades += 1

                finde = {
                    "4": str(_r(base * Decimal("1.15"))),
                    "5": str(_r(base * Decimal("1.20"))),
                }
                db.add(
                    Tarifa(
                        unidad_id=unidad.id,
                        nombre="Tarifa base",
                        precio_noche=base,
                        precios_dia_semana=finde,
                        estadia_minima=az.choice([1, 1, 2, 2, 3]),
                        anticipacion_minima_dias=az.choice([0, 0, 0, 1]),
                        prioridad=0,
                    )
                )
                for nombre_t, desde, hasta, recargo in datos.TEMPORADAS[perfil]:
                    db.add(
                        Tarifa(
                            unidad_id=unidad.id,
                            nombre=nombre_t,
                            fecha_desde=date(*desde),
                            fecha_hasta=date(*hasta),
                            precio_noche=_r(base * recargo),
                            estadia_minima=az.choice([2, 3, 4]),
                            prioridad=10,
                        )
                    )

                # Fechas ya tomadas: sin esto la búsqueda no se puede probar de verdad.
                # El cursor avanza para no violar la restricción de exclusión, que es
                # justamente la que garantiza cero dobles reservas.
                cursor = HOY + timedelta(days=az.randint(3, 25))
                for _ in range(az.randint(0, 4)):
                    inicio = cursor
                    fin = inicio + timedelta(days=az.randint(2, 9))
                    db.add(
                        BloqueoFecha(
                            unidad_id=unidad.id,
                            rango=Range(inicio, fin, bounds="[)"),
                            origen=az.choice([OrigenBloqueo.MANUAL, OrigenBloqueo.ICAL]),
                            activo=True,
                            nota="Bloqueo de ejemplo",
                        )
                    )
                    total_bloqueos += 1
                    cursor = fin + timedelta(days=az.randint(5, 60))
                db.flush()

    return {
        "prestadores": len(prestadores),
        "publicaciones": total_publicaciones,
        "unidades": total_unidades,
        "bloqueos": total_bloqueos,
    }


#: Donde el prestador deja sus fotos, tal cual salen del teléfono. Ver su LEEME.
CARPETA_LOS_BUHOS = Path(__file__).resolve().parents[3] / "fotos" / "los-buhos"
EXTENSIONES_FOTO = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}


def fotos_de_los_buhos() -> list[Path]:
    """Las fotos que haya en la carpeta, en el orden de su nombre."""
    if not CARPETA_LOS_BUHOS.is_dir():
        return []
    return sorted(
        p for p in CARPETA_LOS_BUHOS.iterdir() if p.suffix.lower() in EXTENSIONES_FOTO
    )


def cargar_fotos_los_buhos(db: Session, publicacion: Publicacion) -> int:
    """Mete las fotos reales por el mismo camino que una subida desde la web.

    Importa: el procesador les borra el EXIF, que en una foto de teléfono trae la
    ubicación GPS exacta. Publicarlas crudas sería publicar la dirección.
    """
    from app.services import fotos as procesador

    archivos = fotos_de_los_buhos()
    if not archivos:
        return 0
    for orden, archivo in enumerate(archivos):
        tipo = mimetypes.guess_type(archivo.name)[0]
        try:
            guardada = procesador.guardar(publicacion.id, archivo.read_bytes(), tipo)
        except procesador.FotoInvalida:
            continue
        db.add(Foto(publicacion_id=publicacion.id, url=guardada.url, orden=orden))
    db.flush()
    return len(archivos)


def cargar_los_buhos(db: Session) -> Publicacion | None:
    """Carga la publicación real destacada (docs: `datos.LOS_BUHOS`).

    Los datos verificados son el nombre, el distrito y que tiene piletas y salón.
    Todo lo demás (unidades, precios, fotos) es provisorio y por eso la publicación
    queda marcada con `es_demo`: mientras falte el dato real, no puede presentarse
    como oferta verdadera. La lista de faltantes está en `datos.PENDIENTES_LOS_BUHOS`.
    """
    d = datos.LOS_BUHOS

    ya_esta = db.scalar(select(Publicacion).where(Publicacion.slug == d["slug"]))
    if ya_esta:
        return ya_esta

    localidad = db.scalar(select(Localidad).where(Localidad.slug == d["localidad"]))
    zona = db.scalar(
        select(Zona).where(Zona.localidad_id == localidad.id, Zona.nombre == d["zona"])
    )
    tipo = db.scalar(select(TipoServicio).where(TipoServicio.codigo == "alojamiento"))
    subtipo = db.scalar(select(SubtipoServicio).where(SubtipoServicio.codigo == d["subtipo"]))
    politica = db.scalar(
        select(PoliticaCancelacion).where(PoliticaCancelacion.codigo == "moderada")
    )
    comodidades = list(
        db.scalars(select(Comodidad).where(Comodidad.codigo.in_(d["comodidades"])))
    )

    usuario = Usuario(
        email=f"los-buhos@{DOMINIO_DEMO}",
        nombre="Los",
        apellido="Búhos",
        hash_password=hashear_password(CLAVE_DEMO),
        email_verificado=True,
        es_prestador=True,
    )
    db.add(usuario)
    db.flush()
    prestador = Prestador(
        usuario_id=usuario.id,
        razon_social="Los Búhos",
        condicion_iva="Monotributo",
        fecha_alta=HOY - timedelta(days=30),
        verificado=False,
        mp_user_id="DEMO-LOSBUHOS",
        es_demo=True,
    )
    db.add(prestador)
    db.flush()

    publicacion = Publicacion(
        prestador_id=prestador.id,
        tipo_servicio_id=tipo.id,
        subtipo_servicio_id=subtipo.id,
        titulo=d["titulo"],
        slug=d["slug"],
        descripcion=d["descripcion"],
        reglas_casa="Datos de la casa pendientes de confirmación del prestador.",
        estado=EstadoPublicacion.APROBADA,
        localidad_id=localidad.id,
        zona_id=zona.id if zona else None,
        ubicacion=_punto(d["lat"], d["lon"]),
        confirmacion_inmediata=d["confirmacion_inmediata"],
        politica_cancelacion_id=politica.id if politica else None,
        es_demo=True,
    )
    publicacion.comodidades = comodidades
    db.add(publicacion)
    db.flush()

    # Las fotos reales, si el prestador ya las dejó en `fotos/los-buhos/`. Nunca
    # fotos de banco: los alojamientos generados son ficticios y se pueden
    # ilustrar con cualquier cosa, pero Los Búhos existe, y ponerle la foto de
    # otra casa sería tergiversarlo. Sin fotos, la ficha lo dice.
    cargar_fotos_los_buhos(db, publicacion)

    # Las unidades reales, de `datos.LOS_BUHOS`. Los cargos van en cero porque el
    # prestador no dijo que cobre limpieza ni persona extra: inventarlos sería
    # cobrarle al viajero algo que nadie pidió.
    for u in d["unidades"]:
        unidad = Unidad(
            publicacion_id=publicacion.id,
            nombre=u["nombre"],
            capacidad=u["capacidad"],
            capacidad_base=u.get("capacidad_base", u["capacidad"]),
            cargo_limpieza=u.get("cargo_limpieza", Decimal(0)),
            cargo_persona_extra=u.get("cargo_persona_extra", Decimal(0)),
        )
        db.add(unidad)
        db.flush()
        db.add(
            Tarifa(
                unidad_id=unidad.id,
                nombre="Tarifa base",
                precio_noche=u["precio_noche"],
                estadia_minima=u.get("estadia_minima", 1),
            )
        )
    db.flush()
    return publicacion


def cargar_reservas(db: Session, cantidad: int = 45) -> dict[str, int]:
    """Reservas de ejemplo hechas con el motor real, no con filas a mano.

    Sin esto, media aplicación queda invisible: el panel del prestador, los
    cobros, la cola del operador y el verde del calendario general —que es lo que
    distingue una venta nuestra de una importada— no tienen nada que mostrar.

    Pasan por `cotizar → crear → registrar_pago`, así que la comisión queda con
    su snapshot y las fechas se retienen igual que en producción. Quedan las tres
    situaciones que el anfitrión ve de verdad: confirmada, esperando el pago y
    esperando su aprobación.
    """
    from app.services import reservas as motor
    from app.services.pagos.base import EstadoPago

    azar = random.Random(20260920)
    hoy = date.today()

    unidades = list(
        db.scalars(
            select(Unidad)
            .join(Publicacion)
            .where(Publicacion.es_demo, Publicacion.estado == EstadoPublicacion.APROBADA)
            .order_by(Unidad.id)
        )
    )
    if not unidades:
        return {"reservas": 0}

    viajeros = []
    for i in range(4):
        v = Usuario(
            email=f"viajero{i + 1}@{DOMINIO_DEMO}",
            nombre=f"Viajera {i + 1}",
            apellido="de ejemplo",
            hash_password=hashear_password(CLAVE_DEMO),
            email_verificado=True,
            acepto_terminos_en=datetime.now(UTC),
            version_terminos=get_settings().version_terminos,
        )
        db.add(v)
        viajeros.append(v)
    db.flush()

    hechas = {"confirmada": 0, "pendiente_pago": 0, "pendiente_aprobacion": 0}
    for i in range(cantidad):
        unidad = unidades[azar.randrange(len(unidades))]
        inicio = hoy + timedelta(days=azar.randint(3, 55))
        fin = inicio + timedelta(days=azar.randint(2, 5))
        # Cada intento va en su propio savepoint. Un `rollback()` pelado acá se
        # llevaría puesta la semilla entera, que todavía no está confirmada.
        punto = db.begin_nested()
        try:
            reserva = motor.crear(
                db,
                viajeros[i % len(viajeros)],
                unidad,
                inicio,
                fin,
                personas=min(unidad.capacidad, azar.randint(2, 4)),
                hoy=hoy,
            )
            # Dos de cada tres se pagan; el resto queda esperando, que también es
            # un estado real que el anfitrión tiene que poder ver.
            if azar.random() < 0.7:
                motor.registrar_pago(
                    db,
                    reserva,
                    id_externo=f"demo-{reserva.codigo}",
                    pasarela="simulada",
                    estado=EstadoPago.APROBADO,
                )
            db.flush()
            estado = reserva.estado.value
        except Exception:
            # Fechas ya tomadas o estadía mínima sin cumplir: es la base haciendo
            # su trabajo. Se descarta ese intento y se sigue con el siguiente.
            punto.rollback()
            continue
        punto.commit()
        hechas[estado] = hechas.get(estado, 0) + 1

    db.flush()
    return {"reservas": sum(hechas.values()), **hechas}


def resumen(db: Session) -> dict[str, int]:
    return {
        "provincias": db.scalar(select(func.count()).select_from(Provincia)) or 0,
        "localidades": db.scalar(select(func.count()).select_from(Localidad)) or 0,
        "publicaciones": db.scalar(select(func.count()).select_from(Publicacion)) or 0,
        "unidades": db.scalar(select(func.count()).select_from(Unidad)) or 0,
        "fotos": db.scalar(select(func.count()).select_from(Foto)) or 0,
        "bloqueos": db.scalar(select(func.count()).select_from(BloqueoFecha)) or 0,
    }
