"""Ingreso en mostrador: clientes sin clave, checklist, fotos de ingreso, firmas y
búsqueda exacta por N° de RMA (lector de código de barras)."""
import base64
import io
import uuid

import pytest
from PIL import Image, ImageDraw
from pypdf import PdfReader


def firma_png(vacia=False, tamano=(500, 180)) -> str:
    img = Image.new("RGBA", tamano, (0, 0, 0, 0))   # como un canvas: fondo transparente
    if not vacia:
        d = ImageDraw.Draw(img)
        d.line([(30, 120), (90, 40), (150, 140), (230, 50), (320, 130), (450, 70)], fill=(20, 20, 20, 255), width=5)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


EQUIPO = {"producto": "Notebook Mostrador 14", "numero_serie": "MOS-0001", "fecha_compra": "2026-01-10T00:00:00",
          "descripcion": "No carga la batería"}
CHECKLIST = {"accesorios": ["Cargador", "Funda"], "accesorios_otros": "Mouse inalámbrico",
             "estado_fisico": "Rayón en la tapa", "enciende": True, "tiene_bloqueo": True}


def _nuevo(**kw):
    return {"nombre": "Lucía Mostrador", "telefono": f"11 {uuid.uuid4().int % 10**8:08d}", "email": "", **kw}


@pytest.fixture
def tecnico(make_user):
    h, _ = make_user(rol="tecnico")
    return h


def test_ingreso_cliente_nuevo_queda_a_su_nombre_y_sin_clave(client, tecnico, admin):
    r = client.post("/mostrador/ingreso", headers=tecnico, json={
        "cliente_nuevo": _nuevo(), "ticket": EQUIPO, "checklist": CHECKLIST, "firma": {"imagen": firma_png(),
                                                                                   "aclaracion": "Lucía M."}})
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["usuario_nombre"] == "Lucía Mostrador"
    assert t["numero_rma"].split("-")[2].startswith("CL")       # el RMA sale del cliente, no del técnico
    assert t["checklist_ingreso"]["accesorios"] == ["Cargador", "Funda"]
    assert t["checklist_ingreso"]["tiene_bloqueo"] is True
    assert [f["momento"] for f in t["firmas"]] == ["ingreso"]
    # La cuenta no tiene clave: no se puede iniciar sesión con nada
    cliente = next(u for u in client.get("/users/", headers=admin).json() if u["id"] == t["usuario_id"])
    assert cliente["email"] is None
    for clave in ("x", "admin123", cliente["username"]):
        assert client.post("/login", data={"username": cliente["username"], "password": clave}).status_code == 401
    # El historial registra quién lo cargó
    hist = client.get(f"/tickets/{t['id']}/history", headers=tecnico).json()
    assert any("Ingreso en mostrador" in (h["detalle"] or "") for h in hist)
    assert any(h["tipo_evento"] == "firma_registrada" for h in hist)


def test_ingreso_cliente_existente_y_prioridad_de_empresa(client, tecnico, admin):
    nombre = f"empresa_{uuid.uuid4().hex[:6]}"
    r = client.post("/register", headers=admin, json={"username": nombre, "nombre": "Distribuidora Mostrador SA",
                    "email": f"{nombre}@test.com", "password": "secret1", "rol": "cliente", "tipo_cliente": "empresa"})
    cli = r.json()
    r = client.post("/mostrador/ingreso", headers=tecnico, json={"cliente_id": cli["id"], "ticket": EQUIPO})
    assert r.status_code == 200, r.text
    assert r.json()["usuario_id"] == cli["id"] and r.json()["prioridad"] == "Alta"
    # El cliente lo ve entre sus tickets
    h = {"Authorization": "Bearer " + client.post("/login", data={"username": nombre, "password": "secret1"}).json()["access_token"]}
    assert r.json()["id"] in [t["id"] for t in client.get("/tickets/", headers=h).json()]


def test_buscar_clientes_por_nombre_y_telefono(client, tecnico):
    tel = f"11 {uuid.uuid4().int % 10**8:08d}"
    client.post("/mostrador/ingreso", headers=tecnico, json={
        "cliente_nuevo": _nuevo(nombre="Ramiro Búsqueda", telefono=tel), "ticket": EQUIPO})
    por_nombre = client.get("/mostrador/clientes", params={"q": "ramiro bús"}, headers=tecnico).json()
    assert [c["nombre"] for c in por_nombre] == ["Ramiro Búsqueda"]
    assert por_nombre[0]["tiene_clave"] is False
    digitos = tel.replace(" ", "")
    por_tel = client.get("/mostrador/clientes", params={"q": f"{digitos[:2]}-{digitos[2:6]} {digitos[6:]}"},
                         headers=tecnico).json()
    assert [c["nombre"] for c in por_tel] == ["Ramiro Búsqueda"]


