"""
documentos.py — Orden de ingreso, remito de entrega, presupuesto y etiqueta.

Cada documento es una plantilla HTML (backend/app/templates/documentos/).
- Modo "navegador": se devuelve el HTML, que se abre e imprime solo.
- Modo "servidor": el mismo HTML se convierte a PDF con xhtml2pdf.
Así hay una sola versión de cada documento. Los PDF adjuntos a los mails
siempre se generan en el servidor.
"""
import io
import logging
from pathlib import Path
from urllib.parse import urlencode

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from .. import ajustes, idiomas, models
from . import impresion, recepcion
from ..timeutils import utc_to_local, utcnow

# xhtml2pdf avisa en el log por cada propiedad CSS que ignora (p. ej. border-collapse,
# que sí usa el modo navegador). No es un error: se baja a solo errores.
logging.getLogger("xhtml2pdf").setLevel(logging.ERROR)

TIPOS = {
    "ingreso": "Orden de ingreso",
    "remito": "Remito de entrega",
    "presupuesto": "Presupuesto",
    "etiqueta": "Etiqueta",
    "ticket_ingreso": "Comprobante de ingreso",
    "ticket_entrega": "Comprobante de entrega",
}
# Plantilla de cada tipo (por defecto, la de su mismo nombre)
PLANTILLAS = {"ticket_ingreso": "ticket.html", "ticket_entrega": "ticket.html"}
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


def url_seguimiento(base_url: str, t: models.Ticket) -> str:
    return f"{base_url}/seguimiento?" + urlencode({"rma": t.numero_rma, "serie": t.numero_serie or ""})


def url_taller(base_url: str, t: models.Ticket) -> str:
    """Abre el ticket en el sistema (para el taller, al escanear la etiqueta)."""
    return f"{base_url}/#ticket={t.id}"


def checklist_lineas(t: models.Ticket) -> list:
    """Checklist de ingreso como (etiqueta, valor); vacío si no se cargó."""
    c = t.checklist_ingreso
    if not c:
        return []
    si_no = lambda v, nada: "Sí" if v is True else ("No" if v is False else nada)
    accesorios = list(c.get("accesorios") or [])
    if c.get("accesorios_otros"):
        accesorios.append(c["accesorios_otros"])
    bloqueo = c.get("tiene_bloqueo")
    lineas = [
        ("Accesorios", ", ".join(accesorios) or "Ninguno"),
        ("Estado físico", c.get("estado_fisico") or "Sin observaciones"),
        ("Enciende", si_no(c.get("enciende"), "No se probó")),
        ("Bloqueo", "Sí (la clave se pide si hace falta)" if bloqueo is True else si_no(bloqueo, "No informado")),
    ]
    # Las preguntas extra del taller: solo las que se respondieron
    for pregunta, valor in (c.get("controles") or {}).items():
        if valor is not None:
            lineas.append((pregunta.strip("¿?") or pregunta, si_no(valor, "")))
    return lineas


def _firma(t: models.Ticket, momento: str, max_ancho_mm: float, max_alto_mm: float):
    f = t.firma(momento)
    if not f:
        return None
    escala = min(max_ancho_mm / f.ancho, max_alto_mm / f.alto)
    return {"src": recepcion.firma_data_uri(f), "aclaracion": f.aclaracion or "",
            "fecha": _fecha(f.fecha), "ancho_mm": round(f.ancho * escala, 2), "alto_mm": round(f.alto * escala, 2)}


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
        "url_seguimiento": url_seguimiento(base_url, t),
        # Orden de ingreso en hoja: 32 mm con el margen blanco (el QR, unos 26 mm)
        "qr_seguimiento": impresion.codigo_qr(url_seguimiento(base_url, t), impresion.QR_DPI_HOJA, 32),
        "url_taller": url_taller(base_url, t),
        "checklist": checklist_lineas(t),
        "firma_ingreso": _firma(t, "ingreso", 60, 18),
        "firma_entrega": _firma(t, "entrega", 60, 18),
        "politica_retiro": ajustes.politica_retiro(db),
        "reingreso": (t.reingreso_origen.numero_rma if t.reingreso_garantia and t.reingreso_origen else None),
    }


def _ctx_etiqueta(db: Session, ctx: dict, idioma=None) -> dict:
    t = ctx["t"]
    dpi = int(ajustes.get(db, "etiqueta_dpi"))
    lineas = [t.producto, f"SN {t.numero_serie or ''}", ctx["cliente"]["nombre"],
              idiomas.tr(f"Ingreso {ctx['fecha_ingreso'][:10]}", idioma)]
    return {"e": impresion.disenio_etiqueta(ajustes.get(db, "etiqueta_tamano"), dpi, t.numero_rma, lineas,
                                            qr_texto=ctx["url_taller"]),
            "dpi": dpi}


