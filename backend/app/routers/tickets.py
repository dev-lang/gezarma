from fastapi import APIRouter, Depends, HTTPException, status, Query, File, UploadFile, Request
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import os, shutil, uuid, re

from .. import database, models, schemas, auth, config
from ..timeutils import utcnow, to_utc_naive, iso_utc
from ..services.ticket_service import (
    process_ticket_creation, calculate_sla_deadline, log_event, notify_ticket_actors
)

UPLOAD_DIR = config.UPLOAD_DIR
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _adjunto_path(adj) -> str:
    """Where an attachment lives on disk. Built from the current UPLOAD_DIR, so files
    keep working if UPLOAD_DIR changes (e.g. moving to Docker); falls back to the
    path stored at upload time."""
    path = os.path.join(UPLOAD_DIR, f"ticket_{adj.ticket_id}", adj.nombre_guardado or "")
    if adj.nombre_guardado and os.path.exists(path):
        return path
    return adj.ruta_archivo

ALLOWED_EXTENSIONS = {"pdf", "txt", "jpg", "jpeg", "png"}
ALLOWED_MIME_TYPES = {"application/pdf", "text/plain", "image/jpeg", "image/png"}
MAX_FILE_BYTES         = 10 * 1024 * 1024  # 10 MB per individual file
MAX_TICKET_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB total per ticket

def _safe_filename(original: str) -> tuple[str, str]:
    """
    Returns (safe_display_name, unique_stored_name).
    - Strips path separators and dangerous characters.
    - Prefixes with a short UUID to prevent collisions & path traversal.
    """
    # Remove any directory components
    basename = os.path.basename(original).strip()
    # Keep only safe characters: letters, digits, dots, dashes, underscores
    safe = re.sub(r"[^\w.\-]", "_", basename)
    # Prevent hidden files and double-extension tricks
    if safe.startswith("."):
        safe = "_" + safe
    prefix = uuid.uuid4().hex[:8]
    return safe, f"{prefix}_{safe}"

router = APIRouter(prefix="/tickets", tags=["tickets"])

VALID_ESTADOS = {s.value for s in models.TicketStatus}

# ── Helper: serialize historial entries ──────────────────────────────────────
def _historial_out(entries):
    result = []
    for e in entries:
        result.append(schemas.HistorialEntry(
            id=e.id, ticket_id=e.ticket_id,
            tipo_evento=e.tipo_evento or "cambio_estado",
            estado_anterior=e.estado_anterior,
            estado_nuevo=e.estado_nuevo,
            campo=e.campo,
            valor_anterior=e.valor_anterior,
            valor_nuevo=e.valor_nuevo,
            detalle=e.detalle,
            usuario_nombre=e.usuario.nombre if e.usuario else None,
            fecha=e.fecha,
        ))
    return result

# ── Helper: load a ticket the current user is allowed to see ─────────────────
def _get_ticket_for_user(ticket_id: int, current_user: models.Usuario, db: Session) -> models.Ticket:
    """404 if the ticket doesn't exist, 403 if a client tries to access someone else's ticket."""
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    if current_user.rol == models.UserRole.CLIENTE and ticket.usuario_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return ticket

# ── Create ────────────────────────────────────────────────────────────────────
@router.post("/", response_model=schemas.Ticket)
def create_ticket(
    ticket: schemas.TicketCreate,
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.get_current_user)
):
    ip = request.client.host if request.client else None
    created = process_ticket_creation(db, ticket, current_user, ip_address=ip)
    return schemas.Ticket.for_viewer(created, current_user)

