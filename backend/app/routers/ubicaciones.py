"""
ubicaciones.py — Dónde se guarda cada equipo y cada repuesto (ver services/ubicaciones.py).

  GET    /ubicaciones                         lista plana con ruta y cuántos equipos/repuestos tiene cada una
  POST   /ubicaciones                         (admin) nueva
  PUT    /ubicaciones/{id}                    (admin) renombrar, mover dentro de otra, nota, activar/desactivar
  DELETE /ubicaciones/{id}                    (admin) solo si nunca se usó
  GET    /ubicaciones/{id}/contenido          equipos y repuestos guardados ahí (y en sus sububicaciones)
  GET    /ubicaciones/{id}/etiqueta           etiqueta para pegar en el estante (código U-0001)
  GET    /ubicaciones/escaneo?codigo=         qué es un código leído: ubicación, ticket (RMA) o repuesto
  GET    /ubicaciones/pendientes              equipos sin ubicación o sin moverse hace N días; repuestos sin ubicación
  PUT    /tickets/{id}/ubicacion              guardar el equipo en otro lugar
  GET    /tickets/{id}/ubicacion/historial    por dónde pasó
  GET    /parts/{id}/etiqueta                 etiqueta del repuesto (código, nombre y ubicación)
"""
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from .. import ajustes, auth, database, models
from ..services import documentos, impresion, ubicaciones as U
from ..timeutils import iso_utc, utcnow
from ._tickets_comun import ticket_o_404

router = APIRouter(tags=["ubicaciones"])
TALLER = auth.check_role([models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO])
ADMIN = auth.check_role([models.UserRole.ADMINISTRADOR])


class UbicacionIn(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=60)
    padre_id: Optional[int] = None
    nota: Optional[str] = Field(None, max_length=200)


class UbicacionEdit(BaseModel):
    nombre: Optional[str] = Field(None, min_length=1, max_length=60)
    padre_id: Optional[int] = None
    nota: Optional[str] = Field(None, max_length=200)
    activa: Optional[bool] = None


class MoverIn(BaseModel):
    ubicacion_id: Optional[int] = None
    motivo: str = Field("manual", pattern="^(manual|escaneo|mostrador)$")


def _ubic(db: Session, uid: int) -> models.Ubicacion:
    u = db.query(models.Ubicacion).filter_by(id=uid).first()
    if not u:
        raise HTTPException(404, "Ubicación no encontrada")
    return u


@router.get("/ubicaciones")
def listar(db: Session = Depends(database.get_db), u: models.Usuario = Depends(TALLER)):
    return U.lista(db)


@router.post("/ubicaciones", status_code=201)
def crear(data: UbicacionIn, db: Session = Depends(database.get_db), u: models.Usuario = Depends(ADMIN)):
    nueva = U.crear(db, data.nombre, data.padre_id, data.nota)
    db.commit()
    return next(x for x in U.lista(db) if x["id"] == nueva.id)


@router.put("/ubicaciones/{uid}")
def editar(uid: int, data: UbicacionEdit, db: Session = Depends(database.get_db), u: models.Usuario = Depends(ADMIN)):
    ub = _ubic(db, uid)
    U.editar(db, ub, nombre=data.nombre, padre_id=data.padre_id if "padre_id" in data.model_fields_set else ...,
             nota=data.nota, activa=data.activa)
    db.commit()
    return next(x for x in U.lista(db) if x["id"] == ub.id)


@router.delete("/ubicaciones/{uid}", status_code=204)
def borrar(uid: int, db: Session = Depends(database.get_db), u: models.Usuario = Depends(ADMIN)):
    U.borrar(db, _ubic(db, uid))
    db.commit()
    return Response(status_code=204)


def _equipo(t: models.Ticket, mapa: dict, ahora) -> dict:
    return {"id": t.id, "numero_rma": t.numero_rma, "producto": t.producto, "numero_serie": t.numero_serie,
            "estado": t.estado, "cliente": t.cliente.nombre if t.cliente else None,
            "ubicacion_id": t.ubicacion_id, "ubicacion_ruta": U.ruta(mapa.get(t.ubicacion_id), mapa) if t.ubicacion_id else None,
            "desde": iso_utc(t.ubicacion_fecha) if t.ubicacion_fecha else None,
            "dias_quieto": (ahora - (t.ubicacion_fecha or t.fecha_creacion)).days}


