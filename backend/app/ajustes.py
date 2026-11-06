"""
ajustes.py — Ajustes del sistema editables desde el panel de administración.

Cada ajuste tiene tipo, valor por defecto, grupo y etiqueta. Se guardan en la
tabla config_sistema (clave → valor como texto). Los secretos (contraseña SMTP)
se guardan cifrados con una clave derivada de SECRET_KEY y nunca se devuelven
por la API: solo se informa si están cargados.

Uso en el código:  ajustes.get(db, "pdf_modo")
"""
import base64
import contextvars
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from . import config, models

# tipo: str | text | int | bool | choice | secret
DEFS = {
    # ── General ──────────────────────────────────────────────────────────────
    "public_url": dict(grupo="general", tipo="str", default="",
                       label="URL pública del sistema",
                       ayuda="Se usa en los QR y en los links de los mails (ej. https://rma.tuempresa.com). "
                             "Si queda vacía, se usa la dirección con la que se accede al sistema."),
    "empresa_nombre": dict(grupo="general", tipo="str", default="GEZARMA",
                           label="Nombre que figura en documentos y mails"),
    "empresa_datos": dict(grupo="general", tipo="text", default="",
                          label="Datos de contacto para los documentos",
                          ayuda="Dirección, teléfono, mail, CUIT… (una línea por dato)."),
    "seguimiento_publico": dict(grupo="general", tipo="bool", default=True,
                                label="Seguimiento público de reparaciones",
                                ayuda="Permite consultar el estado con N° de RMA + N° de serie, sin iniciar sesión."),
    # ── Documentos ───────────────────────────────────────────────────────────
    "pdf_modo": dict(grupo="documentos", tipo="choice", default="servidor",
                     opciones={"servidor": "PDF generado por el servidor",
                               "navegador": "Imprimir desde el navegador"},
                     label="Cómo se generan los documentos",
                     ayuda="Orden de ingreso, remito, presupuesto y etiqueta. Los PDF adjuntos a los mails "
                           "siempre los genera el servidor."),
    # ── Email ────────────────────────────────────────────────────────────────
    "email_activo": dict(grupo="email", tipo="bool", default=False, label="Enviar notificaciones por email"),
    "smtp_origen": dict(grupo="email", tipo="choice", default="env",
                        opciones={"env": "Archivo .env (SMTP_HOST, SMTP_USER…)", "panel": "Este panel"},
                        label="De dónde se toma la configuración SMTP"),
    "smtp_host": dict(grupo="email", tipo="str", default="", label="Servidor SMTP"),
    "smtp_port": dict(grupo="email", tipo="int", default=587, label="Puerto"),
    "smtp_seguridad": dict(grupo="email", tipo="choice", default="starttls",
                           opciones={"starttls": "STARTTLS (587)", "ssl": "SSL/TLS (465)", "ninguna": "Sin cifrado"},
                           label="Seguridad"),
    "smtp_usuario": dict(grupo="email", tipo="str", default="", label="Usuario"),
    "smtp_password": dict(grupo="email", tipo="secret", default="", label="Contraseña",
                          ayuda="Se guarda cifrada. Si cambiás la SECRET_KEY hay que volver a cargarla."),
    "smtp_remitente": dict(grupo="email", tipo="str", default="", label="Remitente (From)",
                           ayuda="Ej. GEZARMA <rma@tuempresa.com>. Vacío = el usuario SMTP."),
    "email_cliente_estado": dict(grupo="email_eventos", tipo="bool", default=True,
                                 label="Al cliente: cambio de estado de su ticket"),
    "email_cliente_presupuesto": dict(grupo="email_eventos", tipo="bool", default=True,
                                      label="Al cliente: presupuesto listo para aprobar"),
    "email_adjuntar_pdf": dict(grupo="email_eventos", tipo="bool", default=True,
                               label="Adjuntar el PDF (presupuesto, remito)"),
    "email_tecnico_asignacion": dict(grupo="email_eventos", tipo="bool", default=True,
                                     label="Al técnico: ticket asignado"),
    "email_sla": dict(grupo="email_eventos", tipo="bool", default=True,
                      label="Al taller: SLA vencido o por vencer"),
    "email_stock_bajo": dict(grupo="email_eventos", tipo="bool", default=True,
                             label="A los administradores: repuesto bajo el stock mínimo"),
    # ── SLA ──────────────────────────────────────────────────────────────────
    "sla_alertas": dict(grupo="sla", tipo="bool", default=True, label="Avisar SLA vencidos y por vencer"),
    "sla_aviso_horas": dict(grupo="sla", tipo="int", default=4, minimo=1,
                            label="Avisar cuando falten menos de (horas)",
                            ayuda="Tiene que ser menor que el SLA más corto (24 h para tickets nuevos); "
                                  "si no, todo ticket nace «por vencer»."),
    "sla_intervalo_minutos": dict(grupo="sla", tipo="int", default=15, minimo=1,
                                  label="Cada cuántos minutos se revisan los SLA"),
}

