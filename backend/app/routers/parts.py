from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from .. import database, models, schemas, auth
from ..services import stock_service

router = APIRouter(prefix="/parts", tags=["parts"])

@router.get("/", response_model=List[schemas.SparePart])
def list_parts(
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([
        models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO
    ]))
):
    return db.query(models.Repuesto).all()

@router.post("/", response_model=schemas.SparePart, status_code=status.HTTP_201_CREATED)
def create_part(
    part: schemas.SparePartCreate,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([models.UserRole.ADMINISTRADOR]))
):
    existing = db.query(models.Repuesto).filter(models.Repuesto.codigo == part.codigo).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Ya existe un repuesto con el código '{part.codigo}'")
    db_part = models.Repuesto(**part.model_dump())
    db.add(db_part)
    db.commit()
    db.refresh(db_part)
    return db_part

@router.put("/{part_id}", response_model=schemas.SparePart)
def update_part(
    part_id: int,
    part: schemas.SparePartCreate,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([models.UserRole.ADMINISTRADOR]))
):
    db_part = db.query(models.Repuesto).filter(models.Repuesto.id == part_id).first()
    if not db_part:
        raise HTTPException(status_code=404, detail="Repuesto no encontrado")

    if part.codigo != db_part.codigo:
        existing = db.query(models.Repuesto).filter(
            models.Repuesto.codigo == part.codigo,
            models.Repuesto.id != part_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Ya existe un repuesto con el código '{part.codigo}'")

    if part.stock_minimo < 0:
        raise HTTPException(status_code=400, detail="El stock mínimo no puede ser negativo")
    stock_anterior = db_part.stock
    for key, value in part.model_dump().items():
        setattr(db_part, key, value)
    stock_service.revisar_minimo(db, db_part, stock_anterior)

    db.commit()
    db.refresh(db_part)
    return db_part

@router.delete("/{part_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_part(
    part_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([models.UserRole.ADMINISTRADOR]))
):
    db_part = db.query(models.Repuesto).filter(models.Repuesto.id == part_id).first()
    if not db_part:
        raise HTTPException(status_code=404, detail="Repuesto no encontrado")

    in_use = db.query(models.TicketRepuesto).filter(models.TicketRepuesto.repuesto_id == part_id).first()
    if in_use:
        raise HTTPException(
            status_code=400,
            detail="No se puede eliminar: el repuesto está asociado a uno o más tickets"
        )

    db.delete(db_part)
    db.commit()
    return None
