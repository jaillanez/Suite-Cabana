"""Alta, edición y aprobación de publicaciones (docs/01 §5 R2)."""

from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy import select

from app.core.config import get_settings
from app.models import (
    Comodidad,
    Foto,
    Localidad,
    PoliticaCancelacion,
    Prestador,
    Provincia,
    Publicacion,
    SubtipoServicio,
    TipoServicio,
    Usuario,
)
from app.models.enums import EstadoPublicacion, ModoReserva
from app.services import edicion


@pytest.fixture
def media(tmp_path, monkeypatch):
    """Las fotos de los tests no ensucian el directorio del proyecto."""
    get_settings.cache_clear()
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path / "media"))
    yield tmp_path / "media"
    get_settings.cache_clear()


@pytest.fixture
def catalogo(db):
    provincia = Provincia(nombre="San Juan", slug="san-juan")
    db.add(provincia)
    db.flush()
    localidad = Localidad(
        provincia_id=provincia.id,
        nombre="Rivadavia",
        slug="rivadavia",
        ubicacion="SRID=4326;POINT(-68.5833 -31.5333)",
    )
    tipo = TipoServicio(codigo="alojamiento", nombre="Alojamiento", modo_reserva=ModoReserva.NOCHES)
    db.add_all([localidad, tipo])
    db.flush()
    subtipo = SubtipoServicio(tipo_id=tipo.id, codigo="cabana", nombre="Cabaña")
    politica = PoliticaCancelacion(codigo="moderada", nombre="Moderada", tramos=[])
    wifi = Comodidad(codigo="wifi", nombre="WiFi", tipos=[tipo])
    db.add_all([subtipo, politica, wifi])
    db.flush()
    return {"localidad": localidad, "subtipo": subtipo, "politica": politica}


def _cuenta(cliente, db, email: str, *, operador=False, habilitado=False) -> str:
    r = cliente.post(
        "/api/v1/auth/registro",
        json={
            "email": email,
            "password": "unaclavelarga",
            "nombre": "N",
            "apellido": "A",
            "acepta_terminos": True,
        },
    )
    token = r.json()["token"]
    usuario = db.scalar(select(Usuario).where(Usuario.email == email))
    if operador:
        usuario.es_operador = True
        db.commit()
        return token

    cliente.post(
        "/api/v1/auth/prestador",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "razon_social": f"Prestador {email}",
            "cuit": f"27{abs(hash(email)) % 10**9:09d}",
            "condicion_iva": "Monotributo",
        },
    )
    if habilitado:
        prestador = db.scalar(select(Prestador).where(Prestador.usuario_id == usuario.id))
        prestador.mp_user_id = "MP-TEST"
        db.commit()
    return token


@pytest.fixture
def prestador(cliente, db):
    token = _cuenta(cliente, db, "pres@ejemplo.com.ar", habilitado=True)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def operador(cliente, db):
    token = _cuenta(cliente, db, "oper@ejemplo.com.ar", operador=True)
    return {"Authorization": f"Bearer {token}"}


def _imagen(ancho=2400, alto=1600, color=(120, 160, 90)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (ancho, alto), color).save(buffer, format="JPEG")
    return buffer.getvalue()