# ── Dashboard stats ───────────────────────────────────────────────────────────
@router.get("/stats/dashboard", response_model=schemas.DashboardStats)
def get_dashboard_stats(
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([
        models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO
    ]))
):
    total     = db.query(models.Ticket).count()
    abiertos  = db.query(models.Ticket).filter(models.Ticket.estado != models.TicketStatus.CERRADO).count()
    cerrados  = db.query(models.Ticket).filter(models.Ticket.estado == models.TicketStatus.CERRADO).count()
    reparacion= db.query(models.Ticket).filter(models.Ticket.estado == models.TicketStatus.REPARACION).count()
    closed    = db.query(models.Ticket).filter(models.Ticket.fecha_cierre != None).all()
    avg_time  = 0
    if closed:
        total_time = sum([(t.fecha_cierre - t.fecha_creacion).total_seconds() for t in closed])
        avg_time   = (total_time / len(closed)) / 3600
    products  = db.query(models.Ticket.producto, func.count(models.Ticket.id)).group_by(models.Ticket.producto).all()
    states    = db.query(models.Ticket.estado, func.count(models.Ticket.id)).group_by(models.Ticket.estado).all()
    techs     = db.query(models.Usuario.nombre, func.count(models.Ticket.id))\
                  .join(models.Ticket, models.Usuario.id == models.Ticket.tecnico_asignado)\
                  .group_by(models.Usuario.nombre).all()
    return {
        "total_tickets": total, "abiertos": abiertos,
        "cerrados": cerrados,   "en_reparacion": reparacion,
        "tiempo_promedio_reparacion_horas": round(avg_time, 2),
        "fallas_por_producto":  {p[0]: p[1] for p in products},
        "tickets_por_estado":   {s[0]: s[1] for s in states},
        "tickets_por_tecnico":  {t[0]: t[1] for t in techs},
    }

# ── Global search ─────────────────────────────────────────────────────────────
@router.get("/search/global")
def global_search(
    q: str = Query(...),
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.get_current_user)
):
    query = db.query(models.Ticket).outerjoin(models.Comentario).filter(
        (models.Ticket.numero_rma.contains(q))   |
        (models.Ticket.numero_serie.contains(q)) |
        (models.Ticket.producto.contains(q))     |
        (models.Ticket.descripcion.contains(q))  |
        (models.Comentario.comentario.contains(q))
    ).distinct()
    if current_user.rol == models.UserRole.CLIENTE:
        query = query.filter(models.Ticket.usuario_id == current_user.id)
    return [schemas.Ticket.for_viewer(t, current_user) for t in query.all()]

# ── List ──────────────────────────────────────────────────────────────────────
@router.get("/", response_model=List[schemas.Ticket])
def list_tickets(
    status: Optional[str] = None,
    tecnico_id: Optional[int] = None,
    usuario_id: Optional[int] = None,
    skip: int = 0, limit: int = 100,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.get_current_user)
):
    query = db.query(models.Ticket)
    if current_user.rol == models.UserRole.CLIENTE:
        query = query.filter(models.Ticket.usuario_id == current_user.id)
    if status:     query = query.filter(models.Ticket.estado     == status)
    if tecnico_id: query = query.filter(models.Ticket.tecnico_asignado == tecnico_id)
    if usuario_id: query = query.filter(models.Ticket.usuario_id == usuario_id)
    tickets = query.order_by(models.Ticket.fecha_creacion.desc()).offset(skip).limit(limit).all()
    return [schemas.Ticket.for_viewer(t, current_user) for t in tickets]

# ── Get single ────────────────────────────────────────────────────────────────
@router.get("/{ticket_id}", response_model=schemas.Ticket)
def get_ticket(
    ticket_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.get_current_user)
):
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    if current_user.rol == models.UserRole.CLIENTE and ticket.usuario_id != current_user.id:
        raise HTTPException(status_code=403, detail="Acceso denegado")
    return schemas.Ticket.for_viewer(ticket, current_user)

