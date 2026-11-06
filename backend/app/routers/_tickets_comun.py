"""_tickets_comun.py — Lo que comparten los routers del ticket."""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models

STAFF = [models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO]


def ticket_o_404(db: Session, ticket_id: int) -> models.Ticket:
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    return ticket


def ticket_para_usuario(ticket_id: int, current_user: models.Usuario, db: Session) -> models.Ticket:
    """404 si no existe; 403 si un cliente pide un ticket que no es suyo."""
    ticket = ticket_o_404(db, ticket_id)
    if current_user.rol == models.UserRole.CLIENTE and ticket.usuario_id != current_user.id:
        raise HTTPException(status_code=403, detail="Acceso denegado")
    return ticket
