"""Calendario de horas: cargar, mover, corregir y borrar tramos con reglas y registro de cambios."""
from datetime import datetime, timedelta

from backend.app.services import horas

HOY = horas.hoy()


def _iso(dia, hh, mm=0):
    """Hora del negocio (sin zona), como la manda la pantalla."""
    return datetime(dia.year, dia.month, dia.day, hh, mm).isoformat()


def _tramo(client, h, ticket_id=None, dia=None, desde=(9, 0), hasta=(10, 0), **extra):
    dia = dia or HOY - timedelta(days=1)
    body = {"ticket_id": ticket_id, "inicio": _iso(dia, *desde), "fin": _iso(dia, *hasta), **extra}
    return client.post("/tiempo", headers=h, json=body)


def test_cargar_y_ver_en_el_calendario(client, admin, make_user, make_ticket):
    cli, _ = make_user()
    tec, yo = make_user(rol="tecnico")
    t = make_ticket(cli)
    ayer = HOY - timedelta(days=1)
    r = _tramo(client, tec, t["id"], nota="Cambio de pantalla")
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["minutos"] == 60 and d["dia"] == ayer.isoformat() and d["editable"] and d["manual"]
    # Sin ticket: tarea del taller
    r = _tramo(client, tec, categoria="limpieza", desde=(10, 0), hasta=(10, 30))
    assert r.status_code == 201 and r.json()["categoria_etiqueta"].startswith("Limpieza")
    cal = client.get("/tiempo/calendario", headers=tec, params={"desde": ayer.isoformat(), "hasta": HOY.isoformat()}).json()
    assert cal["total_minutos"] == 90 and len(cal["registros"]) == 2
    assert cal["tecnicos"] == [] and cal["limite_correccion"]          # el técnico no elige a otros
    # El admin ve a todos o filtra por uno
    cal = client.get("/tiempo/calendario", headers=admin,
                     params={"desde": ayer.isoformat(), "hasta": ayer.isoformat(), "usuario_id": yo["id"]}).json()
    assert len(cal["registros"]) == 2 and any(x["id"] == yo["id"] for x in cal["tecnicos"])
    # El tiempo del ticket solo cuenta lo del ticket
    assert client.get(f"/tickets/{t['id']}/tiempo", headers=tec).json()["total_minutos"] == 60
    assert not any(e["tipo_evento"] == "tiempo_editado" for e in client.get(f"/tickets/{t['id']}/history", headers=cli).json())
    hist = client.get(f"/tickets/{t['id']}/history", headers=admin).json()
    assert any("tiempo_editado" in str(e) and "Horas cargadas: 1 h 00 min" in str(e) for e in hist)


def test_reglas_de_carga(client, admin, make_user, make_ticket):
    cli, _ = make_user()
    tec, _ = make_user(rol="tecnico")
    t = make_ticket(cli)
    ayer = HOY - timedelta(days=1)
    assert _tramo(client, tec, t["id"], desde=(11, 0), hasta=(10, 0)).status_code == 400          # fin antes
    r = _tramo(client, tec, t["id"], dia=HOY + timedelta(days=1))
    assert r.status_code == 400 and "futuro" in r.json()["detail"]
    assert _tramo(client, tec, t["id"]).status_code == 201
    r = _tramo(client, tec, t["id"], desde=(9, 30), hasta=(11, 0))
    assert r.status_code == 400 and "superpone" in r.json()["detail"]
    assert _tramo(client, tec, t["id"], desde=(10, 0), hasta=(11, 0)).status_code == 201         # pegado: vale
    r = _tramo(client, tec, t["id"], desde=(11, 0), hasta=(23, 59))      # 2 h + 13 h = 15 h: vale
    assert r.status_code == 201
    r = _tramo(client, tec, t["id"], desde=(7, 0), hasta=(8, 30))        # 16,5 h en el día
    assert r.status_code == 400 and "16 h" in r.json()["detail"]
    # Ticket o tarea: una de las dos
    assert _tramo(client, tec, None, desde=(1, 0), hasta=(2, 0)).status_code == 400
    assert _tramo(client, tec, t["id"], categoria="limpieza", desde=(1, 0), hasta=(2, 0)).status_code == 400
    assert _tramo(client, tec, None, categoria="siesta", desde=(1, 0), hasta=(2, 0)).status_code == 400
    # Un cliente no carga horas
    assert _tramo(client, cli, t["id"], dia=ayer - timedelta(days=1)).status_code == 403


