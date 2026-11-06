"""
garantia.py — Garantía de la reparación.

Cuando el mismo cliente trae un equipo (mismo N° de serie) que se entregó o cerró
hace menos de `garantia_reparacion_dias`, el ticket nuevo se marca como
reingreso en garantía: queda vinculado al anterior, sube a prioridad Alta y se
avisa al técnico que lo reparó (y a los administradores).
"""
from datetime import timedelta

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import ajustes, models
from ..timeutils import utc_to_local, utcnow
from . import avisos

PRIORIDADES_ALTAS = {"Alta", "Urgente"}


def reparacion_anterior(db: Session, t: models.Ticket):
    """La última reparación terminada de ese N° de serie dentro del plazo, o None."""
    dias = ajustes.get(db, "garantia_reparacion_dias")
    serie = (t.numero_serie or "").strip().upper()
    if not dias or not serie:
        return None
    desde = utcnow() - timedelta(days=dias)
    entregado = func.coalesce(models.Ticket.fecha_cierre, models.Ticket.fecha_envio)
    # Solo reparaciones del mismo cliente: si no, con el N° de serie de un equipo
    # ajeno se obtendría su RMA (y con él, su seguimiento público)
    return (db.query(models.Ticket)
            .filter(models.Ticket.id != t.id,
                    models.Ticket.usuario_id == t.usuario_id,
                    func.upper(func.trim(models.Ticket.numero_serie)) == serie,
                    or_(models.Ticket.estado == models.TicketStatus.CERRADO.value,
                        models.Ticket.estado == models.TicketStatus.ENVIADO.value),
                    entregado.isnot(None), entregado >= desde)
            .order_by(entregado.desc()).first())


def revisar_reingreso(db: Session, t: models.Ticket, usuario: models.Usuario) -> bool:
    """Llamar al crear el ticket (antes del commit). Devuelve True si es reingreso en garantía."""
    prev = reparacion_anterior(db, t)
    if not prev:
        return False
    t.reingreso_de = prev.id
    t.reingreso_garantia = True
    if not t.ticket_relacionado:
        t.ticket_relacionado = prev.id
    if t.prioridad not in PRIORIDADES_ALTAS:
        t.prioridad = "Alta"
    cuando = utc_to_local(prev.fecha_cierre or prev.fecha_envio).strftime("%d/%m/%Y")
    from .ticket_service import log_event
    log_event(db, t.id, usuario.id, models.EventoHistorial.TICKET_RELACIONADO,
              detalle=f"Reingreso en garantía de la reparación {prev.numero_rma} (entregado el {cuando})")
    destinatarios = [prev.tecnico] if prev.tecnico and prev.tecnico.activo else []
    destinatarios += [a for a in avisos.admins(db) if a not in destinatarios]
    avisos.notificar(db, destinatarios, models.TipoNotificacion.ASIGNACION,
                     f"Reingreso en garantía: {t.numero_rma}",
                     f"{t.producto} (SN {t.numero_serie}) volvió: lo había reparado "
                     f"{prev.tecnico.nombre if prev.tecnico else 'el taller'} en {prev.numero_rma} ({cuando}).",
                     ticket_id=t.id)
    if prev.tecnico and prev.tecnico.activo:
        from . import email
        email.reingreso(db, t, prev)
    return True
