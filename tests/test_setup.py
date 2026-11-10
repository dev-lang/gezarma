"""Configuración inicial: estado del asistente, rubros, checklist configurable, SLA y datos de ejemplo."""
import os
import tempfile
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from backend.app import ajustes, auth, models
from backend.app.database import Base
from backend.app.services import rubros, setup as S


def test_estado_y_marcar_pasos(client, admin):
    r = client.get("/setup", headers=admin)
    assert r.status_code == 200
    e = r.json()
    assert set(e) >= {"terminado", "pospuesto", "pasos", "rubros", "demo", "hay_tickets_reales"}
    assert client.put("/setup", headers=admin, json={"paso": "taller"}).json()["pasos"].count("taller") == 1
    assert client.put("/setup", headers=admin, json={"paso": "taller"}).json()["pasos"].count("taller") == 1   # no se repite
    assert client.put("/setup", headers=admin, json={"paso": "cualquiera"}).status_code == 400
    assert client.put("/setup", headers=admin, json={"pospuesto": True}).json()["pospuesto"] is True
    fin = client.put("/setup", headers=admin, json={"terminado": True}).json()
    assert fin["terminado"] is True and fin["pospuesto"] is False
    guia = client.get("/config/guia", headers=admin).json()
    assert next(p for p in guia["pasos"] if p["id"] == "setup")["hecho"] is True
    client.put("/setup", headers=admin, json={"terminado": False})


def test_solo_administradores(client, make_user):
    tec, _ = make_user(rol="tecnico")
    for metodo, ruta in (("get", "/setup"), ("get", "/setup/rubros"), ("post", "/setup/demo"), ("delete", "/setup/demo")):
        assert getattr(client, metodo)(ruta, headers=tec).status_code == 403


def test_listado_de_rubros(client, admin):
    lista = client.get("/setup/rubros", headers=admin).json()
    ids = [r["id"] for r in lista]
    assert ids == ["celulares", "computacion", "consolas", "electro", "audio_tv", "herramientas", "general"]
    cel = lista[0]
    assert "Respaldo de datos" in cel["estados"] and cel["etiqueta"] == "50x25" and cel["sla"]["dias_reparacion"] == 2


def test_combinar_rubros():
    c = rubros.combinar(["celulares", "electro"])
    assert c["sla"] == (48, 72, 7)                    # el plazo más largo de cada uno
    assert c["etiqueta"] == "62x29"                   # no coinciden → la general
    assert rubros.combinar(["celulares"])["etiqueta"] == "50x25"
    assert set(c["estados"]) == {"Respaldo de datos", "En prueba"}
    assert c["accesorios"].count("Cargador") == 1     # sin repetir
    assert rubros.validar(["celulares", "x", "celulares"]) == ["celulares"]


def test_aplicar_rubros_idempotente(client, admin):
    assert client.post("/setup/rubros", headers=admin, json={"rubros": []}).status_code == 400
    r = client.post("/setup/rubros", headers=admin, json={"rubros": ["celulares", "consolas"]})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["sla"] == {"horas_nuevo": 24, "horas_diagnostico": 48, "dias_reparacion": 5}
    estados = {e["valor"]: e for e in client.get("/config/estados", headers=admin).json()}
    assert estados["Respaldo de datos"]["activo"]
    pub = client.get("/config/ajustes/publicos", headers=admin).json()
    assert "Chip / SIM" in pub["checklist_accesorios"] and "¿Lee discos?" in pub["checklist_controles"]
    assert "Consolas" in pub["producto_categorias"]
    nombres = [p["nombre"] for p in client.get("/config/plantillas", headers=admin).json()]
    assert "Pantalla rota" in nombres and "Stick drift" in nombres
    # Otra vez: no duplica nada
    res2 = client.post("/setup/rubros", headers=admin, json={"rubros": ["celulares", "consolas"]}).json()
    assert res2["estados"] == [] and res2["plantillas_agregadas"] == 0 and res2["controles"] == 0
    nombres2 = [p["nombre"] for p in client.get("/config/plantillas", headers=admin).json()]
    assert sorted(nombres2) == sorted(nombres)
    pub2 = client.get("/config/ajustes/publicos", headers=admin).json()
    assert pub2["checklist_controles"] == pub["checklist_controles"]
    assert client.get("/setup", headers=admin).json()["rubros"] == ["celulares", "consolas"]
    assert "rubro" in client.get("/setup", headers=admin).json()["pasos"]