def test_solo_duracion_va_despues_de_lo_cargado(client, make_user, make_ticket):
    cli, _ = make_user()
    tec, _ = make_user(rol="tecnico")
    t = make_ticket(cli)
    dia = HOY - timedelta(days=2)
    r = client.post("/tiempo", headers=tec, json={"ticket_id": t["id"], "fecha": dia.isoformat(), "minutos": 45})
    assert r.status_code == 201
    primero = r.json()
    assert horas.a_local(datetime.fromisoformat(primero["inicio"][:-1])).strftime("%H:%M") == "09:00"
    r = client.post("/tiempo", headers=tec, json={"categoria": "capacitacion", "fecha": dia.isoformat(), "minutos": 30}).json()
    assert r["inicio"] == primero["fin"] and r["minutos"] == 30
    # Hoy: termina ahora, no en el futuro
    r = client.post("/tiempo", headers=tec, json={"categoria": "otra", "fecha": HOY.isoformat(), "minutos": 1})
    assert r.status_code in (201, 400)          # 400 solo si a esta hora ya se pisa con algo (no debería)
    assert r.status_code == 201, r.text


def test_mover_corregir_y_registro_de_cambios(client, admin, make_user, make_ticket):
    cli, _ = make_user()
    tec, _ = make_user(rol="tecnico")
    otro, _ = make_user(rol="tecnico")
    t = make_ticket(cli)
    ayer, antes = HOY - timedelta(days=1), HOY - timedelta(days=3)
    reg = _tramo(client, tec, t["id"]).json()
    # Mover al día anterior, mismo horario
    r = client.put(f"/tiempo/{reg['id']}", headers=tec, json={"ticket_id": t["id"], "inicio": _iso(antes, 9),
                                                              "fin": _iso(antes, 10)})
    assert r.status_code == 200 and r.json()["dia"] == antes.isoformat() and r.json()["editado"]
    # Corregir la duración y pasarlo a una tarea del taller
    r = client.put(f"/tiempo/{reg['id']}", headers=tec, json={"categoria": "administracion", "inicio": _iso(antes, 9),
                                                              "fin": _iso(antes, 9, 40), "nota": "Era papeleo"})
    assert r.status_code == 200 and r.json()["minutos"] == 40 and r.json()["ticket_id"] is None
    cambios = client.get(f"/tiempo/{reg['id']}/cambios", headers=tec).json()
    assert [c["accion"] for c in cambios] == ["edicion", "movido", "alta"]
    assert cambios[0]["antes"]["ticket_id"] == t["id"] and cambios[0]["despues"]["categoria"] == "administracion"
    # Otro técnico no lo toca ni lo ve
    assert client.put(f"/tiempo/{reg['id']}", headers=otro, json={"categoria": "otra", "inicio": _iso(ayer, 9),
                                                                  "fin": _iso(ayer, 10)}).status_code == 403
    assert client.get(f"/tiempo/{reg['id']}/cambios", headers=otro).status_code == 403
    assert client.delete(f"/tiempo/{reg['id']}", headers=otro).status_code == 403
    # Mover encima de otro tramo: no
    _tramo(client, tec, t["id"], dia=ayer, desde=(14, 0), hasta=(15, 0))
    r = client.put(f"/tiempo/{reg['id']}", headers=tec, json={"categoria": "otra", "inicio": _iso(ayer, 14, 30),
                                                              "fin": _iso(ayer, 15, 10)})
    assert r.status_code == 400 and "superpone" in r.json()["detail"]
    # Borrar queda registrado
    assert client.delete(f"/tiempo/{reg['id']}", headers=tec).status_code == 204


