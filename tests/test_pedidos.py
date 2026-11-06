"""Pedidos de repuestos a proveedores: sugeridos, envío, recepción parcial y total."""
import io
import uuid

import pytest
from pypdf import PdfReader

from backend.app.services import email
from test_email import smtp  # noqa: F401  (fixture)


def _repuesto(client, admin, proveedor, stock, minimo, precio=1000):
    cod = f"R-{uuid.uuid4().hex[:6]}"
    r = client.post("/parts/", headers=admin, json={"nombre": f"Repuesto {cod}", "codigo": cod, "stock": stock,
                                                    "proveedor": proveedor, "precio": precio, "stock_minimo": minimo})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def proveedor():
    return f"Proveedor {uuid.uuid4().hex[:5]}"


def _grupo(client, admin, proveedor):
    return next((g for g in client.get("/pedidos/sugeridos", headers=admin).json() if g["proveedor"] == proveedor), None)


def test_sugeridos_llevan_al_doble_del_minimo(client, admin, proveedor):
    a = _repuesto(client, admin, proveedor, stock=1, minimo=5)
    _repuesto(client, admin, proveedor, stock=20, minimo=5)          # con stock: no se sugiere
    b = _repuesto(client, admin, proveedor, stock=-2, minimo=0)      # negativo sin mínimo: reponer lo que falta
    g = _grupo(client, admin, proveedor)
    cant = {i["repuesto_id"]: i["cantidad"] for i in g["items"]}
    assert cant == {a["id"]: 9, b["id"]: 3}


def test_flujo_completo_con_recepcion_parcial(client, admin, proveedor):
    a = _repuesto(client, admin, proveedor, stock=1, minimo=5)
    p = client.post("/pedidos/desde-sugeridos", headers=admin, json={"proveedores": [proveedor]}).json()[0]
    assert p["estado"] == "borrador" and p["items"][0]["cantidad"] == 9 and p["costo_estimado"] == 9000
    assert _grupo(client, admin, proveedor) is None                  # ya está pedido: no se vuelve a sugerir
    # Se puede editar en borrador
    p = client.put(f"/pedidos/{p['id']}", headers=admin, json={"proveedor": proveedor, "notas": "Urgente",
                   "items": [{"repuesto_id": a["id"], "cantidad": 10}]}).json()
    assert p["unidades"] == 10
    p = client.post(f"/pedidos/{p['id']}/enviar", headers=admin, json={}).json()
    assert p["estado"] == "enviado" and p["fecha_envio"]
    assert client.put(f"/pedidos/{p['id']}", headers=admin, json={"proveedor": proveedor, "items": []}).status_code == 400
    item = p["items"][0]["id"]
    p = client.post(f"/pedidos/{p['id']}/recibir", headers=admin, json={"items": [{"item_id": item, "cantidad": 4}]}).json()
    assert p["estado"] == "parcial" and p["items"][0]["pendiente"] == 6
    assert next(x for x in client.get("/parts/", headers=admin).json() if x["id"] == a["id"])["stock"] == 5
    r = client.post(f"/pedidos/{p['id']}/recibir", headers=admin, json={"items": [{"item_id": item, "cantidad": 7}]})
    assert r.status_code == 400 and "hasta 6" in r.json()["detail"]
    p = client.post(f"/pedidos/{p['id']}/recibir", headers=admin, json={"items": [{"item_id": item, "cantidad": 6}]}).json()
    assert p["estado"] == "recibido" and p["fecha_recepcion"]
    stock = next(x for x in client.get("/parts/", headers=admin).json() if x["id"] == a["id"])["stock"]
    assert stock == 11
    movs = [m for m in client.get("/stock/history", headers=admin, params={"repuesto_id": a["id"]}).json()]
    assert sum(1 for m in movs if f"Pedido N° {p['id']}" in (m.get("nota") or "")) == 2


def test_validaciones(client, admin, proveedor):
    a = _repuesto(client, admin, proveedor, stock=1, minimo=5)
    assert client.post("/pedidos/", headers=admin, json={"proveedor": " ", "items": [{"repuesto_id": a["id"], "cantidad": 1}]}).status_code == 400
    assert client.post("/pedidos/", headers=admin, json={"proveedor": proveedor, "items": []}).status_code == 400
    assert client.post("/pedidos/", headers=admin, json={"proveedor": proveedor, "items": [{"repuesto_id": a["id"], "cantidad": 0}]}).status_code == 400
    dup = [{"repuesto_id": a["id"], "cantidad": 1}] * 2
    assert client.post("/pedidos/", headers=admin, json={"proveedor": proveedor, "items": dup}).status_code == 400
    p = client.post("/pedidos/", headers=admin, json={"proveedor": proveedor, "items": [{"repuesto_id": a["id"], "cantidad": 2}]}).json()
    assert client.post(f"/pedidos/{p['id']}/recibir", headers=admin, json={"items": [{"item_id": p["items"][0]["id"], "cantidad": 1}]}).status_code == 400
    assert client.post(f"/pedidos/{p['id']}/cancelar", headers=admin).json()["estado"] == "cancelado"
    assert client.post(f"/pedidos/{p['id']}/cancelar", headers=admin).status_code == 400


def test_pdf_csv_y_mail_al_proveedor(client, admin, proveedor, smtp):  # noqa: F811
    a = _repuesto(client, admin, proveedor, stock=0, minimo=3)
    p = client.post("/pedidos/", headers=admin, json={"proveedor": proveedor, "notas": "Entregar por la mañana",
                    "items": [{"repuesto_id": a["id"], "cantidad": 6}]}).json()
    texto = PdfReader(io.BytesIO(client.get(f"/pedidos/{p['id']}/pdf?formato=pdf", headers=admin).content)).pages[0].extract_text()
    assert proveedor in texto and a["codigo"] in texto and f"Pedido N° {p['id']:05d}" in texto
    csv = client.get(f"/pedidos/{p['id']}/csv", headers=admin).content.decode("utf-8-sig")
    assert csv.splitlines() == ["Código;Repuesto;Cantidad", f"{a['codigo']};{a['nombre']};6"]
    p = client.post(f"/pedidos/{p['id']}/enviar", headers=admin, json={"email": "ventas@proveedor.com"}).json()
    assert p["estado"] == "enviado"
    m = smtp.para("ventas@proveedor.com")[-1]
    assert "Pedido de repuestos" in m["Subject"]
    assert sorted(x.get_filename() for x in m.iter_attachments()) == [f"pedido-{p['id']:05d}.csv", f"pedido-{p['id']:05d}.pdf"]


def test_si_el_mail_falla_no_se_marca_enviado(client, admin, proveedor):
    a = _repuesto(client, admin, proveedor, stock=0, minimo=3)
    p = client.post("/pedidos/", headers=admin, json={"proveedor": proveedor, "items": [{"repuesto_id": a["id"], "cantidad": 1}]}).json()
    r = client.post(f"/pedidos/{p['id']}/enviar", headers=admin, json={"email": "x@proveedor.com"})
    assert r.status_code == 400 and "desactivado" in r.json()["detail"]       # email apagado en Ajustes
    assert client.get(f"/pedidos/{p['id']}", headers=admin).json()["estado"] == "borrador"


def test_solo_admin(client, make_user):
    h, _ = make_user(rol="tecnico")
    assert client.get("/pedidos/", headers=h).status_code == 403
    assert client.get("/pedidos/sugeridos", headers=h).status_code == 403
