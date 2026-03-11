"""
notifications.py — In-app notification system.
  GET  /notifications/          — list unread (and optionally all) for current user
  GET  /notifications/unread-count — fast badge count
  POST /notifications/mark-read — mark specific ids (or all) as read
  DELETE /notifications/{nid}   — delete one notification
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List

from .. import database, models, schemas, auth

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _serialize(n: models.Notificacion) -> schemas.NotificacionOut:
    return schemas.NotificacionOut(
        id=n.id,
        ticket_id=n.ticket_id,
        ticket_rma=n.ticket.numero_rma if n.ticket else None,
        tipo=n.tipo,
        titulo=n.titulo,
        mensaje=n.mensaje,
        leida=n.leida,
        fecha=n.fecha,
        origen_nombre=n.origen_usuario.nombre if n.origen_usuario else None,
    )


@router.get("/", response_model=List[schemas.NotificacionOut])
def list_notifications(
    all: bool = Query(False, description="Include already-read notifications"),
    limit: int = Query(50, le=200),
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.get_current_user),
):
    # Build all filters BEFORE applying limit (SQLAlchemy requirement)
    q = (
        db.query(models.Notificacion)
        .filter(models.Notificacion.usuario_id == current_user.id)
    )
    if not all:
        q = q.filter(models.Notificacion.leida == False)
    q = q.order_by(models.Notificacion.fecha.desc()).limit(limit)
    return [_serialize(n) for n in q.all()]


@router.get("/unread-count")
def unread_count(
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.get_current_user),
):
    count = (
        db.query(models.Notificacion)
        .filter(
            models.Notificacion.usuario_id == current_user.id,
            models.Notificacion.leida == False,
        )
        .count()
    )
    return {"count": count}


@router.post("/mark-read")
def mark_read(
    body: schemas.NotificacionMarkRead,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.get_current_user),
):
    q = db.query(models.Notificacion).filter(
        models.Notificacion.usuario_id == current_user.id
    )
    if body.ids:
        q = q.filter(models.Notificacion.id.in_(body.ids))
    updated = q.update({"leida": True}, synchronize_session=False)
    db.commit()
    return {"updated": updated}


@router.delete("/{nid}", status_code=204)
def delete_notification(
    nid: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.get_current_user),
):
    n = db.query(models.Notificacion).filter_by(id=nid, usuario_id=current_user.id).first()
    if n:
        db.delete(n)
        db.commit()
