"""
horas.py — Calendario de horas de los técnicos: cargar, mover, corregir y borrar
tramos a mano, con reglas y registro de cambios.

Reglas (para cualquier alta o cambio hecho a mano):
- El fin es posterior al inicio, no hay horas a futuro y un tramo dura hasta 16 h.
- Un técnico no puede tener dos tramos que se pisen, ni más de 16 h en un día.
- Un técnico corrige sus horas hasta `horas_dias_correccion` días atrás (ajuste);
  después solo un administrador. Un técnico solo toca sus propias horas.
- Un cronómetro en curso no se edita ni se mueve: primero se pausa.
- Un tramo es de un ticket o, sin ticket, de una tarea del taller (CATEGORIAS).
Cada cambio queda en tiempo_cambios (antes / después) y, si hay ticket, en su historial.

Los días se cuentan en la hora del negocio (config.TIMEZONE).
"""
from datetime import date, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload

from .. import ajustes, config, models
from ..timeutils import iso_utc, tz, utcnow
from .ticket_service import log_event

CATEGORIAS = {
    "capacitacion":   "Capacitación",
    "limpieza":       "Limpieza y orden del taller",
    "administracion": "Tareas administrativas",
    "otra":           "Otra tarea del taller",
}
MAX_TRAMO = timedelta(hours=16)
MAX_DIA_MIN = 16 * 60
INICIO_DIA = time(9, 0)   # "solo duración" sin nada cargado ese día: arranca a las 9


def _error(msg: str, status: int = 400):
    raise HTTPException(status_code=status, detail=msg)


# ── Hora local ⇄ UTC naive ───────────────────────────────────────────────────
def a_local(dt_utc: datetime) -> datetime:
    from datetime import timezone
    return dt_utc.replace(tzinfo=timezone.utc).astimezone(tz()).replace(tzinfo=None)


def a_utc(dt_local: datetime) -> datetime:
    from datetime import timezone
    return dt_local.replace(tzinfo=tz()).astimezone(timezone.utc).replace(tzinfo=None)


def dia_de(dt_utc: datetime) -> date:
    return a_local(dt_utc).date()


def limites_dia(d: date) -> tuple[datetime, datetime]:
    """[inicio, fin) del día local d, en UTC naive."""
    return a_utc(datetime.combine(d, time.min)), a_utc(datetime.combine(d + timedelta(days=1), time.min))


def hoy() -> date:
    return dia_de(utcnow())


# ── Serialización ────────────────────────────────────────────────────────────
def minutos(r: models.TiempoTrabajo, ahora=None) -> float:
    return max(0.0, ((r.fin or ahora or utcnow()) - r.inicio).total_seconds() / 60)


def foto(r: models.TiempoTrabajo) -> dict:
    """Lo que se guarda en el registro de cambios."""
    return {"ticket_id": r.ticket_id, "numero_rma": r.ticket.numero_rma if r.ticket else None,
            "categoria": r.categoria, "inicio": iso_utc(r.inicio), "fin": iso_utc(r.fin) if r.fin else None,
            "minutos": round(minutos(r)), "nota": r.nota}


def puede_editar(db: Session, r: models.TiempoTrabajo, usuario: models.Usuario) -> tuple[bool, str]:
    if r.fin is None:
        return False, "Está corriendo: pausalo para editarlo."
    if usuario.rol == models.UserRole.ADMINISTRADOR:
        return True, ""
    if r.usuario_id != usuario.id:
        return False, "Solo podés modificar tus propias horas."
    if dia_de(r.inicio) < limite_correccion(db):
        return False, "Pasó el plazo para corregirlo: pedíselo a un administrador."
    return True, ""


def limite_correccion(db: Session) -> date:
    return hoy() - timedelta(days=int(ajustes.get(db, "horas_dias_correccion")))


