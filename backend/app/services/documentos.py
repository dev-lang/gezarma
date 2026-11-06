"""
documentos.py — Orden de ingreso, remito de entrega, presupuesto y etiqueta.

Cada documento es una plantilla HTML (backend/app/templates/documentos/).
- Modo "navegador": se devuelve el HTML, que se abre e imprime solo.
- Modo "servidor": el mismo HTML se convierte a PDF con xhtml2pdf.
Así hay una sola versión de cada documento. Los PDF adjuntos a los mails
siempre se generan en el servidor.
"""
import base64
import io
from pathlib import Path
from urllib.parse import urlencode

import barcode
import qrcode
from barcode.writer import ImageWriter
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from .. import ajustes, models
from ..timeutils import utc_to_local, utcnow

TIPOS = {
    "ingreso": "Orden de ingreso",
    "remito": "Remito de entrega",
    "presupuesto": "Presupuesto",
    "etiqueta": "Etiqueta",
}
# Lo que puede pedir el cliente sobre sus propios tickets (la etiqueta es interna)
TIPOS_CLIENTE = {"ingreso", "remito", "presupuesto"}

_env = Environment(
    loader=FileSystemLoader(str(Path(__file__).resolve().parent.parent / "templates" / "documentos")),
    autoescape=select_autoescape(["html"]),
)


def _pesos(n) -> str:
    """1234.5 → '$ 1.234,50' (formato argentino)."""
    return "$ " + f"{float(n or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


_env.filters["pesos"] = _pesos


def _fecha(dt, con_hora=True):
    if not dt:
        return ""
    return utc_to_local(dt).strftime("%d/%m/%Y %H:%M" if con_hora else "%d/%m/%Y")


def _png_data_uri(img_bytes: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(img_bytes).decode()


def qr_png(texto: str) -> str:
    img = qrcode.make(texto, box_size=8, border=1)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return _png_data_uri(buf.getvalue())


# Código de barras para impresoras de etiquetas de 300 dpi: cada barra mide un
# número entero de puntos (2) y la imagen se ubica en su tamaño exacto, sin
# reescalar. Si se achica, las barras quedan desparejas y los lectores no lo leen.
BARCODE_DPI = 300
BARCODE_MODULO_MM = 2 * 25.4 / BARCODE_DPI   # 2 puntos ≈ 0,17 mm


def code128_png(texto: str) -> dict:
    """{"src": data URI, "ancho_mm": ..., "alto_mm": ...} en tamaño de impresión exacto."""
    buf = io.BytesIO()
    barcode.get("code128", texto, writer=ImageWriter()).write(buf, options={
        "write_text": False, "module_width": BARCODE_MODULO_MM, "module_height": 4.5,
        "quiet_zone": 2.0, "dpi": BARCODE_DPI})
    png = buf.getvalue()
    from PIL import Image
    w, h = Image.open(io.BytesIO(png)).size
    return {"src": _png_data_uri(png), "ancho_mm": round(w * 25.4 / BARCODE_DPI, 2),
            "alto_mm": round(h * 25.4 / BARCODE_DPI, 2)}


def url_seguimiento(base_url: str, t: models.Ticket) -> str:
    return f"{base_url}/seguimiento?" + urlencode({"rma": t.numero_rma, "serie": t.numero_serie or ""})


def url_taller(base_url: str, t: models.Ticket) -> str:
    """Abre el ticket en el sistema (para el taller, al escanear la etiqueta)."""
    return f"{base_url}/#ticket={t.id}"


def contexto(db: Session, t: models.Ticket, base_url: str) -> dict:
    estados = {e.valor: e.etiqueta for e in db.query(models.TicketStatusConfig).all()}
    pres = t.presupuesto
    items = []
    if pres:
        for i in pres.items:
            items.append({"descripcion": i.descripcion, "cantidad": i.cantidad,
                          "precio": i.precio_cliente, "subtotal": i.cantidad * i.precio_cliente})
    cliente = t.cliente
    return {
        "empresa": ajustes.get(db, "empresa_nombre") or "GEZARMA",
        "empresa_datos": [l for l in (ajustes.get(db, "empresa_datos") or "").splitlines() if l.strip()],
        "t": t,
        "estado": estados.get(t.estado, t.estado),
        "cliente": {
            "nombre": cliente.nombre if cliente else "",
            "email": cliente.email if cliente else "",
            "telefono": (cliente.telefono or "") if cliente else "",
            "tipo": ("Empresa" if cliente and cliente.tipo_cliente == "empresa" else "Persona"),
        },
        "tecnico": t.tecnico.nombre if t.tecnico else "",
        "fecha_ingreso": _fecha(t.fecha_creacion),
        "fecha_compra": t.fecha_compra.strftime("%d/%m/%Y") if t.fecha_compra else "",
        "fecha_envio": _fecha(t.fecha_envio),
        "fecha_cierre": _fecha(t.fecha_cierre),
        "hoy": _fecha(utcnow()),
        "repuestos": [{"nombre": r.nombre, "codigo": r.codigo, "cantidad": r.cantidad} for r in t.repuestos_usados],
        "presupuesto": ({
            "estado": pres.estado, "version": pres.version, "notas": pres.notas or "",
            "items": items, "total": sum(i["subtotal"] for i in items),
            "fecha": _fecha(pres.fecha_actualizacion),
        } if pres else None),
        "qr_seguimiento": qr_png(url_seguimiento(base_url, t)),
        "url_seguimiento": url_seguimiento(base_url, t),
        "qr_taller": qr_png(url_taller(base_url, t)),
        "barcode_rma": code128_png(t.numero_rma),
    }


def render_html(tipo: str, ctx: dict, imprimir: bool = False) -> str:
    return _env.get_template(f"{tipo}.html").render(**ctx, titulo=TIPOS[tipo], imprimir=imprimir)


def render_pdf(html: str) -> bytes:
    from xhtml2pdf import pisa
    out = io.BytesIO()
    res = pisa.CreatePDF(html, dest=out, encoding="utf-8")
    if res.err:
        raise RuntimeError("No se pudo generar el PDF")
    return out.getvalue()


def nombre_archivo(tipo: str, t: models.Ticket, ext: str) -> str:
    return f"{tipo}-{t.numero_rma}.{ext}"


def generar_pdf(db: Session, t: models.Ticket, tipo: str, base_url: str) -> bytes:
    return render_pdf(render_html(tipo, contexto(db, t, base_url)))
