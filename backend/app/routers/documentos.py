"""
documentos.py — GET /tickets/{id}/documentos/{tipo}

tipo: ingreso | remito | presupuesto | etiqueta | ticket_ingreso | ticket_entrega
formato: pdf | html. Si no se indica, se usa el ajuste "pdf_modo"
(servidor → pdf, navegador → html que se imprime solo).
El cliente solo puede pedir ingreso, remito y presupuesto de sus tickets
(la etiqueta y los comprobantes de ticketera son para el mostrador del taller).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from .. import ajustes, auth, database, models
from ..services import documentos

router = APIRouter(prefix="/tickets", tags=["documentos"])


@router.get("/{ticket_id}/documentos/{tipo}")
def documento(
    ticket_id: int,
    tipo: str,
    request: Request,
    formato: Optional[str] = Query(None, pattern="^(pdf|html)$"),
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.get_current_user),
):
    if tipo not in documentos.TIPOS:
        raise HTTPException(404, f"Documento inexistente. Opciones: {', '.join(documentos.TIPOS)}")
    ticket = db.query(models.Ticket).filter_by(id=ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Ticket no encontrado")
    if current_user.rol == models.UserRole.CLIENTE:
        if ticket.usuario_id != current_user.id or tipo not in documentos.TIPOS_CLIENTE:
            raise HTTPException(403, "Sin acceso a este documento")
        pres = ticket.presupuesto
        if tipo == "presupuesto" and (not pres or pres.estado == models.PresupuestoEstado.BORRADOR):
            raise HTTPException(404, "Todavía no hay un presupuesto para este ticket")
    if tipo == "presupuesto" and not ticket.presupuesto:
        raise HTTPException(404, "Este ticket no tiene presupuesto")

    if formato is None:
        formato = "pdf" if ajustes.get(db, "pdf_modo") == "servidor" else "html"
    ctx = documentos.contexto_tipo(db, tipo, documentos.contexto(db, ticket, ajustes.public_url(db, request)))

    if formato == "html":
        return HTMLResponse(documentos.render_html(tipo, ctx, imprimir=True))
    pdf = documentos.render_pdf(documentos.render_html(tipo, ctx))
    nombre = documentos.nombre_archivo(tipo, ticket, "pdf")
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{nombre}"'})
