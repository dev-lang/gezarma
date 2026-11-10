"""
ubicaciones.py — Dónde está guardado cada equipo y cada repuesto.

- Las ubicaciones forman un árbol (Depósito → Estante B → B3). Cada una tiene un código
  (U-0001) que va en su etiqueta: escanear la etiqueta del equipo y después la del estante
  lo guarda ahí.
- "Fuera del taller" (tipo externa) la crea el sistema para los equipos que están en el
  fabricante o en un servicio oficial; no se elige a mano.
- Cada cambio de lugar queda en ubicacion_movimientos (de dónde, a dónde, quién y cuándo)
  y, para los equipos, también en el historial del ticket.
"""
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models
from ..timeutils import utcnow
from .ticket_service import log_event

SEP = " › "
EXTERNA = "Fuera del taller"


def _error(msg: str, status: int = 400):
    raise HTTPException(status_code=status, detail=msg)


def todas(db: Session) -> dict:
    return {u.id: u for u in db.query(models.Ubicacion).all()}


def ruta(u: models.Ubicacion, mapa: dict = None) -> str:
    partes, vistos = [], set()
    while u is not None and u.id not in vistos:
        vistos.add(u.id)
        partes.append(u.nombre)
        u = (mapa or {}).get(u.padre_id) if mapa is not None else u.padre
    return SEP.join(reversed(partes))


def descendientes(db: Session, uid: int) -> set:
    hijos = {}
    for u in db.query(models.Ubicacion.id, models.Ubicacion.padre_id).all():
        hijos.setdefault(u.padre_id, []).append(u.id)
    res, pila = set(), [uid]
    while pila:
        x = pila.pop()
        if x in res:
            continue
        res.add(x)
        pila.extend(hijos.get(x, []))
    return res


def _nuevo_codigo(db: Session, u: models.Ubicacion) -> None:
    u.codigo = f"U-{u.id:04d}"


def externa(db: Session) -> models.Ubicacion:
    """La ubicación del sistema para lo que está fuera del taller (se crea la primera vez)."""
    u = db.query(models.Ubicacion).filter_by(tipo="externa", padre_id=None).first()
    if not u:
        u = models.Ubicacion(nombre=EXTERNA, tipo="externa", nota="Equipos en el fabricante o en un servicio oficial", orden=999)
        db.add(u)
        db.flush()
        _nuevo_codigo(db, u)
    return u


def obtener(db: Session, uid: int, para_guardar: bool = True) -> models.Ubicacion:
    u = db.query(models.Ubicacion).filter_by(id=uid).first()
    if not u:
        _error("Ubicación no encontrada", 404)
    if para_guardar and not u.activa:
        _error("Esa ubicación está desactivada.")
    if para_guardar and u.tipo == "externa":
        _error("\"Fuera del taller\" la usa el sistema para los envíos al fabricante: elegí un lugar del taller.")
    return u


def crear(db: Session, nombre: str, padre_id=None, nota=None) -> models.Ubicacion:
    nombre = (nombre or "").strip()
    if not nombre:
        _error("Poné un nombre para la ubicación.")
    padre = obtener(db, padre_id) if padre_id else None
    if db.query(models.Ubicacion).filter(models.Ubicacion.padre_id == (padre.id if padre else None),
                                         func.lower(models.Ubicacion.nombre) == nombre.lower()).first():
        _error(f"Ya hay una ubicación \"{nombre}\" en ese lugar.")
    u = models.Ubicacion(nombre=nombre, padre_id=padre.id if padre else None, nota=(nota or "").strip() or None)
    db.add(u)
    db.flush()
    _nuevo_codigo(db, u)
    return u


def editar(db: Session, u: models.Ubicacion, nombre=None, padre_id=..., nota=None, activa=None) -> models.Ubicacion:
    if u.tipo == "externa":
        _error("Esta ubicación la maneja el sistema.")
    if nombre is not None:
        nombre = nombre.strip()
        if not nombre:
            _error("Poné un nombre para la ubicación.")
        u.nombre = nombre
    if padre_id is not ...:
        if padre_id:
            if padre_id in descendientes(db, u.id):
                _error("No se puede poner una ubicación dentro de sí misma.")
            obtener(db, padre_id)
        u.padre_id = padre_id or None
    if nota is not None:
        u.nota = nota.strip() or None
    if activa is not None:
        if not activa and contenido_cuenta(db, descendientes(db, u.id))["total"]:
            _error("Tiene equipos o repuestos guardados (ella o sus sububicaciones): movelos antes de desactivarla.")
        u.activa = activa
    return u


def contenido_cuenta(db: Session, ids: set) -> dict:
    T, R = models.Ticket, models.Repuesto
    eq = db.query(func.count(T.id)).filter(T.ubicacion_id.in_(ids)).scalar() or 0
    rep = db.query(func.count(R.id)).filter(R.ubicacion_id.in_(ids)).scalar() or 0
    return {"equipos": eq, "repuestos": rep, "total": eq + rep}


