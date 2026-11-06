"""Regresión de la revisión de seguridad (CONTEXTO.md, sección 5.1)."""
import io
import os
import subprocess
import sys
import uuid

from openpyxl import load_workbook

from backend.app.config import ROOT_DIR
from backend.app.routers import ticket_adjuntos as tickets_router
from conftest import login


def _cliente_con_clave(client, admin):
    nombre = f"seg_{uuid.uuid4().hex[:6]}"
    r = client.post("/register", headers=admin, json={"username": nombre, "nombre": nombre, "email": f"{nombre}@t.com",
                                                      "password": "secret1", "rol": "cliente"})
    return r.json(), nombre


def test_busqueda_del_cliente_no_mira_notas_internas(client, admin, make_user, make_ticket):
    h, _ = make_user()
    t = make_ticket(h, serie="SEG-BUS")
    client.post(f"/tickets/{t['id']}/comments/", headers=admin, json={"comentario": "cliente palabrasecreta", "is_internal": True})
    client.post(f"/tickets/{t['id']}/comments/", headers=admin, json={"comentario": "palabrapublica", "is_internal": False})
    assert client.get("/tickets/search/global", params={"q": "palabrasecreta"}, headers=h).json() == []
    assert [x["id"] for x in client.get("/tickets/search/global", params={"q": "palabrapublica"}, headers=h).json()] == [t["id"]]
    # El taller sí encuentra por la nota interna
    assert t["id"] in [x["id"] for x in client.get("/tickets/search/global", params={"q": "palabrasecreta"}, headers=admin).json()]


def test_clave_temporal_solo_sirve_para_cambiarla(client, admin, make_user):
    _, user = make_user()
    temp = client.post(f"/users/{user['id']}/reset-password", headers=admin).json()["temp_password"]
    h = login(client, user["username"], temp)
    r = client.get("/tickets/", headers=h)
    assert r.status_code == 403 and "cambiar tu contraseña" in r.json()["detail"]
    r = client.post("/users/change-password", headers=h, json={"current_password": temp, "new_password": "nueva-123"})
    assert r.status_code == 200
    nuevo = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/tickets/", headers=nuevo).status_code == 200
    assert client.get("/tickets/", headers=h).status_code == 401           # el token viejo ya no vale


def test_cambiar_o_resetear_la_clave_cierra_las_otras_sesiones(client, admin, make_user):
    h1, user = make_user(password="clave-1")
    h2 = login(client, user["username"], "clave-1")                        # otra sesión
    r = client.post("/users/change-password", headers=h1, json={"current_password": "clave-1", "new_password": "clave-2"})
    nuevo = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/tickets/", headers=h2).status_code == 401
    assert client.get("/tickets/", headers=nuevo).status_code == 200
    client.post(f"/users/{user['id']}/reset-password", headers=admin)
    assert client.get("/tickets/", headers=nuevo).status_code == 401


def test_solo_se_asigna_personal_del_taller(client, admin, make_user, make_ticket):
    h, cli = make_user()
    otro_h, otro = make_user()
    t = make_ticket(h)
    r = client.put(f"/tickets/{t['id']}/assign", headers=admin, json={"tecnico_id": otro["id"]})
    assert r.status_code == 400
    _, tec = make_user(rol="tecnico")
    client.patch(f"/users/{tec['id']}", headers=admin, json={"activo": False})
    assert client.put(f"/tickets/{t['id']}/assign", headers=admin, json={"tecnico_id": tec["id"]}).status_code == 400


def test_exportacion_neutraliza_formulas(client, admin, make_user):
    h, _ = make_user()
    client.post("/tickets/", headers=h, json={"producto": "X", "numero_serie": "SEG-XLSX", "fecha_compra": "2026-01-01T00:00:00",
                                              "descripcion": '=HYPERLINK("http://evil","clic")'})
    wb = load_workbook(io.BytesIO(client.get("/export/tickets?formato=xlsx", headers=admin).content))
    celdas = [c for fila in wb.active.iter_rows() for c in fila if isinstance(c.value, str) and "HYPERLINK" in c.value]
    assert celdas and all(c.data_type == "s" and c.value.startswith("'=") for c in celdas)
    csv = client.get("/export/tickets?formato=csv", headers=admin).content.decode("utf-8-sig")
    assert "\"'=HYPERLINK" in csv


def test_prioridad_validada_y_el_cliente_no_la_elige(client, admin, make_user):
    h, _ = make_user()
    base = {"producto": "X", "numero_serie": "SEG-P", "fecha_compra": "2026-01-01T00:00:00", "descripcion": "x"}
    assert client.post("/tickets/", headers=h, json={**base, "prioridad": "<b>Urgente</b>"}).status_code == 422
    assert client.post("/tickets/", headers=h, json={**base, "prioridad": "Urgente"}).json()["prioridad"] == "Normal"
    t = client.post("/tickets/", headers=admin, json={**base, "prioridad": "Urgente"}).json()
    assert t["prioridad"] == "Urgente"
    assert client.patch(f"/tickets/{t['id']}/fields", headers=admin, json={"prioridad": "Altísima"}).status_code == 422


