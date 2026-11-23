"""Agenda por horas del propietario de un salón (docs/04, etapa 5)."""

from datetime import timedelta

import pytest

from app.core.security import crear_token
from app.models import Usuario
from tests.test_api_salones import DIA, _reservar, evento, viajero  # noqa: F401
from tests.test_salones import salon  # noqa: F401


@pytest.fixture
def anfitrion(db, evento):  # noqa: F811
    dueno = db.get(Usuario, evento["publicacion"].prestador.usuario_id)
    return {"Authorization": f"Bearer {crear_token(str(dueno.id))}"}


def _base(evento):  # noqa: F811
    return (
        f"/api/v1/mis-publicaciones/{evento['publicacion'].id}"
        f"/unidades/{evento['unidad'].id}"
    )


def _agenda(cliente, anfitrion, evento, desde=DIA):  # noqa: F811
    return cliente.get(
        f"{_base(evento)}/agenda-horaria", headers=anfitrion,
        params={"desde": desde.isoformat(), "dias": 3},
    )


def _bloquear(cliente, anfitrion, evento, desde="15:00", hasta="18:00", dia=DIA, nota=None):  # noqa: F811
    return cliente.post(
        f"{_base(evento)}/bloqueos-horarios", headers=anfitrion,
        json={"dia": dia.isoformat(), "hora_desde": desde, "hora_hasta": hasta, "nota": nota},
    )


def test_la_agenda_muestra_la_reserva_con_su_codigo(cliente, viajero, anfitrion, evento):  # noqa: F811
    codigo = _reservar(cliente, viajero, evento, franja_id=str(evento["noche"].id)).json()[
        "codigo"
    ]
    r = _agenda(cliente, anfitrion, evento)
    assert r.status_code == 200, r.text
    tramos = r.json()["tramos"]
    assert len(tramos) == 1
    t = tramos[0]
    assert t["reserva"] == codigo
    assert t["etiqueta"] == "Esperando el pago"  # todavía no pagó la seña
    assert t["editable"] is False
    assert r.json()["preparacion_minutos"] == 60


def test_bloquear_horas_a_mano_y_soltarlas(cliente, anfitrion, evento):  # noqa: F811
    r = _bloquear(cliente, anfitrion, evento, nota="Cumple vendido por WhatsApp")
    assert r.status_code == 201, r.text
    t = r.json()["tramos"][0]
    assert (t["etiqueta"], t["nota"], t["editable"]) == (
        "Bloqueado a mano", "Cumple vendido por WhatsApp", True,
    )
    r = cliente.delete(f"{_base(evento)}/bloqueos-horarios/{t['id']}", headers=anfitrion)
    assert r.status_code == 200
    assert r.json()["tramos"] == []


def test_lo_bloqueado_a_mano_no_se_puede_reservar(cliente, viajero, anfitrion, evento):  # noqa: F811
    assert _bloquear(cliente, anfitrion, evento, "20:00", "23:00").status_code == 201
    d = cliente.get(
        f"/api/v1/salones/unidades/{evento['unidad'].id}/disponibilidad",
        params={"dia": DIA.isoformat()},
    ).json()
    assert {f["nombre"]: f["libre"] for f in d["franjas"]}["Noche"] is False
    r = _reservar(cliente, viajero, evento, franja_id=str(evento["noche"].id))
    assert r.status_code == 409


def test_un_bloqueo_no_pisa_una_reserva(cliente, viajero, anfitrion, evento):  # noqa: F811
    _reservar(cliente, viajero, evento, franja_id=str(evento["manana"].id))  # 9 a 14 (+1 h)
    r = _bloquear(cliente, anfitrion, evento, "14:30", "16:00")  # cae en la preparación
    assert r.status_code == 409
    assert _bloquear(cliente, anfitrion, evento, "15:00", "16:00").status_code == 201


def test_un_bloqueo_puede_cruzar_la_medianoche(cliente, anfitrion, evento):  # noqa: F811
    r = _bloquear(cliente, anfitrion, evento, "22:00", "03:00")
    assert r.status_code == 201, r.text
    t = r.json()["tramos"][0]
    from datetime import datetime

    inicio, fin = datetime.fromisoformat(t["inicio"]), datetime.fromisoformat(t["fin"])
    assert fin - inicio == timedelta(hours=5)


def test_una_reserva_no_se_suelta_desde_la_agenda(cliente, viajero, anfitrion, evento):  # noqa: F811
    _reservar(cliente, viajero, evento, franja_id=str(evento["noche"].id))
    t = _agenda(cliente, anfitrion, evento).json()["tramos"][0]
    r = cliente.delete(f"{_base(evento)}/bloqueos-horarios/{t['id']}", headers=anfitrion)
    assert r.status_code == 409


def test_un_dia_pasado_no_se_bloquea(cliente, anfitrion, evento):  # noqa: F811
    from datetime import date

    r = _bloquear(cliente, anfitrion, evento, dia=date.today() - timedelta(days=1))
    assert r.status_code == 422


def test_la_agenda_de_otro_no_se_ve(cliente, db, evento):  # noqa: F811
    r = cliente.post(
        "/api/v1/auth/registro",
        json={"email": "otro@ejemplo.com.ar", "password": "unaclavelarga", "nombre": "O",
              "apellido": "T", "acepta_terminos": True},
    )
    otro = {"Authorization": f"Bearer {r.json()['token']}"}
    cliente.post("/api/v1/auth/prestador", headers=otro,
                 json={"razon_social": "Otro", "cuit": "20111111112", "condicion_iva": "Mono"})
    assert _agenda(cliente, otro, evento).status_code == 404
    assert _bloquear(cliente, otro, evento).status_code == 404


def test_cada_tipo_con_su_agenda(cliente, anfitrion, evento, oferta):  # noqa: F811
    # Un salón no tiene calendario por días...
    r = cliente.get(f"{_base(evento)}/calendario", headers=anfitrion)
    assert r.status_code == 409
    # ...ni una cabaña agenda por horas.
    cabana = f"/api/v1/mis-publicaciones/{oferta['cara'].id}/unidades/{oferta['u_cara'].id}"
    assert cliente.get(f"{cabana}/agenda-horaria", headers=anfitrion).status_code == 409
    # Y el calendario general (por días) no muestra los salones como siempre libres.
    general = cliente.get("/api/v1/mi-calendario", headers=anfitrion).json()
    assert str(evento["unidad"].id) not in {u["unidad_id"] for u in general["unidades"]}
    assert str(oferta["u_cara"].id) in {u["unidad_id"] for u in general["unidades"]}


def test_las_reservas_recibidas_se_listan(cliente, viajero, anfitrion, evento, oferta):  # noqa: F811
    """La lista fallaba siempre (SELECT DISTINCT + ORDER BY) y la pantalla lo tapaba."""
    from tests.test_api_reservas import reservar as reservar_noches

    cabana = reservar_noches(cliente, viajero, oferta).json()["codigo"]
    del_salon = _reservar(cliente, viajero, evento, franja_id=str(evento["noche"].id)).json()[
        "codigo"
    ]
    r = cliente.get("/api/v1/mis-reservas", headers=anfitrion)
    assert r.status_code == 200, r.text
    codigos = [x["codigo"] for x in r.json()]
    # Las dos, una vez cada una. (En el test las dos se crean en la misma
    # transacción, con la misma hora: el orden entre ellas no dice nada.)
    assert sorted(codigos) == sorted([del_salon, cabana])
    evento_item = next(x for x in r.json() if x["codigo"] == del_salon)["items"][0]
    assert evento_item["inicio_en"] is not None
