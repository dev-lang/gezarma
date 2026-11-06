"""
ticket_adjuntos.py — Adjuntos de un ticket: subir, listar, descargar y borrar.
(Separado de tickets.py; mismas URLs: /tickets/{id}/attachments…)
"""
from fastapi import APIRouter, Depends, HTTPException, File, Form, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Optional
import os, re, uuid

from .. import database, models, auth, config
from ..timeutils import iso_utc
from ..services.ticket_service import log_event
from ._tickets_comun import ticket_para_usuario

router = APIRouter(prefix="/tickets", tags=["adjuntos"])

UPLOAD_DIR = config.UPLOAD_DIR
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _adjunto_path(adj) -> str:
    """Where an attachment lives on disk. Built from the current UPLOAD_DIR, so files
    keep working if UPLOAD_DIR changes (e.g. moving to Docker); falls back to the
    path stored at upload time."""
    path = os.path.join(UPLOAD_DIR, f"ticket_{adj.ticket_id}", adj.nombre_guardado or "")
    if adj.nombre_guardado and os.path.exists(path):
        return path
    return adj.ruta_archivo

ALLOWED_EXTENSIONS = {"pdf", "txt", "jpg", "jpeg", "png"}
ALLOWED_MIME_TYPES = {"application/pdf", "text/plain", "image/jpeg", "image/png"}
MAX_FILE_BYTES         = 10 * 1024 * 1024  # 10 MB per individual file
MAX_TICKET_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB total per ticket
# Tope por cliente entre todos sus tickets: como puede crear tickets, sin esto
# podría llenar el disco subiendo 10 MB a cada uno
MAX_CLIENTE_UPLOAD_BYTES = 50 * 1024 * 1024

def _safe_filename(original: str) -> tuple[str, str]:
    """
    Returns (safe_display_name, unique_stored_name).
    - Strips path separators and dangerous characters.
    - Prefixes with a short UUID to prevent collisions & path traversal.
    """
    # Remove any directory components
    basename = os.path.basename(original).strip()
    # Keep only safe characters: letters, digits, dots, dashes, underscores
    safe = re.sub(r"[^\w.\-]", "_", basename)
    # Prevent hidden files and double-extension tricks
    if safe.startswith("."):
        safe = "_" + safe
    prefix = uuid.uuid4().hex[:8]
    return safe, f"{prefix}_{safe}"


# ── Attachments ───────────────────────────────────────────────────────────────

def _ticket_used_bytes(ticket_id: int, db) -> int:
    """Sum of stored file sizes for a ticket (based on DB tamanio field)."""
    adjuntos = db.query(models.Adjunto).filter_by(ticket_id=ticket_id).all()
    return sum(a.tamanio or 0 for a in adjuntos)


def _serialize_adjunto(a: models.Adjunto) -> dict:
    ext = (a.nombre_archivo or "").rsplit(".", 1)[-1].lower()
    return {
        "id":             a.id,
        "ticket_id":      a.ticket_id,
        "nombre_archivo": a.nombre_archivo,
        "tamanio":        a.tamanio or 0,
        "mime_type":      a.mime_type or "",
        "ext":            ext,
        "fecha":          iso_utc(a.fecha) if a.fecha else None,
        "categoria":      a.categoria,
    }


