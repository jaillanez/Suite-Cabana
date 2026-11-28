"""Primeros pasos (mejora 3): la lista que lleva al prestador hasta su primera
publicación, con las mismas reglas que deciden si se puede mandar a revisión."""

from datetime import date, time
from decimal import Decimal

import pytest

from app.core.security import crear_token
from app.models import (
    CalendarioExterno,
    Foto,
    Prestador,
    Publicacion,
    Tarifa,
    Unidad,
    Usuario,
)
from app.models.enums import EstadoPublicacion
from app.services import edicion, primeros_pasos
from tests.test_salones import salon  # noqa: F401  (fixture)


@pytest.fixture
def nuevo(db):
    u = Usuario(email="nueva@ejemplo.com.ar", nombre="Virginia", apellido="B",
                email_verificado=True)
    db.add(u)
    db.flush()
    p = Prestador(usuario_id=u.id, razon_social="Los Búhos", cuit="27301234564",
                  condicion_iva="Monotributo", fecha_alta=date.today())
    db.add(p)
    db.flush()
    return p


def _pasos(db, prestador) -> dict[str, primeros_pasos.Paso]:
    return {x.codigo: x for x in primeros_pasos.calcular(db, prestador).pasos}


def _borrador(db, prestador, oferta, slug="cabanas-los-buhos") -> Publicacion:
    base = oferta["cara"]
    p = Publicacion(
        prestador_id=prestador.id, tipo_servicio_id=base.tipo_servicio_id,
        titulo="Cabañas Los Búhos", slug=slug, descripcion="",
        estado=EstadoPublicacion.BORRADOR, localidad_id=base.localidad_id,
    )
    db.add(p)
    db.flush()
    return p


def _completar(db, p, oferta):
    """Todo lo que pide `edicion.faltantes` para una cabaña."""
    p.descripcion = "Dos cabañas de madera entre álamos, a cinco minutos del centro."
    p.subtipo_servicio_id = oferta["cara"].subtipo_servicio_id
    p.ubicacion = oferta["cara"].ubicacion
    p.hora_ingreso, p.hora_salida = time(14), time(10)
    p.tramos_cancelacion = [{"dias_antes": 7, "porcentaje_reintegro": 100}]
    p.prestador.usuario.telefono = "+5492644123456"
    for i in range(5):
        db.add(Foto(publicacion_id=p.id, url=f"/media/x{i}.webp", orden=i))
    u = Unidad(publicacion_id=p.id, nombre="Loft", capacidad=4)
    db.add(u)
    db.flush()
    db.add(Tarifa(unidad_id=u.id, nombre="Base", precio_noche=Decimal(50000)))
    db.flush()
    return u


def test_sin_publicacion_el_paso_siguiente_es_crearla(db, nuevo):
    r = primeros_pasos.calcular(db, nuevo)
    assert [p.codigo for p in r.pasos] == [
        "datos_fiscales", "whatsapp", "mercado_pago", "publicacion",
        "datos", "ubicacion", "fotos", "unidades", "revision",
    ]
    assert (r.hechos, r.terminado) == (1, False)  # los datos fiscales, del alta
    assert r.pasos[3].disponible and r.pasos[3].accion == "Crear"
    # Lo que depende de la publicación espera, sin botón.
    assert not any(p.disponible for p in r.pasos[4:])


def test_la_barra_no_retrocede_al_crear_la_publicacion(db, nuevo, oferta):
    antes = primeros_pasos.calcular(db, nuevo)
    _borrador(db, nuevo, oferta)
    despues = primeros_pasos.calcular(db, nuevo)
    assert despues.total == antes.total
    assert despues.hechos == antes.hechos + 1


def test_un_borrador_dice_que_falta_en_cada_paso(db, nuevo, oferta):
    p = _borrador(db, nuevo, oferta)
    pasos = _pasos(db, nuevo)
    assert pasos["publicacion"].hecho
    assert not pasos["datos"].hecho and "descripción" in pasos["datos"].detalle
    assert not pasos["ubicacion"].hecho and pasos["ubicacion"].enlace.endswith("#ubicacion")
    assert "se necesitan 5 y hay 0" in pasos["fotos"].detalle
    assert pasos["unidades"].titulo == "Unidades y precios"
    assert pasos["calendarios"].opcional
    assert pasos["revision"].enlace == f"/mis-publicaciones/{p.id}"


