"""Notificaciones por email, contra un servidor SMTP de prueba (aiosmtpd)."""
import email as email_lib
import socket
import uuid
from email import policy

import pytest
from aiosmtpd.controller import Controller

from backend.app import database
from backend.app.services import email


class _Buzon:
    def __init__(self):
        self.mensajes = []

    async def handle_DATA(self, server, session, envelope):
        self.mensajes.append(email_lib.message_from_bytes(envelope.content, policy=policy.default))
        return "250 OK"

    def para(self, direccion):
        return [m for m in self.mensajes if direccion in m["To"]]


def _puerto_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def smtp(client, admin):
    buzon = _Buzon()
    ctrl = Controller(buzon, hostname="127.0.0.1", port=_puerto_libre())
    ctrl.start()
    client.put("/config/ajustes", headers=admin, json={
        "email_activo": True, "smtp_origen": "panel", "smtp_host": "127.0.0.1", "smtp_port": ctrl.port,
        "smtp_seguridad": "ninguna", "smtp_usuario": "", "smtp_remitente": "Taller GEZARMA <rma@test.com>"})
    yield buzon
    email.esperar_envios()
    client.put("/config/ajustes", headers=admin, json={"email_activo": False, "smtp_origen": "env"})
    ctrl.stop()


@pytest.fixture
def cliente(client, admin):
    nombre = f"cli_{uuid.uuid4().hex[:6]}"
    mail = f"{nombre}@cliente.com"
    client.post("/register", json={"username": nombre, "nombre": "Ana Cliente", "email": mail, "password": "secret1"})
    h = {"Authorization": "Bearer " + client.post("/login", data={"username": nombre, "password": "secret1"}).json()["access_token"]}
    return h, mail


def _adjuntos(msg):
    return [(p.get_filename(), p.get_content_type()) for p in msg.iter_attachments()]


def test_mail_de_prueba(client, admin, smtp):
    r = client.post("/config/email/prueba", headers=admin, json={"destino": "yo@test.com"})
    assert r.status_code == 200, r.text
    m = smtp.para("yo@test.com")[0]
    assert m["Subject"] == "Prueba de email de GEZARMA"
    assert "Taller GEZARMA" in m["From"]


def test_mail_de_prueba_muestra_el_error_real(client, admin, smtp):
    client.put("/config/ajustes", headers=admin, json={"smtp_port": _puerto_libre()})   # nadie escucha ahí
    r = client.post("/config/email/prueba", headers=admin, json={"destino": "yo@test.com"})
    assert r.status_code == 400 and "rechazó la conexión" in r.json()["detail"]


def test_cliente_recibe_cambio_de_estado(client, admin, smtp, cliente, make_ticket):
    h, mail = cliente
    t = make_ticket(h, serie="MAIL-1")
    client.put(f"/tickets/{t['id']}/status", headers=admin, json={"estado": "En reparación"})
    email.esperar_envios()
    m = smtp.para(mail)[0]
    assert m["Subject"] == f"{t['numero_rma']}: En reparación"
    cuerpo = m.get_body(("plain",)).get_content()
    assert "Ana Cliente" in cuerpo and "/seguimiento?rma=" in cuerpo and "serie=MAIL-1" in cuerpo
    assert m.get_body(("html",)) is not None and _adjuntos(m) == []


def test_al_despachar_se_adjunta_el_remito(client, admin, smtp, cliente, make_ticket):
    h, mail = cliente
    t = make_ticket(h)
    client.put(f"/tickets/{t['id']}/shipping", headers=admin, json={"empresa_transporte": "Andreani", "tracking_number": "AN-1"})
    client.put(f"/tickets/{t['id']}/status", headers=admin, json={"estado": "Enviado al cliente"})
    email.esperar_envios()
    m = smtp.para(mail)[-1]
    assert _adjuntos(m) == [(f"remito-{t['numero_rma']}.pdf", "application/pdf")]
    assert "AN-1" in m.get_body(("plain",)).get_content()


def test_presupuesto_listo_con_pdf(client, admin, smtp, cliente, make_ticket):
    h, mail = cliente
    t = make_ticket(h)
    client.post(f"/budget/tickets/{t['id']}/presupuesto", headers=admin,
                json={"items": [{"descripcion": "Pantalla", "cantidad": 1, "costo_interno": 777, "precio_cliente": 150000}]})
    client.patch(f"/budget/tickets/{t['id']}/presupuesto/estado", headers=admin, json={"estado": "enviado"})
    email.esperar_envios()
    m = smtp.para(mail)[-1]
    assert "presupuesto para aprobar" in m["Subject"]
    cuerpo = m.get_body(("plain",)).get_content()
    assert "150.000,00" in cuerpo and "777" not in cuerpo
    assert _adjuntos(m) == [(f"presupuesto-{t['numero_rma']}.pdf", "application/pdf")]


def test_tecnico_recibe_asignacion(client, admin, smtp, make_user, make_ticket):
    cli, _ = make_user()
    tec_h, tec = make_user("tecnico")
    t = make_ticket(cli)
    client.put(f"/tickets/{t['id']}/assign", headers=admin, json={"tecnico_id": tec["id"]})
    email.esperar_envios()
    m = smtp.para(tec["email"])[0]
    assert m["Subject"] == f"Te asignaron el {t['numero_rma']}"
    assert f"#ticket={t['id']}" in m.get_body(("plain",)).get_content()


def test_admins_reciben_stock_bajo(client, admin, smtp):
    codigo = f"R-{uuid.uuid4().hex[:6]}"
    p = client.post("/parts/", headers=admin, json={"nombre": "Fuente", "codigo": codigo, "stock": 5,
                                                    "proveedor": "X", "precio": 1, "stock_minimo": 3}).json()
    p["stock"] = 2
    client.put(f"/parts/{p['id']}", headers=admin, json=p)
    email.esperar_envios()
    assert any("Stock bajo: Fuente" in m["Subject"] for m in smtp.para("admin@gezarma.local"))


def test_eventos_desactivados_no_envian(client, admin, smtp, cliente, make_ticket):
    h, mail = cliente
    t = make_ticket(h)
    client.put("/config/ajustes", headers=admin, json={"email_cliente_estado": False})
    try:
        client.put(f"/tickets/{t['id']}/status", headers=admin, json={"estado": "En revisión"})
        email.esperar_envios()
        assert smtp.para(mail) == []
    finally:
        client.put("/config/ajustes", headers=admin, json={"email_cliente_estado": True})


def test_si_la_transaccion_se_revierte_no_sale_el_mail():
    enviados = []
    db = database.SessionLocal()
    try:
        email.programar(db, lambda s: enviados.append(1))
        db.rollback()
        db.commit()
    finally:
        db.close()
    email.esperar_envios()
    assert enviados == []


def test_si_el_smtp_falla_el_sistema_sigue_andando(client, admin, smtp, cliente, make_ticket):
    h, _ = cliente
    t = make_ticket(h)
    client.put("/config/ajustes", headers=admin, json={"smtp_port": _puerto_libre()})
    r = client.put(f"/tickets/{t['id']}/status", headers=admin, json={"estado": "En diagnóstico"})
    assert r.status_code == 200
    email.esperar_envios()
    assert "No se pudo conectar" in client.get("/config/email/estado", headers=admin).json()["ultimo_error"]
