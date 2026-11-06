"""
email.py — Notificaciones por email.

Cómo funciona:
- Cada evento (cambio de estado, presupuesto, asignación, stock bajo, SLA)
  llama a una función de este módulo dentro del request. Esa función solo
  *programa* el envío: lo guarda en la sesión de base de datos.
- Cuando la transacción se confirma (commit), los envíos programados pasan a
  un hilo aparte: el request no espera al servidor SMTP. Si la transacción se
  revierte, los mails se descartan (no sale un aviso de algo que no pasó).
- La configuración SMTP sale del .env o del panel, según el ajuste smtp_origen.
"""
import logging
import smtplib
import socket
import ssl
import threading
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parseaddr
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import event
from sqlalchemy.orm import Session

from .. import ajustes, config, database, models
from ..timeutils import utcnow

log = logging.getLogger("uvicorn.error")

_env = Environment(
    loader=FileSystemLoader(str(Path(__file__).resolve().parent.parent / "templates" / "email")),
    autoescape=select_autoescape(["html"]),
)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="email")
_futuros = []
_lock = threading.Lock()
estado = {"ultimo_ok": None, "ultimo_error": None, "ultimo_error_fecha": None}


class ErrorEmail(Exception):
    pass


# ── Configuración SMTP ───────────────────────────────────────────────────────
def smtp_config(db: Session) -> dict:
    if ajustes.get(db, "smtp_origen") == "panel":
        return {"host": ajustes.get(db, "smtp_host"), "port": ajustes.get(db, "smtp_port"),
                "seguridad": ajustes.get(db, "smtp_seguridad"), "usuario": ajustes.get(db, "smtp_usuario"),
                "password": ajustes.get(db, "smtp_password"), "remitente": ajustes.get(db, "smtp_remitente")}
    return {"host": config.SMTP_HOST, "port": config.SMTP_PORT, "seguridad": config.SMTP_SECURITY,
            "usuario": config.SMTP_USER, "password": config.SMTP_PASSWORD, "remitente": config.SMTP_FROM}


def evento_activo(db: Session, clave: str) -> bool:
    return bool(ajustes.get(db, "email_activo") and ajustes.get(db, clave))


def _remitente(cfg: dict, empresa: str) -> str:
    nombre, direccion = parseaddr(cfg.get("remitente") or "")
    direccion = direccion or cfg.get("usuario") or ""
    if not direccion or "@" not in direccion:
        raise ErrorEmail("Falta la dirección del remitente: completá «Remitente» o un usuario SMTP que sea un email.")
    return formataddr((nombre or empresa, direccion))


def _enviar_smtp(cfg: dict, msg: EmailMessage) -> None:
    if not cfg.get("host"):
        raise ErrorEmail("No hay servidor SMTP configurado.")
    try:
        port = int(cfg.get("port") or 587)
        ctx = ssl.create_default_context()
        if cfg.get("seguridad") == "ssl":
            server = smtplib.SMTP_SSL(cfg["host"], port, timeout=20, context=ctx)
        else:
            server = smtplib.SMTP(cfg["host"], port, timeout=20)
        with server:
            if cfg.get("seguridad") == "starttls":
                server.starttls(context=ctx)
            if cfg.get("usuario"):
                server.login(cfg["usuario"], cfg.get("password") or "")
            server.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        raise ErrorEmail("El servidor SMTP rechazó el usuario o la contraseña.")
    except smtplib.SMTPNotSupportedError:
        raise ErrorEmail("El servidor no soporta STARTTLS: probá con otra opción de «Seguridad».")
    except (ssl.SSLError, smtplib.SMTPServerDisconnected) as e:
        raise ErrorEmail(f"Error de conexión segura ({e}). Revisá el puerto y la opción de «Seguridad».")
    except ConnectionRefusedError:
        raise ErrorEmail(f"No se pudo conectar a {cfg['host']}:{cfg.get('port')}: el servidor rechazó la conexión. "
                         "Revisá el servidor y el puerto.")
    except socket.gaierror:
        raise ErrorEmail(f"No se encontró el servidor «{cfg['host']}». Revisá que el nombre esté bien escrito.")
    except (socket.timeout, TimeoutError):
        raise ErrorEmail(f"El servidor {cfg['host']}:{cfg.get('port')} no respondió. Revisá el puerto y que no lo "
                         "bloquee un firewall.")
    except smtplib.SMTPRecipientsRefused:
        raise ErrorEmail("El servidor rechazó el destinatario.")
    except (OSError, smtplib.SMTPException) as e:
        raise ErrorEmail(f"No se pudo enviar: {e}")


