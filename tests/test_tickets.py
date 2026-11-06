"""Tickets: aislamiento entre clientes y notas internas."""


def test_cliente_solo_ve_sus_tickets(client, make_user, make_ticket):
    a, _ = make_user()
    b, _ = make_user()
    t = make_ticket(a)
    assert client.get(f"/tickets/{t['id']}", headers=b).status_code == 403
    assert all(x["id"] != t["id"] for x in client.get("/tickets/", headers=b).json())
    assert client.get(f"/tickets/{t['id']}/history", headers=b).status_code == 403


def test_notas_internas_no_llegan_al_cliente(client, make_user, make_ticket):
    a, _ = make_user()
    tec, _ = make_user("tecnico")
    t = make_ticket(a)
    secreto = "Cliente conflictivo, cobrar diagnóstico"
    client.post(f"/tickets/{t['id']}/comments/", headers=tec, json={"comentario": secreto, "is_internal": True})
    client.post(f"/tickets/{t['id']}/comments/", headers=tec, json={"comentario": "Recibido", "is_internal": False})

    comentarios = client.get(f"/tickets/{t['id']}/comments/", headers=a).json()
    historial = client.get(f"/tickets/{t['id']}/history", headers=a).json()
    assert [c["comentario"] for c in comentarios] == ["Recibido"]
    assert not any(secreto[:20] in (h.get("detalle") or "") for h in historial)
    assert any("Recibido" in (h.get("detalle") or "") for h in historial)   # lo público sí

    # el taller ve todo
    hist_tec = client.get(f"/tickets/{t['id']}/history", headers=tec).json()
    assert any(secreto[:20] in (h.get("detalle") or "") for h in hist_tec)
