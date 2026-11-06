"""Documentos: orden de ingreso, remito, presupuesto y etiqueta (PDF o HTML)."""
import io

import pytest
from pypdf import PdfReader


@pytest.fixture
def ticket_completo(client, admin, make_user, make_ticket):
    cli, _ = make_user()
    t = make_ticket(cli, serie="DOC-123")
    client.post(f"/budget/tickets/{t['id']}/presupuesto", headers=admin, json={
        "items": [{"descripcion": "Cambio de pantalla", "cantidad": 1, "costo_interno": 999, "precio_cliente": 150000}]})
    return cli, t


def _pdf(r):
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    return PdfReader(io.BytesIO(r.content))


def _texto(reader):
    return " ".join(p.extract_text() for p in reader.pages)


@pytest.mark.parametrize("tipo", ["ingreso", "remito", "presupuesto"])
def test_documentos_a4_en_pdf(client, admin, ticket_completo, tipo):
    _, t = ticket_completo
    pdf = _pdf(client.get(f"/tickets/{t['id']}/documentos/{tipo}", headers=admin))
    assert len(pdf.pages) == 1
    assert t["numero_rma"] in _texto(pdf)


def test_etiqueta_mide_62x29(client, admin, ticket_completo):
    _, t = ticket_completo
    pdf = _pdf(client.get(f"/tickets/{t['id']}/documentos/etiqueta", headers=admin))
    box = pdf.pages[0].mediabox
    assert len(pdf.pages) == 1
    assert (round(float(box.width) / 72 * 25.4), round(float(box.height) / 72 * 25.4)) == (62, 29)


def test_presupuesto_muestra_precio_y_nunca_costo(client, admin, ticket_completo):
    _, t = ticket_completo
    texto = _texto(_pdf(client.get(f"/tickets/{t['id']}/documentos/presupuesto", headers=admin)))
    assert "150.000,00" in texto and "999" not in texto


def test_modo_navegador_devuelve_html_que_se_imprime(client, admin, ticket_completo):
    _, t = ticket_completo
    r = client.get(f"/tickets/{t['id']}/documentos/ingreso?formato=html", headers=admin)
    assert r.headers["content-type"].startswith("text/html")
    assert "window.print" in r.text and t["numero_rma"] in r.text
    # El formato por defecto sale del ajuste pdf_modo
    client.put("/config/ajustes", headers=admin, json={"pdf_modo": "navegador"})
    try:
        r = client.get(f"/tickets/{t['id']}/documentos/ingreso", headers=admin)
        assert r.headers["content-type"].startswith("text/html")
    finally:
        client.put("/config/ajustes", headers=admin, json={"pdf_modo": "servidor"})


def test_qr_apunta_al_seguimiento_y_a_la_url_publica(client, admin, ticket_completo):
    _, t = ticket_completo
    client.put("/config/ajustes", headers=admin, json={"public_url": "https://rma.ejemplo.com"})
    try:
        html = client.get(f"/tickets/{t['id']}/documentos/ingreso?formato=html", headers=admin).text
        assert f"https://rma.ejemplo.com/seguimiento?rma={t['numero_rma']}&amp;serie=DOC-123" in html
    finally:
        client.put("/config/ajustes", headers=admin, json={"public_url": ""})


def test_permisos_del_cliente(client, admin, ticket_completo, make_user):
    cli, t = ticket_completo
    url = f"/tickets/{t['id']}/documentos"
    assert client.get(f"{url}/ingreso", headers=cli).status_code == 200
    assert client.get(f"{url}/etiqueta", headers=cli).status_code == 403          # interna
    assert client.get(f"{url}/presupuesto", headers=cli).status_code == 404       # todavía en borrador
    client.patch(f"/budget/tickets/{t['id']}/presupuesto/estado", headers=admin, json={"estado": "enviado"})
    assert client.get(f"{url}/presupuesto", headers=cli).status_code == 200
    otro, _ = make_user()
    assert client.get(f"{url}/ingreso", headers=otro).status_code == 403
    assert client.get(f"{url}/inventado", headers=admin).status_code == 404
