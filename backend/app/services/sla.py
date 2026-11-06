"""
sla.py — Alertas de SLA (tickets vencidos o por vencer).

- alertas(db): lo que muestra el panel del dashboard.
- revisar(db): la tarea periódica. Avisa una sola vez cuando un ticket entra
  en "por vencer" y otra cuando vence (si el SLA cambia, vuelve a avisar).
  Avisa al técnico asignado (o a los administradores si no hay); cuando vence,
  también a los administradores. Con email activado, cada persona recibe un
  solo mail con la lista de sus tickets.
"""
import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .. import ajustes, config, database, models
from ..timeutils import utcnow
from . import avisos

log = logging.getLogger("uvicorn.error")
NIVELES = {"por_vencer": 1, "vencido": 2}


def _tickets_con_sla(db: Session):
    finales = {e.valor for e in db.query(models.TicketStatusConfig).filter_by(es_final=True).all()}
    finales |= {models.TicketStatus.CERRADO.value, models.TicketStatus.CANCELADO.value}
    from sqlalchemy.orm import joinedload
    return (db.query(models.Ticket).options(joinedload(models.Ticket.tecnico))
            .filter(models.Ticket.deadline_sla.isnot(None), models.Ticket.estado.notin_(finales))
            .order_by(models.Ticket.deadline_sla.asc()).all())


def alertas(db: Session, ahora: datetime = None) -> list:
    ahora = ahora or utcnow()
    limite = ahora + timedelta(hours=ajustes.get(db, "sla_aviso_horas"))
    return [t for t in _tickets_con_sla(db) if t.deadline_sla <= limite]


def horas_restantes(t: models.Ticket, ahora: datetime = None) -> float:
    return round((t.deadline_sla - (ahora or utcnow())).total_seconds() / 3600, 2)


def _texto(t: models.Ticket, ahora: datetime) -> str:
    h = horas_restantes(t, ahora)
    cuando = f"vencido hace {abs(h):.0f} h" if h < 0 else f"vence en {h:.0f} h"
    return f"{t.numero_rma} · {t.producto} · {t.estado} · {cuando}"


def revisar(db: Session, ahora: datetime = None) -> int:
    """Manda los avisos pendientes. Devuelve cuántos tickets avisó."""
    if not ajustes.get(db, "sla_alertas"):
        return 0
    ahora = ahora or utcnow()
    admins = avisos.admins(db)
    por_usuario = {}   # usuario → lista de líneas para un único mail
    avisados = 0
    for t in alertas(db, ahora):
        nivel = "vencido" if t.deadline_sla <= ahora else "por_vencer"
        ya = t.sla_aviso_deadline == t.deadline_sla and NIVELES.get(t.sla_aviso_nivel, 0) >= NIVELES[nivel]
        if ya:
            continue
        destinatarios = [t.tecnico] if t.tecnico and t.tecnico.activo else []
        if nivel == "vencido" or not destinatarios:
            destinatarios += [a for a in admins if a not in destinatarios]
        titulo = f"SLA {'vencido' if nivel == 'vencido' else 'por vencer'}: {t.numero_rma}"
        avisos.notificar(db, destinatarios, models.TipoNotificacion.CAMBIO_ESTADO, titulo, _texto(t, ahora),
                         ticket_id=t.id)
        for u in destinatarios:
            por_usuario.setdefault(u.id, (u, []))[1].append(_texto(t, ahora))
        t.sla_aviso_deadline, t.sla_aviso_nivel = t.deadline_sla, nivel
        avisados += 1
    from . import email
    for u, lineas in por_usuario.values():
        email.sla(db, [u], f"SLA: {len(lineas)} ticket(s) vencido(s) o por vencer",
                  ["Estos tickets tienen el SLA vencido o por vencer:"] + lineas)
    db.commit()
    return avisados


def _una_vuelta() -> int:
    """Una revisión completa (corre en un hilo aparte). Cada tarea tiene su propia
    sesión y su propio manejo de errores: si una falla, las otras igual corren.
    Devuelve los minutos a esperar hasta la próxima."""
    from . import retiro
    tareas = (("SLA", revisar, "se avisó sobre %d ticket(s)"),
              ("Retiro", retiro.revisar, "%d aviso(s) de equipos sin retirar"))
    for nombre, tarea, mensaje in tareas:
        db = database.SessionLocal()
        try:
            n = tarea(db)
            if n:
                log.info(f"{nombre}: {mensaje}", n)
        except Exception:
            db.rollback()
            log.exception("Error en la tarea periódica %s", nombre)
        finally:
            db.close()
    db = database.SessionLocal()
    try:
        return ajustes.get(db, "sla_intervalo_minutos")
    finally:
        db.close()


async def bucle() -> None:
    """Tarea de fondo: revisa los SLA cada `sla_intervalo_minutos` (Ajustes)."""
    await asyncio.sleep(60)   # dejar arrancar la app
    while True:
        try:
            intervalo = await asyncio.to_thread(_una_vuelta)
        except Exception:
            log.exception("Error revisando los SLA")
            intervalo = 15
        await asyncio.sleep(max(1, intervalo) * 60)


def iniciar():
    """Arranca la tarea de fondo (si TAREAS_PERIODICAS lo permite)."""
    if not config.TAREAS_PERIODICAS:
        return None
    return asyncio.create_task(bucle())
