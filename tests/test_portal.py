"""Portal del cliente: sus equipos agrupados por N° de serie, documentos y pendientes."""


def test_mis_equipos_agrupa_por_serie_y_muestra_pendientes(client, admin, make_user, make_ticket):
    h, _ = make_user()
    otro, _ = make_user()
    t1 = make_ticket(h, serie="PORTAL-1")
    t2 = make_ticket(h, serie="portal-1 ")          # misma serie, otra reparación
    t3 = make_ticket(h, serie="PORTAL-2")
    make_ticket(otro, serie="PORTAL-1")             # de otro cliente: no aparece
    client.post(f"/budget/tickets/{t1['id']}/presupuesto", headers=admin, json={
        "items": [{"descripcion": "Pantalla", "cantidad": 1, "costo_interno": 1, "precio_cliente": 100}]})
    client.patch(f"/budget/tickets/{t1['id']}/presupuesto/estado", headers=admin, json={"estado": "enviado"})
    client.put(f"/tickets/{t2['id']}/status", headers=admin, json={"estado": "Reparado"})
    client.put(f"/tickets/{t3['id']}/status", headers=admin, json={"estado": "Cerrado"})

    d = client.get("/portal/equipos", headers=h).json()
    assert d["resumen"] == {"equipos": 2, "reparaciones": 3, "en_curso": 2}
    eq1 = next(e for e in d["equipos"] if e["numero_serie"].strip().upper() == "PORTAL-1")
    assert [r["id"] for r in eq1["reparaciones"]] == [t2["id"], t1["id"]]     # la más reciente primero
    r1 = next(r for r in eq1["reparaciones"] if r["id"] == t1["id"])
    assert r1["documentos"] == ["ingreso", "presupuesto"]
    tipos = {(p["ticket_id"], p["tipo"]) for p in d["pendientes"]}
    assert tipos == {(t1["id"], "presupuesto"), (t2["id"], "retiro"), (t3["id"], "encuesta")}
    r3 = next(e for e in d["equipos"] if e["numero_serie"] == "PORTAL-2")["reparaciones"][0]
    assert "remito" in r3["documentos"]
    # Los documentos que lista se pueden bajar de verdad
    for doc in r1["documentos"] + r3["documentos"]:
        tid = t1["id"] if doc in r1["documentos"] else t3["id"]
        assert client.get(f"/tickets/{tid}/documentos/{doc}?formato=html", headers=h).status_code == 200


def test_sin_equipos(client, make_user):
    h, _ = make_user()
    d = client.get("/portal/equipos", headers=h).json()
    assert d == {"equipos": [], "pendientes": [], "resumen": {"equipos": 0, "reparaciones": 0, "en_curso": 0}}