def test_no_pisa_lo_que_cambio_el_taller(client, admin):
    client.put("/config/ajustes", headers=admin, json={"checklist_accesorios": "Mi accesorio\nCargador"})
    client.post("/setup/rubros", headers=admin, json={"rubros": ["herramientas"]})
    acc = client.get("/config/ajustes/publicos", headers=admin).json()["checklist_accesorios"]
    assert acc[:2] == ["Mi accesorio", "Cargador"] and "Maletín" in acc and acc.count("Cargador") == 1


def test_sla_configurable(client, admin, make_ticket):
    client.put("/config/ajustes", headers=admin, json={"sla_horas_nuevo": 72, "sla_aviso_horas": 4})
    t = make_ticket(admin)
    falta = datetime.fromisoformat(t["deadline_sla"].replace("Z", "+00:00")) - datetime.now().astimezone()
    assert timedelta(hours=71) < falta <= timedelta(hours=72)
    client.put("/config/ajustes", headers=admin, json={"sla_horas_nuevo": 24})


def test_checklist_con_preguntas_extra(client, admin, make_ticket):
    t = make_ticket(admin)
    r = client.put(f"/tickets/{t['id']}/checklist", headers=admin,
                   json={"accesorios": ["Cargador"], "controles": {"¿Lee discos?": False, "  ": True, "¿Gira?": None}})
    assert r.status_code == 200, r.text
    assert r.json()["checklist_ingreso"]["controles"] == {"¿Lee discos?": False, "¿Gira?": None}
    from backend.app.database import SessionLocal
    from backend.app.services.documentos import checklist_lineas
    db = SessionLocal()
    try:
        lineas = dict(checklist_lineas(db.get(models.Ticket, t["id"])))
        assert lineas["Lee discos"] == "No" and "Gira" not in lineas   # sin responder no sale
    finally:
        db.close()
    demasiadas = {f"P{i}": True for i in range(21)}
    assert client.put(f"/tickets/{t['id']}/checklist", headers=admin, json={"controles": demasiadas}).status_code == 422


def test_demo_no_con_tickets_reales(client, admin, make_ticket):
    make_ticket(admin)
    e = client.get("/setup", headers=admin).json()
    assert e["hay_tickets_reales"] and not e["demo"]["puede_crear"]
    r = client.post("/setup/demo", headers=admin)
    assert r.status_code == 400 and "reales" in r.json()["detail"]


