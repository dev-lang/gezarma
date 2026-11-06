"""Repuestos (datos internos ocultos al cliente) y exportación."""
import pytest


def test_catalogo_de_repuestos_solo_para_taller(client, make_user):
    cli, _ = make_user()
    tec, _ = make_user("tecnico")
    assert client.get("/parts/", headers=cli).status_code == 403
    assert client.get("/parts/", headers=tec).status_code == 200


def test_cliente_ve_repuestos_del_ticket_sin_datos_internos(client, admin, make_user, make_ticket):
    cli, _ = make_user()
    tec, _ = make_user("tecnico")
    t = make_ticket(cli, serie="SN-REP")
    part_id = client.get("/parts/", headers=admin).json()[0]["id"]
    assert client.post(f"/tickets/{t['id']}/parts", headers=tec,
                       json={"part_id": part_id, "cantidad": 1}).status_code == 200

    vistas = [
        client.get(f"/tickets/{t['id']}", headers=cli).json(),
        next(x for x in client.get("/tickets/", headers=cli).json() if x["id"] == t["id"]),
        client.get("/tickets/search/global?q=SN-REP", headers=cli).json()[0],
    ]
    for ticket in vistas:
        r = ticket["repuestos_usados"][0]
        assert r["nombre"] and r["codigo"] and r["cantidad"] == 1
        assert r["stock"] is None and r["proveedor"] is None and r["precio"] is None

    r = client.get(f"/tickets/{t['id']}", headers=tec).json()["repuestos_usados"][0]
    assert r["precio"] is not None and r["proveedor"] and r["stock"] is not None


@pytest.mark.parametrize("entidad", ["tickets", "users", "products", "parts",
                                     "usuarios", "productos", "repuestos"])
@pytest.mark.parametrize("formato", ["csv", "xlsx"])
def test_export_todas_las_entidades(client, admin, entidad, formato):
    # users/products/parts son los nombres que usa el panel de admin
    assert client.get(f"/export/{entidad}?formato={formato}", headers=admin).status_code == 200


def test_export_csv_con_bom_y_descripcion(client, admin, make_user, make_ticket):
    cli, _ = make_user()
    make_ticket(cli)
    body = client.get("/export/tickets?formato=csv", headers=admin).content
    assert body.startswith(b"\xef\xbb\xbf")
    assert "Descripción".encode() in body


def test_cliente_no_exporta(client, make_user):
    cli, _ = make_user()
    assert client.get("/export/tickets", headers=cli).status_code == 403