# ── Edit core fields (Feature 3) ──────────────────────────────────────────────
@router.patch("/{ticket_id}/fields", response_model=schemas.Ticket)
def edit_ticket_fields(
    ticket_id: int,
    fields: schemas.TicketEditFields,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([
        models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO
    ]))
):
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    data = fields.model_dump(exclude_unset=True)
    changed_labels = []
    for campo, valor_nuevo in data.items():
        valor_anterior = getattr(ticket, campo, None)
        if valor_anterior != valor_nuevo:
            log_event(db, ticket_id, current_user.id,
                      models.EventoHistorial.CAMPO_EDITADO,
                      detalle=f"Campo '{campo}' modificado",
                      campo=campo, val_ant=valor_anterior, val_nuevo=valor_nuevo)
            setattr(ticket, campo, valor_nuevo)
            changed_labels.append(campo)
    ticket.fecha_actualizacion = utcnow()
    if changed_labels:
        notify_ticket_actors(
            db, ticket,
            tipo=models.TipoNotificacion.CAMPO_EDITADO,
            titulo=f"Ticket modificado: {ticket.numero_rma}",
            mensaje=f"{current_user.nombre} modificó: {', '.join(changed_labels)}",
            origen_usuario_id=current_user.id,
        )
    db.commit()
    db.refresh(ticket)
    return schemas.Ticket.from_orm_with_tecnico(ticket, current_user.id)

# ── Update status ────────────────────────────────────────────────────────────
@router.put("/{ticket_id}/status", response_model=schemas.Ticket)
def update_ticket_status(
    ticket_id: int,
    update: schemas.TicketUpdateStatus,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([
        models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO
    ]))
):
    if update.estado not in VALID_ESTADOS:
        raise HTTPException(status_code=400, detail="Estado inválido")
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    # Guard: if the status hasn't actually changed, do nothing — no historial, no notification.
    if ticket.estado == update.estado:
        return schemas.Ticket.from_orm_with_tecnico(ticket, current_user.id)
    estado_ant = ticket.estado
    ticket.estado = update.estado
    ticket.fecha_actualizacion = utcnow()
    if update.estado in (models.TicketStatus.CERRADO, models.TicketStatus.CANCELADO):
        ticket.fecha_cierre = utcnow()
    ticket.deadline_sla = calculate_sla_deadline(update.estado)
    log_event(db, ticket_id, current_user.id,
              models.EventoHistorial.CAMBIO_ESTADO,
              detalle=f"Estado: {estado_ant} → {update.estado}",
              estado_ant=estado_ant, estado_nuevo=update.estado)
    notify_ticket_actors(
        db, ticket,
        tipo=models.TipoNotificacion.CAMBIO_ESTADO,
        titulo=f"Estado actualizado: {ticket.numero_rma}",
        mensaje=f"{current_user.nombre} cambió el estado a «{update.estado}»",
        origen_usuario_id=current_user.id,
    )
    db.commit()
    db.refresh(ticket)
    return schemas.Ticket.from_orm_with_tecnico(ticket, current_user.id)

# ── Assign technician ─────────────────────────────────────────────────────────
@router.put("/{ticket_id}/assign", response_model=schemas.Ticket)
def assign_technician(
    ticket_id: int,
    assignment: schemas.TicketUpdateAssignment,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([
        models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO
    ]))
):
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    if assignment.tecnico_id:
        tech = db.query(models.Usuario).filter(models.Usuario.id == assignment.tecnico_id).first()
        if not tech:
            raise HTTPException(status_code=404, detail="Técnico no encontrado")
        tech_nombre = tech.nombre
    else:
        tech_nombre = "Sin asignar"

    ant = ticket.tecnico_asignado
    tecnico_cambio = ant != assignment.tecnico_id   # ← only notify if value actually changed

    ticket.tecnico_asignado = assignment.tecnico_id
    ticket.fecha_actualizacion = utcnow()

    if tecnico_cambio:
        log_event(db, ticket_id, current_user.id,
                  models.EventoHistorial.TECNICO_ASIGNADO,
                  detalle=f"Técnico asignado: {tech_nombre}")
        # Notify the newly assigned technician directly
        if assignment.tecnico_id and assignment.tecnico_id != current_user.id:
            db.add(models.Notificacion(
                usuario_id=assignment.tecnico_id,
                ticket_id=ticket.id,
                tipo=models.TipoNotificacion.ASIGNACION,
                titulo=f"Ticket asignado: {ticket.numero_rma}",
                mensaje=f"{current_user.nombre} te asignó el ticket {ticket.numero_rma} ({ticket.producto})",
                origen_usuario_id=current_user.id,
            ))
        # Notify the ticket owner
        notify_ticket_actors(
            db, ticket,
            tipo=models.TipoNotificacion.ASIGNACION,
            titulo=f"Técnico asignado: {ticket.numero_rma}",
            mensaje=f"Técnico asignado: {tech_nombre}",
            origen_usuario_id=current_user.id,
            extra_recipient_ids=[assignment.tecnico_id],
        )
    db.commit()
    db.refresh(ticket)
    return schemas.Ticket.from_orm_with_tecnico(ticket, current_user.id)

