"""
avisos.py — Avisos internos del sistema que no son de un ticket en particular
(stock bajo, SLA) o que van a un grupo de usuarios (administradores, taller).

Crea las notificaciones dentro del sistema. El envío por email se engancha
desde services/email.py.
"""
from sqlalchemy.orm import Session

from .. import models


def admins(db: Session) -> list:
    return db.query(models.Usuario).filter(
        models.Usuario.rol == models.UserRole.ADMINISTRADOR, models.Usuario.activo == True  # noqa: E712
    ).all()


def notificar(db: Session, usuarios, tipo: str, titulo: str, mensaje: str,
              ticket_id: int = None, origen_usuario_id: int = None) -> None:
    for u in usuarios:
        db.add(models.Notificacion(usuario_id=u.id, ticket_id=ticket_id, tipo=tipo, titulo=titulo,
                                   mensaje=mensaje, origen_usuario_id=origen_usuario_id))


def stock_bajo(db: Session, repuesto: models.Repuesto) -> None:
    """Un repuesto quedó en o bajo su stock mínimo (o en negativo)."""
    if repuesto.stock < 0:
        titulo = f"Faltan repuestos: {repuesto.nombre}"
        mensaje = (f"El stock de {repuesto.nombre} ({repuesto.codigo}) quedó en {repuesto.stock}: "
                   f"se usaron más unidades de las disponibles. Hay que reponer.")
    else:
        titulo = f"Stock bajo: {repuesto.nombre}"
        mensaje = (f"Quedan {repuesto.stock} unidades de {repuesto.nombre} ({repuesto.codigo}); "
                   f"el mínimo es {repuesto.stock_minimo}.")
    destinatarios = admins(db)
    notificar(db, destinatarios, models.TipoNotificacion.REPUESTO, titulo, mensaje)
    from . import email
    email.stock_bajo(db, repuesto, destinatarios, titulo, mensaje)
