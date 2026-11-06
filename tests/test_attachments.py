"""Adjuntos: solo el dueño del ticket (o taller) accede, y nunca sin autenticar."""


def test_cliente_accede_a_sus_adjuntos(client, make_user, make_ticket, upload):
    a, _ = make_user()
    t = make_ticket(a)
    adj = upload(a, t["id"]).json()["adjunto"]
    assert client.get(f"/tickets/{t['id']}/attachments", headers=a).status_code == 200
    r = client.get(f"/tickets/{t['id']}/attachments/{adj['id']}/download", headers=a)
    assert r.status_code == 200 and r.content == b"hola"


def test_otro_cliente_no_ve_ni_sube_adjuntos(client, make_user, make_ticket, upload):
    a, _ = make_user()
    b, _ = make_user()
    t = make_ticket(a)
    adj = upload(a, t["id"]).json()["adjunto"]
    assert client.get(f"/tickets/{t['id']}/attachments", headers=b).status_code == 403
    assert client.get(f"/tickets/{t['id']}/attachments/{adj['id']}/download", headers=b).status_code == 403
    assert upload(b, t["id"]).status_code == 403


def test_tecnico_accede_a_cualquier_adjunto(client, make_user, make_ticket, upload):
    a, _ = make_user()
    tec, _ = make_user("tecnico")
    t = make_ticket(a)
    adj = upload(a, t["id"]).json()["adjunto"]
    assert client.get(f"/tickets/{t['id']}/attachments/{adj['id']}/download", headers=tec).status_code == 200


def test_uploads_no_se_sirve_estatico(client, make_user, make_ticket, upload):
    a, _ = make_user()
    t = make_ticket(a)
    upload(a, t["id"])
    assert client.get(f"/uploads/ticket_{t['id']}/").status_code == 404


def test_descarga_no_acepta_token_en_la_url(client, make_user, make_ticket, upload):
    a, _ = make_user()
    t = make_ticket(a)
    adj = upload(a, t["id"]).json()["adjunto"]
    token = a["Authorization"].split()[1]
    r = client.get(f"/tickets/{t['id']}/attachments/{adj['id']}/download?token={token}")
    assert r.status_code == 401
