"""Panel de control personalizable: disposición por usuario y predeterminado del equipo."""

BASE = [{"id": "tickets", "visible": True, "ancho": "completo"}, {"id": "resumen_nuevos", "visible": False, "ancho": "mitad"}]


def test_cada_usuario_guarda_el_suyo(client, admin, make_user):
    tec, _ = make_user(rol="tecnico")
    cli, _ = make_user()
    for h in (tec, cli):
        r = client.get("/users/me/panel", headers=h).json()
        assert r["propio"] is False and "tickets" in r["bloques_conocidos"] and r["anchos"] == ["completo", "mitad", "cuarto"]
    r = client.put("/users/me/panel", headers=tec, json={"bloques": BASE})
    assert r.status_code == 200 and r.json()["propio"] is True and r.json()["bloques"][1] == BASE[1]
    assert client.get("/users/me/panel", headers=tec).json()["bloques"] == BASE
    assert client.get("/users/me/panel", headers=cli).json()["propio"] is False      # el de otro no cambia
    # Restablecer
    assert client.delete("/users/me/panel", headers=tec).json()["propio"] is False
    assert client.get("/users/me/panel").status_code == 401


def test_validacion(client, make_user):
    h, _ = make_user()
    malos = [[], [{"id": "nada"}], [{"id": "resumen", "ancho": "gigante"}], "x"]
    for b in malos:
        assert client.put("/users/me/panel", headers=h, json={"bloques": b}).status_code in (400, 422), b
    # Los tickets no se ocultan; los repetidos se descartan
    r = client.put("/users/me/panel", headers=h, json={"bloques": [{"id": "tickets", "visible": False},
                                                                     {"id": "guia"}, {"id": "guia", "ancho": "cuarto"}]}).json()
    assert r["bloques"] == [{"id": "tickets", "visible": True, "ancho": "completo"}, {"id": "guia", "visible": True, "ancho": "completo"}]


def test_predeterminado_del_equipo(client, admin, make_user):
    tec, _ = make_user(rol="tecnico")
    nuevo, _ = make_user(rol="tecnico")
    client.put("/users/me/panel", headers=tec, json={"bloques": BASE})
    equipo = [{"id": "alertas", "visible": True, "ancho": "completo"}, {"id": "tickets", "visible": True, "ancho": "completo"}]
    assert client.put("/users/me/panel/equipo", headers=tec, json={"bloques": equipo}).status_code == 403
    assert client.put("/users/me/panel/equipo", headers=admin, json={"bloques": equipo}).status_code == 200
    r = client.get("/users/me/panel", headers=nuevo).json()
    assert r["bloques"] == equipo and r["propio"] is False and r["equipo"] == equipo
    assert client.get("/users/me/panel", headers=tec).json()["bloques"] == BASE      # el que armó el suyo lo conserva
    # Restablecer el propio vuelve al del equipo
    assert client.delete("/users/me/panel", headers=tec).json()["bloques"] == equipo
    assert client.delete("/users/me/panel/equipo", headers=admin).json() == {"equipo": None}
    assert client.get("/users/me/panel", headers=nuevo).json()["bloques"] is None   # → el de fábrica (lo arma el frontend)


def test_resumen_viejo_se_parte_en_cuatro_tarjetas(client, make_user):
    """Quien guardó el panel cuando el resumen era un solo bloque lo sigue teniendo, ahora como 4 tarjetas."""
    h, _ = make_user()
    r = client.put("/users/me/panel", headers=h, json={"bloques": [
        {"id": "guia"}, {"id": "resumen", "visible": False, "ancho": "completo"}, {"id": "tickets"}]}).json()
    assert [b["id"] for b in r["bloques"]] == ["guia", "resumen_total", "resumen_nuevos", "resumen_proceso",
                                              "resumen_cerrados", "tickets"]
    assert all(b["ancho"] == "cuarto" and b["visible"] is False for b in r["bloques"][1:5])
    assert "resumen" not in r["bloques_conocidos"]


def test_no_se_expone_en_usuarios(client, admin, make_user):
    h, u = make_user()
    client.put("/users/me/panel", headers=h, json={"bloques": BASE})
    assert all("panel_config" not in x for x in client.get("/users/", headers=admin).json())