def _repuesto(r: models.Repuesto, mapa: dict) -> dict:
    return {"id": r.id, "codigo": r.codigo, "nombre": r.nombre, "stock": r.stock, "categoria": r.categoria,
            "ubicacion_id": r.ubicacion_id, "ubicacion_ruta": U.ruta(mapa.get(r.ubicacion_id), mapa) if r.ubicacion_id else None}


@router.get("/ubicaciones/{uid}/contenido")
def contenido(uid: int, incluir_sub: bool = True, db: Session = Depends(database.get_db), u: models.Usuario = Depends(TALLER)):
    ub = _ubic(db, uid)
    ids = U.descendientes(db, ub.id) if incluir_sub else {ub.id}
    mapa, ahora = U.todas(db), utcnow()
    T, R = models.Ticket, models.Repuesto
    equipos = (db.query(T).options(joinedload(T.cliente)).filter(T.ubicacion_id.in_(ids))
               .order_by(T.ubicacion_fecha.desc()).all())
    repuestos = db.query(R).filter(R.ubicacion_id.in_(ids)).order_by(R.nombre).all()
    return {"ubicacion": next(x for x in U.lista(db) if x["id"] == ub.id),
            "equipos": [_equipo(t, mapa, ahora) for t in equipos],
            "repuestos": [_repuesto(r, mapa) for r in repuestos]}


@router.get("/ubicaciones/pendientes")
def pendientes(dias: int = Query(None, ge=1, le=365), db: Session = Depends(database.get_db),
               u: models.Usuario = Depends(TALLER)):
    """Para ordenar: equipos abiertos sin ubicación, equipos que no se mueven hace `dias`
    (ajuste ubicacion_dias_quieto) y repuestos sin ubicación."""
    from ..services import estados
    dias = dias or int(ajustes.get(db, "ubicacion_dias_quieto"))
    finales = {e.valor for e in db.query(models.TicketStatusConfig).filter_by(es_final=True).all()} or \
              {models.TicketStatus.CERRADO.value, models.TicketStatus.CANCELADO.value}
    finales |= {models.TicketStatus.ENVIADO.value}
    mapa, ahora = U.todas(db), utcnow()
    T, R = models.Ticket, models.Repuesto
    abiertos = db.query(T).options(joinedload(T.cliente)).filter(T.estado.notin_(finales))
    sin = abiertos.filter(T.ubicacion_id.is_(None)).order_by(T.fecha_creacion).all()
    limite = ahora - timedelta(days=dias)
    externas = {x.id for x in mapa.values() if x.tipo == "externa"}
    quietos = (abiertos.filter(T.ubicacion_id.isnot(None), T.ubicacion_id.notin_(externas or {-1}),
                               func.coalesce(T.ubicacion_fecha, T.fecha_creacion) < limite)
               .order_by(func.coalesce(T.ubicacion_fecha, T.fecha_creacion)).all())
    return {"dias": dias,
            "equipos_sin_ubicacion": [_equipo(t, mapa, ahora) for t in sin],
            "equipos_quietos": [_equipo(t, mapa, ahora) for t in quietos],
            "repuestos_sin_ubicacion": [_repuesto(r, mapa) for r in db.query(R).filter(R.ubicacion_id.is_(None)).order_by(R.nombre).all()]}


@router.get("/ubicaciones/escaneo")
def escaneo(codigo: str = Query(..., min_length=1, max_length=80), db: Session = Depends(database.get_db),
            u: models.Usuario = Depends(TALLER)):
    """Lo que leyó el lector: una ubicación (U-0001), un ticket (RMA) o un repuesto (su código)."""
    c = codigo.strip()
    ub = db.query(models.Ubicacion).filter(func.upper(models.Ubicacion.codigo) == c.upper()).first()
    if ub:
        return {"tipo": "ubicacion", "id": ub.id, "ruta": U.ruta(ub), "activa": ub.activa, "externa": ub.tipo == "externa"}
    t = db.query(models.Ticket).filter(func.upper(models.Ticket.numero_rma) == c.upper()).first()
    if t:
        return {"tipo": "ticket", "id": t.id, "numero_rma": t.numero_rma, "producto": t.producto,
                "ubicacion_ruta": U.ruta(t.ubicacion) if t.ubicacion else None}
    r = db.query(models.Repuesto).filter(func.upper(models.Repuesto.codigo) == c.upper()).first()
    if r:
        return {"tipo": "repuesto", "id": r.id, "codigo": r.codigo, "nombre": r.nombre, "stock": r.stock,
                "ubicacion_ruta": r.ubicacion_ruta}
    raise HTTPException(404, f"No se encontró nada con el código {c}")


