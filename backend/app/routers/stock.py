from fastapi import APIRouter, Depends, HTTPException, Query as QParam
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from .. import database, models, schemas, auth

router = APIRouter(prefix="/stock", tags=["stock"])
STAFF = [models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO]

def _enrich(m: models.StockMovimiento) -> schemas.StockMovimientoOut:
    out = schemas.StockMovimientoOut.model_validate(m)
    if m.repuesto:  out.repuesto_nombre = m.repuesto.nombre
    if m.ticket:    out.ticket_rma      = m.ticket.numero_rma
    if m.usuario:   out.usuario_nombre  = m.usuario.nombre
    return out

@router.get("/history", response_model=List[schemas.StockMovimientoOut])
def get_stock_history(
    repuesto_id: Optional[int] = QParam(None),
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role(STAFF))
):
    q = db.query(models.StockMovimiento).order_by(models.StockMovimiento.fecha.desc())
    if repuesto_id:
        q = q.filter(models.StockMovimiento.repuesto_id == repuesto_id)
    return [_enrich(m) for m in q.limit(300).all()]

@router.patch("/{mov_id}", response_model=schemas.StockMovimientoOut)
def update_stock_mov(
    mov_id: int,
    upd: schemas.StockMovimientoUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([models.UserRole.ADMINISTRADOR]))
):
    mov = db.query(models.StockMovimiento).filter_by(id=mov_id).first()
    if not mov:
        raise HTTPException(status_code=404, detail="Movimiento no encontrado")
    if upd.nota is not None:
        mov.nota = upd.nota
    db.commit()
    db.refresh(mov)
    return _enrich(mov)

@router.delete("/{mov_id}")
def delete_stock_mov(
    mov_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([models.UserRole.ADMINISTRADOR]))
):
    """Only allowed if this is the latest movement for that repuesto."""
    mov = db.query(models.StockMovimiento).filter_by(id=mov_id).first()
    if not mov:
        raise HTTPException(status_code=404, detail="Movimiento no encontrado")
    last = (db.query(models.StockMovimiento)
            .filter_by(repuesto_id=mov.repuesto_id)
            .order_by(models.StockMovimiento.fecha.desc())
            .first())
    if last.id != mov_id:
        raise HTTPException(status_code=400,
            detail="Solo se puede eliminar el último movimiento de un repuesto")
    # Revert stock
    part = db.query(models.Repuesto).filter_by(id=mov.repuesto_id).first()
    if part:
        part.stock = mov.stock_anterior
    db.delete(mov)
    db.commit()
    return {"deleted": mov_id, "stock_revertido": mov.stock_anterior}

@router.post("/reposicion", response_model=schemas.StockMovimientoOut)
def reponer_stock(
    repuesto_id: int, cantidad: int, nota: Optional[str] = None,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([models.UserRole.ADMINISTRADOR]))
):
    part = db.query(models.Repuesto).filter_by(id=repuesto_id).first()
    if not part:
        raise HTTPException(status_code=404, detail="Repuesto no encontrado")
    if cantidad <= 0:
        raise HTTPException(status_code=400, detail="La cantidad debe ser mayor a 0")
    stock_anterior = part.stock
    part.stock += cantidad
    mov = models.StockMovimiento(
        repuesto_id=repuesto_id, ticket_id=None, usuario_id=current_user.id,
        tipo="reposicion", cantidad=cantidad,
        stock_anterior=stock_anterior, stock_nuevo=part.stock,
        nota=nota or f"Reposición manual por {current_user.nombre}",
    )
    db.add(mov)
    db.commit()
    db.refresh(mov)
    return _enrich(mov)


@router.patch("/history/{mov_id}", response_model=schemas.StockMovimientoOut)
def update_stock_movimiento(
    mov_id: int,
    payload: schemas.StockMovimientoUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([models.UserRole.ADMINISTRADOR]))
):
    mov = db.query(models.StockMovimiento).filter(models.StockMovimiento.id == mov_id).first()
    if not mov:
        raise HTTPException(status_code=404, detail="Movimiento no encontrado")
    if payload.nota is not None:
        mov.nota = payload.nota
    db.commit()
    db.refresh(mov)
    out = schemas.StockMovimientoOut.model_validate(mov)
    if mov.repuesto: out.repuesto_nombre = mov.repuesto.nombre
    if mov.ticket:   out.ticket_rma      = mov.ticket.numero_rma
    if mov.usuario:  out.usuario_nombre  = mov.usuario.nombre
    return out


@router.delete("/history/{mov_id}", status_code=204)
def delete_stock_movimiento(
    mov_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([models.UserRole.ADMINISTRADOR]))
):
    """Only the most recent movement for a given repuesto can be deleted."""
    mov = db.query(models.StockMovimiento).filter(models.StockMovimiento.id == mov_id).first()
    if not mov:
        raise HTTPException(status_code=404, detail="Movimiento no encontrado")

    # Check it is the latest for this repuesto
    latest = (
        db.query(models.StockMovimiento)
        .filter(models.StockMovimiento.repuesto_id == mov.repuesto_id)
        .order_by(models.StockMovimiento.fecha.desc(), models.StockMovimiento.id.desc())
        .first()
    )
    if not latest or latest.id != mov_id:
        raise HTTPException(
            status_code=400,
            detail="Solo se puede eliminar el último movimiento de un repuesto"
        )

    # Revert stock
    part = db.query(models.Repuesto).filter(models.Repuesto.id == mov.repuesto_id).first()
    if part:
        part.stock = mov.stock_anterior  # restore previous balance

    db.delete(mov)
    db.commit()
    return None
