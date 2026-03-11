"""
ticket_service.py
-----------------
RMA number generation (Feature 12) + ticket creation logic.

RMA format: RMA-{year}-{ROLE_PREFIX}{SERIE}{SEQ:03d}
  ROLE_PREFIX : 2-char code per role  (CL=cliente, TC=tecnico, AD=administrador, OT=other)
  SERIE       : AA..ZZ  (resets to AA when crossing years, increments when seq > 999)
  SEQ         : 001..999 (per serie)
"""
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from .. import models, schemas

# ── Role prefix map ──────────────────────────────────────────────────────────
ROLE_PREFIX = {
    "cliente":       "CL",
    "tecnico":       "TC",
    "administrador": "AD",
}

def _next_serie(current: str) -> str:
    """AA → AB → ... → AZ → BA → ... → ZZ"""
    a, b = current[0], current[1]
    if b < "Z":
        return a + chr(ord(b) + 1)
    if a < "Z":
        return chr(ord(a) + 1) + "A"
    raise ValueError("RMA counter exhausted for this year/prefix")

def generate_rma_number(db: Session, user_rol: str, year: int = None) -> str:
    year = year or datetime.now().year
    prefix = ROLE_PREFIX.get(user_rol, "OT")

    counter = (
        db.query(models.RmaCounter)
        .filter_by(year=year, rol_prefix=prefix)
        .with_for_update()
        .first()
    )
    if counter is None:
        counter = models.RmaCounter(year=year, rol_prefix=prefix, serie="AA", last_seq=0)
        db.add(counter)

    counter.last_seq += 1
    if counter.last_seq > 999:
        counter.serie  = _next_serie(counter.serie)
        counter.last_seq = 1

    db.flush()
    return f"RMA-{year}-{prefix}{counter.serie}{counter.last_seq:03d}"

# ── SLA helpers ──────────────────────────────────────────────────────────────
def calculate_sla_deadline(status: str):
    now = datetime.now()
    if status == models.TicketStatus.NUEVO:
        return now + timedelta(hours=24)
    elif status in (models.TicketStatus.REVISION, models.TicketStatus.DIAGNOSTICO):
        return now + timedelta(hours=48)
    elif status == models.TicketStatus.REPARACION:
        return now + timedelta(days=5)
    return None

# ── Historial helper ─────────────────────────────────────────────────────────
def log_event(db: Session, ticket_id: int, usuario_id: int,
               tipo: str, detalle: str = None,
               estado_ant=None, estado_nuevo=None,
               campo=None, val_ant=None, val_nuevo=None):
    entry = models.HistorialEstado(
        ticket_id=ticket_id,
        usuario_id=usuario_id,
        tipo_evento=tipo,
        estado_anterior=estado_ant,
        estado_nuevo=estado_nuevo,
        campo=campo,
        valor_anterior=str(val_ant) if val_ant is not None else None,
        valor_nuevo=str(val_nuevo) if val_nuevo is not None else None,
        detalle=detalle,
    )
    db.add(entry)

# ── Ticket creation ───────────────────────────────────────────────────────────
def process_ticket_creation(db: Session, ticket: schemas.TicketCreate,
                             current_user: models.Usuario, ip_address: str = None):
    rma_num = generate_rma_number(db, current_user.rol)

    # Auto-priority
    priority = "Normal"
    if current_user.tipo_cliente == models.UserType.EMPRESA:
        priority = "Alta"

    fecha_compra_naive = ticket.fecha_compra.replace(tzinfo=None) if ticket.fecha_compra.tzinfo else ticket.fecha_compra
    if fecha_compra_naive > datetime.now():
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="La fecha de compra no puede ser una fecha futura.")

    is_warranty = True
    if fecha_compra_naive < datetime.now() - timedelta(days=365):
        is_warranty = False
        if priority != "Alta":
            priority = "Baja"

    # Override priority from request if explicitly set
    if ticket.prioridad and ticket.prioridad != "Normal":
        priority = ticket.prioridad

    deadline = calculate_sla_deadline(models.TicketStatus.NUEVO)

    new_data = ticket.dict()
    new_data["fecha_compra"] = fecha_compra_naive
    new_data["prioridad"] = priority

    new_ticket = models.Ticket(
        **new_data,
        numero_rma=rma_num,
        usuario_id=current_user.id,
        estado=models.TicketStatus.NUEVO,
        en_garantia=is_warranty,
        deadline_sla=deadline,
        fecha_actualizacion=datetime.now(),
    )
    db.add(new_ticket)
    db.flush()

    log_event(db, new_ticket.id, current_user.id,
              models.EventoHistorial.CAMBIO_ESTADO,
              detalle=f"Ticket creado con estado Nuevo",
              estado_ant=None, estado_nuevo=models.TicketStatus.NUEVO)

    # Auditoría
    audit = models.Auditoria(
        usuario_id=current_user.id,
        accion="CREATE_TICKET",
        detalle=f"Ticket creado: {rma_num} para {ticket.numero_serie}",
        ip_address=ip_address,
    )
    db.add(audit)
    db.commit()
    db.refresh(new_ticket)
    return new_ticket

# ── Notification helper ───────────────────────────────────────────────────────
def notify_ticket_actors(
    db,
    ticket,
    tipo: str,
    titulo: str,
    mensaje: str,
    origen_usuario_id: int,
    extra_recipient_ids: list = None,
):
    """
    Create in-app notifications for all relevant users of a ticket:
      - the assigned technician (if any, and not the one who triggered it)
      - the ticket owner/cliente (if not the one who triggered it)
      - any extra recipient ids passed in
    """
    recipients = set()
    if ticket.tecnico_asignado and ticket.tecnico_asignado != origen_usuario_id:
        recipients.add(ticket.tecnico_asignado)
    if ticket.usuario_id and ticket.usuario_id != origen_usuario_id:
        recipients.add(ticket.usuario_id)
    if extra_recipient_ids:
        for uid in extra_recipient_ids:
            if uid and uid != origen_usuario_id:
                recipients.add(uid)
    for uid in recipients:
        notif = models.Notificacion(
            usuario_id=uid,
            ticket_id=ticket.id,
            tipo=tipo,
            titulo=titulo,
            mensaje=mensaje,
            origen_usuario_id=origen_usuario_id,
        )
        db.add(notif)
