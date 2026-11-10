"""Ubicaciones (dónde se guarda cada equipo y repuesto) y envíos a garantía del fabricante."""
import io
import uuid
from datetime import datetime, timedelta, timezone


def _u(client, h, nombre, padre=None):
    r = client.post("/ubicaciones", headers=h, json={"nombre": nombre, "padre_id": padre})
    assert r.status_code == 201, r.text
    return r.json()


def _nombre():
    return f"Dep-{uuid.uuid4().hex[:5]}"


def test_arbol_de_ubicaciones(client, admin, make_user):
    tec, _ = make_user(rol="tecnico")
    dep = _u(client, admin, _nombre())
    est = _u(client, admin, "Estante B", dep["id"])
    b3 = _u(client, admin, "B3", est["id"])
    assert b3["ruta"] == f"{dep['nombre']} › Estante B › B3" and b3["codigo"].startswith("U-")
    # Nombres repetidos en el mismo lugar no; en otro sí
    assert client.post("/ubicaciones", headers=admin, json={"nombre": "estante b", "padre_id": dep["id"]}).status_code == 400
    assert client.post("/ubicaciones", headers=admin, json={"nombre": "B3", "padre_id": dep["id"]}).status_code == 201
    # Sin ciclos
    r = client.put(f"/ubicaciones/{dep['id']}", headers=admin, json={"padre_id": b3["id"]})
    assert r.status_code == 400 and "sí misma" in r.json()["detail"]
    # Renombrar cambia la ruta de los hijos
    client.put(f"/ubicaciones/{est['id']}", headers=admin, json={"nombre": "Estante Azul"})
    assert next(x for x in client.get("/ubicaciones", headers=tec).json() if x["id"] == b3["id"])["ruta"].endswith("Estante Azul › B3")
    # Solo el admin las crea; el técnico las ve
    assert client.post("/ubicaciones", headers=tec, json={"nombre": "X"}).status_code == 403
    # Borrar: con hijos no
    assert client.delete(f"/ubicaciones/{est['id']}", headers=admin).status_code == 400
    assert client.delete(f"/ubicaciones/{b3['id']}", headers=admin).status_code == 204


def test_mover_equipo_y_su_historial(client, admin, make_user, make_ticket):
    cli, _ = make_user()
    tec, _ = make_user(rol="tecnico")
    t = make_ticket(cli)
    dep = _u(client, admin, _nombre())
    a, b = _u(client, admin, "A1", dep["id"]), _u(client, admin, "Mesa", dep["id"])
    r = client.put(f"/tickets/{t['id']}/ubicacion", headers=tec, json={"ubicacion_id": a["id"]})
    assert r.status_code == 200 and r.json()["ubicacion_ruta"].endswith("A1") and r.json()["cambio"]
    assert client.put(f"/tickets/{t['id']}/ubicacion", headers=tec, json={"ubicacion_id": a["id"]}).json()["cambio"] is False
    client.put(f"/tickets/{t['id']}/ubicacion", headers=tec, json={"ubicacion_id": b["id"], "motivo": "escaneo"})
    hist = client.get(f"/tickets/{t['id']}/ubicacion/historial", headers=tec).json()
    assert [(h["desde"] or "", h["hacia"]) for h in hist][0][1].endswith("Mesa") and len(hist) == 2
    assert hist[0]["motivo"] == "escaneo" and hist[1]["desde"] is None
    # Queda en el historial del ticket y en el detalle (no para el cliente)
    ev = client.get(f"/tickets/{t['id']}/history", headers=admin).json()
    assert any(e["tipo_evento"] == "ubicacion_cambiada" for e in ev)
    assert client.get(f"/tickets/{t['id']}", headers=tec).json()["ubicacion_ruta"].endswith("Mesa")
    vista_cliente = client.get(f"/tickets/{t['id']}", headers=cli).json()
    assert vista_cliente["ubicacion_ruta"] is None and vista_cliente["ubicacion_id"] is None
    assert client.put(f"/tickets/{t['id']}/ubicacion", headers=cli, json={"ubicacion_id": a["id"]}).status_code == 403
    # Contenido de la ubicación (con sububicaciones)
    c = client.get(f"/ubicaciones/{dep['id']}/contenido", headers=tec).json()
    assert [e["id"] for e in c["equipos"]] == [t["id"]]
    # Desactivar con algo guardado no; borrar una usada no (se desactiva)
    assert client.put(f"/ubicaciones/{b['id']}", headers=admin, json={"activa": False}).status_code == 400
    client.put(f"/tickets/{t['id']}/ubicacion", headers=tec, json={"ubicacion_id": None})
    r = client.delete(f"/ubicaciones/{b['id']}", headers=admin)
    assert r.status_code == 400 and "desactivala" in r.json()["detail"]
    assert client.put(f"/ubicaciones/{b['id']}", headers=admin, json={"activa": False}).status_code == 200
    r = client.put(f"/tickets/{t['id']}/ubicacion", headers=tec, json={"ubicacion_id": b["id"]})
    assert r.status_code == 400 and "desactivada" in r.json()["detail"]


