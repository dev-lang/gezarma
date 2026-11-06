"""Encuesta de satisfacción: al cerrar, desde la cuenta o el seguimiento público."""
import pytest

from backend.app.routers import public
from backend.app.services import email
from test_email import cliente, smtp  # noqa: F401  (fixtures)


@pytest.fixture(autouse=True)
def _limites():
    public.reiniciar_limites()
    yield
    public.reiniciar_limites()


def _cerrar(client, admin, t):
    assert client.put(f"/tickets/{t['id']}/status", headers=admin, json={"estado": "Cerrado"}).status_code == 200


def test_cliente_califica_desde_su_cuenta(client, admin, make_user, make_ticket):
    h, _ = make_user()
    t = make_ticket(h)
    r = client.post(f"/tickets/{t['id']}/encuesta", headers=h, json={"puntaje": 5})
    assert r.status_code == 400 and "cuando se cierra" in r.json()["detail"]   # todavía abierto
    _cerrar(client, admin, t)
    r = client.post(f"/tickets/{t['id']}/encuesta", headers=h, json={"puntaje": 4, "comentario": "Rápidos y claros"})
    assert r.status_code == 200 and r.json()["encuesta"]["puntaje"] == 4
    assert client.post(f"/tickets/{t['id']}/encuesta", headers=h, json={"puntaje": 1}).status_code == 409   # una sola vez
    # El taller la ve en el ticket
    assert client.get(f"/tickets/{t['id']}", headers=admin).json()["encuesta"]["comentario"] == "Rápidos y claros"


@pytest.mark.parametrize("puntaje", [0, 6, -1])
def test_puntaje_fuera_de_rango(client, admin, make_user, make_ticket, puntaje):
    h, _ = make_user()
    t = make_ticket(h)
    _cerrar(client, admin, t)
    assert client.post(f"/tickets/{t['id']}/encuesta", headers=h, json={"puntaje": puntaje}).status_code == 400


def test_solo_el_cliente_del_ticket(client, admin, make_user, make_ticket):
    h, _ = make_user()
    otro, _ = make_user()
    t = make_ticket(h)
    _cerrar(client, admin, t)
    assert client.post(f"/tickets/{t['id']}/encuesta", headers=otro, json={"puntaje": 1}).status_code == 403
    assert client.post(f"/tickets/{t['id']}/encuesta", headers=admin, json={"puntaje": 5}).status_code == 403


def test_desde_el_seguimiento_publico(client, admin, make_user, make_ticket):
    h, _ = make_user()
    t = make_ticket(h, serie="ENC-PUB")
    q = {"rma": t["numero_rma"], "serie": "ENC-PUB"}
    assert client.get("/public/seguimiento", params=q).json()["encuesta"] is None    # abierto: no hay encuesta
    _cerrar(client, admin, t)
    assert client.get("/public/seguimiento", params=q).json()["encuesta"] == {"respondida": False, "puntaje": None}
    assert client.post("/public/encuesta", json={**q, "serie": "OTRA", "puntaje": 5}).status_code == 404
    assert client.post("/public/encuesta", json={**q, "puntaje": 3, "comentario": "Tardó un poco"}).status_code == 200
    assert client.get("/public/seguimiento", params=q).json()["encuesta"] == {"respondida": True, "puntaje": 3}
    assert client.post("/public/encuesta", json={**q, "puntaje": 5}).status_code == 409


def test_resumen_para_el_taller(client, admin, make_user, make_ticket):
    antes = client.get("/encuestas/resumen", headers=admin).json()
    for p, com in ((5, "Excelente atención"), (2, "")):
        h, _ = make_user()
        t = make_ticket(h)
        _cerrar(client, admin, t)
        client.post(f"/tickets/{t['id']}/encuesta", headers=h, json={"puntaje": p, "comentario": com})
    r = client.get("/encuestas/resumen", headers=admin).json()
    assert r["cantidad"] == antes["cantidad"] + 2
    assert r["distribucion"]["5"] == antes["distribucion"]["5"] + 1
    assert r["comentarios"][0]["comentario"] == "Excelente atención"
    assert 1 <= r["promedio"] <= 5 and r["tasa_respuesta"] <= 1
    h, _ = make_user()
    assert client.get("/encuestas/resumen", headers=h).status_code == 403


def test_mail_al_cerrar_con_link_a_la_encuesta(client, admin, smtp, cliente, make_ticket):  # noqa: F811
    h, mail = cliente
    t = make_ticket(h, serie="ENC-MAIL")
    _cerrar(client, admin, t)
    email.esperar_envios()
    m = smtp.para(mail)[-1]
    assert "cómo te fue" in m["Subject"]
    assert "/seguimiento?" in m.get_body(("plain",)).get_content() and "#encuesta" in m.get_body(("plain",)).get_content()


def test_desactivada(client, admin, make_user, make_ticket):
    h, _ = make_user()
    t = make_ticket(h)
    _cerrar(client, admin, t)
    client.put("/config/ajustes", headers=admin, json={"encuesta_activa": False})
    try:
        assert client.post(f"/tickets/{t['id']}/encuesta", headers=h, json={"puntaje": 5}).status_code == 400
    finally:
        client.put("/config/ajustes", headers=admin, json={"encuesta_activa": True})
