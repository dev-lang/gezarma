"""
ticket_tags.py — Etiquetas de un ticket (agregar, reemplazar, quitar).
(Separado de tickets.py; mismas URLs: /tickets/{id}/tags…)
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import database, models, schemas, auth
from ..timeutils import utcnow
from ..services.ticket_service import log_event
from ._tickets_comun import ticket_o_404

router = APIRouter(prefix="/tickets", tags=["tickets"])

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
    ticket = ticket_o_404(db, ticket_id)
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
    ticket = ticket_o_404(db, ticket_id)

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
    ticket = ticket_o_404(db, ticket_id)
    tag = db.query(models.Tag).filter_by(nombre=tag_nombre).first()
    if tag and tag in ticket.tags:
        ticket.tags.remove(tag)
        ticket.fecha_actualizacion = utcnow()
        log_event(db, ticket_id, current_user.id, models.EventoHistorial.TAG_ELIMINADO,
                  detalle=f"Etiqueta eliminada: {tag.nombre}")
        db.commit()
    db.refresh(ticket)
    return schemas.Ticket.from_orm_with_tecnico(ticket, current_user.id)