def test_plazo_para_corregir(client, admin, make_user, make_ticket):
    cli, _ = make_user()
    tec, yo = make_user(rol="tecnico")
    t = make_ticket(cli)
    viejo = HOY - timedelta(days=10)
    r = _tramo(client, tec, t["id"], dia=viejo)
    assert r.status_code == 400 and "7 días" in r.json()["detail"]
    # El admin sí, y por el técnico
    r = _tramo(client, admin, t["id"], dia=viejo, usuario_id=yo["id"])
    assert r.status_code == 201 and r.json()["usuario_id"] == yo["id"]
    reg = r.json()
    cal = client.get("/tiempo/calendario", headers=tec, params={"desde": viejo.isoformat(), "hasta": viejo.isoformat()}).json()
    fila = cal["registros"][0]
    assert not fila["editable"] and "plazo" in fila["motivo_no_editable"]
    assert client.delete(f"/tiempo/{reg['id']}", headers=tec).status_code == 400
    # Un técnico no carga por otro
    assert _tramo(client, tec, t["id"], usuario_id=1).status_code == 403
    # Ajuste: con 30 días ya puede
    client.put("/config/ajustes", headers=admin, json={"horas_dias_correccion": 30})
    try:
        assert _tramo(client, tec, t["id"], dia=viejo, desde=(11, 0), hasta=(12, 0)).status_code == 201
        assert client.put("/config/ajustes", headers=admin, json={"horas_dias_correccion": 400}).status_code == 400
    finally:
        client.put("/config/ajustes", headers=admin, json={"horas_dias_correccion": 7})


def test_en_curso_no_se_edita(client, make_user, make_ticket):
    cli, _ = make_user()
    tec, _ = make_user(rol="tecnico")
    t = make_ticket(cli)
    client.post(f"/tickets/{t['id']}/tiempo/iniciar", headers=tec)
    cal = client.get("/tiempo/calendario", headers=tec, params={"desde": HOY.isoformat(), "hasta": HOY.isoformat()}).json()
    fila = next(x for x in cal["registros"] if x["en_curso"])
    assert not fila["editable"]
    ayer = HOY - timedelta(days=1)
    r = client.put(f"/tiempo/{fila['id']}", headers=tec, json={"ticket_id": t["id"], "inicio": _iso(ayer, 9), "fin": _iso(ayer, 10)})
    assert r.status_code == 400 and "pausalo" in r.json()["detail"]
    client.post(f"/tickets/{t['id']}/tiempo/pausar", headers=tec)
    assert client.get("/tiempo/actual", headers=tec).json() is None


def test_rango_y_exportar(client, admin, make_user, make_ticket):
    cli, _ = make_user()
    tec, _ = make_user(rol="tecnico")
    t = make_ticket(cli)
    _tramo(client, tec, t["id"])
    _tramo(client, tec, categoria="capacitacion", desde=(15, 0), hasta=(16, 0))
    assert client.get("/tiempo/calendario", headers=tec, params={"desde": "2026-01-01", "hasta": "2026-06-01"}).status_code == 400
    assert client.get("/tiempo/calendario", headers=tec, params={"desde": "2026-02-01", "hasta": "2026-01-01"}).status_code == 400
    p = {"desde": (HOY - timedelta(days=1)).isoformat(), "hasta": HOY.isoformat()}
    r = client.get("/tiempo/exportar", headers=tec, params={**p, "formato": "csv"})
    assert r.status_code == 200 and "Tarea del taller" in r.text and t["numero_rma"] in r.text and "Capacitación" in r.text
    r = client.get("/tiempo/exportar", headers=tec, params=p)
    assert r.status_code == 200 and r.content[:2] == b"PK"
    # El resumen del admin no se rompe con horas sin ticket
    assert client.get("/tiempo/resumen", headers=admin).status_code == 200
