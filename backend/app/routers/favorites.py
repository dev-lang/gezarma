"""
favorites.py — Ticket bookmarks per user.
  GET    /favorites/           — list favourite tickets for current user
  POST   /favorites/{ticket_id} — add to favourites (idempotent)
  DELETE /favorites/{ticket_id} — remove from favourites
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from sqlalchemy.exc import IntegrityError

from .. import database, models, schemas, auth

router = APIRouter(prefix="/favorites", tags=["favorites"])

_ALLOWED = [models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO]


@router.get("/", response_model=List[schemas.Ticket])
def list_favourites(
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role(_ALLOWED)),
):
    favs = (
        db.query(models.TicketFavorito)
        .filter_by(usuario_id=current_user.id)
        .order_by(models.TicketFavorito.fecha.desc())
        .all()
    )
    return [
        schemas.Ticket.from_orm_with_tecnico(f.ticket, current_user.id)
        for f in favs
        if f.ticket
    ]


@router.post("/{ticket_id}", status_code=201)
def add_favourite(
    ticket_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role(_ALLOWED)),
):
    ticket = db.query(models.Ticket).filter_by(id=ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    existing = db.query(models.TicketFavorito).filter_by(
        usuario_id=current_user.id, ticket_id=ticket_id
    ).first()
    if existing:
        return {"ok": True, "already": True}
    fav = models.TicketFavorito(usuario_id=current_user.id, ticket_id=ticket_id)
    db.add(fav)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    return {"ok": True}


@router.delete("/{ticket_id}", status_code=200)
def remove_favourite(
    ticket_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role(_ALLOWED)),
):
    fav = db.query(models.TicketFavorito).filter_by(
        usuario_id=current_user.id, ticket_id=ticket_id
    ).first()
    if fav:
        db.delete(fav)
        db.commit()
    return {"ok": True}