def enviar(db: Session, para: list, asunto: str, titulo: str, parrafos: list,
           boton: tuple = None, adjuntos: list = None) -> None:
    """Arma y envía un mail ya mismo (bloquea). Lanza ErrorEmail si falla."""
    para = [p for p in dict.fromkeys(para) if p and "@" in p]
    if not para:
        return
    cfg = smtp_config(db)
    empresa = ajustes.get(db, "empresa_nombre") or "GEZARMA"
    ctx = {"empresa": empresa, "titulo": titulo, "parrafos": parrafos,
           "boton_texto": boton[0] if boton else None, "boton_url": boton[1] if boton else None}
    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = _remitente(cfg, empresa)
    msg["To"] = ", ".join(para)
    msg["Message-ID"] = make_msgid(domain="gezarma")
    msg.set_content(_env.get_template("mensaje.txt").render(**ctx))
    msg.add_alternative(_env.get_template("mensaje.html").render(**ctx), subtype="html")
    for nombre, contenido, mime in adjuntos or []:
        tipo, subtipo = mime.split("/", 1)
        msg.add_attachment(contenido, maintype=tipo, subtype=subtipo, filename=nombre)
    _enviar_smtp(cfg, msg)
    estado["ultimo_ok"] = utcnow()


# ── Envío diferido: después del commit, en otro hilo ─────────────────────────
def programar(db: Session, trabajo) -> None:
    """trabajo(db) se ejecuta en otro hilo, con su propia sesión, después del commit."""
    # Asegura una transacción abierta: así un rollback siempre descarta lo programado
    # (sin transacción, rollback() no hace nada y el próximo commit lo enviaría).
    db.connection()
    db.info.setdefault("emails_pendientes", []).append(trabajo)


def _ejecutar(trabajo) -> None:
    db = database.SessionLocal()
    try:
        trabajo(db)
    except Exception as e:  # el mail nunca rompe nada: se registra y se sigue
        estado["ultimo_error"] = str(e)
        estado["ultimo_error_fecha"] = utcnow()
        log.warning("No se pudo enviar un email: %s", e)
    finally:
        db.close()


@event.listens_for(database.SessionLocal, "after_commit")
def _despachar(session) -> None:
    pendientes = session.info.pop("emails_pendientes", [])
    with _lock:
        for trabajo in pendientes:
            _futuros.append(_executor.submit(_ejecutar, trabajo))


@event.listens_for(database.SessionLocal, "after_soft_rollback")
def _descartar(session, previous_transaction) -> None:
    # after_soft_rollback se dispara en todo rollback(), haya o no transacción activa
    session.info.pop("emails_pendientes", None)


def esperar_envios(timeout: float = 15) -> None:
    """Espera a que terminen los envíos en curso (para tests)."""
    with _lock:
        futuros, _futuros[:] = list(_futuros), []
    for f in futuros:
        f.result(timeout=timeout)


# ── Eventos ──────────────────────────────────────────────────────────────────
def _mail_usuario(u) -> str:
    return u.email if u is not None and u.activo and u.email else ""


def _etiqueta_estado(db, valor) -> str:
    cfg = db.query(models.TicketStatusConfig).filter_by(valor=valor).first()
    return cfg.etiqueta if cfg else valor


def _pdf(db, ticket, tipo, base_url):
    from . import documentos
    return (documentos.nombre_archivo(tipo, ticket, "pdf"),
            documentos.generar_pdf(db, ticket, tipo, base_url), "application/pdf")


def cliente_cambio_estado(db: Session, ticket: models.Ticket) -> None:
    if not ticket.cliente or ticket.cliente.rol != models.UserRole.CLIENTE:
        return
    from . import retiro
    if ticket.estado == retiro.estado_retiro(db) and evento_activo(db, "email_cliente_retiro"):
        cliente_retiro(db, ticket)   # en lugar del aviso genérico de cambio de estado
        return
    if not evento_activo(db, "email_cliente_estado"):
        return
    ticket_id, base = ticket.id, ajustes.public_url(db)

    def trabajo(s):
        t = s.get(models.Ticket, ticket_id)
        etiqueta = _etiqueta_estado(s, t.estado)
        from . import documentos
        parrafos = [f"Hola {t.cliente.nombre},",
                    f"Tu equipo {t.producto} (RMA {t.numero_rma}) cambió de estado: ahora está «{etiqueta}»."]
        adjuntos = []
        if t.estado == models.TicketStatus.ENVIADO:
            if t.empresa_transporte or t.tracking_number:
                parrafos.append(f"Lo despachamos por {t.empresa_transporte or 'transporte'}"
                                + (f", con N° de seguimiento {t.tracking_number}." if t.tracking_number else "."))
            if ajustes.get(s, "email_adjuntar_pdf"):
                adjuntos.append(_pdf(s, t, "remito", base))
                parrafos.append("Te adjuntamos el remito de entrega.")
        enviar(s, [_mail_usuario(t.cliente)], f"{t.numero_rma}: {etiqueta}", f"Tu equipo está «{etiqueta}»",
               parrafos, ("Ver el seguimiento", documentos.url_seguimiento(base, t)), adjuntos)
    programar(db, trabajo)


