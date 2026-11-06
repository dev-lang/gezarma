"""Presupuestos: el cliente ve el precio, nunca el costo interno ni la ganancia."""
import pytest


@pytest.fixture
def ticket_con_presupuesto(client, admin, make_user, make_ticket):
    a, _ = make_user()
    t = make_ticket(a)
    client.post(f"/budget/tickets/{t['id']}/presupuesto", headers=admin, json={
        "notas": "n", "items": [{"descripcion": "Pantalla", "cantidad": 1,
                                 "costo_interno": 80, "precio_cliente": 150}]})
    client.patch(f"/budget/tickets/{t['id']}/presupuesto/estado", headers=admin, json={"estado": "enviado"})
    return a, t["id"]


def test_cliente_no_recibe_costos(client, ticket_con_presupuesto):
    a, tid = ticket_con_presupuesto
    p = client.get(f"/budget/tickets/{tid}/presupuesto", headers=a).json()
    assert p["precio_total"] == 150
    assert p["costo_total"] is None and p["ganancia"] is None and p["versiones"] == []
    assert all(i["costo_interno"] is None and i["costo_total"] is None for i in p["items"])


def test_taller_si_ve_costos(client, admin, ticket_con_presupuesto):
    _, tid = ticket_con_presupuesto
    p = client.get(f"/budget/tickets/{tid}/presupuesto", headers=admin).json()
    assert p["costo_total"] == 80 and p["ganancia"] == 70


def test_plantillas_con_costos_solo_para_taller(client, make_user):
    cli, _ = make_user()
    tec, _ = make_user("tecnico")
    assert client.get("/budget/plantillas", headers=cli).status_code == 403
    assert client.get("/budget/plantillas", headers=tec).status_code == 200


def test_otro_cliente_no_aprueba_presupuesto_ajeno(client, make_user, ticket_con_presupuesto):
    _, tid = ticket_con_presupuesto
    b, _ = make_user()
    r = client.patch(f"/budget/tickets/{tid}/presupuesto/estado", headers=b, json={"estado": "aprobado"})
    assert r.status_code == 403


def test_cliente_solo_aprueba_o_rechaza(client, ticket_con_presupuesto):
    a, tid = ticket_con_presupuesto
    url = f"/budget/tickets/{tid}/presupuesto/estado"
    assert client.patch(url, headers=a, json={"estado": "borrador"}).status_code == 403
    r = client.patch(url, headers=a, json={"estado": "aprobado"})
    assert r.status_code == 200 and r.json()["ganancia"] is None
