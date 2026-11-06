"""
encuestas.py — Encuesta de satisfacción al cerrar el ticket.

El cliente califica de 1 a 5 (con comentario opcional) una sola vez por
ticket, desde su cuenta o desde el seguimiento público (RMA + N° de serie,
así también pueden responder los clientes de mostrador sin clave).
"""
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import ajustes, models
from ..timeutils import utcnow


def habilitada(db: Session, t: models.Ticket) -> bool:
    return bool(ajustes.get(db, "encuesta_activa")) and t.estado == models.TicketStatus.CERRADO.value


def pendiente(db: Session, t: models.Ticket) -> bool:
    return habilitada(db, t) and t.encuesta is None


def responder(db: Session, t: models.Ticket, puntaje: int, comentario: str, origen: str) -> models.Encuesta:
    if not habilitada(db, t):
        raise HTTPException(status_code=400, detail="La encuesta está disponible cuando se cierra el ticket.")
    if t.encuesta is not None:
        raise HTTPException(status_code=409, detail="Esta reparación ya fue calificada. ¡Gracias!")
    if not isinstance(puntaje, int) or not 1 <= puntaje <= 5:
        raise HTTPException(status_code=400, detail="El puntaje va de 1 a 5.")
    e = models.Encuesta(ticket_id=t.id, puntaje=puntaje, comentario=(comentario or "").strip()[:1000] or None,
                        origen=origen)
    db.add(e)
    t.encuesta = e
    return e


def resumen(db: Session, dias: int = 90) -> dict:
    desde = utcnow() - timedelta(days=dias)
    encuestas = (db.query(models.Encuesta).filter(models.Encuesta.fecha >= desde)
                 .order_by(models.Encuesta.fecha.desc()).all())
    cerrados = (db.query(models.Ticket).filter(models.Ticket.estado == models.TicketStatus.CERRADO.value,
                                               models.Ticket.fecha_cierre >= desde).count())
    n = len(encuestas)
    return {
        "dias": dias, "cantidad": n, "cerrados": cerrados,
        "tasa_respuesta": round(n / cerrados, 3) if cerrados else None,
        "promedio": round(sum(e.puntaje for e in encuestas) / n, 2) if n else None,
        "distribucion": {str(p): sum(1 for e in encuestas if e.puntaje == p) for p in range(1, 6)},
        "comentarios": [{"ticket_id": e.ticket_id, "numero_rma": e.ticket.numero_rma, "puntaje": e.puntaje,
                         "comentario": e.comentario, "fecha": e.fecha,
                         "cliente": e.ticket.cliente.nombre if e.ticket.cliente else None,
                         "tecnico": e.ticket.tecnico.nombre if e.ticket.tecnico else None}
                        for e in encuestas if e.comentario][:10],
    }