def cliente_retiro(db: Session, ticket: models.Ticket, recordatorio: bool = False) -> None:
    """Equipo listo para retirar (o recordatorio), con el plazo de guarda."""
    if not evento_activo(db, "email_cliente_retiro"):
        return
    if not ticket.cliente or ticket.cliente.rol != models.UserRole.CLIENTE:
        return
    ticket_id, base = ticket.id, ajustes.public_url(db)

    def trabajo(s):
        t = s.get(models.Ticket, ticket_id)
        from . import documentos, retiro
        from ..timeutils import utc_to_local
        v = retiro.vence(s, t)
        hasta = utc_to_local(v).strftime("%d/%m/%Y") if v else ""
        parrafos = [f"Hola {t.cliente.nombre},"]
        if recordatorio:
            parrafos.append(f"Te recordamos que tu equipo {t.producto} (RMA {t.numero_rma}) está listo para retirar "
                            f"desde el {utc_to_local(t.fecha_listo).strftime('%d/%m/%Y')}.")
        else:
            parrafos.append(f"¡Tu equipo {t.producto} (RMA {t.numero_rma}) está listo para retirar!")
        if hasta:
            parrafos.append(f"Podés retirarlo hasta el {hasta}. {ajustes.politica_retiro(s)}")
        parrafos.append("Traé el comprobante de ingreso o tu N° de RMA.")
        asunto = f"{t.numero_rma}: " + ("recordatorio, tu equipo te espera" if recordatorio else "listo para retirar")
        enviar(s, [_mail_usuario(t.cliente)], asunto,
               "Tu equipo te espera" if recordatorio else "Tu equipo está listo para retirar",
               parrafos, ("Ver el seguimiento", documentos.url_seguimiento(base, t)))
    programar(db, trabajo)


def cliente_presupuesto(db: Session, ticket: models.Ticket) -> None:
    if not evento_activo(db, "email_cliente_presupuesto"):
        return
    if not ticket.cliente or ticket.cliente.rol != models.UserRole.CLIENTE:
        return
    ticket_id, base = ticket.id, ajustes.public_url(db)

    def trabajo(s):
        t = s.get(models.Ticket, ticket_id)
        from . import documentos
        total = sum(i.cantidad * i.precio_cliente for i in t.presupuesto.items)
        parrafos = [f"Hola {t.cliente.nombre},",
                    f"Ya tenemos el presupuesto para tu equipo {t.producto} (RMA {t.numero_rma}): "
                    f"{documentos._pesos(total)}.",
                    "Ingresá al sistema para aprobarlo o rechazarlo. Hasta que lo apruebes no avanzamos con la reparación."]
        adjuntos = [_pdf(s, t, "presupuesto", base)] if ajustes.get(s, "email_adjuntar_pdf") else []
        if adjuntos:
            parrafos.append("Te adjuntamos el presupuesto en PDF.")
        enviar(s, [_mail_usuario(t.cliente)], f"{t.numero_rma}: presupuesto para aprobar",
               "Presupuesto listo para aprobar", parrafos, ("Ver y aprobar", f"{base}/#ticket={t.id}"), adjuntos)
    programar(db, trabajo)


def tecnico_asignado(db: Session, ticket: models.Ticket, tecnico_id: int, asignado_por: str) -> None:
    if not evento_activo(db, "email_tecnico_asignacion") or not tecnico_id:
        return
    ticket_id, base = ticket.id, ajustes.public_url(db)

    def trabajo(s):
        t = s.get(models.Ticket, ticket_id)
        tec = s.get(models.Usuario, tecnico_id)
        enviar(s, [_mail_usuario(tec)], f"Te asignaron el {t.numero_rma}", "Nuevo ticket asignado",
               [f"Hola {tec.nombre},",
                f"{asignado_por} te asignó el ticket {t.numero_rma}: {t.producto} (SN {t.numero_serie}).",
                f"Falla informada: {t.descripcion}"],
               ("Abrir el ticket", f"{base}/#ticket={t.id}"))
    programar(db, trabajo)


def stock_bajo(db: Session, repuesto, destinatarios, titulo: str, mensaje: str) -> None:
    if not evento_activo(db, "email_stock_bajo"):
        return
    mails, base = [_mail_usuario(u) for u in destinatarios], ajustes.public_url(db)

    def trabajo(s):
        enviar(s, mails, titulo, titulo, [mensaje], ("Abrir el sistema", base))
    programar(db, trabajo)


def sla(db: Session, destinatarios, titulo: str, lineas: list) -> None:
    if not evento_activo(db, "email_sla"):
        return
    mails, base = [_mail_usuario(u) for u in destinatarios], ajustes.public_url(db)

    def trabajo(s):
        enviar(s, mails, titulo, titulo, lineas, ("Abrir el sistema", base))
    programar(db, trabajo)
