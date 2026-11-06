"""Plantillas de presupuesto por producto."""
import uuid


def _producto(client, admin):
    r = client.post("/products/", headers=admin, json={"marca": "Marca", "modelo": f"M-{uuid.uuid4().hex[:5]}",
                                                        "categoria": "Notebooks"})
    assert r.status_code in (200, 201), r.text
    return r.json()


def _plantilla(client, admin, **kw):
    body = {"nombre": f"P {uuid.uuid4().hex[:6]}", "descripcion": "Cambio de pantalla", "costo_interno": 100,
            "precio_cliente": 250, **kw}
    return client.post("/budget/plantillas", headers=admin, json=body)


def test_plantilla_vinculada_a_un_producto(client, admin, make_user):
    prod = _producto(client, admin)
    r = _plantilla(client, admin, producto_id=prod["id"])
    assert r.status_code == 200 and r.json()["producto_id"] == prod["id"]
    assert r.json()["producto_nombre"] == f"Marca {prod['modelo']}"
    general = _plantilla(client, admin).json()
    assert general["producto_id"] is None and general["producto_nombre"] is None
    tec, _ = make_user(rol="tecnico")
    lista = {p["id"]: p for p in client.get("/budget/plantillas", headers=tec).json()}
    assert lista[r.json()["id"]]["producto_id"] == prod["id"]
    # Editar: pasar a general
    pid = r.json()["id"]
    body = {k: r.json()[k] for k in ("nombre", "descripcion", "costo_interno", "precio_cliente", "categoria", "activo", "orden")}
    assert client.patch(f"/budget/plantillas/{pid}", headers=admin, json={**body, "producto_id": None}).json()["producto_id"] is None


def test_producto_inexistente(client, admin):
    assert _plantilla(client, admin, producto_id=999999).status_code == 400


def test_al_borrar_el_producto_la_plantilla_queda_general(client, admin):
    prod = _producto(client, admin)
    p = _plantilla(client, admin, producto_id=prod["id"]).json()
    assert client.delete(f"/products/{prod['id']}", headers=admin).status_code in (200, 204)
    lista = {x["id"]: x for x in client.get("/budget/plantillas", headers=admin).json()}
    assert lista[p["id"]]["producto_id"] is None
