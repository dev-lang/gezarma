"""
ticket_repuestos.py — Repuestos usados en un ticket (agregar, ajustar cantidad, quitar).
(Separado de tickets.py; mismas URLs: /tickets/{id}/parts…)
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import database, models, schemas, auth
from ..timeutils import utcnow
from ..services import stock_service
from ..services.ticket_service import log_event
from ._tickets_comun import ticket_o_404

router = APIRouter(prefix="/tickets", tags=["tickets"])

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
    db_ticket = ticket_o_404(db, ticket_id)
    part = db.query(models.Repuesto).filter(models.Repuesto.id == part_add.part_id).first()
    if not part:
        raise HTTPException(status_code=404, detail="Repuesto no encontrado")
    stock_service.agregar_al_ticket(db, db_ticket, part, part_add.cantidad, current_user.id)
    db_ticket.fecha_actualizacion = utcnow()
    db.commit()
    db.refresh(db_ticket)
    return schemas.Ticket.from_orm_with_tecnico(db_ticket, current_user.id)

@router.patch("/{ticket_id}/parts/{part_id}", response_model=schemas.Ticket)
def update_ticket_part(
    ticket_id: int,
    part_id: int,
    payload: schemas.TicketPartQty,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([
        models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO
    ]))
):
    """Change the quantity of a part already assigned to a ticket."""
    db_ticket = ticket_o_404(db, ticket_id)
    assoc = db.query(models.TicketRepuesto).filter_by(
        ticket_id=ticket_id, repuesto_id=part_id
    ).first()
    if not assoc:
        raise HTTPException(status_code=404, detail="Repuesto no asignado a este ticket")
    part = assoc.repuesto
    nueva_cantidad = payload.cantidad
    diff = nueva_cantidad - assoc.cantidad  # positive = need more stock, negative = return stock
    if diff == 0:
        return schemas.Ticket.from_orm_with_tecnico(db_ticket, current_user.id)
    stock_anterior, _ = stock_service.ajustar(db, part, -diff, minimo_cero=True)
    stock_service.revisar_minimo(db, part, stock_anterior)
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
    db_ticket = ticket_o_404(db, ticket_id)
    assoc = db.query(models.TicketRepuesto).filter_by(
        ticket_id=ticket_id, repuesto_id=part_id
    ).first()
    if not assoc:
        raise HTTPException(status_code=404, detail="Repuesto no asignado a este ticket")
    part = assoc.repuesto
    stock_anterior, _ = stock_service.ajustar(db, part, assoc.cantidad)  # vuelve al stock
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
