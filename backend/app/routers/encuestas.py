"""encuestas.py — Encuesta de satisfacción: respuesta desde la cuenta del cliente y resumen."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import auth, database, models, schemas
from ..services import encuestas

router = APIRouter(tags=["encuestas"])


@router.post("/tickets/{ticket_id}/encuesta", response_model=schemas.Ticket)
def responder(ticket_id: int, data: schemas.EncuestaIn, db: Session = Depends(database.get_db),
              current_user: models.Usuario = Depends(auth.get_current_user)):
    t = db.query(models.Ticket).filter_by(id=ticket_id).first()
    if not t or t.usuario_id != current_user.id:
        # La responde el cliente del ticket (no el taller en su nombre)
        raise HTTPException(status_code=404 if not t else 403, detail="Solo el cliente del ticket puede calificarlo.")
    encuestas.responder(db, t, data.puntaje, data.comentario, "cuenta")
    db.commit()
    db.refresh(t)
    return schemas.Ticket.for_viewer(t, current_user)


@router.get("/encuestas/resumen")
def resumen(dias: int = Query(90, ge=1, le=3650), db: Session = Depends(database.get_db),
            _: models.Usuario = Depends(auth.check_role([models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO]))):
    from ..timeutils import iso_utc
    r = encuestas.resumen(db, dias)
    for c in r["comentarios"]:
        c["fecha"] = iso_utc(c["fecha"])
    return r
