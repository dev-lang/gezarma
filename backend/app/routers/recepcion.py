"""
recepcion.py — Ingreso en mostrador y recepción del equipo.

- Búsqueda de clientes y alta de cliente + ticket en un solo paso (el ticket
  queda a nombre del cliente, aunque lo cargue el taller).
- Checklist de ingreso (accesorios, estado físico, si enciende, si tiene bloqueo).
- Firmas del cliente en pantalla, al ingreso y a la entrega.
- Búsqueda exacta por N° de RMA (para el lector de código de barras).
"""
import re
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import auth, database, models, schemas
from ..services import recepcion
from ..services.ticket_service import log_event, process_ticket_creation

router = APIRouter(tags=["recepcion"])

TALLER = auth.check_role([models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO])


class ClienteNuevo(BaseModel):
    nombre:       str
    telefono:     str = ""
    email:        str = ""
    tipo_cliente: str = "persona"


class FirmaIn(BaseModel):
    imagen:     str                # data:image/png;base64,...
    aclaracion: str = ""


class IngresoIn(BaseModel):
    cliente_id:    Optional[int] = None
    cliente_nuevo: Optional[ClienteNuevo] = None
    ticket:        schemas.TicketCreate
    checklist:     schemas.ChecklistIngreso = schemas.ChecklistIngreso()
    firma:         Optional[FirmaIn] = None


def _cliente_out(u: models.Usuario) -> dict:
    return {"id": u.id, "nombre": u.nombre, "email": u.email, "telefono": u.telefono,
            "tipo_cliente": u.tipo_cliente, "username": u.username,
            "tiene_clave": bool(u.password_hash), "activo": u.activo}


@router.get("/mostrador/clientes")
def buscar_clientes(q: str = Query("", max_length=100), db: Session = Depends(database.get_db),
                    _: models.Usuario = Depends(TALLER)):
    """Clientes por nombre, email, teléfono o usuario (máx. 10)."""
    q = q.strip()
    if len(q) < 2:
        return []
    like = f"%{q.lower()}%"
    digitos = re.sub(r"\D", "", q)
    condiciones = [func.lower(models.Usuario.nombre).like(like),
                   func.lower(models.Usuario.email).like(like),
                   func.lower(models.Usuario.username).like(like),
                   models.Usuario.telefono.like(f"%{q}%")]
    if len(digitos) >= 4:   # "11 5555-0000" encuentra "1155550000" y viceversa
        tel = func.replace(func.replace(func.replace(models.Usuario.telefono, " ", ""), "-", ""), ".", "")
        condiciones.append(tel.like(f"%{digitos}%"))
    clientes = (db.query(models.Usuario)
                .filter(models.Usuario.rol == models.UserRole.CLIENTE, models.Usuario.activo.is_(True),
                        or_(*condiciones))
                .order_by(models.Usuario.nombre).limit(10).all())
    return [_cliente_out(u) for u in clientes]


@router.post("/mostrador/ingreso", response_model=schemas.Ticket)
def ingreso(data: IngresoIn, request: Request, db: Session = Depends(database.get_db),
            current_user: models.Usuario = Depends(TALLER)):
    """Alta del ticket a nombre del cliente (existente o nuevo, sin clave), con
    checklist y, si el cliente firmó, su firma de conformidad."""
    if (data.cliente_id is None) == (data.cliente_nuevo is None):
        raise HTTPException(status_code=400, detail="Elegí un cliente de la lista o cargá uno nuevo.")
    # La firma se valida antes de crear nada: si es inválida no queda un ticket a medias
    firma = recepcion.procesar_firma(data.firma.imagen) if data.firma else None

    if data.cliente_id is not None:
        cliente = db.query(models.Usuario).filter_by(id=data.cliente_id).first()
        if not cliente or cliente.rol != models.UserRole.CLIENTE:
            raise HTTPException(status_code=404, detail="Cliente no encontrado")
        if not cliente.activo:
            raise HTTPException(status_code=400, detail="La cuenta de ese cliente está deshabilitada.")
    else:
        n = data.cliente_nuevo
        cliente = recepcion.crear_cliente(db, n.nombre, n.telefono, n.email, n.tipo_cliente)

    ip = request.client.host if request.client else None
    ticket = process_ticket_creation(db, data.ticket, current_user, ip_address=ip, cliente=cliente,
                                     checklist=data.checklist.model_dump())
    if firma:
        recepcion.guardar_firma(db, ticket, "ingreso", *firma, data.firma.aclaracion, current_user)
        log_event(db, ticket.id, current_user.id, models.EventoHistorial.FIRMA_REGISTRADA,
                  detalle="El cliente firmó la conformidad del ingreso")
        db.commit()
        db.refresh(ticket)
    return schemas.Ticket.for_viewer(ticket, current_user)


