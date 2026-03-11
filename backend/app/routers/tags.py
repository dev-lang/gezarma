"""
tags.py — CRUD completo de etiquetas (Feature 4).
Las etiquetas se pueden crear, editar, eliminar y listar desde admin.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from .. import database, models, schemas, auth

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("/", response_model=List[schemas.Tag])
def list_tags(
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.get_current_user)
):
    return db.query(models.Tag).order_by(models.Tag.nombre).all()


@router.post("/", response_model=schemas.Tag)
def create_tag(
    tag: schemas.TagCreate,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([models.UserRole.ADMINISTRADOR]))
):
    existing = db.query(models.Tag).filter_by(nombre=tag.nombre).first()
    if existing:
        raise HTTPException(status_code=400, detail="Ya existe una etiqueta con ese nombre")
    new_tag = models.Tag(nombre=tag.nombre, color=tag.color)
    db.add(new_tag)
    db.commit()
    db.refresh(new_tag)
    return new_tag


@router.patch("/{tag_id}", response_model=schemas.Tag)
def update_tag(
    tag_id: int,
    tag: schemas.TagCreate,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([models.UserRole.ADMINISTRADOR]))
):
    db_tag = db.query(models.Tag).filter(models.Tag.id == tag_id).first()
    if not db_tag:
        raise HTTPException(status_code=404, detail="Etiqueta no encontrada")
    # Check name uniqueness
    conflict = db.query(models.Tag).filter(
        models.Tag.nombre == tag.nombre, models.Tag.id != tag_id
    ).first()
    if conflict:
        raise HTTPException(status_code=400, detail="Ya existe otra etiqueta con ese nombre")
    db_tag.nombre = tag.nombre
    db_tag.color  = tag.color
    db.commit()
    db.refresh(db_tag)
    return db_tag


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag(
    tag_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([models.UserRole.ADMINISTRADOR]))
):
    db_tag = db.query(models.Tag).filter(models.Tag.id == tag_id).first()
    if not db_tag:
        raise HTTPException(status_code=404, detail="Etiqueta no encontrada")
    # Remove from all tickets first
    db.execute(
        models.ticket_tags.delete().where(models.ticket_tags.c.tag_id == tag_id)
    )
    db.delete(db_tag)
    db.commit()
    return None
