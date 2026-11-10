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
from ..timeutils import utcnow, now_local

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
    """Siguiente N° de RMA, sin repetidos aunque haya dos altas a la vez.

    El incremento se hace en la base (UPDATE ... SET last_seq = last_seq + 1
    RETURNING): la segunda alta espera a que la primera confirme y recibe el
    número siguiente. (Leer el contador y escribirlo desde Python daba el mismo
    número a las dos: en SQLite with_for_update no bloquea nada.)
    """
    from sqlalchemy import update
    from sqlalchemy.exc import IntegrityError
    C = models.RmaCounter
    year = year or now_local().year
    prefix = ROLE_PREFIX.get(user_rol, "OT")
    for _ in range(5):
        fila = db.execute(
            update(C).where(C.year == year, C.rol_prefix == prefix)
            .values(last_seq=C.last_seq + 1)
            .returning(C.id, C.serie, C.last_seq)
            .execution_options(synchronize_session=False)
        ).first()
        if fila is None:
            # Primer RMA del año para ese prefijo. La restricción única (año, prefijo)
            # hace que, si otra alta lo crea al mismo tiempo, esta lo reintente.
            try:
                with db.begin_nested():
                    db.add(C(year=year, rol_prefix=prefix, serie="AA", last_seq=0))
            except IntegrityError:
                pass
            continue
        cid, serie, seq = fila
        if seq > 999:
            serie, seq = _next_serie(serie), 1
            db.execute(update(C).where(C.id == cid).values(serie=serie, last_seq=seq)
                       .execution_options(synchronize_session=False))
        return f"RMA-{year}-{prefix}{serie}{seq:03d}"
    raise RuntimeError("No se pudo generar el N° de RMA")

def sumar_meses(fecha: datetime, meses: int) -> datetime:
    """fecha + meses de calendario (31/01 + 1 mes = 28 o 29/02)."""
    import calendar
    m = fecha.month - 1 + meses
    anio, mes = fecha.year + m // 12, m % 12 + 1
    return fecha.replace(year=anio, month=mes, day=min(fecha.day, calendar.monthrange(anio, mes)[1]))


# ── SLA helpers ──────────────────────────────────────────────────────────────
def calculate_sla_deadline(status: str, db: Session = None):
    """Vencimiento del SLA según el estado. Los plazos salen de Ajustes → SLA
    (sin base, los valores por defecto: 24 h, 48 h y 5 días)."""
    from .. import ajustes
    plazo = (lambda clave: ajustes.get(db, clave)) if db is not None else (lambda clave: ajustes.DEFS[clave]["default"])
    now = utcnow()
    if status == models.TicketStatus.NUEVO:
        return now + timedelta(hours=plazo("sla_horas_nuevo"))
    elif status in (models.TicketStatus.REVISION, models.TicketStatus.DIAGNOSTICO):
        return now + timedelta(hours=plazo("sla_horas_diagnostico"))
    elif status == models.TicketStatus.REPARACION:
        return now + timedelta(days=plazo("sla_dias_reparacion"))
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
                             current_user: models.Usuario, ip_address: str = None,
                             cliente: models.Usuario = None, checklist: dict = None, detalle_alta: str = None):
    """Crea el ticket. Por defecto queda a nombre de quien lo carga; en el ingreso
    en mostrador, el taller lo carga a nombre de `cliente` (el N° de RMA y la
    prioridad automática salen del cliente, el historial registra quién lo cargó)."""
    duenio = cliente or current_user
    if ticket.producto_id is not None and not db.get(models.Producto, ticket.producto_id):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="El producto elegido no existe")
    rma_num = generate_rma_number(db, duenio.rol)

    # Auto-priority
    priority = "Normal"
    if duenio.tipo_cliente == models.UserType.EMPRESA:
        priority = "Alta"

    fecha_compra_naive = ticket.fecha_compra.replace(tzinfo=None) if ticket.fecha_compra.tzinfo else ticket.fecha_compra
    if fecha_compra_naive > now_local():
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="La fecha de compra no puede ser una fecha futura.")

    # Garantía de compra: la del producto (periodo_garantia_meses); sin producto, 12 meses
    meses = 12
    if ticket.producto_id:
        prod = db.get(models.Producto, ticket.producto_id)
        if prod and prod.periodo_garantia_meses is not None:
            meses = prod.periodo_garantia_meses
    is_warranty = now_local() <= sumar_meses(fecha_compra_naive, meses)
    if not is_warranty and priority != "Alta":
        priority = "Baja"

    # La prioridad elegida a mano solo vale si la carga el taller; la del cliente es automática
    if current_user.rol != models.UserRole.CLIENTE and ticket.prioridad and ticket.prioridad != "Normal":
        priority = ticket.prioridad

    deadline = calculate_sla_deadline(models.TicketStatus.NUEVO, db)

    new_data = ticket.model_dump()
    new_data["fecha_compra"] = fecha_compra_naive
    new_data["prioridad"] = priority

    new_ticket = models.Ticket(
        **new_data,
        numero_rma=rma_num,
        usuario_id=duenio.id,
        checklist_ingreso=checklist,
        estado=models.TicketStatus.NUEVO,
        en_garantia=is_warranty,
        deadline_sla=deadline,
        fecha_actualizacion=utcnow(),
    )
    db.add(new_ticket)
    db.flush()

    from . import garantia
    garantia.revisar_reingreso(db, new_ticket, current_user)

    log_event(db, new_ticket.id, current_user.id,
              models.EventoHistorial.CAMBIO_ESTADO,
              detalle=detalle_alta or ("Ticket creado con estado Nuevo" if duenio is current_user
                       else f"Ingreso en mostrador para {duenio.nombre}, cargado por {current_user.nombre}"),
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