def _ticket(db: Session, ticket_id: int) -> models.Ticket:
    t = db.query(models.Ticket).filter_by(id=ticket_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    return t


@router.put("/tickets/{ticket_id}/checklist", response_model=schemas.Ticket)
def editar_checklist(ticket_id: int, checklist: schemas.ChecklistIngreso, db: Session = Depends(database.get_db),
                     current_user: models.Usuario = Depends(TALLER)):
    t = _ticket(db, ticket_id)
    t.checklist_ingreso = checklist.model_dump()
    log_event(db, t.id, current_user.id, models.EventoHistorial.CHECKLIST_INGRESO,
              detalle="Checklist de ingreso actualizado")
    db.commit()
    db.refresh(t)
    return schemas.Ticket.for_viewer(t, current_user)


@router.put("/tickets/{ticket_id}/firmas/{momento}", response_model=schemas.Ticket)
def firmar(ticket_id: int, momento: Literal["ingreso", "entrega"], data: FirmaIn,
           db: Session = Depends(database.get_db), current_user: models.Usuario = Depends(TALLER)):
    """Registra (o reemplaza) la firma del cliente. La firma se hace en el equipo
    del mostrador, con la sesión del taller."""
    t = _ticket(db, ticket_id)
    png = recepcion.procesar_firma(data.imagen)
    habia = t.firma(momento) is not None
    recepcion.guardar_firma(db, t, momento, *png, data.aclaracion, current_user)
    log_event(db, t.id, current_user.id, models.EventoHistorial.FIRMA_REGISTRADA,
              detalle=("Firma de " + ("ingreso" if momento == "ingreso" else "entrega")
                       + (" reemplazada" if habia else " registrada")))
    db.commit()
    db.refresh(t)
    return schemas.Ticket.for_viewer(t, current_user)


@router.get("/tickets/{ticket_id}/firmas/{momento}/imagen")
def imagen_firma(ticket_id: int, momento: Literal["ingreso", "entrega"], db: Session = Depends(database.get_db),
                 current_user: models.Usuario = Depends(auth.get_current_user)):
    t = _ticket(db, ticket_id)
    if current_user.rol == models.UserRole.CLIENTE and t.usuario_id != current_user.id:
        raise HTTPException(status_code=403, detail="Acceso denegado")
    f = t.firma(momento)
    if not f:
        raise HTTPException(status_code=404, detail="Sin firma")
    return Response(content=f.imagen, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.get("/tickets/rma/{rma}", response_model=schemas.Ticket)
def por_rma(rma: str, db: Session = Depends(database.get_db),
            current_user: models.Usuario = Depends(auth.get_current_user)):
    """Ticket por N° de RMA exacto (sin distinguir mayúsculas). Lo usa el lector de
    código de barras: escanear la etiqueta abre el ticket directo."""
    t = (db.query(models.Ticket)
         .filter(func.upper(models.Ticket.numero_rma) == rma.strip().upper()).first())
    if not t or (current_user.rol == models.UserRole.CLIENTE and t.usuario_id != current_user.id):
        raise HTTPException(status_code=404, detail="No hay un ticket con ese N° de RMA")
    return schemas.Ticket.for_viewer(t, current_user)
