from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from .. import database, models, schemas, auth
from ..services.ticket_service import log_event, notify_ticket_actors
from ..timeutils import utcnow

router = APIRouter(prefix="/tickets/{ticket_id}/comments", tags=["comments"])

@router.post("/", response_model=schemas.Comment)
def create_comment(
    ticket_id: int,
    comment: schemas.CommentCreate,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.get_current_user)
):
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if current_user.rol == models.UserRole.CLIENTE and ticket.usuario_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    is_internal = comment.is_internal and current_user.rol != models.UserRole.CLIENTE
    new_comment = models.Comentario(
        ticket_id=ticket_id, usuario_id=current_user.id,
        comentario=comment.comentario, is_internal=is_internal,
    )
    db.add(new_comment)
    ticket.fecha_actualizacion = utcnow()
    tipo = models.EventoHistorial.NOTA_INTERNA if is_internal else models.EventoHistorial.COMENTARIO
    log_event(db, ticket_id, current_user.id, tipo,
              detalle=f"{'[Interna] ' if is_internal else ''}{comment.comentario[:80]}")
    # Notify: don't notify for internal notes sent to the client
    if not is_internal:
        preview = comment.comentario[:100] + ("…" if len(comment.comentario) > 100 else "")
        notify_ticket_actors(
            db, ticket,
            tipo=models.TipoNotificacion.COMENTARIO,
            titulo=f"Nuevo comentario en {ticket.numero_rma}",
            mensaje=f"{current_user.nombre}: {preview}",
            origen_usuario_id=current_user.id,
        )
    elif is_internal:
        # Internal note: only notify assigned tech / admin, not the client
        if ticket.tecnico_asignado and ticket.tecnico_asignado != current_user.id:
            preview = comment.comentario[:100] + ("…" if len(comment.comentario) > 100 else "")
            db.add(models.Notificacion(
                usuario_id=ticket.tecnico_asignado,
                ticket_id=ticket.id,
                tipo=models.TipoNotificacion.COMENTARIO,
                titulo=f"Nota interna en {ticket.numero_rma}",
                mensaje=f"{current_user.nombre}: {preview}",
                origen_usuario_id=current_user.id,
            ))
    db.commit()
    db.refresh(new_comment)
    return schemas.Comment.from_orm_with_nombre(new_comment)

@router.get("/", response_model=List[schemas.Comment])
def list_comments(
    ticket_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.get_current_user)
):
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if current_user.rol == models.UserRole.CLIENTE and ticket.usuario_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    query = db.query(models.Comentario).filter(models.Comentario.ticket_id == ticket_id)
    if current_user.rol == models.UserRole.CLIENTE:
        query = query.filter(models.Comentario.is_internal == False)
    return [schemas.Comment.from_orm_with_nombre(c) for c in query.all()]