# ── Shipping ──────────────────────────────────────────────────────────────────
@router.put("/{ticket_id}/shipping", response_model=schemas.Ticket)
def update_shipping(
    ticket_id: int,
    shipping: schemas.TicketUpdateShipping,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([
        models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO
    ]))
):
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    ticket.empresa_transporte  = shipping.empresa_transporte
    ticket.tracking_number     = shipping.tracking_number
    ticket.fecha_envio         = to_utc_naive(shipping.fecha_envio) if shipping.fecha_envio else utcnow()
    ticket.fecha_actualizacion = utcnow()
    db.commit()
    db.refresh(ticket)
    return schemas.Ticket.from_orm_with_tecnico(ticket, current_user.id)

# ── Tags — add (Feature 4: log event) ────────────────────────────────────────
@router.post("/{ticket_id}/tags", response_model=schemas.Ticket)
def add_ticket_tag(
    ticket_id: int,
    tag_add: schemas.TicketAddTag,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([
        models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO
    ]))
):
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    tag = db.query(models.Tag).filter_by(nombre=tag_add.tag_nombre).first()
    if not tag:
        tag = models.Tag(nombre=tag_add.tag_nombre)
        db.add(tag); db.flush()
    if tag not in ticket.tags:
        ticket.tags.append(tag)
        ticket.fecha_actualizacion = utcnow()
        log_event(db, ticket_id, current_user.id,
                  models.EventoHistorial.TAG_AGREGADO,
                  detalle=f"Etiqueta agregada: {tag.nombre}")
        db.commit()
    db.refresh(ticket)
    return schemas.Ticket.from_orm_with_tecnico(ticket, current_user.id)

# ── Tags — set (replace all, Feature 4) ──────────────────────────────────────
@router.put("/{ticket_id}/tags", response_model=schemas.Ticket)
def set_ticket_tags(
    ticket_id: int,
    payload: schemas.TicketSetTags,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([
        models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO
    ]))
):
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")

    old_nombres = {t.nombre for t in ticket.tags}
    new_nombres = set(payload.tag_nombres)

    # added
    for name in new_nombres - old_nombres:
        tag = db.query(models.Tag).filter_by(nombre=name).first()
        if not tag:
            tag = models.Tag(nombre=name); db.add(tag); db.flush()
        ticket.tags.append(tag)
        log_event(db, ticket_id, current_user.id, models.EventoHistorial.TAG_AGREGADO,
                  detalle=f"Etiqueta agregada: {name}")
    # removed
    for name in old_nombres - new_nombres:
        tag = db.query(models.Tag).filter_by(nombre=name).first()
        if tag and tag in ticket.tags:
            ticket.tags.remove(tag)
            log_event(db, ticket_id, current_user.id, models.EventoHistorial.TAG_ELIMINADO,
                      detalle=f"Etiqueta eliminada: {name}")
    ticket.fecha_actualizacion = utcnow()
    db.commit()
    db.refresh(ticket)
    return schemas.Ticket.from_orm_with_tecnico(ticket, current_user.id)

