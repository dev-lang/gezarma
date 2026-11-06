"""Stock mínimo, alertas y descuento de repuestos al aprobar un presupuesto."""
import uuid

import pytest


@pytest.fixture
def make_part(client, admin):
    def _make(stock=5, minimo=0, precio=40.0):
        codigo = f"R-{uuid.uuid4().hex[:6]}"
        r = client.post("/parts/", headers=admin, json={
            "nombre": f"Repuesto {codigo}", "codigo": codigo, "stock": stock, "proveedor": "Prov",
            "precio": precio, "stock_minimo": minimo})
        assert r.status_code == 201, r.text
        return r.json()
    return _make


def _stock(client, admin, part_id):
    return next(p for p in client.get("/parts/", headers=admin).json() if p["id"] == part_id)["stock"]


def _notifs_admin(client, admin, texto):
    return [n for n in client.get("/notifications/", headers=admin).json() if texto in n["titulo"]]


def _presupuesto(client, tec, tid, items):
    r = client.post(f"/budget/tickets/{tid}/presupuesto", headers=tec, json={"notas": "", "items": items})
    assert r.status_code == 200, r.text
    assert client.patch(f"/budget/tickets/{tid}/presupuesto/estado", headers=tec,
                        json={"estado": "enviado"}).status_code == 200
    return r.json()


def test_stock_minimo_y_alertas(client, admin, make_part, make_user):
    p = make_part(stock=10, minimo=3)
    assert p["stock_minimo"] == 3
    assert all(a["id"] != p["id"] for a in client.get("/stock/alertas", headers=admin).json())
    p["stock"] = 2
    assert client.put(f"/parts/{p['id']}", headers=admin, json=p).status_code == 200
    assert any(a["id"] == p["id"] for a in client.get("/stock/alertas", headers=admin).json())
    assert _notifs_admin(client, admin, p["nombre"])           # aviso al cruzar el mínimo
    cli, _ = make_user()
    assert client.get("/stock/alertas", headers=cli).status_code == 403


def test_aviso_solo_al_cruzar_el_minimo(client, admin, make_part, make_user, make_ticket):
    p = make_part(stock=5, minimo=3)
    tec, _ = make_user("tecnico")
    cli, _ = make_user()
    t = make_ticket(cli)
    for _ in range(3):   # 5 → 4 → 3 (cruza) → 2 (ya estaba bajo)
        assert client.post(f"/tickets/{t['id']}/parts", headers=tec,
                           json={"part_id": p["id"], "cantidad": 1}).status_code == 200
    assert len(_notifs_admin(client, admin, p["nombre"])) == 1


def test_presupuesto_con_repuesto_descuenta_al_aprobar(client, admin, make_part, make_user, make_ticket):
    p = make_part(stock=5)
    tec, _ = make_user("tecnico")
    cli, _ = make_user()
    t = make_ticket(cli)
    pres = _presupuesto(client, tec, t["id"], [
        {"repuesto_id": p["id"], "cantidad": 2, "costo_interno": 40, "precio_cliente": 90},
        {"descripcion": "Mano de obra", "cantidad": 1, "costo_interno": 0, "precio_cliente": 50}])
    item = pres["items"][0]
    assert item["descripcion"] == p["nombre"]                    # toma el nombre del repuesto
    assert item["stock_disponible"] == 5 and item["repuesto_codigo"] == p["codigo"]
    assert _stock(client, admin, p["id"]) == 5                   # enviar no descuenta

    vista_cliente = client.get(f"/budget/tickets/{t['id']}/presupuesto", headers=cli).json()["items"][0]
    assert vista_cliente["stock_disponible"] is None and vista_cliente["repuesto_codigo"] is None

    assert client.patch(f"/budget/tickets/{t['id']}/presupuesto/estado", headers=cli,
                        json={"estado": "aprobado"}).status_code == 200
    assert _stock(client, admin, p["id"]) == 3
    usados = client.get(f"/tickets/{t['id']}", headers=tec).json()["repuestos_usados"]
    assert [(u["id"], u["cantidad"]) for u in usados] == [(p["id"], 2)]
    movs = client.get(f"/stock/history?repuesto_id={p['id']}", headers=tec).json()
    assert movs[0]["cantidad"] == -2 and "Presupuesto aprobado" in movs[0]["nota"]


def test_aprobar_sin_stock_suficiente_deja_negativo_y_avisa(client, admin, make_part, make_user, make_ticket):
    p = make_part(stock=1)
    tec, _ = make_user("tecnico")
    cli, _ = make_user()
    t = make_ticket(cli)
    _presupuesto(client, tec, t["id"], [{"repuesto_id": p["id"], "cantidad": 3, "precio_cliente": 10}])
    r = client.patch(f"/budget/tickets/{t['id']}/presupuesto/estado", headers=cli, json={"estado": "aprobado"})
    assert r.status_code == 200                                  # al cliente no se le rechaza
    assert _stock(client, admin, p["id"]) == -2
    assert _notifs_admin(client, admin, f"Faltan repuestos: {p['nombre']}")


def test_validaciones_de_items(client, make_part, make_user, make_ticket):
    p = make_part()
    tec, _ = make_user("tecnico")
    cli, _ = make_user()
    t = make_ticket(cli)
    url = f"/budget/tickets/{t['id']}/presupuesto"
    assert client.post(url, headers=tec, json={"items": [{"repuesto_id": p["id"], "cantidad": 1.5}]}).status_code == 400
    assert client.post(url, headers=tec, json={"items": [{"repuesto_id": 999999, "cantidad": 1}]}).status_code == 400
    assert client.post(url, headers=tec, json={"items": [{"descripcion": "  ", "cantidad": 1}]}).status_code == 400


def test_agregado_manual_sin_stock_sigue_rechazandose(client, make_part, make_user, make_ticket):
    p = make_part(stock=1)
    tec, _ = make_user("tecnico")
    cli, _ = make_user()
    t = make_ticket(cli)
    r = client.post(f"/tickets/{t['id']}/parts", headers=tec, json={"part_id": p["id"], "cantidad": 2})
    assert r.status_code == 400 and "insuficiente" in r.json()["detail"]
