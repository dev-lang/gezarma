"""
public.py — Endpoints públicos (sin login).

GET /public/seguimiento?rma=...&serie=...
    Estado de una reparación. El N° de RMA y el N° de serie juntos funcionan
    como credencial: el cliente los tiene en su orden de ingreso (y en el QR).
    Devuelve solo lo necesario para seguir el equipo: nada de nombres,
    comentarios, diagnóstico ni montos.
"""
import threading
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import ajustes, database, models
from ..timeutils import iso_utc

router = APIRouter(prefix="/public", tags=["público"])

# ── Límite de consultas fallidas por IP (en memoria, por proceso) ────────────
MAX_FALLOS = 10
VENTANA_SEG = 10 * 60
_fallos = defaultdict(deque)
_lock = threading.Lock()


def _ip(request: Request) -> str:
    return request.client.host if request.client else "desconocida"


def _bloqueada(ip: str) -> bool:
    ahora = time.monotonic()
    with _lock:
        q = _fallos[ip]
        while q and ahora - q[0] > VENTANA_SEG:
            q.popleft()
        return len(q) >= MAX_FALLOS


def _registrar_fallo(ip: str) -> None:
    with _lock:
        _fallos[ip].append(time.monotonic())


def reiniciar_limites() -> None:   # para tests
    with _lock:
        _fallos.clear()


NO_ENCONTRADO = "No encontramos una reparación con ese N° de RMA y N° de serie. Revisá los datos de tu orden de ingreso."


def _retiro(db: Session, ticket: models.Ticket):
    from ..services import retiro
    if ticket.estado != retiro.estado_retiro(db) or not ticket.fecha_listo:
        return None
    i = retiro.info(db, ticket)
    return {"listo_desde": iso_utc(i["listo_desde"]), "vence": iso_utc(i["vence"]),
            "politica": ajustes.politica_retiro(db)}


@router.get("/seguimiento")
def seguimiento(
    request: Request,
    rma: str = Query(..., min_length=3, max_length=40),
    serie: str = Query(..., min_length=1, max_length=80),
    db: Session = Depends(database.get_db),
):
    if not ajustes.get(db, "seguimiento_publico"):
        raise HTTPException(404, "El seguimiento público no está habilitado.")
    ip = _ip(request)
    if _bloqueada(ip):
        raise HTTPException(429, "Demasiados intentos. Probá de nuevo en unos minutos.")

    ticket = (db.query(models.Ticket)
              .filter(func.upper(models.Ticket.numero_rma) == rma.strip().upper())
              .first())
    if not ticket or (ticket.numero_serie or "").strip().upper() != serie.strip().upper():
        _registrar_fallo(ip)
        raise HTTPException(404, NO_ENCONTRADO)

    estados = {e.valor: e for e in db.query(models.TicketStatusConfig).all()}

    def estado_info(valor):
        cfg = estados.get(valor)
        return {"valor": valor, "etiqueta": cfg.etiqueta if cfg else valor,
                "color": cfg.color if cfg else "#6b7280", "final": bool(cfg and cfg.es_final)}

    historial = (db.query(models.HistorialEstado)
                 .filter(models.HistorialEstado.ticket_id == ticket.id,
                         models.HistorialEstado.estado_nuevo.isnot(None))
                 .order_by(models.HistorialEstado.fecha.asc()).all())
    linea = []
    for h in historial:
        if not linea or linea[-1]["estado"]["valor"] != h.estado_nuevo:
            linea.append({"estado": estado_info(h.estado_nuevo), "fecha": iso_utc(h.fecha)})

    pres = ticket.presupuesto
    return {
        "numero_rma": ticket.numero_rma,
        "producto": ticket.producto,
        "estado": estado_info(ticket.estado),
        "en_garantia": bool(ticket.en_garantia),
        "fecha_ingreso": iso_utc(ticket.fecha_creacion) if ticket.fecha_creacion else None,
        "ultima_actualizacion": iso_utc(ticket.fecha_actualizacion) if ticket.fecha_actualizacion else None,
        "envio": ({"empresa": ticket.empresa_transporte, "tracking": ticket.tracking_number,
                   "fecha": iso_utc(ticket.fecha_envio) if ticket.fecha_envio else None}
                  if ticket.tracking_number or ticket.empresa_transporte else None),
        # Solo si hay algo que el cliente tenga que hacer; sin montos
        "presupuesto_pendiente": bool(pres and pres.estado == models.PresupuestoEstado.ENVIADO),
        "retiro": _retiro(db, ticket),
        "historial": linea,
        "empresa": ajustes.get(db, "empresa_nombre"),
    }
