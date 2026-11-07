"""Rendimiento (CONTEXTO.md, 5.4): las consultas no crecen con la cantidad de tickets."""
import contextlib
import uuid

import pytest
from sqlalchemy import event

from backend.app import database
from test_recepcion import firma_png


@contextlib.contextmanager
def contar_consultas():
    n = {"total": 0}

    def contar(*_a, **_k):
        n["total"] += 1
    event.listen(database.engine, "before_cursor_execute", contar)
    try:
        yield n
    finally:
        event.remove(database.engine, "before_cursor_execute", contar)


@pytest.fixture
def tickets_completos(client, admin, make_user):
    """Tickets con todo lo que se serializa: técnico, cliente, etiqueta, repuesto, firma y favorito."""
    _, tec = make_user(rol="tecnico")
    cod = f"Q-{uuid.uuid4().hex[:5]}"
    part = client.post("/parts/", headers=admin, json={"nombre": cod, "codigo": cod, "stock": 999, "proveedor": "x", "precio": 1}).json()
    marca = f"PERF{uuid.uuid4().hex[:5]}"

    def crear(n):
        for i in range(n):
            t = client.post("/mostrador/ingreso", headers=admin, json={
                "cliente_nuevo": {"nombre": f"Cliente {i}", "telefono": f"11{uuid.uuid4().int % 10**8:08d}"},
                "ticket": {"producto": marca, "numero_serie": f"{marca}-{i}", "fecha_compra": "2026-01-01T00:00:00",
                           "descripcion": "No enciende"},
                "firma": {"imagen": firma_png()}}).json()
            client.put(f"/tickets/{t['id']}/assign", headers=admin, json={"tecnico_id": tec["id"]})
            client.post(f"/tickets/{t['id']}/tags", headers=admin, json={"tag_nombre": "Garantía"})
            client.post(f"/tickets/{t['id']}/parts", headers=admin, json={"part_id": part["id"], "cantidad": 1})
            client.post(f"/favorites/{t['id']}", headers=admin)
    return crear, marca


def test_consultas_constantes_al_listar_y_buscar(client, admin, tickets_completos):
    crear, marca = tickets_completos
    crear(3)
    with contar_consultas() as pocos:
        assert len(client.get("/tickets/search/global", params={"q": marca}, headers=admin).json()) == 3
    crear(12)
    with contar_consultas() as muchos:
        r = client.get("/tickets/search/global", params={"q": marca.lower()}, headers=admin)   # sin distinguir mayúsculas
    assert len(r.json()) == 15
    assert muchos["total"] == pocos["total"] <= 12, (pocos, muchos)
    with contar_consultas() as lista:
        client.get("/tickets/", params={"limit": 15}, headers=admin)
    assert lista["total"] <= 12, lista


def test_busqueda_toma_comodines_como_texto_y_tiene_limite(client, admin, make_user, make_ticket):
    h, _ = make_user()
    make_ticket(h, serie="LIKE_100%")
    make_ticket(h, serie="LIKEX100Y")
    r = client.get("/tickets/search/global", params={"q": "LIKE_100%"}, headers=admin).json()
    assert [t["numero_serie"] for t in r] == ["LIKE_100%"]
    assert client.get("/tickets/search/global", params={"q": "ab", "limit": 500}, headers=admin).status_code == 422
    assert client.get("/tickets/", params={"limit": 5000}, headers=admin).status_code == 422


def test_cache_de_ajustes_se_actualiza_al_guardar(client, admin):
    from backend.app import ajustes
    db = database.SessionLocal()
    try:
        ajustes.get(db, "retiro_dias_guarda")                       # carga el caché
        client.put("/config/ajustes", headers=admin, json={"retiro_dias_guarda": 45})
        assert ajustes.get(db, "retiro_dias_guarda") == 45           # sin esperar los 5 s
        client.put("/config/ajustes", headers=admin, json={"retiro_dias_guarda": 90})
        assert ajustes.get(db, "retiro_dias_guarda") == 90
    finally:
        db.close()


def test_claves_foraneas_activas(client, admin, make_user, make_ticket):
    from sqlalchemy import text
    with database.engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
    # Borrar un usuario con actividad: mensaje claro, no un error 500 ni registros huérfanos
    h, cli = make_user()
    make_ticket(h)
    r = client.delete(f"/users/{cli['id']}", headers=admin)
    assert r.status_code == 400 and "Deshabilitalo" in r.json()["detail"]
    _, nuevo = make_user()
    assert client.delete(f"/users/{nuevo['id']}", headers=admin).status_code == 204   # sin actividad, sí
    r = client.post("/tickets/", headers=h, json={"producto_id": 999999, "producto": "X", "numero_serie": "FK",
                                                  "fecha_compra": "2026-01-01T00:00:00", "descripcion": "x"})
    assert r.status_code == 400


def test_etiqueta_repetida_no_duplica(client, admin, make_user, make_ticket):
    h, _ = make_user()
    t = make_ticket(h)
    for _ in range(2):
        assert client.post(f"/tickets/{t['id']}/tags", headers=admin, json={"tag_nombre": "Garantía"}).status_code in (200, 400)
    assert [x["nombre"] for x in client.get(f"/tickets/{t['id']}", headers=admin).json()["tags"]].count("Garantía") == 1


def test_resumen_cuenta_todo_y_respeta_al_cliente(client, admin, make_user, make_ticket):
    """Las tarjetas del listado: totales reales (no los 50 cargados) y el cliente ve solo lo suyo."""
    h, _ = make_user()
    otro, _ = make_user()
    antes = client.get("/tickets/stats/resumen", headers=admin).json()
    tickets = [make_ticket(h, serie=f"RES-{i}") for i in range(3)]
    make_ticket(otro, serie="RES-otro")
    client.put(f"/tickets/{tickets[0]['id']}/status", headers=admin, json={"estado": "Cerrado"})
    despues = client.get("/tickets/stats/resumen", headers=admin).json()
    assert despues["total"] - antes["total"] == 4
    assert despues["cerrados"] - antes["cerrados"] == 1
    assert client.get("/tickets/stats/resumen", headers=h).json() == {"total": 3, "nuevos": 2, "en_proceso": 0, "cerrados": 1,
                                                                         "por_estado": {"Nuevo": 2, "Cerrado": 1}}
