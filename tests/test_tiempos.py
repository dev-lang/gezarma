"""Registro de tiempo de trabajo por técnico."""
from datetime import timedelta

from backend.app import database, models
from backend.app.timeutils import utcnow


def _atrasar_en_curso(usuario_id, minutos):
    """Simula que el trabajo en curso empezó hace `minutos`."""
    db = database.SessionLocal()
    try:
        r = db.query(models.TiempoTrabajo).filter_by(usuario_id=usuario_id, fin=None).one()
        r.inicio = utcnow() - timedelta(minutes=minutos)
        db.commit()
    finally:
        db.close()


def test_iniciar_pausar_y_total(client, admin, make_user, make_ticket):
    cli, _ = make_user()
    tec, datos = make_user(rol="tecnico")
    t = make_ticket(cli)
    d = client.post(f"/tickets/{t['id']}/tiempo/iniciar", headers=tec).json()
    assert d["en_curso_mio"] and d["registros"][0]["en_curso"]
    assert client.get("/tiempo/actual", headers=tec).json()["ticket_id"] == t["id"]
    _atrasar_en_curso(datos["id"], 45)
    d = client.post(f"/tickets/{t['id']}/tiempo/pausar", headers=tec).json()
    assert d["en_curso_mio"] is None and 44.9 <= d["total_minutos"] <= 45.5
    assert client.get("/tiempo/actual", headers=tec).json() is None
    d = client.post(f"/tickets/{t['id']}/tiempo/manual", headers=tec, json={"minutos": 30, "nota": "Prueba de carga"}).json()
    assert 74.9 <= d["total_minutos"] <= 75.5 and d["registros"][0]["manual"] is True
    assert d["por_tecnico"][0]["nombre"] == datos["nombre"]


def test_un_solo_trabajo_en_curso_por_tecnico(client, make_user, make_ticket):
    cli, _ = make_user()
    tec, _ = make_user(rol="tecnico")
    t1, t2 = make_ticket(cli), make_ticket(cli)
    client.post(f"/tickets/{t1['id']}/tiempo/iniciar", headers=tec)
    client.post(f"/tickets/{t1['id']}/tiempo/iniciar", headers=tec)          # repetir no duplica
    assert len(client.get(f"/tickets/{t1['id']}/tiempo", headers=tec).json()["registros"]) == 1
    client.post(f"/tickets/{t2['id']}/tiempo/iniciar", headers=tec)          # pasa al otro ticket
    d1 = client.get(f"/tickets/{t1['id']}/tiempo", headers=tec).json()
    assert d1["en_curso_mio"] is None and not d1["registros"][0]["en_curso"]
    assert client.get("/tiempo/actual", headers=tec).json()["ticket_id"] == t2["id"]


def test_costo_de_mano_de_obra_y_resumen(client, admin, make_user, make_ticket):
    cli, _ = make_user()
    tec, datos = make_user(rol="tecnico")
    t = make_ticket(cli)
    client.put("/config/ajustes", headers=admin, json={"tarifa_hora": 12000})
    try:
        d = client.post(f"/tickets/{t['id']}/tiempo/manual", headers=tec, json={"minutos": 90}).json()
        assert d["costo"] == 18000
        r = client.get("/tiempo/resumen", headers=admin).json()
        fila = next(x for x in r["tecnicos"] if x["nombre"] == datos["nombre"])
        assert fila["minutos"] == 90 and fila["tickets"] == 1 and fila["costo"] == 18000
    finally:
        client.put("/config/ajustes", headers=admin, json={"tarifa_hora": 0})
    assert client.get(f"/tickets/{t['id']}/tiempo", headers=tec).json()["costo"] is None
    assert client.get("/tiempo/resumen", headers=tec).status_code == 403


def test_permisos(client, admin, make_user, make_ticket):
    cli, _ = make_user()
    tec1, _ = make_user(rol="tecnico")
    tec2, _ = make_user(rol="tecnico")
    t = make_ticket(cli)
    assert client.get(f"/tickets/{t['id']}/tiempo", headers=cli).status_code == 403
    assert client.post(f"/tickets/{t['id']}/tiempo/iniciar", headers=cli).status_code == 403
    rid = client.post(f"/tickets/{t['id']}/tiempo/manual", headers=tec1, json={"minutos": 10}).json()["registros"][0]["id"]
    assert client.delete(f"/tiempo/{rid}", headers=tec2).status_code == 403      # no es suyo
    assert client.delete(f"/tiempo/{rid}", headers=tec1).status_code == 204
    rid = client.post(f"/tickets/{t['id']}/tiempo/manual", headers=tec1, json={"minutos": 10}).json()["registros"][0]["id"]
    assert client.delete(f"/tiempo/{rid}", headers=admin).status_code == 204     # el admin sí puede
    for minutos in (0, 1441):
        assert client.post(f"/tickets/{t['id']}/tiempo/manual", headers=tec1, json={"minutos": minutos}).status_code == 422
