"""
envios.py — Envíos a la garantía del fabricante o a un servicio oficial (ver services/envios.py).

  POST /tickets/{id}/envios           enviar (el ticket pasa a "En servicio técnico oficial")
  GET  /tickets/{id}/envios           todos los envíos del ticket
  PUT  /envios/{id}                   corregir datos (caso, guía, fecha estimada…)
  POST /envios/{id}/recepcion         volvió: resultado, serie nueva, comprobante, dónde se guarda
  GET  /envios?estado=&destino=&atrasados=   pantalla "Fuera del taller"
  GET  /envios/exportar?formato=xlsx|csv
  GET  /envios/destinos               fabricantes/servicios usados antes (para autocompletar)
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from .. import auth, database, models
from ..services import envios as E
from ..timeutils import to_utc_naive, utcnow
from ._tickets_comun import ticket_o_404

router = APIRouter(tags=["envios"])
TALLER = auth.check_role([models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO])


class EnvioIn(BaseModel):
    destino: str = Field(..., min_length=1, max_length=120)
    numero_caso: Optional[str] = Field(None, max_length=60)
    fecha_envio: Optional[datetime] = None
    transportista: Optional[str] = Field(None, max_length=80)
    guia: Optional[str] = Field(None, max_length=80)
    contenido: Optional[str] = Field(None, max_length=120)
    accesorios: Optional[str] = Field(None, max_length=300)
    fecha_estimada: Optional[datetime] = None
    nota: Optional[str] = Field(None, max_length=2000)


class EnvioEdit(BaseModel):
    destino: Optional[str] = Field(None, max_length=120)
    numero_caso: Optional[str] = Field(None, max_length=60)
    transportista: Optional[str] = Field(None, max_length=80)
    guia: Optional[str] = Field(None, max_length=80)
    contenido: Optional[str] = Field(None, max_length=120)
    accesorios: Optional[str] = Field(None, max_length=300)
    fecha_estimada: Optional[datetime] = None
    nota: Optional[str] = Field(None, max_length=2000)
    comprobante: Optional[str] = Field(None, max_length=80)
    serie_nueva: Optional[str] = Field(None, max_length=80)
    nota_recepcion: Optional[str] = Field(None, max_length=2000)


class RecepcionIn(BaseModel):
    resultado: str
    fecha_recepcion: Optional[datetime] = None
    serie_nueva: Optional[str] = Field(None, max_length=80)
    comprobante: Optional[str] = Field(None, max_length=80)
    nota_recepcion: Optional[str] = Field(None, max_length=2000)
    ubicacion_id: Optional[int] = None


def _fechas(d: dict) -> dict:
    for k in ("fecha_envio", "fecha_estimada", "fecha_recepcion"):
        if d.get(k):
            d[k] = to_utc_naive(d[k])
    return d


def _envio(db: Session, eid: int) -> models.EnvioExterno:
    e = (db.query(models.EnvioExterno)
         .options(joinedload(models.EnvioExterno.ticket).joinedload(models.Ticket.cliente)).filter_by(id=eid).first())
    if not e:
        raise HTTPException(404, "Envío no encontrado")
    return e


@router.post("/tickets/{ticket_id}/envios", status_code=201)
def enviar(ticket_id: int, data: EnvioIn, db: Session = Depends(database.get_db), u: models.Usuario = Depends(TALLER)):
    t = ticket_o_404(db, ticket_id)
    e = E.enviar(db, t, u, _fechas(data.model_dump()))
    db.commit()
    return E.salida(_envio(db, e.id))


@router.get("/tickets/{ticket_id}/envios")
def del_ticket(ticket_id: int, db: Session = Depends(database.get_db), u: models.Usuario = Depends(TALLER)):
    ticket_o_404(db, ticket_id)
    filas = (db.query(models.EnvioExterno).filter_by(ticket_id=ticket_id)
             .order_by(models.EnvioExterno.fecha_envio.desc(), models.EnvioExterno.id.desc()).all())
    ahora = utcnow()
    return [E.salida(e, ahora) for e in filas]


@router.put("/envios/{eid}")
def editar(eid: int, data: EnvioEdit, db: Session = Depends(database.get_db), u: models.Usuario = Depends(TALLER)):
    e = _envio(db, eid)
    d = _fechas(data.model_dump())
    if "fecha_estimada" not in data.model_fields_set:
        d.pop("fecha_estimada", None)
    E.editar(db, e, d)
    db.commit()
    return E.salida(e)


@router.post("/envios/{eid}/recepcion")
def recibir(eid: int, data: RecepcionIn, db: Session = Depends(database.get_db), u: models.Usuario = Depends(TALLER)):
    e = _envio(db, eid)
    E.recibir(db, e, u, _fechas(data.model_dump()))
    db.commit()
    return E.salida(_envio(db, eid))


def _consulta(db: Session, estado: str, destino: Optional[str]):
    X = models.EnvioExterno
    q = db.query(X).options(joinedload(X.ticket).joinedload(models.Ticket.cliente),
                            joinedload(X.usuario_envio), joinedload(X.usuario_recepcion))
    if estado != "todos":
        q = q.filter(X.estado == estado)
    if destino:
        q = q.filter(func.lower(X.destino) == destino.lower())
    return q.order_by(X.fecha_envio)


@router.get("/envios")
def listar(estado: str = Query("enviado", pattern="^(enviado|recibido|todos)$"), destino: Optional[str] = None,
           atrasados: bool = False, db: Session = Depends(database.get_db), u: models.Usuario = Depends(TALLER)):
    ahora = utcnow()
    filas = [E.salida(e, ahora) for e in _consulta(db, estado, destino).all()]
    if atrasados:
        filas = [f for f in filas if f["atrasado"]]
    abiertos = db.query(models.EnvioExterno).filter_by(estado="enviado")
    return {"envios": filas,
            "resumen": {"afuera": abiertos.count(),
                        "atrasados": sum(1 for e in abiertos.all() if e.fecha_estimada and e.fecha_estimada < ahora)}}


@router.get("/envios/destinos")
def destinos(db: Session = Depends(database.get_db), u: models.Usuario = Depends(TALLER)):
    X = models.EnvioExterno
    return [d for (d,) in db.query(X.destino).group_by(X.destino).order_by(func.count(X.id).desc()).limit(30).all()]


@router.get("/envios/exportar")
def exportar(estado: str = Query("todos", pattern="^(enviado|recibido|todos)$"), destino: Optional[str] = None,
             formato: str = Query("xlsx", pattern="^(csv|xlsx)$"),
             db: Session = Depends(database.get_db), u: models.Usuario = Depends(TALLER)):
    from .export import _to_csv, _to_xlsx
    from ..services.horas import a_local
    cab = ["Ticket", "Equipo", "Serie", "Cliente", "Enviado a", "Caso del fabricante", "Fecha de envío", "Transportista",
           "Guía", "Qué se mandó", "Accesorios", "Vuelta estimada", "Estado", "Días", "Fecha de vuelta", "Resultado",
           "Serie nueva", "Comprobante", "Enviado por", "Recibido por"]
    f = lambda dt: a_local(dt).strftime("%d/%m/%Y") if dt else ""
    filas = []
    ahora = utcnow()
    for e in _consulta(db, estado, destino).all():
        s = E.salida(e, ahora)
        filas.append([s["numero_rma"], s["producto"], s["numero_serie"], s["cliente"], e.destino, e.numero_caso or "",
                      f(e.fecha_envio), e.transportista or "", e.guia or "", e.contenido or "", e.accesorios or "",
                      f(e.fecha_estimada), "Afuera" + (" (atrasado)" if s["atrasado"] else "") if e.estado == "enviado" else "Volvió",
                      s["dias"], f(e.fecha_recepcion), s["resultado_texto"] or "", e.serie_nueva or "", e.comprobante or "",
                      s["enviado_por"] or "", s["recibido_por"] or ""])
    nombre = f"envios_fabricante_{a_local(ahora).strftime('%Y-%m-%d')}"
    if formato == "csv":
        return Response(_to_csv(cab, filas).encode("utf-8-sig"), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{nombre}.csv"'})
    return Response(_to_xlsx(cab, filas, "Envíos"),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}.xlsx"'})
