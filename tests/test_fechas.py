"""Fechas: se guardan en UTC, la API las manda con zona y los datos viejos se migran."""
import csv
import io
import sqlite3
from datetime import datetime, timedelta, timezone

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

from backend.app.config import ROOT_DIR
from backend.app.database import run_migrations


def _parse(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _ahora_utc():
    return datetime.now(timezone.utc)


def test_api_manda_las_fechas_en_utc_con_zona(client, admin, make_user, make_ticket):
    cli, _ = make_user()
    t = make_ticket(cli)
    client.put(f"/tickets/{t['id']}/status", headers=admin, json={"estado": "En reparación"})
    t = client.get(f"/tickets/{t['id']}", headers=admin).json()
    for campo in ("fecha_creacion", "fecha_actualizacion", "deadline_sla"):
        assert t[campo].endswith("Z"), (campo, t[campo])
        # instante correcto: cerca de ahora (o en el futuro, para el SLA)
        assert _parse(t[campo]) > _ahora_utc() - timedelta(minutes=5), (campo, t[campo])
    assert abs(_parse(t["fecha_actualizacion"]) - _ahora_utc()) < timedelta(minutes=5)
    # SLA de "En reparación" = 5 días desde ahora, no corrido 3 horas
    sla = _parse(t["deadline_sla"]) - _ahora_utc()
    assert timedelta(days=5) - timedelta(minutes=5) < sla < timedelta(days=5) + timedelta(minutes=5)


def test_fecha_de_compra_sigue_siendo_una_fecha_de_calendario(client, make_user, make_ticket):
    cli, _ = make_user()
    t = make_ticket(cli)   # fecha_compra = 2026-01-01
    assert t["fecha_compra"].startswith("2026-01-01T00:00:00")
    assert not t["fecha_compra"].endswith("Z")


def test_otras_respuestas_tambien_van_con_zona(client, admin, make_user, make_ticket, upload):
    cli, _ = make_user()
    t = make_ticket(cli)
    upload(cli, t["id"])
    client.post(f"/tickets/{t['id']}/comments/", headers=admin, json={"comentario": "hola", "is_internal": False})
    assert client.get(f"/tickets/{t['id']}/comments/", headers=cli).json()[0]["fecha"].endswith("Z")
    assert client.get(f"/tickets/{t['id']}/history", headers=cli).json()[0]["fecha"].endswith("Z")
    assert client.get(f"/tickets/{t['id']}/attachments", headers=cli).json()["adjuntos"][0]["fecha"].endswith("Z")
    assert client.get("/notifications/", headers=cli).json()[0]["fecha"].endswith("Z")


def test_cerrar_ticket_usa_utc_y_el_tiempo_de_reparacion_no_queda_corrido(client, admin, make_user, make_ticket):
    cli, _ = make_user()
    t = make_ticket(cli)
    client.put(f"/tickets/{t['id']}/status", headers=admin, json={"estado": "Cerrado"})
    t = client.get(f"/tickets/{t['id']}", headers=admin).json()
    cierre, creacion = _parse(t["fecha_cierre"]), _parse(t["fecha_creacion"])
    assert timedelta(0) <= cierre - creacion < timedelta(minutes=5)   # antes daba -3 h


def test_export_muestra_hora_local(client, admin, make_user, make_ticket):
    cli, _ = make_user()
    t = make_ticket(cli, serie="SN-EXPORT-HORA")
    creacion_utc = _parse(client.get(f"/tickets/{t['id']}", headers=admin).json()["fecha_creacion"])
    local = (creacion_utc - timedelta(hours=3)).strftime("%d/%m/%Y %H:%M")   # Buenos Aires = UTC-3
    texto = client.get("/export/tickets?formato=csv", headers=admin).content.decode("utf-8-sig")
    fila = next(r for r in csv.DictReader(io.StringIO(texto)) if r["Nº Serie"] == "SN-EXPORT-HORA")
    assert fila["Fecha Creación"] == local, (local, fila["Fecha Creación"])


def _cfg(url):
    cfg = Config(str(ROOT_DIR / "alembic.ini"))
    cfg.attributes["configure_logger"] = False
    cfg.attributes["url"] = url
    return cfg


def test_migracion_pasa_a_utc_las_fechas_que_estaban_en_hora_local(tmp_path):
    db = tmp_path / "fechas.db"
    url = f"sqlite:///{db}"
    command.upgrade(_cfg(url), "0002")
    con = sqlite3.connect(db)
    con.execute("insert into usuarios (id, username, nombre, rol, activo) values (1, 'u', 'U', 'cliente', 1)")
    # Ticket viejo: creado 10:00 UTC (= 07:00 hora local); cerrado y enviado a las 09:00 hora local
    # (= 12:00 UTC); la última actualización quedó guardada en hora local (09:00).
    con.execute("""insert into tickets (id, numero_rma, usuario_id, numero_serie, fecha_compra, descripcion,
                   estado, fecha_creacion, fecha_actualizacion, fecha_cierre, deadline_sla, fecha_envio)
                   values (1, 'RMA-1', 1, 'S', '2026-03-01 00:00:00.000000', 'x', 'Cerrado',
                   '2026-03-10 10:00:00.000000', '2026-03-10 09:00:00.000000', '2026-03-10 09:00:00.000000',
                   '2026-03-11 07:00:00.000000', '2026-03-10 09:00:00.000000')""")
    # El historial siempre se guardó en UTC: el último evento fue el cierre, 12:00 UTC
    con.execute("insert into historial_estados (ticket_id, tipo_evento, usuario_id, fecha) "
                "values (1, 'cambio_estado', 1, '2026-03-10 12:00:00.000000')")
    con.commit(); con.close()

    assert run_migrations(create_engine(url)) == []
    row = sqlite3.connect(db).execute(
        "select fecha_creacion, fecha_actualizacion, fecha_cierre, deadline_sla, fecha_envio, fecha_compra "
        "from tickets where id = 1").fetchone()
    creacion, actualizacion, cierre, sla, envio, compra = (r[:16] for r in row)
    assert creacion == "2026-03-10 10:00"        # ya estaba en UTC: no cambia
    assert cierre == "2026-03-10 12:00"          # 09:00 local → 12:00 UTC
    assert envio == "2026-03-10 12:00"
    assert sla == "2026-03-11 10:00"             # 07:00 local → 10:00 UTC
    assert actualizacion == "2026-03-10 12:00"   # reconstruida desde el historial
    assert compra == "2026-03-01 00:00"          # fecha de calendario: no cambia
