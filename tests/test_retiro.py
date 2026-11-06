"""Equipos listos para retirar: aviso al cliente, recordatorios y plazo de guarda."""
from datetime import timedelta

import pytest

from backend.app import database, models
from backend.app.services import email, retiro
from backend.app.timeutils import utcnow
from test_email import cliente, smtp  # noqa: F401  (fixtures)


def _mover_listo(ticket_id, dias):
    """Simula que el equipo está listo desde hace `dias` días (y el último aviso también)."""
    db = database.SessionLocal()
    try:
        t = db.get(models.Ticket, ticket_id)
        t.fecha_listo = t.retiro_ultimo_aviso = utcnow() - timedelta(days=dias)
        db.commit()
    finally:
        db.close()


def _revisar():
    db = database.SessionLocal()
    try:
        return retiro.revisar(db)
    finally:
        db.close()
        email.esperar_envios()


def _listo(client, admin, t):
    r = client.put(f"/tickets/{t['id']}/status", headers=admin, json={"estado": "Reparado"})
    assert r.status_code == 200, r.text


def test_al_quedar_listo_se_avisa_con_el_plazo(client, admin, smtp, cliente, make_ticket):  # noqa: F811
    h, mail = cliente
    t = make_ticket(h, serie="RET-1")
    _listo(client, admin, t)
    email.esperar_envios()
    m = smtp.para(mail)[-1]
    assert "listo para retirar" in m["Subject"]
    cuerpo = m.get_body(("plain",)).get_content()
    assert "Podés retirarlo hasta el" in cuerpo and "90 días" in cuerpo
    # Solo ese mail (no además el genérico de cambio de estado)
    assert sum(1 for x in smtp.para(mail) if t["numero_rma"] in x["Subject"]) == 1
    # Notificación dentro del sistema, seguimiento público y panel del taller
    assert any("Listo para retirar" in n["titulo"] for n in client.get("/notifications/", headers=h).json())
    pub = client.get("/public/seguimiento", params={"rma": t["numero_rma"], "serie": "RET-1"}).json()
    assert pub["retiro"] and "90 días" in pub["retiro"]["politica"]
    pend = [p for p in client.get("/tickets/retiro/pendientes", headers=admin).json() if p["id"] == t["id"]]
    assert pend and pend[0]["vencido"] is False and pend[0]["dias_restantes"] in (89, 90)


def test_recordatorios_y_aviso_de_plazo_vencido(client, admin, smtp, cliente, make_ticket):  # noqa: F811
    h, mail = cliente
    t = make_ticket(h, serie="RET-2")
    _listo(client, admin, t)
    email.esperar_envios()
    antes = len(smtp.para(mail))
    _revisar()                                   # recién avisado: nada
    assert len(smtp.para(mail)) == antes
    _mover_listo(t["id"], 8)                     # pasó más de una semana
    _revisar()
    assert "recordatorio" in smtp.para(mail)[-1]["Subject"]
    _revisar()                                   # el recordatorio no se repite enseguida
    assert len(smtp.para(mail)) == antes + 1
    _mover_listo(t["id"], 91)                    # venció el plazo de guarda
    _revisar(); _revisar()
    avisos_admin = [n for n in client.get("/notifications/", headers=admin).json()
                    if n["titulo"] == f"Sin retirar: {t['numero_rma']}"]
    assert len(avisos_admin) == 1               # una sola vez
    assert len(smtp.para(mail)) == antes + 1    # vencido: ya no se le recuerda al cliente
    pend = next(p for p in client.get("/tickets/retiro/pendientes", headers=admin).json() if p["id"] == t["id"])
    assert pend["vencido"] is True


def test_al_retirarlo_deja_de_estar_pendiente(client, admin, make_user, make_ticket):
    h, _ = make_user()
    t = make_ticket(h)
    _listo(client, admin, t)
    client.put(f"/tickets/{t['id']}/status", headers=admin, json={"estado": "Cerrado"})
    assert t["id"] not in [p["id"] for p in client.get("/tickets/retiro/pendientes", headers=admin).json()]
    pub = client.get("/public/seguimiento", params={"rma": t["numero_rma"], "serie": "SN1"}).json()
    assert pub["retiro"] is None


def test_estado_y_plazo_configurables(client, admin, make_user, make_ticket):
    h, _ = make_user()
    t = make_ticket(h)
    client.put("/config/ajustes", headers=admin, json={"retiro_estado": "Esperando repuestos", "retiro_dias_guarda": 30})
    try:
        _listo(client, admin, t)   # Reparado ya no es el estado de retiro
        assert t["id"] not in [p["id"] for p in client.get("/tickets/retiro/pendientes", headers=admin).json()]
        client.put(f"/tickets/{t['id']}/status", headers=admin, json={"estado": "Esperando repuestos"})
        p = next(p for p in client.get("/tickets/retiro/pendientes", headers=admin).json() if p["id"] == t["id"])
        assert p["dias_restantes"] in (29, 30)
        assert client.put("/config/ajustes", headers=admin, json={"retiro_estado": "Cerrado"}).status_code == 400
    finally:
        client.put("/config/ajustes", headers=admin, json={"retiro_estado": "Reparado", "retiro_dias_guarda": 90})


def test_la_politica_sale_en_los_comprobantes(client, admin, make_user, make_ticket):
    h, _ = make_user()
    t = make_ticket(h)
    r = client.get(f"/tickets/{t['id']}/documentos/ingreso?formato=html", headers=admin)
    assert "dentro de los 90 días" in r.text
    r = client.get(f"/tickets/{t['id']}/documentos/ticket_ingreso?formato=html", headers=admin)
    assert "dentro de los 90 días" in r.text


def test_solo_el_taller_ve_los_pendientes(client, make_user):
    h, _ = make_user()
    assert client.get("/tickets/retiro/pendientes", headers=h).status_code == 403