def test_escaneo_y_etiquetas(client, admin, make_user, make_ticket):
    cli, _ = make_user()
    t = make_ticket(cli)
    est = _u(client, admin, _nombre())
    assert client.get("/ubicaciones/escaneo", headers=admin, params={"codigo": est["codigo"].lower()}).json()["tipo"] == "ubicacion"
    assert client.get("/ubicaciones/escaneo", headers=admin, params={"codigo": t["numero_rma"]}).json()["id"] == t["id"]
    cod = f"R-{uuid.uuid4().hex[:5]}"
    p = client.post("/parts/", headers=admin, json={"nombre": "Pila CR2032", "codigo": cod, "proveedor": "X", "ubicacion_id": est["id"]}).json()
    assert p["ubicacion_ruta"] == est["ruta"]
    s = client.get("/ubicaciones/escaneo", headers=admin, params={"codigo": cod}).json()
    assert s["tipo"] == "repuesto" and s["ubicacion_ruta"] == est["ruta"]
    assert client.get("/ubicaciones/escaneo", headers=admin, params={"codigo": "NADA-123"}).status_code == 404
    for url in (f"/ubicaciones/{est['id']}/etiqueta", f"/parts/{p['id']}/etiqueta"):
        r = client.get(url, headers=admin, params={"formato": "html"})
        assert r.status_code == 200 and "<svg" in r.text
        assert client.get(url, headers=admin, params={"formato": "pdf"}).content[:4] == b"%PDF"
    assert est["codigo"] in client.get(f"/ubicaciones/{est['id']}/etiqueta", headers=admin, params={"formato": "html"}).text
    assert client.get(f"/ubicaciones/{est['id']}/etiqueta", headers=cli).status_code == 403


def test_repuestos_con_ubicacion(client, admin, make_user):
    tec, _ = make_user(rol="tecnico")
    caj = _u(client, admin, _nombre())
    ids = []
    for i in range(3):
        ids.append(client.post("/parts/", headers=admin, json={"nombre": f"Tornillo {i}", "codigo": f"T-{uuid.uuid4().hex[:6]}",
                                                               "proveedor": "X"}).json()["id"])
    pend = client.get("/ubicaciones/pendientes", headers=tec).json()
    assert set(ids) <= {r["id"] for r in pend["repuestos_sin_ubicacion"]}
    assert client.post("/parts/ubicacion", headers=tec, json={"ids": ids, "ubicacion_id": caj["id"]}).json() == {"movidos": 3}
    partes = {p["id"]: p for p in client.get("/parts/", headers=tec).json()}
    assert all(partes[i]["ubicacion_ruta"] == caj["ruta"] for i in ids)
    # Editar el repuesto sin mandar la ubicación no la borra; mandándola en null sí
    p = partes[ids[0]]
    body = {k: p[k] for k in ("nombre", "codigo", "stock", "proveedor", "precio", "categoria", "stock_minimo")}
    assert client.put(f"/parts/{p['id']}", headers=admin, json=body).json()["ubicacion_id"] == caj["id"]
    assert client.put(f"/parts/{p['id']}", headers=admin, json={**body, "ubicacion_id": None}).json()["ubicacion_id"] is None
    assert len(client.get(f"/ubicaciones/{caj['id']}/contenido", headers=tec).json()["repuestos"]) == 2