def test_cliente_no_ve_contacto_de_tecnicos(client, admin, make_user):
    h, _ = make_user()
    make_user(rol="tecnico")
    lista = client.get("/users/tecnicos", headers=h).json()
    assert lista and all(set(x) == {"id", "nombre", "rol"} for x in lista)
    assert "email" in client.get("/users/tecnicos", headers=admin).json()[0]


def test_presupuesto_en_borrador_no_es_visible_para_el_cliente(client, admin, make_user, make_ticket):
    h, _ = make_user()
    t = make_ticket(h)
    client.post(f"/budget/tickets/{t['id']}/presupuesto", headers=admin, json={
        "notas": "interno", "items": [{"descripcion": "Pantalla", "cantidad": 1, "costo_interno": 1, "precio_cliente": 9}]})
    assert client.get(f"/budget/tickets/{t['id']}/presupuesto", headers=h).status_code == 404
    client.patch(f"/budget/tickets/{t['id']}/presupuesto/estado", headers=admin, json={"estado": "enviado"})
    assert client.get(f"/budget/tickets/{t['id']}/presupuesto", headers=h).status_code == 200


def test_emails_sin_duplicados_por_mayusculas(client, admin):
    nombre = f"may_{uuid.uuid4().hex[:6]}"
    r = client.post("/register", json={"username": nombre, "nombre": "A", "email": f"{nombre}@T.com", "password": "secret1"})
    assert r.status_code == 200 and r.json()["email"] == f"{nombre}@t.com"
    r = client.post("/register", json={"username": nombre + "b", "nombre": "B", "email": f"{nombre.upper()}@t.COM", "password": "secret1"})
    assert r.status_code == 400
    otro, _ = _cliente_con_clave(client, admin)
    assert client.patch(f"/users/{otro['id']}", headers=admin, json={"email": f"{nombre.upper()}@T.COM"}).status_code == 400
    assert client.patch(f"/users/{otro['id']}/profile", headers=admin, json={"email": f"{nombre}@t.com"}).status_code == 400


def test_limite_de_altas_publicas(client):
    for i in range(10):
        n = f"alta_{uuid.uuid4().hex[:6]}"
        assert client.post("/register", json={"username": n, "nombre": n, "email": f"{n}@t.com", "password": "secret1"}).status_code == 200
    n = f"alta_{uuid.uuid4().hex[:6]}"
    assert client.post("/register", json={"username": n, "nombre": n, "email": f"{n}@t.com", "password": "secret1"}).status_code == 429


def test_limite_de_intentos_por_cuenta(client, admin, make_user):
    from backend.app import database, models
    _, user = make_user(password="buena-1")
    db = database.SessionLocal()
    try:   # 15 fallos desde IPs distintas (el límite por IP no los frena)
        for i in range(15):
            db.add(models.LoginAttempt(ip_address=f"10.0.0.{i}", username=user["username"], exitoso=False))
        db.commit()
    finally:
        db.close()
    r = client.post("/login", data={"username": user["username"], "password": "buena-1"})
    assert r.status_code == 429


def test_cupo_de_adjuntos_por_cliente(client, make_user, make_ticket, monkeypatch, upload):
    h, _ = make_user()
    monkeypatch.setattr(tickets_router, "MAX_CLIENTE_UPLOAD_BYTES", 10)
    t1, t2 = make_ticket(h), make_ticket(h)
    assert upload(h, t1["id"], content=b"123456").status_code == 200
    r = upload(h, t2["id"], content=b"123456")                              # otro ticket, mismo cliente
    assert r.status_code == 400 and "límite" in r.json()["detail"]


def test_sin_secret_key_genera_una_propia_y_la_reutiliza(tmp_path):
    codigo = "from backend.app import config; print(config.SECRET_KEY_ORIGEN, config.SECRET_KEY)"
    env = {k: v for k, v in os.environ.items() if k != "SECRET_KEY"}
    env.update(DATABASE_URL=f"sqlite:///{tmp_path}/x.db", PYTHONPATH=str(ROOT_DIR))
    correr = lambda e: subprocess.run([sys.executable, "-c", codigo], env=e, capture_output=True, text=True,
                                      cwd=tmp_path, check=True).stdout.split()
    origen1, clave1 = correr(env)
    origen2, clave2 = correr(env)
    assert (origen1, origen2) == ("generada", "archivo") and clave1 == clave2 and len(clave1) > 40
    assert (tmp_path / "secret_key").exists()
    # La clave histórica del repo se ignora aunque esté en el entorno
    origen3, clave3 = correr({**env, "SECRET_KEY": "gezatek_super_secret_key_123"})
    assert clave3 == clave1 and clave3 != "gezatek_super_secret_key_123"