def salida(db: Session, r: models.TiempoTrabajo, usuario: models.Usuario, ahora=None) -> dict:
    ok, motivo = puede_editar(db, r, usuario)
    t = r.ticket
    return {
        "id": r.id, "usuario_id": r.usuario_id, "usuario_nombre": r.usuario.nombre if r.usuario else None,
        "ticket_id": r.ticket_id, "numero_rma": t.numero_rma if t else None, "producto": t.producto if t else None,
        "estado": t.estado if t else None, "categoria": r.categoria,
        "categoria_etiqueta": CATEGORIAS.get(r.categoria) if r.categoria else None,
        "inicio": iso_utc(r.inicio), "fin": iso_utc(r.fin) if r.fin else None, "dia": dia_de(r.inicio).isoformat(),
        "minutos": round(minutos(r, ahora), 1), "nota": r.nota, "manual": r.manual, "editado": r.editado,
        "en_curso": r.fin is None, "editable": ok, "motivo_no_editable": motivo,
    }


# ── Validación ───────────────────────────────────────────────────────────────
def _validar(db: Session, usuario: models.Usuario, tecnico_id: int, inicio: datetime, fin: datetime,
             excluir_id: int = None) -> None:
    ahora = utcnow()
    if fin <= inicio:
        _error("La hora de fin tiene que ser posterior a la de inicio.")
    if fin - inicio < timedelta(minutes=1):
        _error("El tramo tiene que durar al menos 1 minuto.")
    if fin - inicio > MAX_TRAMO:
        _error("Un tramo puede durar como mucho 16 horas.")
    if fin > ahora + timedelta(minutes=1):
        _error("No se pueden cargar horas a futuro.")
    if usuario.rol != models.UserRole.ADMINISTRADOR and dia_de(inicio) < limite_correccion(db):
        dias = int(ajustes.get(db, "horas_dias_correccion"))
        _error(f"Solo podés cargar o corregir horas de los últimos {dias} días: pedíselo a un administrador.")
    T = models.TiempoTrabajo
    pisa = (db.query(T).options(joinedload(T.ticket))
            .filter(T.usuario_id == tecnico_id, T.inicio < fin, func.coalesce(T.fin, ahora) > inicio,
                    *( [T.id != excluir_id] if excluir_id else [] )).first())
    if pisa:
        cual = pisa.ticket.numero_rma if pisa.ticket else CATEGORIAS.get(pisa.categoria, "otra tarea")
        de, a = a_local(pisa.inicio).strftime("%H:%M"), a_local(pisa.fin or ahora).strftime("%H:%M")
        _error(f"Se superpone con otro tramo ({cual}, de {de} a {a}).")
    d = dia_de(inicio)
    desde, hasta = limites_dia(d)
    otros = (db.query(T).filter(T.usuario_id == tecnico_id, T.inicio >= desde, T.inicio < hasta,
                                *( [T.id != excluir_id] if excluir_id else [] )).all())
    total = sum(minutos(o, ahora) for o in otros) + (fin - inicio).total_seconds() / 60
    if total > MAX_DIA_MIN + 0.5:
        _error(f"Con este tramo el {d.strftime('%d/%m')} sumaría {total / 60:.1f} h: el máximo es 16 h por día.")


def _destino(db: Session, ticket_id, categoria) -> tuple:
    if bool(ticket_id) == bool(categoria):
        _error("Elegí un ticket o una tarea del taller (una de las dos).")
    if ticket_id:
        t = db.query(models.Ticket).filter_by(id=ticket_id).first()
        if not t:
            _error("Ticket no encontrado", 404)
        return t.id, None
    if categoria not in CATEGORIAS:
        _error("Tarea del taller inválida.")
    return None, categoria


def _tecnico(db: Session, usuario: models.Usuario, tecnico_id) -> int:
    if tecnico_id in (None, usuario.id):
        return usuario.id
    if usuario.rol != models.UserRole.ADMINISTRADOR:
        _error("Solo podés cargar tus propias horas.", 403)
    u = db.query(models.Usuario).filter_by(id=tecnico_id).first()
    if not u or u.rol not in (models.UserRole.TECNICO.value, models.UserRole.ADMINISTRADOR.value):
        _error("Técnico no encontrado", 404)
    return u.id