def _bloques_ticket(ctx: dict, entrega: bool) -> list:
    t, cli = ctx["t"], ctx["cliente"]
    B = lambda tipo, texto="", **kw: {"tipo": tipo, "texto": texto, **kw}
    bloques = [B("titulo", ctx["empresa"])]
    bloques += [B("texto", l, centro=True) for l in ctx["empresa_datos"]]
    bloques += [B("separador"),
                B("grande", "COMPROBANTE DE ENTREGA" if entrega else "COMPROBANTE DE INGRESO"),
                B("grande", t.numero_rma, mono=True),
                B("texto", f"Emitido el {ctx['hoy']}", centro=True),
                B("separador"),
                B("par", cli["nombre"], etiqueta="Cliente")]
    if cli["telefono"]:
        bloques.append(B("par", cli["telefono"], etiqueta="Teléfono"))
    bloques += [B("par", t.producto or "", etiqueta="Equipo"),
                B("par", t.numero_serie or "", etiqueta="N° de serie"),
                B("par", "Sí" if t.en_garantia else "No", etiqueta="Garantía"),
                B("par", ctx["fecha_ingreso"], etiqueta="Ingreso")]
    if entrega:
        bloques.append(B("par", ctx["estado"], etiqueta="Estado"))
        if t.diagnostico:
            bloques += [B("texto", "Trabajo realizado:", negrita=True), B("texto", t.diagnostico)]
        if ctx["repuestos"]:
            bloques.append(B("texto", "Repuestos:", negrita=True))
            bloques += [B("texto", f"{r['cantidad']} × {r['nombre']}") for r in ctx["repuestos"]]
        if t.tracking_number or t.empresa_transporte:
            bloques.append(B("par", f"{t.empresa_transporte or ''} {t.tracking_number or ''}".strip(), etiqueta="Envío"))
    else:
        if ctx["reingreso"]:
            bloques.append(B("texto", f"Reingreso en garantía de la reparación {ctx['reingreso']}", negrita=True))
        bloques += [B("texto", "Falla informada:", negrita=True), B("texto", t.descripcion or "")]
        if ctx["checklist"]:
            bloques.append(B("texto", "Recepción del equipo:", negrita=True))
            bloques += [B("par", valor, etiqueta=etq) for etq, valor in ctx["checklist"]]
    bloques += [B("separador"), B("qr"),
                B("texto", "Seguí tu reparación escaneando el código, o en la página de seguimiento con tu "
                           "N° de RMA y el N° de serie.", centro=True),
                B("barras")]
    firma = ctx["firma_entrega" if entrega else "firma_ingreso"]
    if firma:
        bloques.append(B("firma_img", "Recibí conforme" if entrega else "Conforme con el ingreso", firma=firma))
    elif entrega:
        bloques.append(B("firma", "Recibí conforme · firma y aclaración"))
    if not entrega:
        bloques.append(B("texto", "Conservá este comprobante para retirar el equipo.", centro=True))
        if ctx["politica_retiro"]:
            bloques.append(B("texto", ctx["politica_retiro"], centro=True))
    return bloques


def _ctx_ticket(db: Session, ctx: dict, entrega: bool, idioma=None) -> dict:
    d = impresion.disenio_ticket(ajustes.get(db, "ticketera_ancho"), int(ajustes.get(db, "ticketera_dpi")),
                                 ctx["t"].numero_rma, ctx["url_seguimiento"])
    # La firma, al ancho del rollo (hasta 70 % y 20 mm de alto)
    for clave, momento in (("firma_ingreso", "ingreso"), ("firma_entrega", "entrega")):
        ctx[clave] = _firma(ctx["t"], momento, d["imprimible_mm"] * 0.7, 20)
    d["bloques"] = _bloques_ticket(ctx, entrega)
    # Traducido antes de medir: el largo del ticket depende del texto
    for b in d["bloques"]:
        for k in ("texto", "etiqueta"):
            if b.get(k):
                b[k] = idiomas.tr(b[k], idioma)
    d["largo_mm"] = impresion.largo_ticket(d, d["bloques"])
    return {"k": d}


def contexto_tipo(db: Session, tipo: str, ctx: dict, idioma: str = None) -> dict:
    """Agrega lo específico de cada documento (medidas de etiqueta / ticket)."""
    ctx = {**ctx, "idioma": idioma or idiomas.BASE}
    if tipo == "etiqueta":
        return {**ctx, **_ctx_etiqueta(db, ctx, idioma)}
    if tipo in ("ticket_ingreso", "ticket_entrega"):
        return {**ctx, **_ctx_ticket(db, ctx, tipo == "ticket_entrega", idioma)}
    return ctx


def idioma_documento(db: Session, tipo: str, t: models.Ticket, quien_pide: str = None) -> str:
    """Los documentos para el cliente salen en su idioma; los internos (etiqueta), en el de quien los pide."""
    if tipo in TIPOS_CLIENTE or tipo.startswith("ticket_"):
        return idiomas.de_usuario(db, t.cliente)
    return quien_pide or idiomas.de_usuario(db, None)


def render_html(tipo: str, ctx: dict, imprimir: bool = False) -> str:
    plantilla = PLANTILLAS.get(tipo, f"{tipo}.html")
    idioma = ctx.get("idioma")
    html = _env.get_template(plantilla).render(**ctx, titulo=idiomas.tr(TIPOS[tipo], idioma), imprimir=imprimir)
    return idiomas.traducir_html(html, idioma)


def render_pdf(html: str) -> bytes:
    from xhtml2pdf import pisa
    out = io.BytesIO()
    res = pisa.CreatePDF(html, dest=out, encoding="utf-8")
    if res.err:
        raise RuntimeError("No se pudo generar el PDF")
    return out.getvalue()


def nombre_archivo(tipo: str, t: models.Ticket, ext: str) -> str:
    return f"{tipo}-{t.numero_rma}.{ext}"


def generar_pdf(db: Session, t: models.Ticket, tipo: str, base_url: str, idioma: str = None) -> bytes:
    idioma = idioma or idioma_documento(db, tipo, t)
    return render_pdf(render_html(tipo, contexto_tipo(db, tipo, contexto(db, t, base_url), idioma)))
