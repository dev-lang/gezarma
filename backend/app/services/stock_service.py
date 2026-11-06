"""
stock_service.py — Consumo de repuestos y alertas de stock mínimo.

Lo usan "agregar repuesto al ticket" (tickets.py) y la aprobación de un
presupuesto con ítems vinculados a repuestos (budget.py).
"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models
from . import avisos
from .ticket_service import log_event


def esta_bajo_minimo(r: models.Repuesto) -> bool:
    return r.stock < 0 or (bool(r.stock_minimo) and r.stock <= r.stock_minimo)


def revisar_minimo(db: Session, repuesto: models.Repuesto, stock_anterior: int) -> None:
    """Avisa si el stock acaba de cruzar el mínimo (o de pasar a negativo).
    Solo al cruzar, para no repetir el aviso en cada consumo."""
    m = repuesto.stock_minimo or 0
    cruzo_minimo = m > 0 and stock_anterior > m and repuesto.stock <= m
    cruzo_cero = stock_anterior >= 0 and repuesto.stock < 0
    if cruzo_minimo or cruzo_cero:
        avisos.stock_bajo(db, repuesto)


def agregar_al_ticket(db: Session, ticket: models.Ticket, repuesto: models.Repuesto, cantidad: int,
                      usuario_id: int, permitir_negativo: bool = False, nota: str = None) -> None:
    """Agrega `cantidad` del repuesto al ticket y la descuenta del stock.

    permitir_negativo=False → error 400 si no alcanza (agregado manual del técnico).
    permitir_negativo=True  → el stock puede quedar negativo (aprobación de un
    presupuesto: no se le rechaza al cliente; se avisa a los administradores).
    """
    if cantidad < 1:
        raise HTTPException(400, "La cantidad debe ser al menos 1")
    if not permitir_negativo and repuesto.stock < cantidad:
        raise HTTPException(400, f"Stock insuficiente (disponible: {repuesto.stock})")

    assoc = db.query(models.TicketRepuesto).filter_by(ticket_id=ticket.id, repuesto_id=repuesto.id).first()
    if assoc:
        assoc.cantidad += cantidad
    else:
        db.add(models.TicketRepuesto(ticket_id=ticket.id, repuesto_id=repuesto.id, cantidad=cantidad))

    anterior = repuesto.stock
    repuesto.stock -= cantidad
    db.add(models.StockMovimiento(
        repuesto_id=repuesto.id, ticket_id=ticket.id, usuario_id=usuario_id, tipo="consumo",
        cantidad=-cantidad, stock_anterior=anterior, stock_nuevo=repuesto.stock,
        nota=nota or f"Consumido en ticket {ticket.numero_rma}",
    ))
    log_event(db, ticket.id, usuario_id, models.EventoHistorial.REPUESTO_AGREGADO,
              detalle=f"Repuesto: {repuesto.nombre} × {cantidad}")
    revisar_minimo(db, repuesto, anterior)


def alertas(db: Session) -> list:
    """Repuestos en o bajo su mínimo, o con stock negativo."""
    return [r for r in db.query(models.Repuesto).order_by(models.Repuesto.nombre).all() if esta_bajo_minimo(r)]