def solo_duracion(db: Session, tecnico_id: int, d: date, minutos_: int) -> tuple[datetime, datetime]:
    """Ubica un tramo de "solo duración" a continuación de lo cargado ese día (o a las 9)."""
    desde, hasta = limites_dia(d)
    T = models.TiempoTrabajo
    ultimo = (db.query(func.max(func.coalesce(T.fin, utcnow())))
              .filter(T.usuario_id == tecnico_id, T.inicio >= desde, T.inicio < hasta).scalar())
    inicio = ultimo or a_utc(datetime.combine(d, INICIO_DIA))
    fin = inicio + timedelta(minutes=minutos_)
    if d == hoy() and fin > utcnow():                  # hoy: que termine ahora, no en el futuro
        fin = utcnow().replace(microsecond=0)
        inicio = fin - timedelta(minutes=minutos_)
    return inicio, fin


def _registrar(db: Session, r, tecnico_id: int, usuario: models.Usuario, accion: str, antes, despues) -> None:
    db.add(models.TiempoCambio(registro_id=r.id if r is not None and accion != "borrado" else None,
                               tecnico_id=tecnico_id, usuario_id=usuario.id, accion=accion,
                               antes=antes, despues=despues))
    # En el historial de los tickets afectados (texto neutro: "1 h 30 min (05/11 09:00)")
    def texto(f):
        return f"{f['minutos'] // 60} h {f['minutos'] % 60:02d} min ({a_local_iso(f['inicio'])})"

    def destino(f):
        return f.get("numero_rma") or CATEGORIAS.get(f.get("categoria"), "")
    tickets = {f["ticket_id"] for f in (antes, despues) if f and f.get("ticket_id")}
    for tid in tickets:
        if accion == "alta":
            detalle = f"Horas cargadas: {texto(despues)}"
        elif accion == "borrado":
            detalle = f"Horas borradas: {texto(antes)}"
        elif antes.get("ticket_id") != despues.get("ticket_id"):
            detalle = (f"Horas pasadas a {destino(despues)}: {texto(antes)}" if tid == antes.get("ticket_id")
                       else f"Horas traídas desde {destino(antes)}: {texto(despues)}")
        elif accion == "movido":
            detalle = f"Horas movidas: {texto(antes)} → {texto(despues)}"
        else:
            detalle = f"Horas corregidas: {texto(antes)} → {texto(despues)}"
        log_event(db, tid, usuario.id, models.EventoHistorial.TIEMPO_EDITADO, detalle=detalle)


def a_local_iso(iso: str) -> str:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).replace(tzinfo=None)
    return a_local(dt).strftime("%d/%m %H:%M")


# ── Operaciones ──────────────────────────────────────────────────────────────
def crear(db: Session, usuario: models.Usuario, *, tecnico_id=None, ticket_id=None, categoria=None,
          inicio: datetime = None, fin: datetime = None, dia: date = None, minutos_: int = None, nota: str = "") -> models.TiempoTrabajo:
    tecnico = _tecnico(db, usuario, tecnico_id)
    ticket_id, categoria = _destino(db, ticket_id, categoria)
    if inicio is None or fin is None:
        if dia is None or not minutos_:
            _error("Indicá el horario (desde y hasta) o el día y la duración.")
        if dia > hoy():
            _error("No se pueden cargar horas a futuro.")
        inicio, fin = solo_duracion(db, tecnico, dia, minutos_)
    _validar(db, usuario, tecnico, inicio, fin)
    r = models.TiempoTrabajo(ticket_id=ticket_id, categoria=categoria, usuario_id=tecnico, inicio=inicio, fin=fin,
                             nota=(nota or "").strip() or None, manual=True)
    db.add(r)
    db.flush()
    db.refresh(r)
    _registrar(db, r, tecnico, usuario, "alta", None, foto(r))
    return r