@pytest.mark.parametrize("cuerpo,error", [
    ({}, "Elegí un cliente"),
    ({"cliente_id": 1, "cliente_nuevo": {"nombre": "X", "telefono": "1155550000"}}, "Elegí un cliente"),
    ({"cliente_nuevo": {"nombre": "Sin contacto"}}, "teléfono o un email"),
    ({"cliente_nuevo": {"nombre": "Tel raro", "telefono": "abc"}}, "Teléfono inválido"),
    ({"cliente_nuevo": {"nombre": "Mail raro", "email": "no-es-mail"}}, "Email inválido"),
    ({"cliente_nuevo": {"nombre": "Firma vacía", "telefono": "1155550001"}, "firma": {"imagen": firma_png(vacia=True)}},
     "firma está vacía"),
    ({"cliente_nuevo": {"nombre": "Firma JPG", "telefono": "1155550002"}, "firma": {"imagen": "data:image/jpeg;base64,AAAA"}},
     "PNG"),
])
def test_ingreso_invalido_no_deja_nada_a_medias(client, tecnico, admin, cuerpo, error):
    antes = len(client.get("/tickets/", headers=admin, params={"limit": 1000}).json())
    usuarios_antes = len(client.get("/users/", headers=admin).json())
    r = client.post("/mostrador/ingreso", headers=tecnico, json={"ticket": EQUIPO, **cuerpo})
    assert r.status_code == 400 and error in r.json()["detail"], r.text
    assert len(client.get("/tickets/", headers=admin, params={"limit": 1000}).json()) == antes
    assert len(client.get("/users/", headers=admin).json()) == usuarios_antes


def test_email_repetido_pide_elegir_de_la_lista(client, tecnico, admin):
    nombre = f"cli_{uuid.uuid4().hex[:6]}"
    client.post("/register", headers=admin, json={"username": nombre, "nombre": "Ya Existe", "email": f"{nombre}@test.com",
                                                   "password": "secret1", "rol": "cliente"})
    r = client.post("/mostrador/ingreso", headers=tecnico, json={
        "cliente_nuevo": {"nombre": "Otro", "email": f"{nombre.upper()}@test.com"}, "ticket": EQUIPO})
    assert r.status_code == 400 and "elegilo de la lista" in r.json()["detail"]


def test_mostrador_es_solo_para_el_taller(client, make_user, make_ticket):
    h, _ = make_user()
    t = make_ticket(h)
    assert client.get("/mostrador/clientes", params={"q": "ab"}, headers=h).status_code == 403
    assert client.post("/mostrador/ingreso", headers=h, json={"cliente_nuevo": _nuevo(), "ticket": EQUIPO}).status_code == 403
    assert client.put(f"/tickets/{t['id']}/checklist", headers=h, json=CHECKLIST).status_code == 403
    assert client.put(f"/tickets/{t['id']}/firmas/entrega", headers=h, json={"imagen": firma_png()}).status_code == 403


def test_checklist_editable_y_validado(client, tecnico, make_user, make_ticket):
    h, _ = make_user()
    t = make_ticket(h)
    r = client.put(f"/tickets/{t['id']}/checklist", headers=tecnico,
                   json={"accesorios": [" Cargador ", "Cargador", ""], "enciende": False})
    assert r.status_code == 200
    assert r.json()["checklist_ingreso"]["accesorios"] == ["Cargador"]
    assert r.json()["checklist_ingreso"]["tiene_bloqueo"] is None
    assert client.put(f"/tickets/{t['id']}/checklist", headers=tecnico,
                      json={"estado_fisico": "x" * 501}).status_code == 422


def test_firma_de_entrega_se_reemplaza_y_se_guarda_en_blanco_y_negro(client, tecnico, make_user, make_ticket):
    h, _ = make_user()
    otro, _ = make_user()
    t = make_ticket(h)
    for _ in range(2):
        r = client.put(f"/tickets/{t['id']}/firmas/entrega", headers=tecnico,
                       json={"imagen": firma_png(tamano=(1400, 500)), "aclaracion": "Juan P."})
        assert r.status_code == 200, r.text
    assert [f["momento"] for f in r.json()["firmas"]] == ["entrega"]   # una sola: la segunda reemplaza
    img = client.get(f"/tickets/{t['id']}/firmas/entrega/imagen", headers=h)
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    png = Image.open(io.BytesIO(img.content))
    assert png.mode == "1" and png.width <= 600                         # B/N puro y achicada
    assert png.width < 1400 and png.height < 500                        # recortada al trazo
    assert client.get(f"/tickets/{t['id']}/firmas/entrega/imagen", headers=otro).status_code == 403
    assert client.get(f"/tickets/{t['id']}/firmas/ingreso/imagen", headers=h).status_code == 404
    assert client.put(f"/tickets/{t['id']}/firmas/otra", headers=tecnico, json={"imagen": firma_png()}).status_code == 422


