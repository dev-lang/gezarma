"""
retiro.py — Equipos listos para retirar.

- Al pasar al estado configurado (Ajustes → Retiro, por defecto «Reparado») se
  registra desde cuándo está listo y se avisa al cliente con el plazo de guarda.
- La tarea periódica (la misma de los SLA) manda recordatorios cada N días
  mientras siga sin retirar y, al vencer el plazo, avisa una vez al taller.
- Deja de estar "para retirar" cuando cambia de estado (entregado, enviado…).
"""
import math
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .. import ajustes, models
from ..timeutils import utcnow
from . import avisos


def estado_retiro(db: Session) -> str:
    return ajustes.get(db, "retiro_estado")


def vence(db: Session, t: models.Ticket):
    if not t.fecha_listo:
        return None
    return t.fecha_listo + timedelta(days=ajustes.get(db, "retiro_dias_guarda"))


def al_cambiar_estado(db: Session, t: models.Ticket, ahora: datetime = None) -> bool:
    """Llamar después de cambiar t.estado. Devuelve True si quedó listo para retirar."""
    if t.estado != estado_retiro(db):
        return False
    ahora = ahora or utcnow()
    t.fecha_listo = t.retiro_ultimo_aviso = ahora
    t.retiro_recordatorios = 0
    t.retiro_vencido_avisado = False
    return True


def pendientes(db: Session) -> list:
    from sqlalchemy.orm import joinedload
    return (db.query(models.Ticket).options(joinedload(models.Ticket.cliente))
            .filter(models.Ticket.estado == estado_retiro(db), models.Ticket.fecha_listo.isnot(None))
            .order_by(models.Ticket.fecha_listo.asc()).all())


def info(db: Session, t: models.Ticket, ahora: datetime = None) -> dict:
    ahora = ahora or utcnow()
    v = vence(db, t)
    return {"listo_desde": t.fecha_listo, "vence": v, "dias_esperando": (ahora - t.fecha_listo).days,
            # Días que quedan, redondeando para arriba: el día del aviso con 90 de plazo, "quedan 90"
            "dias_restantes": max(0, math.ceil((v - ahora).total_seconds() / 86400)) if v else None,
            "vencido": bool(v and ahora >= v),
            "recordatorios": t.retiro_recordatorios}


def revisar(db: Session, ahora: datetime = None) -> int:
    """Recordatorios al cliente y aviso de plazo vencido. Devuelve cuántos avisos mandó."""
    ahora = ahora or utcnow()
    cada = ajustes.get(db, "retiro_recordatorio_dias")
    from . import email
    n = 0
    for t in pendientes(db):
        v = vence(db, t)
        if ahora >= v:
            if not t.retiro_vencido_avisado:
                avisos.notificar(db, avisos.admins(db), models.TipoNotificacion.CAMBIO_ESTADO,
                                 f"Sin retirar: {t.numero_rma}",
                                 f"{t.producto} de {t.cliente.nombre if t.cliente else 'cliente'} lleva "
                                 f"{(ahora - t.fecha_listo).days} días listo y venció el plazo de guarda.",
                                 ticket_id=t.id)
                t.retiro_vencido_avisado = True
                n += 1
            continue
        if cada and t.retiro_ultimo_aviso and ahora - t.retiro_ultimo_aviso >= timedelta(days=cada):
            if t.cliente:
                avisos.notificar(db, [t.cliente], models.TipoNotificacion.CAMBIO_ESTADO,
                                 f"Tu equipo te espera: {t.numero_rma}",
                                 f"Tu {t.producto} está listo para retirar desde hace {(ahora - t.fecha_listo).days} días.",
                                 ticket_id=t.id)
            email.cliente_retiro(db, t, recordatorio=True)
            t.retiro_ultimo_aviso = ahora
            t.retiro_recordatorios += 1
            n += 1
    db.commit()
    return n