def test_importar_repuestos_con_ubicacion(client, admin):
    raiz = _nombre()
    cod = f"IMP-{uuid.uuid4().hex[:5]}"
    csv = f"Código,Nombre,Proveedor,Ubicación\n{cod},Flex de pantalla,Sur,{raiz} > Estante C > Cajón 4\n"
    r = client.post("/importar/repuestos/vista-previa", headers=admin, files={"archivo": ("r.csv", csv.encode(), "text/csv")})
    assert r.status_code == 200, r.text
    an = r.json()
    assert an["resumen"]["crear"] == 1, an
    r = client.post("/importar/repuestos", headers=admin, files={"archivo": ("r.csv", csv.encode(), "text/csv")})
    assert r.status_code == 200, r.text
    p = next(x for x in client.get("/parts/", headers=admin).json() if x["codigo"] == cod)
    assert p["ubicacion_ruta"] == f"{raiz} › Estante C › Cajón 4"
    # Volver a importar lo mismo: sin cambios
    an = client.post("/importar/repuestos/vista-previa", headers=admin, files={"archivo": ("r.csv", csv.encode(), "text/csv")}).json()
    assert an["resumen"]["sin_cambios"] == 1, an


def _envio(client, h, tid, **extra):
    return client.post(f"/tickets/{tid}/envios", headers=h, json={"destino": "Servicio oficial ASUS", "numero_caso": "AS-77812",
                                                                  "transportista": "OCA", "guia": "OCA123", **extra})


