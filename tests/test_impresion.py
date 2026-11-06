"""Impresoras térmicas: cada tamaño de etiqueta y cada ticketera, a 203 y 300 dpi.

Los PDF se rasterizan a la resolución exacta de la impresora, sin suavizado y en
blanco y negro puro (como imprime una térmica), y se comprueba que el QR y el
código de barras se lean con un lector real (zxing).
"""
import io

import pypdfium2 as pdfium
import pytest
import zxingcpp
from pypdf import PdfReader

from backend.app.services import impresion

TAMANOS = list(impresion.ETIQUETAS)
DPIS = ["203", "300"]


@pytest.fixture
def ticket(client, admin, make_user, make_ticket):
    cli, _ = make_user()
    t = make_ticket(cli, serie="SN-TERMICA-0042")
    return t


@pytest.fixture
def ajustar(client, admin):
    """Cambia ajustes durante el test y los deja como estaban."""
    previos = {}

    def _set(**valores):
        actuales = {a["clave"]: a["valor"] for a in client.get("/config/ajustes", headers=admin).json()}
        for k in valores:
            previos.setdefault(k, actuales[k])
        r = client.put("/config/ajustes", headers=admin, json=valores)
        assert r.status_code == 200, r.text
    yield _set
    if previos:
        client.put("/config/ajustes", headers=admin, json=previos)


def _rasterizar(pdf_bytes: bytes, dpi: int):
    pdf = pdfium.PdfDocument(pdf_bytes)
    assert len(pdf) == 1, "el documento tiene que salir en una sola página"
    img = pdf[0].render(scale=dpi / 72, no_smoothtext=True, no_smoothimage=True,
                        no_smoothpath=True).to_pil().convert("L")
    return img.point(lambda v: 255 if v > 127 else 0)   # sin grises


def _leidos(img) -> dict:
    return {r.format.name: r.text for r in zxingcpp.read_barcodes(img)}


def _pdf(client, admin, t, tipo):
    r = client.get(f"/tickets/{t['id']}/documentos/{tipo}?formato=pdf", headers=admin)
    assert r.status_code == 200, r.text
    return r.content


def _barras_entra(tamano, dpi, rma):
    return impresion.disenio_etiqueta(tamano, int(dpi), rma, [])["barras"] is not None


@pytest.mark.parametrize("dpi", DPIS)
@pytest.mark.parametrize("tamano", TAMANOS)
def test_etiqueta_legible_en_cada_tamano(client, admin, ticket, ajustar, tamano, dpi):
    ajustar(etiqueta_tamano=tamano, etiqueta_dpi=dpi)
    contenido = _pdf(client, admin, ticket, "etiqueta")
    box = PdfReader(io.BytesIO(contenido)).pages[0].mediabox
    mm = (round(float(box.width) / 72 * 25.4), round(float(box.height) / 72 * 25.4))
    assert mm == impresion.ETIQUETAS[tamano]

    leidos = _leidos(_rasterizar(contenido, int(dpi)))
    assert leidos.get("QRCode", "").endswith(f"/#ticket={ticket['id']}")
    if _barras_entra(tamano, dpi, ticket["numero_rma"]):
        assert leidos.get("Code128") == ticket["numero_rma"]
    else:
        assert "Code128" not in leidos   # no entra con barras de puntos enteros: solo QR


def test_barras_siempre_en_puntos_enteros():
    for dpi in (203, 300):
        for ancho in (40, 60, 100):
            bc = impresion.codigo_barras("RMA-2026-00001", dpi, ancho, 6)
            if bc:
                assert bc["puntos_por_barra"] >= 2
                assert abs(bc["modulo_mm"] - bc["puntos_por_barra"] * 25.4 / dpi) < 1e-3


@pytest.mark.parametrize("dpi", DPIS)
@pytest.mark.parametrize("ancho", ["58", "80"])
@pytest.mark.parametrize("tipo", ["ticket_ingreso", "ticket_entrega"])
def test_ticket_una_sola_pagina_y_legible(client, admin, make_user, make_ticket, ajustar, tipo, ancho, dpi):
    cli, _ = make_user()
    larga = ("NO ENCIENDE. EL EQUIPO SE APAGA SOLO AL CONECTAR EL CARGADOR Y HACE UN RUIDO "
             "AGUDO CERCA DEL PUERTO USB-C. " * 4).strip()
    r = client.post("/tickets/", headers=cli, json={"numero_serie": "SN-ROLLO-9", "fecha_compra": "2026-01-01T00:00:00",
                                                  "descripcion": larga, "producto": "Notebook Ultra 15 Pro Max"})
    assert r.status_code == 200, r.text
    t = r.json()
    client.put(f"/tickets/{t['id']}/diagnostic", headers=admin,
               json={"diagnostico": "Se reemplaza el conector de carga y se limpia la placa. " * 3})
    ajustar(ticketera_ancho=ancho, ticketera_dpi=dpi)
    contenido = _pdf(client, admin, t, tipo)

    reader = PdfReader(io.BytesIO(contenido))
    box = reader.pages[0].mediabox
    assert round(float(box.width) / 72 * 25.4) == int(ancho)
    largo = float(box.height) / 72 * 25.4
    assert 80 < largo < 400, largo                     # largo justo, sin hoja A4 de rollo
    texto = reader.pages[0].extract_text()
    assert t["numero_rma"] in texto and "SN-ROLLO-9" in texto

    leidos = _leidos(_rasterizar(contenido, int(dpi)))
    assert "/seguimiento?" in leidos.get("QRCode", "")
    if impresion.codigo_barras(t["numero_rma"], int(dpi), impresion.TICKETERA_IMPRIMIBLE_MM[ancho], 9):
        assert leidos.get("Code128") == t["numero_rma"]
    else:   # 58 mm a 203 dpi: el código con barras de 2 puntos no entra en 48 mm
        assert "Code128" not in leidos


def test_ticket_es_solo_para_el_taller(client, make_user, make_ticket):
    cli, _ = make_user()
    t = make_ticket(cli)
    for tipo in ("etiqueta", "ticket_ingreso", "ticket_entrega"):
        assert client.get(f"/tickets/{t['id']}/documentos/{tipo}", headers=cli).status_code == 403


def test_modo_navegador_usa_svg(client, admin, ticket, ajustar):
    ajustar(etiqueta_tamano="62x29", etiqueta_dpi="203")
    r = client.get(f"/tickets/{ticket['id']}/documentos/etiqueta?formato=html", headers=admin)
    assert "<svg" in r.text and "size: 62mm 29mm" in r.text.replace("  ", " ")
    r = client.get(f"/tickets/{ticket['id']}/documentos/ticket_ingreso?formato=html", headers=admin)
    assert "<svg" in r.text and "window.print" in r.text