def test_la_lista_dice_lo_mismo_que_el_boton_de_revision(db, nuevo, oferta):
    """Con todo hecho, no queda ningún faltante: la lista y "Mandar a revisión"
    usan las mismas reglas."""
    p = _borrador(db, nuevo, oferta)
    _completar(db, p, oferta)
    nuevo.mp_user_id = "4242"
    db.flush()
    pasos = _pasos(db, nuevo)
    obligatorios = [x for x in pasos.values() if not x.opcional and x.codigo != "revision"]
    assert all(x.hecho for x in obligatorios), [x.codigo for x in obligatorios if not x.hecho]
    assert edicion.faltantes(db, p) == []
    # Lo opcional no frena: sin calendarios conectados igual está todo.
    assert not pasos["calendarios"].hecho


def test_el_calendario_conectado_tilda_el_paso_opcional(db, nuevo, oferta):
    p = _borrador(db, nuevo, oferta)
    u = _completar(db, p, oferta)
    db.add(CalendarioExterno(unidad_id=u.id, nombre="Airbnb", url="https://a/x.ics"))
    db.flush()
    assert _pasos(db, nuevo)["calendarios"].hecho


def test_en_revision_y_rechazada(db, nuevo, oferta):
    p = _borrador(db, nuevo, oferta)
    p.estado = EstadoPublicacion.EN_REVISION
    revision = _pasos(db, nuevo)["revision"]
    assert revision.hecho and "revisando" in revision.detalle
    p.estado = EstadoPublicacion.RECHAZADA
    p.motivo_rechazo = "Las fotos son de otro lugar"
    revision = _pasos(db, nuevo)["revision"]
    assert not revision.hecho and "Las fotos son de otro lugar" in revision.detalle


def test_se_sigue_la_publicacion_mas_avanzada(db, nuevo, oferta):
    from datetime import UTC, datetime, timedelta

    vieja = _borrador(db, nuevo, oferta)
    vieja.estado = EstadoPublicacion.EN_REVISION
    vieja.creado_en = datetime.now(UTC) - timedelta(days=3)
    # Un borrador más nuevo no le gana a la que ya está en revisión.
    nueva = _borrador(db, nuevo, oferta, slug="otra")
    nueva.creado_en = datetime.now(UTC)
    db.flush()
    assert primeros_pasos.calcular(db, nuevo).publicacion_id == vieja.id


def test_con_una_publicacion_aprobada_esta_terminado(db, oferta):
    assert primeros_pasos.calcular(db, oferta["prestador"]).terminado


def test_un_salon_habla_de_espacios_y_no_de_calendarios(db, salon):  # noqa: F811
    prestador = salon["publicacion"].prestador
    salon["publicacion"].estado = EstadoPublicacion.BORRADOR
    # El fixture tiene cabañas aprobadas del mismo prestador: se pasan a borrador.
    for x in db.query(Publicacion).filter(Publicacion.prestador_id == prestador.id):
        if x.id != salon["publicacion"].id:
            x.estado = EstadoPublicacion.PAUSADA
    db.flush()
    r = primeros_pasos.calcular(db, prestador)
    pasos = {x.codigo: x for x in r.pasos}
    assert r.publicacion_id == salon["publicacion"].id
    assert pasos["unidades"].titulo == "Espacios y precios"
    assert "calendarios" not in pasos


def test_la_api_devuelve_los_pasos_con_el_avance(cliente, db, nuevo, oferta):
    _borrador(db, nuevo, oferta)
    db.commit()
    cabecera = {"Authorization": f"Bearer {crear_token(str(nuevo.usuario_id))}"}
    r = cliente.get("/api/v1/auth/prestador/primeros-pasos", headers=cabecera)
    assert r.status_code == 200, r.text
    j = r.json()
    assert (j["hechos"], j["total"], j["terminado"]) == (2, 9, False)
    assert j["pasos"][0] == {
        "codigo": "datos_fiscales", "titulo": "Tus datos de prestador",
        "detalle": "CUIT y condición frente al IVA, para las facturas.", "hecho": True,
        "enlace": "/cuenta#prestador", "accion": "Completar", "opcional": False, "disponible": True,
    }


def test_un_viajero_no_tiene_primeros_pasos(cliente, db):
    u = Usuario(email="viajero@ejemplo.com.ar", nombre="V", apellido="V", email_verificado=True)
    db.add(u)
    db.commit()
    r = cliente.get("/api/v1/auth/prestador/primeros-pasos",
                    headers={"Authorization": f"Bearer {crear_token(str(u.id))}"})
    assert r.status_code == 403
