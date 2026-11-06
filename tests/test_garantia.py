"""Garantía de la reparación: reingreso del mismo equipo dentro del plazo."""
from datetime import timedelta

from backend.app import database, models
from backend.app.services import email
from backend.app.timeutils import utcnow
from test_email import smtp  # noqa: F401  (fixture)


def _cerrado_hace(ticket_id, dias):
    db = database.SessionLocal()
    try:
        db.get(models.Ticket, ticket_id).fecha_cierre = utcnow() - timedelta(days=dias)
        db.commit()
    finally:
        db.close()


def _reparado_y_cerrado(client, admin, tecnico_id, t):
    client.put(f"/tickets/{t['id']}/assign", headers=admin, json={"tecnico_id": tecnico_id})
    client.put(f"/tickets/{t['id']}/diagnostic", headers=admin, json={"diagnostico": "Cambio de conector de carga"})
    client.put(f"/tickets/{t['id']}/status", headers=admin, json={"estado": "Cerrado"})


def test_reingreso_dentro_del_plazo(client, admin, make_user, make_ticket, smtp):  # noqa: F811
    h, _ = make_user()
    tec_h, tec = make_user(rol="tecnico")
    t1 = make_ticket(h, serie="GAR-100")
    _reparado_y_cerrado(client, admin, tec["id"], t1)
    _cerrado_hace(t1["id"], 30)
    t2 = make_ticket(h, serie=" gar-100")                 # mismo equipo (mayúsculas y espacios no importan)
    assert t2["reingreso_garantia"] is True
    assert t2["reingreso_de"] == t1["id"] and t2["rma_reingreso_de"] == t1["numero_rma"]
    assert t2["ticket_relacionado"] == t1["id"] and t2["prioridad"] == "Alta"
    notifs = client.get("/notifications/", headers=tec_h).json()
    assert any(n["titulo"] == f"Reingreso en garantía: {t2['numero_rma']}" for n in notifs)
    hist = client.get(f"/tickets/{t2['id']}/history", headers=admin).json()
    assert any("Reingreso en garantía" in (x["detalle"] or "") for x in hist)
    email.esperar_envios()
    m = smtp.para(tec["email"])[-1]
    assert "Reingreso en garantía" in m["Subject"] and "Cambio de conector" in m.get_body(("plain",)).get_content()
    # Sale en la orden de ingreso y en el comprobante
    for doc in ("ingreso", "ticket_ingreso"):
        r = client.get(f"/tickets/{t2['id']}/documentos/{doc}?formato=html", headers=admin)
        assert f"Reingreso en garantía de la reparación {t1['numero_rma']}" in r.text


def test_fuera_de_plazo_o_sin_cerrar_no_es_reingreso(client, admin, make_user, make_ticket):
    h, _ = make_user()
    _, tec = make_user(rol="tecnico")
    viejo = make_ticket(h, serie="GAR-200")
    _reparado_y_cerrado(client, admin, tec["id"], viejo)
    _cerrado_hace(viejo["id"], 91)
    assert make_ticket(h, serie="GAR-200")["reingreso_garantia"] is False
    abierto = make_ticket(h, serie="GAR-300")
    assert abierto["reingreso_garantia"] is False
    assert make_ticket(h, serie="GAR-300")["reingreso_garantia"] is False   # el anterior sigue abierto
    cancelado = make_ticket(h, serie="GAR-400")
    client.put(f"/tickets/{cancelado['id']}/status", headers=admin, json={"estado": "Cancelado"})
    assert make_ticket(h, serie="GAR-400")["reingreso_garantia"] is False


def test_plazo_configurable_y_desactivable(client, admin, make_user, make_ticket):
    h, _ = make_user()
    _, tec = make_user(rol="tecnico")
    t1 = make_ticket(h, serie="GAR-500")
    _reparado_y_cerrado(client, admin, tec["id"], t1)
    _cerrado_hace(t1["id"], 100)
    client.put("/config/ajustes", headers=admin, json={"garantia_reparacion_dias": 180})
    try:
        assert make_ticket(h, serie="GAR-500")["reingreso_garantia"] is True
        client.put("/config/ajustes", headers=admin, json={"garantia_reparacion_dias": 0})
        assert make_ticket(h, serie="GAR-500")["reingreso_garantia"] is False
    finally:
        client.put("/config/ajustes", headers=admin, json={"garantia_reparacion_dias": 90})


def test_urgente_se_mantiene(client, admin, make_user):
    """Si el taller lo carga como Urgente (el cliente no elige prioridad), no baja a Alta."""
    h, cli = make_user()
    _, tec = make_user(rol="tecnico")
    cuerpo = {"producto": "X", "numero_serie": "GAR-600", "fecha_compra": "2026-01-01T00:00:00", "descripcion": "x"}
    t1 = client.post("/tickets/", headers=h, json=cuerpo).json()
    _reparado_y_cerrado(client, admin, tec["id"], t1)
    t2 = client.post("/mostrador/ingreso", headers=admin,
                     json={"cliente_id": cli["id"], "ticket": {**cuerpo, "prioridad": "Urgente"}}).json()
    assert t2["reingreso_garantia"] is True and t2["prioridad"] == "Urgente"


def test_no_cruza_clientes(client, admin, make_user, make_ticket):
    """Con el N° de serie de un equipo ajeno no se obtiene su RMA."""
    victima, _ = make_user()
    otro, _ = make_user()
    _, tec = make_user(rol="tecnico")
    t1 = make_ticket(victima, serie="GAR-AJENO")
    _reparado_y_cerrado(client, admin, tec["id"], t1)
    t2 = make_ticket(otro, serie="GAR-AJENO")
    assert t2["reingreso_garantia"] is False and t2["rma_reingreso_de"] is None
    assert t2["ticket_relacionado"] is None and t2["rma_relacionado"] is None
    hist = client.get(f"/tickets/{t2['id']}/history", headers=otro).json()
    assert not any(t1["numero_rma"] in (x["detalle"] or "") for x in hist)