def editar(db: Session, usuario: models.Usuario, r: models.TiempoTrabajo, *, ticket_id=None, categoria=None,
           inicio: datetime, fin: datetime, nota: str = None) -> models.TiempoTrabajo:
    ok, motivo = puede_editar(db, r, usuario)
    if not ok:
        _error(motivo, 403 if "propias" in motivo else 400)
    ticket_id, categoria = _destino(db, ticket_id, categoria)
    _validar(db, usuario, r.usuario_id, inicio, fin, excluir_id=r.id)
    antes = foto(r)
    duracion_igual = abs((fin - inicio) - (r.fin - r.inicio)) < timedelta(seconds=30)
    movido = duracion_igual and dia_de(inicio) != dia_de(r.inicio) and ticket_id == r.ticket_id and categoria == r.categoria
    r.ticket_id, r.categoria, r.inicio, r.fin = ticket_id, categoria, inicio, fin
    if nota is not None:
        r.nota = nota.strip() or None
    r.editado = True
    db.flush()
    db.refresh(r)
    despues = foto(r)
    if antes != despues:
        _registrar(db, r, r.usuario_id, usuario, "movido" if movido else "edicion", antes, despues)
    return r


def borrar(db: Session, usuario: models.Usuario, r: models.TiempoTrabajo) -> None:
    if r.fin is not None or usuario.rol != models.UserRole.ADMINISTRADOR:
        if r.usuario_id != usuario.id and usuario.rol != models.UserRole.ADMINISTRADOR:
            _error("Solo podés borrar tus propios registros", 403)
        if r.fin is not None and usuario.rol != models.UserRole.ADMINISTRADOR and dia_de(r.inicio) < limite_correccion(db):
            _error("Pasó el plazo para corregirlo: pedíselo a un administrador.")
    _registrar(db, r, r.usuario_id, usuario, "borrado", foto(r), None)
    db.delete(r)


def calendario(db: Session, usuario: models.Usuario, desde: date, hasta: date, tecnico_id=None) -> dict:
    if hasta < desde:
        _error("El rango de fechas es inválido.")
    if (hasta - desde).days > 62:
        _error("El rango puede ser de hasta 62 días.")
    T = models.TiempoTrabajo
    q = db.query(T).options(joinedload(T.ticket), joinedload(T.usuario))
    if usuario.rol != models.UserRole.ADMINISTRADOR:
        tecnico_id = usuario.id
    if tecnico_id:
        q = q.filter(T.usuario_id == tecnico_id)
    ini, _ = limites_dia(desde)
    _, fin = limites_dia(hasta)
    ahora = utcnow()
    registros = q.filter(T.inicio >= ini, T.inicio < fin).order_by(T.inicio).all()
    tecnicos = []
    if usuario.rol == models.UserRole.ADMINISTRADOR:
        tecnicos = [{"id": u.id, "nombre": u.nombre} for u in db.query(models.Usuario)
                    .filter(models.Usuario.rol.in_([models.UserRole.TECNICO.value, models.UserRole.ADMINISTRADOR.value]),
                            models.Usuario.activo.is_(True)).order_by(models.Usuario.nombre).all()]
    salida_ = [salida(db, r, usuario, ahora) for r in registros]
    tarifa = ajustes.get(db, "tarifa_hora")
    total = sum(r["minutos"] for r in salida_)
    en_tickets = sum(r["minutos"] for r in salida_ if r["ticket_id"])
    return {
        "desde": desde.isoformat(), "hasta": hasta.isoformat(), "hoy": hoy().isoformat(), "zona": config.TIMEZONE,
        "tecnico_id": tecnico_id, "tecnicos": tecnicos, "registros": salida_,
        "total_minutos": round(total, 1), "minutos_tickets": round(en_tickets, 1),
        "costo": round(en_tickets / 60 * tarifa, 2) if tarifa else None,
        "categorias": CATEGORIAS, "limite_correccion": None if usuario.rol == models.UserRole.ADMINISTRADOR
        else limite_correccion(db).isoformat(),
        "dias_correccion": int(ajustes.get(db, "horas_dias_correccion")),
    }