def _crear(cliente, prestador, catalogo) -> str:
    r = cliente.post(
        "/api/v1/mis-publicaciones",
        headers=prestador,
        json={
            "titulo": "Cabañas del Arroyo",
            "localidad_id": str(catalogo["localidad"].id),
            "subtipo_servicio_id": str(catalogo["subtipo"].id),
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _completar(cliente, prestador, catalogo, pid, media) -> None:
    cliente.patch(
        f"/api/v1/mis-publicaciones/{pid}",
        headers=prestador,
        json={
            "descripcion": (
                "Dos cabañas de adobe entre olivos, a diez minutos del centro de la ciudad."
            ),
            "reglas_casa": "Ingreso desde las 14.",
            "lat": -31.53,
            "lon": -68.58,
            "hora_ingreso": "14:00",
            "hora_salida": "10:00",
            "politica_cancelacion_id": str(catalogo["politica"].id),
            "comodidades": ["wifi"],
        },
    )
    for _ in range(5):
        cliente.post(
            f"/api/v1/mis-publicaciones/{pid}/fotos",
            headers=prestador,
            files={"archivo": ("foto.jpg", _imagen(), "image/jpeg")},
        )
    r = cliente.post(
        f"/api/v1/mis-publicaciones/{pid}/unidades",
        headers=prestador,
        json={"nombre": "Cabaña 1", "capacidad": 4, "capacidad_base": 2},
    )
    unidad = r.json()["unidades"][0]["id"]
    cliente.post(
        f"/api/v1/mis-publicaciones/{pid}/unidades/{unidad}/tarifas",
        headers=prestador,
        json={"nombre": "Base", "precio_noche": "52000"},
    )


# --- Alta y edición ---


def test_crear_borrador(cliente, db, prestador, catalogo):
    pid = _crear(cliente, prestador, catalogo)
    p = db.get(Publicacion, pid)
    assert p.estado is EstadoPublicacion.BORRADOR
    assert p.slug == "cabanas-del-arroyo-rivadavia"


def test_el_slug_no_se_repite(cliente, prestador, catalogo):
    _crear(cliente, prestador, catalogo)
    r = cliente.post(
        "/api/v1/mis-publicaciones",
        headers=prestador,
        json={"titulo": "Cabañas del Arroyo", "localidad_id": str(catalogo["localidad"].id)},
    )
    assert r.json()["slug"] == "cabanas-del-arroyo-rivadavia-2"


def test_un_borrador_no_aparece_en_la_busqueda_publica(cliente, prestador, catalogo):
    _crear(cliente, prestador, catalogo)
    r = cliente.get(
        "/api/v1/publicaciones/buscar",
        params={"localidad": "rivadavia", "desde": "2026-10-12", "hasta": "2026-10-15"},
    )
    assert r.json()["total"] == 0


def test_editar_guarda_la_ubicacion(cliente, prestador, catalogo):
    pid = _crear(cliente, prestador, catalogo)
    r = cliente.patch(
        f"/api/v1/mis-publicaciones/{pid}",
        headers=prestador,
        json={"lat": -31.53, "lon": -68.58, "direccion": "Calle 5 N° 200"},
    )
    assert r.status_code == 200
    assert round(r.json()["lat"], 2) == -31.53
    assert r.json()["direccion"] == "Calle 5 N° 200"


def test_la_publicacion_de_otro_prestador_no_se_ve_ni_se_edita(cliente, db, prestador, catalogo):
    pid = _crear(cliente, prestador, catalogo)
    otro = {"Authorization": f"Bearer {_cuenta(cliente, db, 'otro@ejemplo.com.ar')}"}
    assert cliente.get(f"/api/v1/mis-publicaciones/{pid}", headers=otro).status_code == 404
    assert (
        cliente.patch(
            f"/api/v1/mis-publicaciones/{pid}", headers=otro, json={"titulo": "Robada"}
        ).status_code
        == 404
    )


def test_sin_sesion_no_se_entra(cliente, catalogo):
    assert cliente.get("/api/v1/mis-publicaciones").status_code == 401


# --- Fotos ---


def test_la_foto_se_optimiza_al_subirla(cliente, db, prestador, catalogo, media):
    pid = _crear(cliente, prestador, catalogo)
    r = cliente.post(
        f"/api/v1/mis-publicaciones/{pid}/fotos",
        headers=prestador,
        files={"archivo": ("enorme.jpg", _imagen(3000, 2000), "image/jpeg")},
    )
    assert r.status_code == 201, r.text
    fotos = r.json()["fotos"]
    assert len(fotos) == 1
    assert fotos[0]["url"].endswith(".webp")  # convertida

    guardada = db.scalar(select(Foto).where(Foto.publicacion_id == pid))
    archivo = media / guardada.url.split("/media/")[1]
    with Image.open(archivo) as imagen:
        assert imagen.width == get_settings().foto_ancho_maximo  # achicada
        assert imagen.format == "WEBP"


def test_un_archivo_que_no_es_imagen_se_rechaza(cliente, prestador, catalogo, media):
    pid = _crear(cliente, prestador, catalogo)
    r = cliente.post(
        f"/api/v1/mis-publicaciones/{pid}/fotos",
        headers=prestador,
        files={"archivo": ("virus.jpg", b"esto no es una imagen", "image/jpeg")},
    )
    assert r.status_code == 422


def test_borrar_y_reordenar_fotos(cliente, prestador, catalogo, media):
    pid = _crear(cliente, prestador, catalogo)
    for _ in range(3):
        cliente.post(
            f"/api/v1/mis-publicaciones/{pid}/fotos",
            headers=prestador,
            files={"archivo": ("f.jpg", _imagen(), "image/jpeg")},
        )
    fotos = cliente.get(f"/api/v1/mis-publicaciones/{pid}", headers=prestador).json()["fotos"]
    assert [f["orden"] for f in fotos] == [0, 1, 2]

    invertidas = [f["id"] for f in reversed(fotos)]
    r = cliente.patch(
        f"/api/v1/mis-publicaciones/{pid}/fotos", headers=prestador, json={"fotos": invertidas}
    )
    assert [f["id"] for f in r.json()["fotos"]] == invertidas

    r = cliente.delete(f"/api/v1/mis-publicaciones/{pid}/fotos/{invertidas[0]}", headers=prestador)
    assert len(r.json()["fotos"]) == 2


# --- Unidades y tarifas ---


def test_no_se_puede_cobrar_extra_por_mas_gente_de_la_que_entra(cliente, prestador, catalogo):
    pid = _crear(cliente, prestador, catalogo)
    r = cliente.post(
        f"/api/v1/mis-publicaciones/{pid}/unidades",
        headers=prestador,
        json={"nombre": "Cabaña", "capacidad": 2, "capacidad_base": 4},
    )
    assert r.status_code == 422


def test_dos_temporadas_no_pueden_pisarse(cliente, prestador, catalogo):
    pid = _crear(cliente, prestador, catalogo)
    unidad = cliente.post(
        f"/api/v1/mis-publicaciones/{pid}/unidades",
        headers=prestador,
        json={"nombre": "Cabaña", "capacidad": 4},
    ).json()["unidades"][0]["id"]
    base = {"nombre": "Verano", "precio_noche": "80000"}
    primera = cliente.post(
        f"/api/v1/mis-publicaciones/{pid}/unidades/{unidad}/tarifas",
        headers=prestador,
        json={**base, "fecha_desde": "2026-12-15", "fecha_hasta": "2027-03-01"},
    )
    assert primera.status_code == 201
    segunda = cliente.post(
        f"/api/v1/mis-publicaciones/{pid}/unidades/{unidad}/tarifas",
        headers=prestador,
        json={**base, "nombre": "Enero", "fecha_desde": "2027-01-01", "fecha_hasta": "2027-01-31"},
    )
    assert segunda.status_code == 409


def test_la_tarifa_base_convive_con_las_de_temporada(cliente, prestador, catalogo):
    pid = _crear(cliente, prestador, catalogo)
    unidad = cliente.post(
        f"/api/v1/mis-publicaciones/{pid}/unidades",
        headers=prestador,
        json={"nombre": "Cabaña", "capacidad": 4},
    ).json()["unidades"][0]["id"]
    ruta = f"/api/v1/mis-publicaciones/{pid}/unidades/{unidad}/tarifas"
    assert cliente.post(ruta, headers=prestador,
                        json={"nombre": "Base", "precio_noche": "50000"}).status_code == 201
    assert cliente.post(
        ruta,
        headers=prestador,
        json={
            "nombre": "Verano",
            "precio_noche": "80000",
            "fecha_desde": "2026-12-15",
            "fecha_hasta": "2027-03-01",
        },
    ).status_code == 201


def test_el_minimo_de_noches_no_supera_al_maximo(cliente, prestador, catalogo):
    pid = _crear(cliente, prestador, catalogo)
    unidad = cliente.post(
        f"/api/v1/mis-publicaciones/{pid}/unidades",
        headers=prestador,
        json={"nombre": "Cabaña", "capacidad": 4},
    ).json()["unidades"][0]["id"]
    ruta = f"/api/v1/mis-publicaciones/{pid}/unidades/{unidad}/tarifas"
    tarifa = {"nombre": "Base", "precio_noche": "50000", "estadia_minima": 5}
    r = cliente.post(ruta, headers=prestador, json={**tarifa, "estadia_maxima": 3})
    assert r.status_code == 422
    assert cliente.post(ruta, headers=prestador, json={**tarifa, "estadia_maxima": 366}
                        ).status_code == 422
    r = cliente.post(ruta, headers=prestador, json={**tarifa, "estadia_maxima": 30})
    assert r.status_code == 201
    assert r.json()["unidades"][0]["tarifas"][0]["estadia_maxima"] == 30


# --- Estados ---


def test_lo_que_falta_se_dice_todo_junto(cliente, db, prestador, catalogo):
    pid = _crear(cliente, prestador, catalogo)
    r = cliente.post(f"/api/v1/mis-publicaciones/{pid}/enviar-a-revision", headers=prestador)
    assert r.status_code == 422
    faltantes = r.json()["detail"]["faltantes"]
    assert len(faltantes) >= 5
    assert any("descripción" in f.lower() for f in faltantes)
    assert any("fotos" in f.lower() for f in faltantes)
    assert any("unidad" in f.lower() for f in faltantes)


def test_circuito_completo_hasta_aparecer_en_la_busqueda(
    cliente, db, prestador, operador, catalogo, media
):
    pid = _crear(cliente, prestador, catalogo)
    _completar(cliente, prestador, catalogo, pid, media)

    enviada = cliente.post(f"/api/v1/mis-publicaciones/{pid}/enviar-a-revision", headers=prestador)
    assert enviada.status_code == 200, enviada.text
    assert enviada.json()["estado"] == "en_revision"

    cola = cliente.get("/api/v1/admin/publicaciones", headers=operador)
    assert [p["id"] for p in cola.json()] == [pid]

    aprobada = cliente.post(f"/api/v1/admin/publicaciones/{pid}/aprobar", headers=operador)
    assert aprobada.status_code == 200
    assert aprobada.json()["estado"] == "aprobada"

    # Recién ahora es visible para un viajero.
    busqueda = cliente.get(
        "/api/v1/publicaciones/buscar",
        params={"localidad": "rivadavia", "desde": "2026-10-12", "hasta": "2026-10-15",
                "personas": 2},
    )
    assert busqueda.json()["total"] == 1


def test_en_revision_no_se_puede_editar(cliente, prestador, catalogo, media):
    pid = _crear(cliente, prestador, catalogo)
    _completar(cliente, prestador, catalogo, pid, media)
    cliente.post(f"/api/v1/mis-publicaciones/{pid}/enviar-a-revision", headers=prestador)
    r = cliente.patch(
        f"/api/v1/mis-publicaciones/{pid}", headers=prestador, json={"titulo": "Otro nombre"}
    )
    assert r.status_code == 409


def test_el_rechazo_exige_motivo_y_vuelve_al_prestador(
    cliente, db, prestador, operador, catalogo, media
):
    pid = _crear(cliente, prestador, catalogo)
    _completar(cliente, prestador, catalogo, pid, media)
    cliente.post(f"/api/v1/mis-publicaciones/{pid}/enviar-a-revision", headers=prestador)

    sin_motivo = cliente.post(
        f"/api/v1/admin/publicaciones/{pid}/rechazar", headers=operador, json={"motivo": ""}
    )
    assert sin_motivo.status_code == 422

    r = cliente.post(
        f"/api/v1/admin/publicaciones/{pid}/rechazar",
        headers=operador,
        json={"motivo": "Las fotos no muestran el interior"},
    )
    assert r.status_code == 200
    ficha = cliente.get(f"/api/v1/mis-publicaciones/{pid}", headers=prestador).json()
    assert ficha["estado"] == "rechazada"
    assert ficha["motivo_rechazo"] == "Las fotos no muestran el interior"

    vuelta = cliente.post(f"/api/v1/mis-publicaciones/{pid}/volver-a-borrador", headers=prestador)
    assert vuelta.json()["estado"] == "borrador"


def test_pausar_la_saca_de_la_busqueda_y_reactivar_la_devuelve(
    cliente, prestador, operador, catalogo, media
):
    pid = _crear(cliente, prestador, catalogo)
    _completar(cliente, prestador, catalogo, pid, media)
    cliente.post(f"/api/v1/mis-publicaciones/{pid}/enviar-a-revision", headers=prestador)
    cliente.post(f"/api/v1/admin/publicaciones/{pid}/aprobar", headers=operador)

    def cuantas() -> int:
        return cliente.get(
            "/api/v1/publicaciones/buscar",
            params={"localidad": "rivadavia", "desde": "2026-10-12", "hasta": "2026-10-15"},
        ).json()["total"]

    assert cuantas() == 1
    cliente.post(f"/api/v1/mis-publicaciones/{pid}/pausar", headers=prestador)
    assert cuantas() == 0
    cliente.post(f"/api/v1/mis-publicaciones/{pid}/reactivar", headers=prestador)
    assert cuantas() == 1


def test_no_se_puede_aprobar_algo_que_no_esta_en_revision(cliente, prestador, operador, catalogo):
    pid = _crear(cliente, prestador, catalogo)
    r = cliente.post(f"/api/v1/admin/publicaciones/{pid}/aprobar", headers=operador)
    assert r.status_code == 422  # incompleta, ni siquiera llega a la transición


def test_un_prestador_no_puede_aprobar(cliente, prestador, catalogo):
    pid = _crear(cliente, prestador, catalogo)
    r = cliente.post(f"/api/v1/admin/publicaciones/{pid}/aprobar", headers=prestador)
    assert r.status_code == 403


def test_sin_cuenta_de_cobro_no_se_puede_enviar_a_revision(cliente, db, catalogo, media):
    token = _cuenta(cliente, db, "sinmp@ejemplo.com.ar", habilitado=False)
    cabecera = {"Authorization": f"Bearer {token}"}
    pid = _crear(cliente, cabecera, catalogo)
    _completar(cliente, cabecera, catalogo, pid, media)
    r = cliente.post(f"/api/v1/mis-publicaciones/{pid}/enviar-a-revision", headers=cabecera)
    assert r.status_code == 403
    assert "Mercado Pago" in r.json()["detail"]


def test_las_transiciones_invalidas_se_rechazan():
    from app.models import Publicacion as P

    p = P(estado=EstadoPublicacion.BORRADOR)
    with pytest.raises(edicion.TransicionInvalida):
        edicion.aprobar(p)
    with pytest.raises(edicion.TransicionInvalida):
        edicion.pausar(p)
