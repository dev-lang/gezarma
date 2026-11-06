"""Seguimiento público de reparaciones (sin login)."""
import pytest

from backend.app.routers import public


@pytest.fixture(autouse=True)
def _limpiar_limites():
    public.reiniciar_limites()
    yield
    public.reiniciar_limites()


def _consulta(client, rma, serie):
    return client.get("/public/seguimiento", params={"rma": rma, "serie": serie})


def test_consulta_con_rma_y_serie(client, admin, make_user, make_ticket):
    cli, _ = make_user()
    t = make_ticket(cli, serie="ABC-123")
    client.put(f"/tickets/{t['id']}/status", headers=admin, json={"estado": "En reparación"})
    client.post(f"/tickets/{t['id']}/comments/", headers=admin, json={"comentario": "secreto", "is_internal": True})
    r = _consulta(client, t["numero_rma"].lower(), " abc-123 ")     # sin importar mayúsculas/espacios
    assert r.status_code == 200
    d = r.json()
    assert d["estado"]["valor"] == "En reparación"
    assert [h["estado"]["valor"] for h in d["historial"]] == ["Nuevo", "En reparación"]
    assert d["historial"][0]["fecha"].endswith("Z")
    texto = str(d)
    for privado in ("secreto", "usuario", "tecnico", "diagnostico", "descripcion", "precio"):
        assert privado not in texto


def test_datos_incorrectos_dan_el_mismo_error(client, make_user, make_ticket):
    cli, _ = make_user()
    t = make_ticket(cli, serie="XYZ")
    r1 = _consulta(client, t["numero_rma"], "OTRA-SERIE")
    r2 = _consulta(client, "RMA-NO-EXISTE", "XYZ")
    assert r1.status_code == r2.status_code == 404
    assert r1.json() == r2.json()


def test_limite_de_intentos_fallidos(client, make_user, make_ticket):
    cli, _ = make_user()
    t = make_ticket(cli, serie="LIM-1")
    for _ in range(public.MAX_FALLOS):
        assert _consulta(client, t["numero_rma"], "mal").status_code == 404
    assert _consulta(client, t["numero_rma"], "LIM-1").status_code == 429   # bloqueado aunque ahora acierte


def test_presupuesto_pendiente_sin_montos(client, admin, make_user, make_ticket):
    cli, _ = make_user()
    t = make_ticket(cli, serie="PRES-1")
    client.post(f"/budget/tickets/{t['id']}/presupuesto", headers=admin,
                json={"items": [{"descripcion": "X", "cantidad": 1, "precio_cliente": 1234}]})
    client.patch(f"/budget/tickets/{t['id']}/presupuesto/estado", headers=admin, json={"estado": "enviado"})
    d = _consulta(client, t["numero_rma"], "PRES-1").json()
    assert d["presupuesto_pendiente"] is True and "1234" not in str(d)


def test_se_puede_desactivar(client, admin, make_user, make_ticket):
    cli, _ = make_user()
    t = make_ticket(cli, serie="OFF-1")
    client.put("/config/ajustes", headers=admin, json={"seguimiento_publico": False})
    try:
        assert _consulta(client, t["numero_rma"], "OFF-1").status_code == 404
    finally:
        client.put("/config/ajustes", headers=admin, json={"seguimiento_publico": True})


def test_pagina_publica(client):
    r = client.get("/seguimiento")
    assert r.status_code == 200 and "Seguimiento de reparación" in r.text