@router.post("/{ticket_id}/attachments")
def upload_attachment(
    ticket_id: int,
    file: UploadFile = File(...),
    categoria: Optional[str] = Form(None),
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.get_current_user)
):
    ticket_para_usuario(ticket_id, current_user, db)
    # "ingreso" = foto del estado del equipo al recibirlo (la saca el taller)
    if categoria not in (None, "", "ingreso"):
        raise HTTPException(status_code=400, detail="Categoría de adjunto inválida")
    if categoria == "ingreso" and current_user.rol == models.UserRole.CLIENTE:
        raise HTTPException(status_code=403, detail="Las fotos de ingreso las carga el taller")

    # ── Validate extension ────────────────────────────────────────────────
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo de archivo no permitido. Solo se aceptan: {', '.join(sorted(ALLOWED_EXTENSIONS)).upper()}"
        )

    # ── Leer como mucho el límite + 1 byte (no el archivo entero a memoria) ──
    file_data = file.file.read(MAX_FILE_BYTES + 1)
    file_size = len(file_data)

    # ── Per-file size limit ───────────────────────────────────────────────
    if file_size > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=400,
            detail="El archivo supera el límite individual de 10 MB."
        )

    # ── Total ticket quota ────────────────────────────────────────────────
    used_bytes = _ticket_used_bytes(ticket_id, db)
    if used_bytes + file_size > MAX_TICKET_UPLOAD_BYTES:
        remaining_mb = round((MAX_TICKET_UPLOAD_BYTES - used_bytes) / (1024 * 1024), 2)
        raise HTTPException(
            status_code=400,
            detail=f"Límite del ticket alcanzado. Espacio disponible: {remaining_mb} MB de 10 MB."
        )

    if current_user.rol == models.UserRole.CLIENTE:
        usado_cliente = (db.query(func.coalesce(func.sum(models.Adjunto.tamanio), 0))
                         .join(models.Ticket, models.Ticket.id == models.Adjunto.ticket_id)
                         .filter(models.Ticket.usuario_id == current_user.id).scalar())
        if usado_cliente + file_size > MAX_CLIENTE_UPLOAD_BYTES:
            raise HTTPException(status_code=400,
                                detail="Llegaste al límite de archivos de tu cuenta (50 MB). Si necesitás mandar más, consultá al taller.")

    # ── Build safe filename & per-ticket folder ───────────────────────────
    safe_display, stored_name = _safe_filename(file.filename or "archivo")
    ticket_dir = os.path.join(UPLOAD_DIR, f"ticket_{ticket_id}")
    os.makedirs(ticket_dir, exist_ok=True)
    dest = os.path.join(ticket_dir, stored_name)

    with open(dest, "wb") as f:
        f.write(file_data)

    # ── Detect MIME from content type header (fallback to extension) ──────
    mime = file.content_type or ""
    if mime not in ALLOWED_MIME_TYPES:
        ext_to_mime = {
            "pdf": "application/pdf", "txt": "text/plain",
            "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
        }
        mime = ext_to_mime.get(ext, "application/octet-stream")

    adj = models.Adjunto(
        ticket_id=ticket_id,
        nombre_archivo=safe_display,
        nombre_guardado=stored_name,
        ruta_archivo=dest,
        tamanio=file_size,
        mime_type=mime,
        categoria=categoria or None,
    )
    db.add(adj)
    log_event(db, ticket_id, current_user.id,
              models.EventoHistorial.ARCHIVO_SUBIDO,
              detalle=(f"Foto de ingreso: {safe_display}" if categoria == "ingreso"
                       else f"Archivo subido: {safe_display}"))
    db.commit()
    db.refresh(adj)

    used_after = used_bytes + file_size
    return {
        "adjunto": _serialize_adjunto(adj),
        "storage": {
            "used_mb":      round(used_after / (1024 * 1024), 2),
            "remaining_mb": round((MAX_TICKET_UPLOAD_BYTES - used_after) / (1024 * 1024), 2),
            "limit_mb":     10,
        }
    }


@router.get("/{ticket_id}/attachments")
def list_attachments(
    ticket_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.get_current_user)
):
    ticket_para_usuario(ticket_id, current_user, db)
    adjuntos = db.query(models.Adjunto).filter_by(ticket_id=ticket_id).all()
    used_bytes = sum(a.tamanio or 0 for a in adjuntos)
    return {
        "adjuntos": [_serialize_adjunto(a) for a in adjuntos],
        "storage": {
            "used_mb":      round(used_bytes / (1024 * 1024), 2),
            "remaining_mb": round((MAX_TICKET_UPLOAD_BYTES - used_bytes) / (1024 * 1024), 2),
            "limit_mb":     10,
        }
    }


@router.get("/{ticket_id}/attachments/{adj_id}/download")
def download_attachment(
    ticket_id: int,
    adj_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.get_current_user),
):
    # Auth only via the Authorization header: a token in the URL ends up in
    # server logs, browser history and Referer headers.
    ticket_para_usuario(ticket_id, current_user, db)

    adj = db.query(models.Adjunto).filter_by(id=adj_id, ticket_id=ticket_id).first()
    if not adj:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    path = _adjunto_path(adj)
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Archivo no encontrado en el servidor")
    return FileResponse(
        path=path,
        filename=adj.nombre_archivo,
        media_type=adj.mime_type or "application/octet-stream",
    )


@router.delete("/{ticket_id}/attachments/{adj_id}", status_code=204)
def delete_attachment(
    ticket_id: int,
    adj_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([
        models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO
    ]))
):
    adj = db.query(models.Adjunto).filter_by(id=adj_id, ticket_id=ticket_id).first()
    if not adj:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    nombre_del_archivo = adj.nombre_archivo
    # Remove from disk safely
    try:
        path = _adjunto_path(adj)
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass
    db.delete(adj)
    log_event(db, ticket_id, current_user.id,
              models.EventoHistorial.ARCHIVO_ELIMINADO,
              detalle=f"Archivo eliminado: {nombre_del_archivo}")
    db.commit()
