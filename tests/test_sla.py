"""Alertas de SLA: panel del dashboard y avisos periódicos (una sola vez por nivel)."""
from datetime import timedelta

import pytest

from backend.app import database, models
from backend.app.services import email, sla
from backend.app.timeutils import utcnow


def _set_deadline(ticket_id, delta):
    db = database.SessionLocal()
    try:
        db.get(models.Ticket, ticket_id).deadline_sla = utcnow() + delta
        db.commit()
    finally:
        db.close()


def _revisar():
    db = database.SessionLocal()
    try:
        return sla.revisar(db)
    finally:
        db.close()


def _notifs(client, headers, rma):
    return [n["titulo"] for n in client.get("/notifications/", headers=headers).json()
            if rma in n["titulo"] and n["titulo"].startswith("SLA")]


@pytest.fixture
def mails(monkeypatch):
    enviados = []
    monkeypatch.setattr(email, "sla", lambda db, dest, titulo, lineas: enviados.append(([u.username for u in dest], lineas)))
    return enviados


@pytest.fixture(autouse=True)
def _solo_estos_tickets():
    """Los tickets de otros tests no deben interferir: se les saca el SLA."""
    db = database.SessionLocal()
    try:
        db.query(models.Ticket).update({models.Ticket.deadline_sla: None})
        db.commit()
    finally:
        db.close()


def test_ticket_nuevo_no_nace_por_vencer(client, admin, make_user, make_ticket):
    cli, _ = make_user()
    t = make_ticket(cli)   # SLA de 24 h; umbral por defecto 4 h
    assert all(a["id"] != t["id"] for a in client.get("/tickets/sla/alertas", headers=admin).json())


def test_panel_de_alertas(client, admin, make_user, make_ticket):
    cli, _ = make_user()
    pronto, lejos, vencido = make_ticket(cli), make_ticket(cli), make_ticket(cli)
    _set_deadline(pronto["id"], timedelta(hours=2))
    _set_deadline(lejos["id"], timedelta(hours=30))
    _set_deadline(vencido["id"], timedelta(hours=-3))
    alertas = {a["id"]: a for a in client.get("/tickets/sla/alertas", headers=admin).json()}
    assert set(alertas) == {pronto["id"], vencido["id"]}
    assert 1.9 < alertas[pronto["id"]]["horas_restantes"] <= 2
    assert alertas[vencido["id"]]["horas_restantes"] < -2.9
    assert list(alertas)[0] == vencido["id"]             # primero el más urgente
    # un ticket cerrado no alerta
    client.put(f"/tickets/{vencido['id']}/status", headers=admin, json={"estado": "Cerrado"})
    _set_deadline(vencido["id"], timedelta(hours=-3))
    assert vencido["id"] not in {a["id"] for a in client.get("/tickets/sla/alertas", headers=admin).json()}
    assert client.get("/tickets/sla/alertas", headers=cli).status_code == 403


def test_avisos_una_sola_vez_por_nivel(client, admin, make_user, make_ticket, mails):
    cli, _ = make_user()
    tec_h, tec = make_user("tecnico")
    t = make_ticket(cli)
    client.put(f"/tickets/{t['id']}/assign", headers=admin, json={"tecnico_id": tec["id"]})
    rma = t["numero_rma"]

    _set_deadline(t["id"], timedelta(hours=2))
    assert _revisar() == 1
    assert _notifs(client, tec_h, rma) == [f"SLA por vencer: {rma}"]
    assert _notifs(client, admin, rma) == []                 # por vencer: solo el técnico
    assert _revisar() == 0                                   # no repite

    _set_deadline(t["id"], timedelta(hours=-1))              # ahora vencido (otro vencimiento)
    assert _revisar() == 1
    assert f"SLA vencido: {rma}" in _notifs(client, tec_h, rma)
    assert f"SLA vencido: {rma}" in _notifs(client, admin, rma)   # vencido: también los admins
    assert _revisar() == 0
    assert len(mails) == 3 and all(len(lineas) == 2 for _, lineas in mails)   # 1 mail por persona y vuelta


def test_sin_tecnico_avisa_a_los_admins(client, admin, make_user, make_ticket, mails):
    cli, _ = make_user()
    t = make_ticket(cli)
    _set_deadline(t["id"], timedelta(hours=1))
    assert _revisar() == 1
    assert _notifs(client, admin, t["numero_rma"]) == [f"SLA por vencer: {t['numero_rma']}"]


def test_un_mail_por_persona_con_todos_sus_tickets(client, admin, make_user, make_ticket, mails):
    cli, _ = make_user()
    tec_h, tec = make_user("tecnico")
    for _ in range(3):
        t = make_ticket(cli)
        client.put(f"/tickets/{t['id']}/assign", headers=admin, json={"tecnico_id": tec["id"]})
        _set_deadline(t["id"], timedelta(hours=1))
    assert _revisar() == 3
    assert [(d, len(l)) for d, l in mails] == [([tec["username"]], 4)]   # encabezado + 3 tickets


def test_se_puede_desactivar(client, admin, make_user, make_ticket):
    cli, _ = make_user()
    t = make_ticket(cli)
    _set_deadline(t["id"], timedelta(hours=1))
    client.put("/config/ajustes", headers=admin, json={"sla_alertas": False})
    try:
        assert _revisar() == 0
    finally:
        client.put("/config/ajustes", headers=admin, json={"sla_alertas": True})
