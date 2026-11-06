"""Mejoras de UI/UX con respaldo en la API: pendientes del día, guía de primer uso e impresión de prueba."""
import uuid


def test_presupuestos_sin_respuesta(client, admin, make_user, make_ticket):
    h, _ = make_user()
    t = make_ticket(h)
    client.post(f"/budget/tickets/{t['id']}/presupuesto", headers=admin, json={
        "items": [{"descripcion": "Pantalla", "cantidad": 2, "costo_interno": 1, "precio_cliente": 1000}]})
    ids = lambda: [p["id"] for p in client.get("/tickets/presupuestos/pendientes", headers=admin).json()]
    assert t["id"] not in ids()                                   # borrador: todavía no se mandó
    client.patch(f"/budget/tickets/{t['id']}/presupuesto/estado", headers=admin, json={"estado": "enviado"})
    fila = next(p for p in client.get("/tickets/presupuestos/pendientes", headers=admin).json() if p["id"] == t["id"])
    assert fila["total"] == 2000 and fila["dias_esperando"] == 0
    client.patch(f"/budget/tickets/{t['id']}/presupuesto/estado", headers=h, json={"estado": "aprobado"})
    assert t["id"] not in ids()
    assert client.get("/tickets/presupuestos/pendientes", headers=h).status_code == 403


def test_guia_de_primer_uso(client, admin, make_user):
    g = client.get("/config/guia", headers=admin).json()
    pasos = {p["id"]: p for p in g["pasos"]}
    assert set(pasos) == {"taller", "email", "productos", "tecnico", "impresora"}
    make_user(rol="tecnico")
    client.post("/products/", headers=admin, json={"marca": "Lenovo", "modelo": f"T14-{uuid.uuid4().hex[:4]}",
                                                   "categoria": "Notebooks", "periodo_garantia_meses": 12})
    pasos = {p["id"]: p for p in client.get("/config/guia", headers=admin).json()["pasos"]}
    assert pasos["tecnico"]["hecho"] and pasos["productos"]["hecho"]
    # Ocultar y volver a mostrar; los ajustes internos no aparecen en el panel
    assert client.put("/config/guia", headers=admin, json={"oculta": True}).json() == {"oculta": True}
    assert client.get("/config/guia", headers=admin).json()["oculta"] is True
    client.put("/config/guia", headers=admin, json={"oculta": False})
    claves = [a["clave"] for a in client.get("/config/ajustes", headers=admin).json()]
    assert "guia_oculta" not in claves and "guia_impresion_probada" not in claves


def test_impresion_de_prueba_no_crea_nada(client, admin, make_user):
    h, _ = make_user()
    antes = len(client.get("/tickets/", headers=admin, params={"limit": 1000}).json())
    r = client.get("/tickets/impresion-prueba/etiqueta", headers=admin)
    assert r.status_code == 200 and "RMA-2026-PRUEBA1" in r.text
    assert client.get("/tickets/impresion-prueba/ticket_ingreso", headers=admin).status_code == 200
    assert client.get("/tickets/impresion-prueba/remito", headers=admin).status_code == 404
    assert client.get("/tickets/impresion-prueba/etiqueta", headers=h).status_code == 403
    assert len(client.get("/tickets/", headers=admin, params={"limit": 1000}).json()) == antes
    pasos = {p["id"]: p for p in client.get("/config/guia", headers=admin).json()["pasos"]}
    assert pasos["impresora"]["hecho"]