def test_envio_al_fabricante_y_vuelta(client, admin, make_user, make_ticket):
    cli, _ = make_user()
    tec, _ = make_user(rol="tecnico")
    t = make_ticket(cli)
    mesa = _u(client, admin, _nombre())
    client.put(f"/tickets/{t['id']}/ubicacion", headers=tec, json={"ubicacion_id": mesa["id"]})
    estimada = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    r = _envio(client, tec, t["id"], contenido="Solo la placa", accesorios="Cargador", fecha_estimada=estimada)
    assert r.status_code == 201, r.text
    e = r.json()
    assert e["estado"] == "enviado" and e["dias"] == 0 and not e["atrasado"]
    d = client.get(f"/tickets/{t['id']}", headers=tec).json()
    assert d["estado"] == "En servicio técnico oficial" and d["ubicacion_ruta"] == "Fuera del taller"
    assert d["envio_abierto"]["numero_caso"] == "AS-77812"
    # El cliente ve el estado, no los datos del envío
    dc = client.get(f"/tickets/{t['id']}", headers=cli).json()
    assert dc["estado"] == "En servicio técnico oficial" and dc["envio_abierto"] is None
    assert client.get(f"/tickets/{t['id']}/envios", headers=cli).status_code == 403
    # Mientras está afuera: no se mueve, no se cambia el estado a mano, no se manda otra vez
    assert client.put(f"/tickets/{t['id']}/ubicacion", headers=tec, json={"ubicacion_id": mesa["id"]}).status_code == 400
    assert client.put(f"/tickets/{t['id']}/status", headers=tec, json={"estado": "En reparación"}).status_code == 400
    assert _envio(client, tec, t["id"]).status_code == 400
    # "Fuera del taller"
    lista = client.get("/envios", headers=tec).json()
    assert any(x["id"] == e["id"] for x in lista["envios"]) and lista["resumen"]["afuera"] >= 1
    assert "Servicio oficial ASUS" in client.get("/envios/destinos", headers=tec).json()
    # Corregir datos
    assert client.put(f"/envios/{e['id']}", headers=tec, json={"guia": "OCA999"}).json()["guia"] == "OCA999"
    # Vuelta: reemplazado sin serie nueva no
    r = client.post(f"/envios/{e['id']}/recepcion", headers=tec, json={"resultado": "reemplazado"})
    assert r.status_code == 400 and "serie" in r.json()["detail"]
    r = client.post(f"/envios/{e['id']}/recepcion", headers=tec, json={"resultado": "reemplazado", "serie_nueva": "NEW-001",
                                                                        "comprobante": "NC-55", "ubicacion_id": mesa["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "recibido" and r.json()["resultado_texto"].startswith("Reemplazado")
    d = client.get(f"/tickets/{t['id']}", headers=tec).json()
    assert d["estado"] == "Equipo recibido" and d["numero_serie"] == "NEW-001" and d["ubicacion_id"] == mesa["id"]
    assert d["envio_abierto"] is None
    ev = [h["detalle"] for h in client.get(f"/tickets/{t['id']}/history", headers=admin).json()]
    assert any("Enviado a Servicio oficial ASUS" in (x or "") for x in ev) and any("Volvió de" in (x or "") for x in ev)
    assert any("NEW-001" in (x or "") for x in ev)
    # Se puede volver a mandar (otra vuelta)
    assert _envio(client, tec, t["id"]).status_code == 201
    assert len(client.get(f"/tickets/{t['id']}/envios", headers=tec).json()) == 2
    # Exportar
    r = client.get("/envios/exportar", headers=tec, params={"formato": "csv"})
    assert r.status_code == 200 and "AS-77812" in r.text and "NEW-001" in r.text
    assert client.get("/envios/exportar", headers=tec).content[:2] == b"PK"


def test_reglas_del_envio(client, admin, make_user, make_ticket):
    cli, _ = make_user()
    t = make_ticket(cli)
    assert client.post(f"/tickets/{t['id']}/envios", headers=admin, json={"destino": " "}).status_code in (400, 422)
    futuro = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    assert _envio(client, admin, t["id"], fecha_envio=futuro).status_code == 400
    pasado = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    antes = (datetime.now(timezone.utc) - timedelta(days=6)).isoformat()
    assert _envio(client, admin, t["id"], fecha_envio=pasado, fecha_estimada=antes).status_code == 400
    # Atrasado: la vuelta estimada ya pasó
    ayer = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    e = _envio(client, admin, t["id"], fecha_envio=pasado, fecha_estimada=ayer).json()
    assert e["atrasado"] and e["dias"] == 5
    assert any(x["id"] == e["id"] for x in client.get("/envios", headers=admin, params={"atrasados": True}).json()["envios"])
    # El estado no se pone a mano
    t2 = make_ticket(cli)
    r = client.put(f"/tickets/{t2['id']}/status", headers=admin, json={"estado": "En servicio técnico oficial"})
    assert r.status_code == 400 and "Enviar al fabricante" in r.json()["detail"]
    # Recepción anterior al envío, o dos veces
    r = client.post(f"/envios/{e['id']}/recepcion", headers=admin, json={"resultado": "sin_falla", "fecha_recepcion": antes})
    assert r.status_code == 400
    assert client.post(f"/envios/{e['id']}/recepcion", headers=admin, json={"resultado": "otro"}).status_code == 400
    assert client.post(f"/envios/{e['id']}/recepcion", headers=admin, json={"resultado": "sin_falla"}).status_code == 200
    assert client.post(f"/envios/{e['id']}/recepcion", headers=admin, json={"resultado": "sin_falla"}).status_code == 400
    # Ticket cerrado: no se manda
    client.put(f"/tickets/{t['id']}/status", headers=admin, json={"estado": "Cerrado"})
    r = _envio(client, admin, t["id"])
    assert r.status_code == 400 and "cerrado" in r.json()["detail"]


def test_pendientes_de_ordenar(client, admin, make_user, make_ticket):
    cli, _ = make_user()
    t = make_ticket(cli)
    p = client.get("/ubicaciones/pendientes", headers=admin).json()
    assert any(x["id"] == t["id"] for x in p["equipos_sin_ubicacion"]) and p["dias"] == 7
    u = _u(client, admin, _nombre())
    client.put(f"/tickets/{t['id']}/ubicacion", headers=admin, json={"ubicacion_id": u["id"]})
    p = client.get("/ubicaciones/pendientes", headers=admin, params={"dias": 1}).json()
    assert not any(x["id"] == t["id"] for x in p["equipos_sin_ubicacion"] + p["equipos_quietos"])
