from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from .. import database, models, schemas, auth

router = APIRouter(prefix="/products", tags=["products"])

@router.get("/", response_model=List[schemas.Product])
def list_products(
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.get_current_user)
):
    return db.query(models.Producto).all()

@router.post("/", response_model=schemas.Product, status_code=201)
def create_product(
    product: schemas.ProductCreate,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([models.UserRole.ADMINISTRADOR]))
):
    if product.numero_parte:
        existing = db.query(models.Producto).filter(models.Producto.numero_parte == product.numero_parte).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Ya existe un producto con el número de parte '{product.numero_parte}'")
    db_product = models.Producto(**product.model_dump())
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product

@router.put("/{product_id}", response_model=schemas.Product)
def update_product(
    product_id: int,
    product: schemas.ProductUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([models.UserRole.ADMINISTRADOR]))
):
    db_product = db.query(models.Producto).filter(models.Producto.id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    if product.numero_parte and product.numero_parte != db_product.numero_parte:
        existing = db.query(models.Producto).filter(
            models.Producto.numero_parte == product.numero_parte,
            models.Producto.id != product_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Ya existe un producto con el número de parte '{product.numero_parte}'")

    for key, value in product.model_dump().items():
        setattr(db_product, key, value)
    db.commit()
    db.refresh(db_product)
    return db_product

@router.delete("/{product_id}", status_code=204)
def delete_product(
    product_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([models.UserRole.ADMINISTRADOR]))
):
    db_product = db.query(models.Producto).filter(models.Producto.id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    tickets_using = db.query(models.Ticket).filter(models.Ticket.producto_id == product_id).count()
    if tickets_using > 0:
        raise HTTPException(
            status_code=400,
            detail=f"No se puede eliminar: el producto está asociado a {tickets_using} ticket(s)"
        )
    db.delete(db_product)
    db.commit()
    return None