# ── Datos de ejemplo, en una base aparte (la de los tests ya tiene tickets reales) ──
@pytest.fixture
def base_nueva():
    tmp = tempfile.mkdtemp(prefix="gezarma-setup-")
    eng = create_engine(f"sqlite:///{os.path.join(tmp, 'n.db')}", connect_args={"check_same_thread": False})
    event.listen(eng, "connect", lambda con, _: con.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    admin = models.Usuario(username="admin", nombre="Admin", email="a@a.com", rol=models.UserRole.ADMINISTRADOR.value,
                           password_hash=auth.get_password_hash("x123456"))
    db.add(admin)
    finales = {"Cerrado", "Cancelado"}
    for i, s in enumerate(models.TicketStatus):
        db.add(models.TicketStatusConfig(valor=s.value, etiqueta=s.value, orden=i, activo=True, es_final=s.value in finales))
    for nombre, texto in rubros.SEMILLA_PLANTILLAS:
        db.add(models.DiagnosticaPlantilla(nombre=nombre, texto=texto))
    db.add(models.Producto(marca="ASUS", modelo="X515 Laptop", categoria="Notebooks"))
    db.add(models.Repuesto(nombre="Pantalla", codigo="LCD-156-01", stock=5, proveedor="x", precio=1))
    db.commit()
    ajustes.invalidar_cache()
    yield db, admin
    db.close()
    ajustes.invalidar_cache()
    eng.dispose()


def test_rubro_cambia_las_plantillas_de_fabrica(base_nueva):
    db, admin = base_nueva
    res = S.aplicar_rubros(db, ["electro"], quitar_ejemplos=True)
    db.commit()
    nombres = {p.nombre for p in db.query(models.DiagnosticaPlantilla).all()}
    assert "No enciende" not in nombres and "Resistencia" in nombres and res["plantillas_quitadas"] == 7
    assert res["ejemplos_quitados"] == {"productos": 1, "repuestos": 1}
    assert not db.query(models.Producto).filter_by(modelo="X515 Laptop").first()


def test_demo_crear_y_borrar(base_nueva):
    db, admin = base_nueva
    S.aplicar_rubros(db, ["celulares", "computacion"])
    db.commit()
    res = S.crear_demo(db, admin)
    db.commit()
    assert res["tickets"] == 6
    tickets = db.query(models.Ticket).all()
    assert all(t.demo for t in tickets)
    est = {t.estado for t in tickets}
    assert {"Nuevo", "En diagnóstico", "Esperando repuestos", "Reparado", "Cerrado", "En servicio técnico oficial"} <= est
    assert db.query(models.EnvioExterno).count() == 1
    assert db.query(models.Ubicacion).filter_by(demo=True).count() == 2
    e = S.estado(db, admin)
    assert e["demo"] == {"tickets": 6, "puede_crear": False, "puede_borrar": True} and not e["hay_tickets_reales"]
    with pytest.raises(Exception):
        S.crear_demo(db, admin)

    # El taller usa un producto de ejemplo en un ticket real: ese producto y su cliente... el producto se queda
    prod = db.query(models.Producto).filter_by(demo=True).first()
    real = models.Ticket(numero_rma="RMA-REAL-1", numero_serie="REAL1", producto=prod.modelo, producto_id=prod.id,
                         descripcion="real", usuario_id=admin.id, estado="Nuevo", fecha_compra=datetime(2026, 1, 1))
    db.add(real)
    db.commit()
    out = S.borrar_demo(db)
    db.commit()
    assert out["borrados"]["tickets"] == 6 and out["conservados"]["productos"] == 1
    assert db.query(models.Ticket).count() == 1
    assert db.query(models.Usuario).filter_by(demo=True).count() == 0
    assert db.query(models.Repuesto).filter_by(demo=True).count() == 0
    assert db.query(models.Ubicacion).filter_by(demo=True).count() == 0
    assert db.query(models.HistorialEstado).count() == 0 and db.query(models.EnvioExterno).count() == 0
    assert db.get(models.Producto, prod.id).demo is False       # quedó como propio
    assert S.borrar_demo(db)["borrados"]["tickets"] == 0         # otra vez: nada


def test_tecnico_con_clave_temporal(client, admin):
    import uuid
    u = f"tec_{uuid.uuid4().hex[:6]}"
    r = client.post("/register", headers=admin, json={"username": u, "nombre": "Tec", "email": f"{u}@t.com",
                                                      "password": "Temp-123", "rol": "tecnico", "cambiar_clave": True})
    assert r.status_code == 200, r.text
    login = client.post("/login", data={"username": u, "password": "Temp-123"}).json()
    assert login["must_change_password"] is True
    # Un registro público no puede pedirlo (ni elegir rol)
    p = f"cli_{uuid.uuid4().hex[:6]}"
    client.post("/register", json={"username": p, "nombre": "C", "email": f"{p}@t.com", "password": "Clave-123", "cambiar_clave": True})
    assert client.post("/login", data={"username": p, "password": "Clave-123"}).json()["must_change_password"] is False


def test_aviso_de_sla_menor_que_el_plazo(client, admin):
    r = client.put("/config/ajustes", headers=admin, json={"sla_aviso_horas": 500})
    assert r.status_code == 400 and "sla_aviso_horas" in r.json()["detail"]["errores"]
    # Bajar el plazo por debajo del aviso actual también se rechaza
    r = client.put("/config/ajustes", headers=admin, json={"sla_horas_nuevo": 3, "sla_aviso_horas": 4})
    assert r.status_code == 400
    assert client.put("/config/ajustes", headers=admin, json={"sla_horas_nuevo": 30, "sla_aviso_horas": 6}).status_code == 200
    client.put("/config/ajustes", headers=admin, json={"sla_horas_nuevo": 24, "sla_aviso_horas": 4})