def _etiqueta(db: Session, request: Request, codigo: str, titulo: str, lineas: list, formato: Optional[str]):
    dpi = int(ajustes.get(db, "etiqueta_dpi"))
    ctx = {"e": impresion.disenio_etiqueta(ajustes.get(db, "etiqueta_tamano"), dpi, codigo, lineas), "dpi": dpi,
           "codigo": codigo, "titulo": titulo, "qr": documentos.qr_png(codigo)}
    if formato is None:
        formato = "pdf" if ajustes.get(db, "pdf_modo") == "servidor" else "html"
    plantilla = documentos._env.get_template("etiqueta_codigo.html")
    if formato == "html":
        return HTMLResponse(plantilla.render(**ctx, imprimir=True))
    pdf = documentos.render_pdf(plantilla.render(**ctx, imprimir=False))
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="etiqueta-{codigo}.pdf"'})


@router.get("/ubicaciones/{uid}/etiqueta")
def etiqueta_ubicacion(uid: int, request: Request, formato: Optional[str] = Query(None, pattern="^(pdf|html)$"),
                       db: Session = Depends(database.get_db), u: models.Usuario = Depends(TALLER)):
    ub = _ubic(db, uid)
    partes = U.ruta(ub).split(U.SEP)
    lineas = [partes[-1]] + ([U.SEP.join(partes[:-1])] if len(partes) > 1 else []) + ([ub.nota] if ub.nota else [])
    return _etiqueta(db, request, ub.codigo, "Ubicación", lineas, formato)


@router.get("/parts/{pid}/etiqueta")
def etiqueta_repuesto(pid: int, request: Request, formato: Optional[str] = Query(None, pattern="^(pdf|html)$"),
                      db: Session = Depends(database.get_db), u: models.Usuario = Depends(TALLER)):
    r = db.query(models.Repuesto).filter_by(id=pid).first()
    if not r:
        raise HTTPException(404, "Repuesto no encontrado")
    lineas = [r.nombre] + ([r.ubicacion_ruta] if r.ubicacion_ruta else []) + ([r.categoria] if r.categoria else [])
    return _etiqueta(db, request, r.codigo, "Repuesto", lineas, formato)


@router.put("/tickets/{ticket_id}/ubicacion")
def mover_ticket(ticket_id: int, data: MoverIn, db: Session = Depends(database.get_db), u: models.Usuario = Depends(TALLER)):
    t = ticket_o_404(db, ticket_id)
    cambio = U.mover_ticket(db, t, data.ubicacion_id, u, motivo=data.motivo)
    db.commit()
    db.refresh(t)
    return {"cambio": cambio, "ubicacion_id": t.ubicacion_id, "ubicacion_ruta": U.ruta(t.ubicacion) if t.ubicacion else None,
            "ubicacion_fecha": iso_utc(t.ubicacion_fecha) if t.ubicacion_fecha else None}


@router.get("/tickets/{ticket_id}/ubicacion/historial")
def historial_ticket(ticket_id: int, db: Session = Depends(database.get_db), u: models.Usuario = Depends(TALLER)):
    ticket_o_404(db, ticket_id)
    M = models.UbicacionMovimiento
    mapa = U.todas(db)
    filas = db.query(M).options(joinedload(M.usuario)).filter(M.ticket_id == ticket_id).order_by(M.fecha.desc(), M.id.desc()).all()
    return [{"fecha": iso_utc(m.fecha), "desde": U.ruta(mapa[m.desde_id], mapa) if m.desde_id in mapa else None,
             "hacia": U.ruta(mapa[m.hacia_id], mapa) if m.hacia_id in mapa else None,
             "usuario": m.usuario.nombre if m.usuario else None, "motivo": m.motivo} for m in filas]