# ── Tags — remove single ──────────────────────────────────────────────────────
@router.delete("/{ticket_id}/tags/{tag_nombre}", response_model=schemas.Ticket)
def remove_ticket_tag(
    ticket_id: int,
    tag_nombre: str,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([
        models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO
    ]))
):
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    tag = db.query(models.Tag).filter_by(nombre=tag_nombre).first()
    if tag and tag in ticket.tags:
        ticket.tags.remove(tag)
        ticket.fecha_actualizacion = utcnow()
        log_event(db, ticket_id, current_user.id, models.EventoHistorial.TAG_ELIMINADO,
                  detalle=f"Etiqueta eliminada: {tag.nombre}")
        db.commit()
    db.refresh(ticket)
    return schemas.Ticket.from_orm_with_tecnico(ticket, current_user.id)

# ── Repuestos ────────────────────────────────────────────────────────────────
@router.post("/{ticket_id}/parts", response_model=schemas.Ticket)
def add_ticket_part(
    ticket_id: int,
    part_add: schemas.TicketAddPart,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([
        models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO
    ]))
):
    db_ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not db_ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    part = db.query(models.Repuesto).filter(models.Repuesto.id == part_add.part_id).first()
    if not part:
        raise HTTPException(status_code=404, detail="Repuesto no encontrado")
    if part.stock < part_add.cantidad:
        raise HTTPException(status_code=400, detail=f"Stock insuficiente (disponible: {part.stock})")
    assoc = db.query(models.TicketRepuesto).filter_by(
        ticket_id=ticket_id, repuesto_id=part_add.part_id
    ).first()
    if assoc:
        assoc.cantidad += part_add.cantidad
    else:
        assoc = models.TicketRepuesto(ticket_id=ticket_id, repuesto_id=part_add.part_id,
                                      cantidad=part_add.cantidad)
        db.add(assoc)
    stock_anterior = part.stock
    part.stock -= part_add.cantidad
    mov = models.StockMovimiento(
        repuesto_id=part_add.part_id, ticket_id=ticket_id,
        usuario_id=current_user.id, tipo="consumo",
        cantidad=-part_add.cantidad,
        stock_anterior=stock_anterior, stock_nuevo=part.stock,
        nota=f"Consumido en ticket {db_ticket.numero_rma}",
    )
    db.add(mov)
    log_event(db, ticket_id, current_user.id, models.EventoHistorial.REPUESTO_AGREGADO,
              detalle=f"Repuesto: {part.nombre} × {part_add.cantidad}")
    db_ticket.fecha_actualizacion = utcnow()
    db.commit()
    db.refresh(db_ticket)
    return schemas.Ticket.from_orm_with_tecnico(db_ticket, current_user.id)

@router.patch("/{ticket_id}/parts/{part_id}", response_model=schemas.Ticket)
def update_ticket_part(
    ticket_id: int,
    part_id: int,
    payload: dict,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([
        models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO
    ]))
):
    """Change the quantity of a part already assigned to a ticket."""
    db_ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not db_ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    assoc = db.query(models.TicketRepuesto).filter_by(
        ticket_id=ticket_id, repuesto_id=part_id
    ).first()
    if not assoc:
        raise HTTPException(status_code=404, detail="Repuesto no asignado a este ticket")
    part = db.query(models.Repuesto).filter(models.Repuesto.id == part_id).first()
    nueva_cantidad = int(payload.get("cantidad", assoc.cantidad))
    if nueva_cantidad < 1:
        raise HTTPException(status_code=400, detail="La cantidad debe ser al menos 1")
    diff = nueva_cantidad - assoc.cantidad  # positive = need more stock, negative = return stock
    if diff > 0 and part.stock < diff:
        raise HTTPException(status_code=400, detail=f"Stock insuficiente para aumentar (disponible: {part.stock})")
    stock_anterior = part.stock
    part.stock -= diff
    assoc.cantidad = nueva_cantidad
    mov = models.StockMovimiento(
        repuesto_id=part_id, ticket_id=ticket_id,
        usuario_id=current_user.id, tipo="ajuste",
        cantidad=-diff,
        stock_anterior=stock_anterior, stock_nuevo=part.stock,
        nota=f"Ajuste cantidad en ticket {db_ticket.numero_rma}",
    )
    db.add(mov)
    log_event(db, ticket_id, current_user.id, models.EventoHistorial.CAMPO_EDITADO,
              detalle=f"Repuesto '{part.nombre}' cantidad ajustada a {nueva_cantidad}")
    db_ticket.fecha_actualizacion = utcnow()
    db.commit()
    db.refresh(db_ticket)
    return schemas.Ticket.from_orm_with_tecnico(db_ticket, current_user.id)