SECRET_PLACEHOLDER = "••••••••"


# ── Cifrado de secretos ──────────────────────────────────────────────────────
def _fernet() -> Fernet:
    key = hashlib.sha256(("gezarma-ajustes:" + config.SECRET_KEY).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def _encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def _decrypt(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except (InvalidToken, ValueError):
        return ""   # cifrado con otra SECRET_KEY: hay que volver a cargarlo


# ── Conversión texto ↔ tipo ──────────────────────────────────────────────────
def _parse(d: dict, raw: str):
    t = d["tipo"]
    if t == "bool":
        return str(raw).strip().lower() in ("1", "true", "si", "sí", "on")
    if t == "int":
        try:
            return int(raw)
        except (TypeError, ValueError):
            return d["default"]
    return raw


def _validate(clave: str, value) -> str:
    """Valida un valor recibido de la API y lo devuelve como texto para guardar."""
    d = DEFS[clave]
    t = d["tipo"]
    if t == "bool":
        if not isinstance(value, bool) and str(value).lower() not in ("true", "false", "1", "0"):
            raise ValueError("Debe ser verdadero o falso")
        return "1" if (value is True or str(value).lower() in ("true", "1")) else "0"
    if t == "int":
        try:
            n = int(value)
        except (TypeError, ValueError):
            raise ValueError("Debe ser un número entero")
        if n < d.get("minimo", 0):
            raise ValueError(f"Debe ser al menos {d.get('minimo', 0)}")
        return str(n)
    if t == "choice":
        if value not in d["opciones"]:
            raise ValueError(f"Opción inválida. Opciones: {', '.join(d['opciones'])}")
        return value
    value = "" if value is None else str(value).strip()
    if clave == "public_url" and value and not value.startswith(("http://", "https://")):
        raise ValueError("Debe empezar con http:// o https://")
    return value.rstrip("/") if clave == "public_url" else value


# ── API para el resto del código ─────────────────────────────────────────────
def get(db: Session, clave: str):
    d = DEFS[clave]
    row = db.query(models.ConfigSistema).filter_by(clave=clave).first()
    if row is None or row.valor is None:
        return d["default"]
    if d["tipo"] == "secret":
        return _decrypt(row.valor) if row.valor else ""
    return _parse(d, row.valor)


def set(db: Session, clave: str, value) -> None:
    if clave not in DEFS:
        raise KeyError(clave)
    d = DEFS[clave]
    if d["tipo"] == "secret":
        if value == SECRET_PLACEHOLDER:      # sin cambios desde el formulario
            return
        stored = _encrypt(str(value)) if value else ""
    else:
        stored = _validate(clave, value)
    row = db.query(models.ConfigSistema).filter_by(clave=clave).first()
    if row:
        row.valor = stored
    else:
        db.add(models.ConfigSistema(clave=clave, valor=stored))


def listado(db: Session) -> list:
    """Todos los ajustes para el panel (los secretos solo indican si están cargados)."""
    out = []
    for clave, d in DEFS.items():
        valor = get(db, clave)
        item = {"clave": clave, "grupo": d["grupo"], "tipo": d["tipo"], "label": d["label"],
                "ayuda": d.get("ayuda", ""), "default": d["default"]}
        if d["tipo"] == "choice":
            item["opciones"] = d["opciones"]
        if d["tipo"] == "secret":
            item["valor"] = SECRET_PLACEHOLDER if valor else ""
            item["cargado"] = bool(valor)
        else:
            item["valor"] = valor
        out.append(item)
    return out


# URL con la que se está accediendo al sistema en el request actual (la fija un
# middleware en main.py). Sirve de último recurso para QR y links de los mails.
request_base_url: contextvars.ContextVar = contextvars.ContextVar("request_base_url", default="")


def public_url(db: Session, request=None) -> str:
    """URL base para QR y links: ajuste del panel → PUBLIC_URL del entorno →
    la dirección con la que se accede al sistema."""
    url = get(db, "public_url") or config.PUBLIC_URL
    if not url and request is not None:
        url = str(request.base_url)
    if not url:
        url = request_base_url.get()
    return (url or "http://localhost:8000").rstrip("/")
