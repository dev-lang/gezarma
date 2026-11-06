"""
recepcion.py — Ingreso en mostrador: clientes sin clave, checklist y firmas.

Firmas
------
La firma llega del navegador como PNG (trazo oscuro sobre fondo transparente o
blanco). Antes de guardarla se vuelve a dibujar del lado del servidor:
- se valida que sea una imagen de verdad y de tamaño razonable;
- se recorta al trazo (sin márgenes vacíos);
- se pasa a blanco y negro puro, que es lo que imprime una térmica.
Así el archivo guardado nunca es el que mandó el navegador.
"""
import base64
import io
import re
import secrets
import unicodedata

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..timeutils import utcnow

MOMENTOS = ("ingreso", "entrega")
FIRMA_MAX_BYTES = 400 * 1024          # PNG que manda el navegador
FIRMA_MAX_LADO = 2000                  # px
FIRMA_GUARDADA_MAX_ANCHO = 600         # px: alcanza para A4 y para la ticketera


def _error(msg: str):
    raise HTTPException(status_code=400, detail=msg)


def procesar_firma(data_uri: str) -> tuple[bytes, int, int]:
    """data:image/png;base64,... → (PNG en blanco y negro recortado, ancho, alto)."""
    from PIL import Image

    m = re.match(r"^data:image/png;base64,([A-Za-z0-9+/=\s]+)$", data_uri or "")
    if not m:
        _error("La firma tiene que ser una imagen PNG.")
    try:
        crudo = base64.b64decode(m.group(1), validate=False)
    except ValueError:
        _error("La firma no es una imagen válida.")
    if len(crudo) > FIRMA_MAX_BYTES:
        _error("La imagen de la firma es demasiado grande.")
    try:
        img = Image.open(io.BytesIO(crudo))
        if img.format != "PNG":
            raise ValueError
        if img.width > FIRMA_MAX_LADO or img.height > FIRMA_MAX_LADO:
            _error("La imagen de la firma es demasiado grande.")
        img.load()
    except HTTPException:
        raise
    except Exception:
        _error("La firma no es una imagen válida.")

    # Fondo blanco (el canvas suele mandar transparente) y escala de grises
    rgba = img.convert("RGBA")
    fondo = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    gris = Image.alpha_composite(fondo, rgba).convert("L")
    # Trazo = lo oscuro. Si no hay casi nada dibujado, no es una firma.
    mascara = gris.point(lambda v: 255 if v < 160 else 0)
    caja = mascara.getbbox()
    if not caja or mascara.histogram()[255] < 40:
        _error("La firma está vacía: pedile al cliente que firme en el recuadro.")
    margen = 6
    caja = (max(0, caja[0] - margen), max(0, caja[1] - margen),
            min(gris.width, caja[2] + margen), min(gris.height, caja[3] + margen))
    recorte = gris.crop(caja)
    if recorte.width > FIRMA_GUARDADA_MAX_ANCHO:
        alto = max(1, round(recorte.height * FIRMA_GUARDADA_MAX_ANCHO / recorte.width))
        recorte = recorte.resize((FIRMA_GUARDADA_MAX_ANCHO, alto), Image.LANCZOS)
    bn = recorte.point(lambda v: 0 if v < 160 else 255).convert("1")
    out = io.BytesIO()
    bn.save(out, format="PNG", optimize=True)
    return out.getvalue(), bn.width, bn.height


def guardar_firma(db: Session, ticket: models.Ticket, momento: str, png: bytes, ancho: int, alto: int,
                  aclaracion: str, usuario: models.Usuario) -> models.Firma:
    if momento not in MOMENTOS:
        raise HTTPException(status_code=404, detail="Momento de firma inválido")
    firma = ticket.firma(momento)
    if firma is None:
        firma = models.Firma(ticket_id=ticket.id, momento=momento)
        db.add(firma)
        ticket.firmas.append(firma)
    firma.imagen, firma.ancho, firma.alto = png, ancho, alto
    firma.aclaracion = (aclaracion or "").strip()[:120] or None
    firma.registrado_por = usuario.id
    firma.fecha = utcnow()
    return firma


def firma_data_uri(firma) -> str:
    return "data:image/png;base64," + base64.b64encode(firma.imagen).decode()


# ── Clientes sin clave ────────────────────────────────────────────────────────
def _slug(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9]+", ".", t).strip(".")
    return t[:20] or "cliente"


def username_para(db: Session, nombre: str) -> str:
    base = _slug(nombre)
    while True:
        candidato = f"{base}.{secrets.token_hex(2)}"
        if not db.query(models.Usuario).filter_by(username=candidato).first():
            return candidato


def crear_cliente(db: Session, nombre: str, telefono: str, email: str, tipo_cliente: str) -> models.Usuario:
    """Cliente sin clave: no puede iniciar sesión hasta que un admin le genere una
    (Administración → Usuarios → resetear clave). Sigue su reparación con el QR."""
    nombre = (nombre or "").strip()
    telefono = (telefono or "").strip() or None
    email = (email or "").strip().lower() or None
    if not nombre:
        _error("Falta el nombre del cliente.")
    if not telefono and not email:
        _error("Cargá al menos un teléfono o un email del cliente.")
    if telefono:   # mismo criterio que la edición de perfil
        telefono = re.sub(r"[\s\-\(\)]", "", telefono)
        if not re.match(r"^\+?\d{6,20}$", telefono):
            _error("Teléfono inválido: usá solo números, opcionalmente con + al inicio.")
    if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        _error("Email inválido.")
    if email and db.query(models.Usuario).filter(models.Usuario.email == email).first():
        _error("Ya hay un cliente con ese email: buscalo y elegilo de la lista.")
    if tipo_cliente not in {t.value for t in models.UserType}:
        _error("Tipo de cliente inválido.")
    u = models.Usuario(username=username_para(db, nombre), password_hash=None, nombre=nombre,
                       email=email, telefono=telefono, rol=models.UserRole.CLIENTE.value,
                       tipo_cliente=tipo_cliente)
    db.add(u)
    db.flush()
    return u