@router.delete("/{ticket_id}/parts/{part_id}", response_model=schemas.Ticket)
def remove_ticket_part(
    ticket_id: int,
    part_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([
        models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO
    ]))
):
    """Remove a part from a ticket and return its stock."""
    db_ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not db_ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    assoc = db.query(models.TicketRepuesto).filter_by(
        ticket_id=ticket_id, repuesto_id=part_id
    ).first()
    if not assoc:
        raise HTTPException(status_code=404, detail="Repuesto no asignado a este ticket")
    part = db.query(models.Repuesto).filter(models.Repuesto.id == part_id).first()
    stock_anterior = part.stock
    part.stock += assoc.cantidad  # return stock
    mov = models.StockMovimiento(
        repuesto_id=part_id, ticket_id=ticket_id,
        usuario_id=current_user.id, tipo="devolucion",
        cantidad=assoc.cantidad,
        stock_anterior=stock_anterior, stock_nuevo=part.stock,
        nota=f"Devuelto al quitar de ticket {db_ticket.numero_rma}",
    )
    db.add(mov)
    log_event(db, ticket_id, current_user.id, models.EventoHistorial.CAMPO_EDITADO,
              detalle=f"Repuesto '{part.nombre}' eliminado del ticket")
    db.delete(assoc)
    db_ticket.fecha_actualizacion = utcnow()
    db.commit()
    db.refresh(db_ticket)
    return schemas.Ticket.from_orm_with_tecnico(db_ticket, current_user.id)

# ── Historial (full, Feature 9) ───────────────────────────────────────────────
@router.get("/{ticket_id}/history", response_model=List[schemas.HistorialEntry])
def get_ticket_history(
    ticket_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.get_current_user)
):
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    if current_user.rol == models.UserRole.CLIENTE and ticket.usuario_id != current_user.id:
        raise HTTPException(status_code=403, detail="Acceso denegado")
    query = db.query(models.HistorialEstado).filter_by(ticket_id=ticket_id)
    if current_user.rol == models.UserRole.CLIENTE:
        # Las notas internas se registran en el historial con su texto: no son para el cliente
        query = query.filter(models.HistorialEstado.tipo_evento != models.EventoHistorial.NOTA_INTERNA)
    entries = query.order_by(models.HistorialEstado.fecha.desc()).all()
    return _historial_out(entries)

# ── Diagnostic ───────────────────────────────────────────────────────────────
@router.put("/{ticket_id}/diagnostic", response_model=schemas.Ticket)
def update_diagnostic(
    ticket_id: int,
    data: dict,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([
        models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO
    ]))
):
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    old_diag = ticket.diagnostico
    new_diag = data.get("diagnostico", "")
    if old_diag != new_diag:
        log_event(db, ticket_id, current_user.id, models.EventoHistorial.CAMPO_EDITADO,
                  campo="diagnostico", val_ant=old_diag, val_nuevo=new_diag,
                  detalle="Diagnóstico técnico actualizado")
    ticket.diagnostico = new_diag
    ticket.fecha_actualizacion = utcnow()
    db.commit()
    db.refresh(ticket)
    return schemas.Ticket.from_orm_with_tecnico(ticket, current_user.id)

