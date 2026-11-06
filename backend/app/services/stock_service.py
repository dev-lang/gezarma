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


def ajustar(db: Session, repuesto: models.Repuesto, delta: int, minimo_cero: bool = False):
    """Suma `delta` al stock en la base (UPDATE ... SET stock = stock + delta) y
    devuelve (stock_anterior, stock_nuevo). Hecho en SQL, dos consumos simultáneos
    no se pisan. Con minimo_cero=True falla (400) si no alcanza, sin tocar nada."""
    from sqlalchemy import update
    from sqlalchemy.orm.attributes import set_committed_value
    R = models.Repuesto
    q = update(R).where(R.id == repuesto.id)
    if minimo_cero and delta < 0:
        q = q.where(R.stock + delta >= 0)
    nuevo = db.execute(q.values(stock=R.stock + delta).returning(R.stock)
                       .execution_options(synchronize_session=False)).scalar()
    if nuevo is None:
        actual = db.query(R.stock).filter(R.id == repuesto.id).scalar()
        raise HTTPException(400, f"Stock insuficiente (disponible: {actual})")
    set_committed_value(repuesto, "stock", nuevo)
    return nuevo - delta, nuevo


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
    anterior, _ = ajustar(db, repuesto, -cantidad, minimo_cero=not permitir_negativo)

    assoc = db.query(models.TicketRepuesto).filter_by(ticket_id=ticket.id, repuesto_id=repuesto.id).first()
    if assoc:
        assoc.cantidad += cantidad
    else:
        db.add(models.TicketRepuesto(ticket_id=ticket.id, repuesto_id=repuesto.id, cantidad=cantidad))

    db.add(models.StockMovimiento(
        repuesto_id=repuesto.id, ticket_id=ticket.id, usuario_id=usuario_id, tipo="consumo",
        cantidad=-cantidad, stock_anterior=anterior, stock_nuevo=repuesto.stock,
        nota=nota or f"Consumido en ticket {ticket.numero_rma}",
    ))
    log_event(db, ticket.id, usuario_id, models.EventoHistorial.REPUESTO_AGREGADO,
              detalle=f"Repuesto: {repuesto.nombre} × {cantidad}")
    revisar_minimo(db, repuesto, anterior)


def anular_movimiento(db: Session, mov: models.StockMovimiento, usuario: models.Usuario) -> models.StockMovimiento:
    """Anula un movimiento con otro inverso (no se borra: queda el registro).

    Corrige también lo que el movimiento afectó: el repuesto del ticket (consumo
    o ajuste) o lo recibido de un pedido. Lo que no se puede deshacer limpio —
    una devolución o un ajuste dentro de un ticket— se corrige desde el ticket.
    """
    if mov.anulado or mov.anula_id:
        raise HTTPException(400, "Ese movimiento ya está anulado (o es una anulación)")
    delta = -(mov.cantidad or 0)
    if mov.ticket_id and mov.tipo == "consumo":
        assoc = db.query(models.TicketRepuesto).filter_by(ticket_id=mov.ticket_id, repuesto_id=mov.repuesto_id).first()
        usado = assoc.cantidad if assoc else 0
        if usado < -mov.cantidad:
            raise HTTPException(400, f"El ticket {mov.ticket.numero_rma} ya no tiene esas unidades: "
                                     "ajustá la cantidad desde el ticket.")
        assoc.cantidad -= -mov.cantidad
        if assoc.cantidad == 0:
            db.delete(assoc)
        log_event(db, mov.ticket_id, usuario.id, models.EventoHistorial.CAMPO_EDITADO,
                  detalle=f"Consumo de {mov.repuesto.nombre} × {-mov.cantidad} anulado desde Stock")
    elif mov.ticket_id:
        raise HTTPException(400, f"Ese movimiento es del ticket {mov.ticket.numero_rma}: corregilo desde el ticket.")
    if mov.pedido_item_id:
        item = mov.pedido_item
        if item.recibido < mov.cantidad:
            raise HTTPException(400, "El pedido ya no tiene esas unidades recibidas")
        item.recibido -= mov.cantidad
        pedido = item.pedido
        if pedido.estado in ("recibido", "parcial"):
            pedido.estado = "parcial" if any(i.recibido for i in pedido.items) else "enviado"
            pedido.fecha_recepcion = None
    anterior, nuevo = ajustar(db, mov.repuesto, delta)
    mov.anulado = True
    inverso = models.StockMovimiento(
        repuesto_id=mov.repuesto_id, ticket_id=mov.ticket_id, usuario_id=usuario.id, tipo="anulacion",
        cantidad=delta, stock_anterior=anterior, stock_nuevo=nuevo, anula_id=mov.id,
        nota=f"Anula el movimiento #{mov.id} ({mov.tipo})")
    db.add(inverso)
    revisar_minimo(db, mov.repuesto, anterior)
    return inverso


def alertas(db: Session) -> list:
    """Repuestos en o bajo su mínimo, o con stock negativo (filtrado en la base)."""
    from sqlalchemy import and_, or_
    R = models.Repuesto
    return (db.query(R).filter(or_(R.stock < 0, and_(R.stock_minimo > 0, R.stock <= R.stock_minimo)))
            .order_by(R.nombre).all())