def test_rma_exacto_para_el_lector(client, tecnico, make_user, make_ticket):
    h, _ = make_user()
    otro, _ = make_user()
    t = make_ticket(h)
    for q in (t["numero_rma"], t["numero_rma"].lower(), f"  {t['numero_rma']} "):
        r = client.get(f"/tickets/rma/{q}", headers=tecnico)
        assert r.status_code == 200 and r.json()["id"] == t["id"]
    assert client.get(f"/tickets/rma/{t['numero_rma']}", headers=h).status_code == 200
    assert client.get(f"/tickets/rma/{t['numero_rma']}", headers=otro).status_code == 404   # no revela que existe
    assert client.get(f"/tickets/rma/{t['numero_rma'][:-1]}", headers=tecnico).status_code == 404  # exacto, no parcial


def test_fotos_de_ingreso(client, tecnico, make_user, make_ticket):
    h, _ = make_user()
    t = make_ticket(h)
    foto = io.BytesIO()
    Image.new("RGB", (40, 30), (200, 10, 10)).save(foto, format="JPEG")
    archivo = lambda: {"file": ("foto.jpg", foto.getvalue(), "image/jpeg")}
    r = client.post(f"/tickets/{t['id']}/attachments", headers=tecnico, files=archivo(), data={"categoria": "ingreso"})
    assert r.status_code == 200 and r.json()["adjunto"]["categoria"] == "ingreso"
    assert client.post(f"/tickets/{t['id']}/attachments", headers=h, files=archivo(),
                       data={"categoria": "ingreso"}).status_code == 403
    assert client.post(f"/tickets/{t['id']}/attachments", headers=tecnico, files=archivo(),
                       data={"categoria": "otra"}).status_code == 400
    r = client.post(f"/tickets/{t['id']}/attachments", headers=h, files=archivo())   # adjunto común del cliente
    assert r.status_code == 200 and r.json()["adjunto"]["categoria"] is None


def _texto_pdf(r):
    assert r.status_code == 200, r.text
    pdf = PdfReader(io.BytesIO(r.content))
    return len(pdf.pages), " ".join(p.extract_text() for p in pdf.pages)


def test_documentos_llevan_checklist_y_firmas(client, tecnico, admin):
    t = client.post("/mostrador/ingreso", headers=tecnico, json={
        "cliente_nuevo": _nuevo(), "ticket": EQUIPO, "checklist": CHECKLIST,
        "firma": {"imagen": firma_png(), "aclaracion": "Lucía M."}}).json()
    client.put(f"/tickets/{t['id']}/firmas/entrega", headers=tecnico, json={"imagen": firma_png(), "aclaracion": "Lucía M."})
    base = f"/tickets/{t['id']}/documentos"

    paginas, texto = _texto_pdf(client.get(f"{base}/ingreso?formato=pdf", headers=tecnico))
    assert paginas == 1
    for esperado in ("Recepción del equipo", "Cargador, Funda, Mouse inalámbrico", "Rayón en la tapa",
                     "la clave se pide si hace falta", "Firmado en pantalla", "Lucía M."):
        assert esperado.lower() in texto.lower(), esperado   # los títulos salen en mayúsculas
    _, texto = _texto_pdf(client.get(f"{base}/remito?formato=pdf", headers=tecnico))
    assert "Firmado en pantalla" in texto

    for ancho in ("58", "80"):   # termina en 80, el valor por defecto
        client.put("/config/ajustes", headers=admin, json={"ticketera_ancho": ancho})
        paginas, texto = _texto_pdf(client.get(f"{base}/ticket_ingreso?formato=pdf", headers=tecnico))
        assert paginas == 1 and "Cargador" in texto and "Conforme con el ingreso" in texto
        paginas, texto = _texto_pdf(client.get(f"{base}/ticket_entrega?formato=pdf", headers=tecnico))
        assert paginas == 1 and "Recibí conforme" in texto


def test_perfil_sin_email_no_choca_entre_clientes(client, tecnico, admin):
    ids = [client.post("/mostrador/ingreso", headers=tecnico, json={"cliente_nuevo": _nuevo(), "ticket": EQUIPO}).json()["usuario_id"]
           for _ in range(2)]
    for uid in ids:
        r = client.patch(f"/users/{uid}/profile", headers=admin, json={"email": "", "telefono": "1144443333"})
        assert r.status_code == 200, r.text
        assert r.json()["email"] is None