# ── Clone ticket (Feature 11) ─────────────────────────────────────────────────
@router.post("/{ticket_id}/clone", response_model=schemas.Ticket)
def clone_ticket(
    ticket_id: int,
    payload: schemas.TicketClone,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([
        models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO
    ]))
):
    orig = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not orig:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")

    from ..services.ticket_service import generate_rma_number
    rma_num = generate_rma_number(db, orig.cliente.rol if orig.cliente else "cliente")

    clone = models.Ticket(
        numero_rma=rma_num,
        usuario_id=orig.usuario_id,
        producto_id=orig.producto_id,
        producto=orig.producto,
        numero_serie=orig.numero_serie,
        fecha_compra=orig.fecha_compra,
        en_garantia=orig.en_garantia,
        descripcion=orig.descripcion,
        prioridad=orig.prioridad,
        estado=models.TicketStatus.NUEVO,
        clonado_de=orig.id,
        ticket_relacionado=orig.id if payload.relacionar else None,
        fecha_actualizacion=utcnow(),
    )
    db.add(clone)
    db.flush()

    for t in orig.tags:
        clone.tags.append(t)

    log_event(db, clone.id, current_user.id, models.EventoHistorial.TICKET_CLONADO,
              detalle=f"Clonado de {orig.numero_rma}")
    log_event(db, orig.id, current_user.id, models.EventoHistorial.TICKET_RELACIONADO,
              detalle=f"Clonado como {rma_num}")
    db.commit()
    db.refresh(clone)
    return schemas.Ticket.from_orm_with_tecnico(clone, current_user.id)

# ── Set/remove relation (Feature 11) ─────────────────────────────────────────
@router.patch("/{ticket_id}/relation", response_model=schemas.Ticket)
def set_ticket_relation(
    ticket_id: int,
    payload: schemas.TicketSetRelacion,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([
        models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO
    ]))
):
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    old_rel = ticket.ticket_relacionado
    ticket.ticket_relacionado = payload.ticket_relacionado_id
    tipo = models.EventoHistorial.TICKET_DESASOCIADO if payload.ticket_relacionado_id is None \
           else models.EventoHistorial.TICKET_RELACIONADO
    log_event(db, ticket_id, current_user.id, tipo,
              detalle=f"Relación modificada")
    db.commit()
    db.refresh(ticket)
    return schemas.Ticket.from_orm_with_tecnico(ticket, current_user.id)

# ── Attachments ───────────────────────────────────────────────────────────────

def _ticket_used_bytes(ticket_id: int, db) -> int:
    """Sum of stored file sizes for a ticket (based on DB tamanio field)."""
    adjuntos = db.query(models.Adjunto).filter_by(ticket_id=ticket_id).all()
    return sum(a.tamanio or 0 for a in adjuntos)


def _serialize_adjunto(a: models.Adjunto) -> dict:
    ext = (a.nombre_archivo or "").rsplit(".", 1)[-1].lower()
    return {
        "id":             a.id,
        "ticket_id":      a.ticket_id,
        "nombre_archivo": a.nombre_archivo,
        "tamanio":        a.tamanio or 0,
        "mime_type":      a.mime_type or "",
        "ext":            ext,
        "fecha":          iso_utc(a.fecha) if a.fecha else None,
    }


