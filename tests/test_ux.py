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


def test_frontend_se_revalida_en_cada_carga(client):
    """Sin Cache-Control el navegador podía usar un script viejo con una pantalla nueva
    (botones que no hacían nada). Ahora se revalida (304 si no cambió)."""
    for ruta in ("/", "/js/recepcion.js", "/partials/mostrador.html", "/i18n/en.js"):
        r = client.get(ruta)
        assert r.status_code == 200 and r.headers.get("cache-control") == "no-cache", ruta
    r = client.get("/js/recepcion.js")
    assert client.get("/js/recepcion.js", headers={"If-None-Match": r.headers["etag"]}).status_code == 304


def test_lista_de_tickets_ordenada_y_con_total(client, admin, make_user, make_ticket):
    h, _ = make_user()
    for serie in ("SN-B", "SN-A", "SN-C"):
        make_ticket(h, serie=serie)
    r = client.get("/tickets/", headers=admin, params={"limit": 2, "orden": "rma_asc"})
    assert r.status_code == 200 and len(r.json()) == 2
    total = int(r.headers["x-total-count"])
    assert total >= 3
    rmas = [t["numero_rma"] for t in client.get("/tickets/", headers=admin, params={"limit": 1000, "orden": "rma_asc"}).json()]
    assert rmas == sorted(rmas)
    for orden in ("cliente_desc", "tecnico_asc", "dias_desc", "prioridad_desc", "estado_asc", "producto_asc", "fecha_asc"):
        assert client.get("/tickets/", headers=admin, params={"orden": orden}).status_code == 200, orden
    assert client.get("/tickets/", headers=admin, params={"orden": "password_asc"}).status_code == 422
    # El cliente solo cuenta los suyos
    assert client.get("/tickets/", headers=h).headers["x-total-count"] == "3"
    por = client.get("/tickets/stats/resumen", headers=h).json()["por_estado"]
    assert sum(por.values()) == 3


def test_marca_del_taller_y_logo(client, admin, make_user):
    import io
    from PIL import Image
    m = client.get("/config/marca").json()                       # público: lo usa la pantalla de ingreso
    assert m["nombre"] and "registro_publico" in m
    buf = io.BytesIO(); Image.new("RGB", (900, 300), (200, 0, 0)).save(buf, "JPEG")
    h, _ = make_user()
    assert client.put("/config/logo", headers=h, files={"archivo": ("l.jpg", buf.getvalue(), "image/jpeg")}).status_code == 403
    r = client.put("/config/logo", headers=admin, files={"archivo": ("l.jpg", buf.getvalue(), "image/jpeg")})
    assert r.status_code == 200, r.text
    logo = client.get("/config/logo")
    assert logo.status_code == 200 and logo.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(logo.content)).size == (512, 171)          # achicado a 512 px
    assert client.get("/config/marca").json()["logo"]
    # Un archivo que no es imagen (aunque diga .png) no se acepta
    r = client.put("/config/logo", headers=admin, files={"archivo": ("x.png", b"<svg onload=alert(1)>", "image/png")})
    assert r.status_code == 400
    assert client.delete("/config/logo", headers=admin).status_code == 204
    assert client.get("/config/logo").status_code == 404 and client.get("/config/marca").json()["logo"] is None
    assert client.get("/favicon.svg").headers["content-type"].startswith("image/svg")


def test_registro_publico_desactivable(client, admin):
    import uuid
    datos = lambda: {"username": f"cli_{uuid.uuid4().hex[:6]}", "nombre": "Cliente", "email": f"{uuid.uuid4().hex[:6]}@t.com",
                     "password": "secret1", "rol": "cliente"}
    client.put("/config/ajustes", headers=admin, json={"registro_publico": False})
    try:
        r = client.post("/register", json=datos())
        assert r.status_code == 403 and "desactivado" in r.json()["detail"]
        assert client.get("/config/marca").json()["registro_publico"] is False
        assert client.post("/register", headers=admin, json=datos()).status_code == 200   # el taller sí crea cuentas
    finally:
        client.put("/config/ajustes", headers=admin, json={"registro_publico": True})
