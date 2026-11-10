"""
estados.py — Cambiar el estado de un ticket con todas sus consecuencias
(SLA, cierre, aviso de retiro, historial, notificaciones y mail al cliente).

Lo usan PUT /tickets/{id}/status y los cambios automáticos (envío al fabricante y su vuelta).
"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import ajustes, models
from ..timeutils import utcnow
from . import avisos, email
from . import retiro as retiro_service
from .ticket_service import calculate_sla_deadline, log_event, notify_ticket_actors

VALID_ESTADOS = {s.value for s in models.TicketStatus}


def validar(db: Session, estado: str) -> models.TicketStatusConfig:
    """Los estados se configuran en Administración → Estados (no solo los de fábrica)."""
    cfgs = {e.valor: e for e in db.query(models.TicketStatusConfig).all()}
    cfg = cfgs.get(estado)
    if cfgs:
        if not cfg or not cfg.activo:
            raise HTTPException(status_code=400, detail="Estado inválido o desactivado")
    elif estado not in VALID_ESTADOS:
        raise HTTPException(status_code=400, detail="Estado inválido")
    return cfg


def es_final(db: Session, estado: str) -> bool:
    cfg = db.query(models.TicketStatusConfig).filter_by(valor=estado).first()
    return cfg.es_final if cfg else estado in (models.TicketStatus.CERRADO, models.TicketStatus.CANCELADO)


def cambiar(db: Session, ticket: models.Ticket, estado: str, usuario: models.Usuario, detalle: str = None) -> bool:
    """Devuelve False si ya estaba en ese estado (no deja historial ni avisa). No hace commit."""
    cfg = validar(db, estado)
    if ticket.estado == estado:
        return False
    estado_ant = ticket.estado
    ticket.estado = estado
    ticket.fecha_actualizacion = utcnow()
    final = cfg.es_final if cfg else estado in (models.TicketStatus.CERRADO, models.TicketStatus.CANCELADO)
    # reabierto: deja de contar como cerrado (promedios, garantía)
    ticket.fecha_cierre = utcnow() if final else None
    ticket.deadline_sla = calculate_sla_deadline(estado)
    if retiro_service.al_cambiar_estado(db, ticket) and ticket.cliente:
        avisos.notificar(db, [ticket.cliente], models.TipoNotificacion.CAMBIO_ESTADO,
                         f"Listo para retirar: {ticket.numero_rma}",
                         f"Tu {ticket.producto} está listo. {ajustes.politica_retiro(db)}", ticket_id=ticket.id)
    log_event(db, ticket.id, usuario.id, models.EventoHistorial.CAMBIO_ESTADO,
              detalle=detalle or f"Estado: {estado_ant} → {estado}",
              estado_ant=estado_ant, estado_nuevo=estado)
    notify_ticket_actors(
        db, ticket,
        tipo=models.TipoNotificacion.CAMBIO_ESTADO,
        titulo=f"Estado actualizado: {ticket.numero_rma}",
        mensaje=f"{usuario.nombre} cambió el estado a «{estado}»",
        origen_usuario_id=usuario.id,
    )
    email.cliente_cambio_estado(db, ticket)   # se envía después del commit
    return True