def borrar(db: Session, u: models.Ubicacion) -> None:
    if u.tipo == "externa":
        _error("Esta ubicación la maneja el sistema.")
    if db.query(models.Ubicacion).filter_by(padre_id=u.id).first():
        _error("Tiene sububicaciones: borralas o movelas antes.")
    if contenido_cuenta(db, {u.id})["total"]:
        _error("Tiene equipos o repuestos guardados: movelos antes de borrarla.")
    M = models.UbicacionMovimiento
    if db.query(M).filter((M.desde_id == u.id) | (M.hacia_id == u.id)).first():
        _error("Ya se usó (figura en el historial de movimientos): desactivala en lugar de borrarla.")
    db.delete(u)


# ── Mover ────────────────────────────────────────────────────────────────────
def mover_ticket(db: Session, t: models.Ticket, destino_id, usuario: models.Usuario, motivo: str = "manual",
                 permitir_externa: bool = False) -> bool:
    """Guarda el equipo en otra ubicación (None = sin ubicación). False si no cambió."""
    destino = None
    if destino_id:
        destino = (db.query(models.Ubicacion).filter_by(id=destino_id).first() if permitir_externa
                   else obtener(db, destino_id))
    if not permitir_externa and t.ubicacion and t.ubicacion.tipo == "externa" and \
            db.query(models.EnvioExterno).filter_by(ticket_id=t.id, estado="enviado").first():
        _error("El equipo está en el servicio técnico oficial: registrá primero la vuelta.")
    nuevo = destino.id if destino else None
    if t.ubicacion_id == nuevo:
        return False
    mapa = todas(db)
    desde = mapa.get(t.ubicacion_id)
    db.add(models.UbicacionMovimiento(ticket_id=t.id, desde_id=t.ubicacion_id, hacia_id=nuevo,
                                      usuario_id=usuario.id, motivo=motivo))
    t.ubicacion_id, t.ubicacion_fecha = nuevo, utcnow()
    de = ruta(desde, mapa) if desde else "sin ubicación"
    a = ruta(destino, mapa) if destino else "sin ubicación"
    log_event(db, t.id, usuario.id, models.EventoHistorial.UBICACION_CAMBIADA,
              detalle=f"Ubicación: {de} → {a}", campo="ubicacion", val_ant=de, val_nuevo=a)
    return True


def mover_repuestos(db: Session, ids: list, destino_id, usuario: models.Usuario, motivo: str = "manual") -> int:
    destino = obtener(db, destino_id) if destino_id else None
    nuevo = destino.id if destino else None
    n = 0
    for r in db.query(models.Repuesto).filter(models.Repuesto.id.in_(ids)).all():
        if r.ubicacion_id == nuevo:
            continue
        db.add(models.UbicacionMovimiento(repuesto_id=r.id, desde_id=r.ubicacion_id, hacia_id=nuevo,
                                          usuario_id=usuario.id, motivo=motivo))
        r.ubicacion_id = nuevo
        n += 1
    return n


def desde_texto(db: Session, texto: str) -> models.Ubicacion:
    """"Depósito > Estante B > B3" (o con › o /) → la ubicación; crea las que falten (importación)."""
    import re
    partes = [p.strip() for p in re.split(r"\s*[>›/]\s*", texto or "") if p.strip()]
    padre = None
    for p in partes:
        u = (db.query(models.Ubicacion)
             .filter(models.Ubicacion.padre_id == (padre.id if padre else None), func.lower(models.Ubicacion.nombre) == p.lower())
             .first())
        if not u:
            u = crear(db, p[:60], padre.id if padre else None)
        elif not u.activa or u.tipo == "externa":
            _error(f"La ubicación \"{p}\" está desactivada o es del sistema.")
        padre = u
    return padre


# ── Salida ───────────────────────────────────────────────────────────────────
def lista(db: Session) -> list:
    mapa = todas(db)
    T, R = models.Ticket, models.Repuesto
    eq = dict(db.query(T.ubicacion_id, func.count(T.id)).filter(T.ubicacion_id.isnot(None)).group_by(T.ubicacion_id).all())
    rep = dict(db.query(R.ubicacion_id, func.count(R.id)).filter(R.ubicacion_id.isnot(None)).group_by(R.ubicacion_id).all())
    out = [{"id": u.id, "nombre": u.nombre, "padre_id": u.padre_id, "codigo": u.codigo, "tipo": u.tipo,
            "nota": u.nota, "activa": u.activa, "orden": u.orden, "ruta": ruta(u, mapa),
            "equipos": eq.get(u.id, 0), "repuestos": rep.get(u.id, 0)} for u in mapa.values()]
    return sorted(out, key=lambda x: (x["tipo"] == "externa", x["ruta"].lower()))


def resumen(t_or_r, mapa: dict = None):
    u = t_or_r.ubicacion
    if not u:
        return None
    return {"id": u.id, "ruta": ruta(u, mapa), "codigo": u.codigo, "tipo": u.tipo}
