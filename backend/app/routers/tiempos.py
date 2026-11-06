"""
tiempos.py — Registro del tiempo de trabajo de cada técnico sobre los tickets.

Cada técnico tiene a lo sumo un trabajo en curso: al iniciar en otro ticket,
el anterior se pausa solo. También se puede cargar tiempo a mano (si se
olvidó de iniciarlo). Con el costo de la hora en Ajustes, se calcula la mano
de obra.
"""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import ajustes, auth, database, models
from ..timeutils import iso_utc, utcnow

router = APIRouter(tags=["tiempos"])
TALLER = auth.check_role([models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO])
ADMIN = auth.check_role([models.UserRole.ADMINISTRADOR])


class IniciarIn(BaseModel):
    nota: str = Field("", max_length=200)


class ManualIn(BaseModel):
    minutos: int = Field(..., ge=1, le=24 * 60)
    nota: str = Field("", max_length=200)


def _minutos(r: models.TiempoTrabajo, ahora) -> float:
    return max(0.0, ((r.fin or ahora) - r.inicio).total_seconds() / 60)


def _costo(db: Session, minutos: float):
    tarifa = ajustes.get(db, "tarifa_hora")
    return round(minutos / 60 * tarifa, 2) if tarifa else None


def _en_curso(db: Session, usuario_id: int):
    return db.query(models.TiempoTrabajo).filter_by(usuario_id=usuario_id, fin=None).first()


def _ticket(db: Session, ticket_id: int) -> models.Ticket:
    t = db.query(models.Ticket).filter_by(id=ticket_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    return t


def _estado(db: Session, t: models.Ticket, usuario: models.Usuario) -> dict:
    ahora = utcnow()
    registros = sorted(t.tiempos, key=lambda r: r.inicio, reverse=True)
    por_tecnico = {}
    for r in registros:
        nombre = r.usuario.nombre if r.usuario else "?"
        por_tecnico[nombre] = por_tecnico.get(nombre, 0) + _minutos(r, ahora)
    total = sum(por_tecnico.values())
    mio = next((r for r in registros if r.usuario_id == usuario.id and r.fin is None), None)
    return {
        "registros": [{"id": r.id, "usuario_id": r.usuario_id, "usuario_nombre": r.usuario.nombre if r.usuario else None,
                       "inicio": iso_utc(r.inicio), "fin": iso_utc(r.fin) if r.fin else None,
                       "minutos": round(_minutos(r, ahora), 1), "nota": r.nota, "manual": r.manual,
                       "en_curso": r.fin is None} for r in registros],
        "total_minutos": round(total, 1),
        "por_tecnico": [{"nombre": n, "minutos": round(m, 1)} for n, m in sorted(por_tecnico.items(), key=lambda x: -x[1])],
        "costo": _costo(db, total),
        "en_curso_mio": mio.id if mio else None,
    }


@router.get("/tickets/{ticket_id}/tiempo")
def ver(ticket_id: int, db: Session = Depends(database.get_db), u: models.Usuario = Depends(TALLER)):
    return _estado(db, _ticket(db, ticket_id), u)


@router.post("/tickets/{ticket_id}/tiempo/iniciar")
def iniciar(ticket_id: int, data: IniciarIn = IniciarIn(), db: Session = Depends(database.get_db),
            u: models.Usuario = Depends(TALLER)):
    t = _ticket(db, ticket_id)
    ahora = utcnow()
    actual = _en_curso(db, u.id)
    if actual and actual.ticket_id == t.id:
        return _estado(db, t, u)              # ya estaba corriendo acá
    if actual:
        actual.fin = ahora                    # un solo trabajo en curso por técnico
    db.add(models.TiempoTrabajo(ticket_id=t.id, usuario_id=u.id, inicio=ahora, nota=data.nota.strip() or None))
    db.commit()
    db.refresh(t)
    return _estado(db, t, u)


@router.post("/tickets/{ticket_id}/tiempo/pausar")
def pausar(ticket_id: int, db: Session = Depends(database.get_db), u: models.Usuario = Depends(TALLER)):
    t = _ticket(db, ticket_id)
    actual = _en_curso(db, u.id)
    if actual and actual.ticket_id == t.id:
        actual.fin = utcnow()
        db.commit()
        db.refresh(t)
    return _estado(db, t, u)


@router.post("/tickets/{ticket_id}/tiempo/manual")
def manual(ticket_id: int, data: ManualIn, db: Session = Depends(database.get_db), u: models.Usuario = Depends(TALLER)):
    t = _ticket(db, ticket_id)
    fin = utcnow()
    db.add(models.TiempoTrabajo(ticket_id=t.id, usuario_id=u.id, inicio=fin - timedelta(minutes=data.minutos),
                                fin=fin, nota=data.nota.strip() or None, manual=True))
    db.commit()
    db.refresh(t)
    return _estado(db, t, u)


@router.delete("/tiempo/{registro_id}", status_code=204)
def borrar(registro_id: int, db: Session = Depends(database.get_db), u: models.Usuario = Depends(TALLER)):
    r = db.query(models.TiempoTrabajo).filter_by(id=registro_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    if r.usuario_id != u.id and u.rol != models.UserRole.ADMINISTRADOR:
        raise HTTPException(status_code=403, detail="Solo podés borrar tus propios registros")
    db.delete(r)
    db.commit()


@router.get("/tiempo/actual")
def actual(db: Session = Depends(database.get_db), u: models.Usuario = Depends(TALLER)):
    """El trabajo en curso del usuario (para el indicador de la barra superior)."""
    r = _en_curso(db, u.id)
    if not r:
        return None
    return {"id": r.id, "ticket_id": r.ticket_id, "numero_rma": r.ticket.numero_rma, "inicio": iso_utc(r.inicio)}


@router.get("/tiempo/resumen")
def resumen(dias: int = Query(30, ge=1, le=3650), db: Session = Depends(database.get_db),
            _: models.Usuario = Depends(ADMIN)):
    """Horas por técnico en el período (los tramos que empezaron en esos días)."""
    ahora = utcnow()
    desde = ahora - timedelta(days=dias)
    registros = db.query(models.TiempoTrabajo).filter(models.TiempoTrabajo.inicio >= desde).all()
    datos = {}
    for r in registros:
        d = datos.setdefault(r.usuario_id, {"nombre": r.usuario.nombre if r.usuario else "?", "minutos": 0.0,
                                            "tickets": set(), "en_curso": False})
        d["minutos"] += _minutos(r, ahora)
        d["tickets"].add(r.ticket_id)
        d["en_curso"] = d["en_curso"] or r.fin is None
    tecnicos = sorted(datos.values(), key=lambda d: -d["minutos"])
    total = sum(d["minutos"] for d in tecnicos)
    return {"dias": dias, "total_minutos": round(total, 1), "costo": _costo(db, total),
            "tecnicos": [{"nombre": d["nombre"], "minutos": round(d["minutos"], 1), "tickets": len(d["tickets"]),
                          "promedio_por_ticket": round(d["minutos"] / len(d["tickets"]), 1),
                          "costo": _costo(db, d["minutos"]), "en_curso": d["en_curso"]} for d in tecnicos]}