@router.post("/{ticket_id}/attachments")
def upload_attachment(
    ticket_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.get_current_user)
):
    _get_ticket_for_user(ticket_id, current_user, db)

    # ── Validate extension ────────────────────────────────────────────────
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo de archivo no permitido. Solo se aceptan: {', '.join(sorted(ALLOWED_EXTENSIONS)).upper()}"
        )

    # ── Read into memory ──────────────────────────────────────────────────
    file_data = file.file.read()
    file_size = len(file_data)

    # ── Per-file size limit ───────────────────────────────────────────────
    if file_size > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"El archivo supera el límite individual de 10 MB."
        )

    # ── Total ticket quota ────────────────────────────────────────────────
    used_bytes = _ticket_used_bytes(ticket_id, db)
    if used_bytes + file_size > MAX_TICKET_UPLOAD_BYTES:
        remaining_mb = round((MAX_TICKET_UPLOAD_BYTES - used_bytes) / (1024 * 1024), 2)
        raise HTTPException(
            status_code=400,
            detail=f"Límite del ticket alcanzado. Espacio disponible: {remaining_mb} MB de 10 MB."
        )

    # ── Build safe filename & per-ticket folder ───────────────────────────
    safe_display, stored_name = _safe_filename(file.filename or "archivo")
    ticket_dir = os.path.join(UPLOAD_DIR, f"ticket_{ticket_id}")
    os.makedirs(ticket_dir, exist_ok=True)
    dest = os.path.join(ticket_dir, stored_name)

    with open(dest, "wb") as f:
        f.write(file_data)

    # ── Detect MIME from content type header (fallback to extension) ──────
    mime = file.content_type or ""
    if mime not in ALLOWED_MIME_TYPES:
        ext_to_mime = {
            "pdf": "application/pdf", "txt": "text/plain",
            "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
        }
        mime = ext_to_mime.get(ext, "application/octet-stream")

    adj = models.Adjunto(
        ticket_id=ticket_id,
        nombre_archivo=safe_display,
        nombre_guardado=stored_name,
        ruta_archivo=dest,
        tamanio=file_size,
        mime_type=mime,
    )
    db.add(adj)
    log_event(db, ticket_id, current_user.id,
              models.EventoHistorial.ARCHIVO_SUBIDO,
              detalle=f"Archivo subido: {safe_display}")
    db.commit()
    db.refresh(adj)

    used_after = used_bytes + file_size
    return {
        "adjunto": _serialize_adjunto(adj),
        "storage": {
            "used_mb":      round(used_after / (1024 * 1024), 2),
            "remaining_mb": round((MAX_TICKET_UPLOAD_BYTES - used_after) / (1024 * 1024), 2),
            "limit_mb":     10,
        }
    }


@router.get("/{ticket_id}/attachments")
def list_attachments(
    ticket_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.get_current_user)
):
    _get_ticket_for_user(ticket_id, current_user, db)
    adjuntos = db.query(models.Adjunto).filter_by(ticket_id=ticket_id).all()
    used_bytes = sum(a.tamanio or 0 for a in adjuntos)
    return {
        "adjuntos": [_serialize_adjunto(a) for a in adjuntos],
        "storage": {
            "used_mb":      round(used_bytes / (1024 * 1024), 2),
            "remaining_mb": round((MAX_TICKET_UPLOAD_BYTES - used_bytes) / (1024 * 1024), 2),
            "limit_mb":     10,
        }
    }


@router.get("/{ticket_id}/attachments/{adj_id}/download")
def download_attachment(
    ticket_id: int,
    adj_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.get_current_user),
):
    # Auth only via the Authorization header: a token in the URL ends up in
    # server logs, browser history and Referer headers.
    _get_ticket_for_user(ticket_id, current_user, db)

    adj = db.query(models.Adjunto).filter_by(id=adj_id, ticket_id=ticket_id).first()
    if not adj:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    path = _adjunto_path(adj)
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Archivo no encontrado en el servidor")
    return FileResponse(
        path=path,
        filename=adj.nombre_archivo,
        media_type=adj.mime_type or "application/octet-stream",
    )


@router.delete("/{ticket_id}/attachments/{adj_id}", status_code=204)
def delete_attachment(
    ticket_id: int,
    adj_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([
        models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO
    ]))
):
    adj = db.query(models.Adjunto).filter_by(id=adj_id, ticket_id=ticket_id).first()
    if not adj:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    nombre_del_archivo = adj.nombre_archivo
    # Remove from disk safely
    try:
        path = _adjunto_path(adj)
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass
    db.delete(adj)
    log_event(db, ticket_id, current_user.id,
              models.EventoHistorial.ARCHIVO_ELIMINADO,
              detalle=f"Archivo eliminado: {nombre_del_archivo}")
    db.commit()
