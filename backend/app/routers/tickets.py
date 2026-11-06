from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List, Optional

from .. import database, models, schemas, auth
from ..timeutils import utcnow, to_utc_naive, iso_utc
from ..services import email
from ..services import sla as sla_service
from ..services import retiro as retiro_service, avisos
from .. import ajustes
from ._tickets_comun import con_relaciones, ticket_o_404
from ..services.ticket_service import (
    process_ticket_creation, calculate_sla_deadline, log_event, notify_ticket_actors
)

router = APIRouter(prefix="/tickets", tags=["tickets"])

VALID_ESTADOS = {s.value for s in models.TicketStatus}

# ── Helper: serialize historial entries ──────────────────────────────────────
def _historial_out(entries):
    result = []
    for e in entries:
        result.append(schemas.HistorialEntry(
            id=e.id, ticket_id=e.ticket_id,
            tipo_evento=e.tipo_evento or "cambio_estado",
            estado_anterior=e.estado_anterior,
            estado_nuevo=e.estado_nuevo,
            campo=e.campo,
            valor_anterior=e.valor_anterior,
            valor_nuevo=e.valor_nuevo,
            detalle=e.detalle,
            usuario_nombre=e.usuario.nombre if e.usuario else None,
            fecha=e.fecha,
        ))
    return result

# ── Create ────────────────────────────────────────────────────────────────────
@router.post("/", response_model=schemas.Ticket)
def create_ticket(
    ticket: schemas.TicketCreate,
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.get_current_user)
):
    ip = request.client.host if request.client else None
    created = process_ticket_creation(db, ticket, current_user, ip_address=ip)
    return schemas.Ticket.for_viewer(created, current_user)

# ── Dashboard stats ───────────────────────────────────────────────────────────
@router.get("/stats/dashboard", response_model=schemas.DashboardStats)
def get_dashboard_stats(
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([
        models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO
    ]))
):
    finales   = {e.valor for e in db.query(models.TicketStatusConfig).filter_by(es_final=True).all()} \
                or {models.TicketStatus.CERRADO.value, models.TicketStatus.CANCELADO.value}
    cancelado = models.TicketStatus.CANCELADO.value
    total     = db.query(models.Ticket).count()
    abiertos  = db.query(models.Ticket).filter(models.Ticket.estado.notin_(finales)).count()
    cerrados  = db.query(models.Ticket).filter(models.Ticket.estado.in_(finales - {cancelado})).count()
    reparacion= db.query(models.Ticket).filter(models.Ticket.estado == models.TicketStatus.REPARACION).count()
    # Promedio de reparación: solo los terminados (un cancelado no es una reparación)
    # Solo las dos fechas (no los tickets enteros); la resta en Python funciona
    # igual en SQLite y PostgreSQL
    closed    = db.query(models.Ticket.fecha_creacion, models.Ticket.fecha_cierre).filter(
        models.Ticket.fecha_cierre != None,  # noqa: E711
        models.Ticket.estado.in_(finales - {cancelado})).all()
    avg_time  = 0
    if closed:
        total_time = sum((cierre - creacion).total_seconds() for creacion, cierre in closed)
        avg_time   = (total_time / len(closed)) / 3600
    products  = db.query(models.Ticket.producto, func.count(models.Ticket.id)).group_by(models.Ticket.producto).all()
    states    = db.query(models.Ticket.estado, func.count(models.Ticket.id)).group_by(models.Ticket.estado).all()
    techs     = db.query(models.Usuario.nombre, func.count(models.Ticket.id))\
                  .join(models.Ticket, models.Usuario.id == models.Ticket.tecnico_asignado)\
                  .group_by(models.Usuario.nombre).all()
    return {
        "total_tickets": total, "abiertos": abiertos,
        "cerrados": cerrados,   "en_reparacion": reparacion,
        "tiempo_promedio_reparacion_horas": round(avg_time, 2),
        "fallas_por_producto":  {p[0]: p[1] for p in products},
        "tickets_por_estado":   {s[0]: s[1] for s in states},
        "tickets_por_tecnico":  {t[0]: t[1] for t in techs},
    }

# ── Resumen para las tarjetas del listado (todos los roles) ──────────────────
@router.get("/stats/resumen")
def resumen(
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.get_current_user)
):
    """Totales reales de las tarjetas del listado (antes se contaban solo los
    tickets de la página cargada). El cliente ve solo los suyos."""
    T = models.Ticket
    q = db.query(T.estado, func.count(T.id))
    if current_user.rol == models.UserRole.CLIENTE:
        q = q.filter(T.usuario_id == current_user.id)
    por_estado = dict(q.group_by(T.estado).all())
    finales = {e.valor for e in db.query(models.TicketStatusConfig).filter_by(es_final=True).all()} \
              or {models.TicketStatus.CERRADO.value, models.TicketStatus.CANCELADO.value}
    nuevo = models.TicketStatus.NUEVO.value
    total = sum(por_estado.values())
    return {
        "total": total,
        "nuevos": por_estado.get(nuevo, 0),
        "en_proceso": sum(n for e, n in por_estado.items() if e != nuevo and e not in finales),
        "cerrados": sum(n for e, n in por_estado.items() if e in finales and e != models.TicketStatus.CANCELADO.value),
    }

# ── SLA: vencidos o por vencer (panel de alertas del dashboard) ──────────────
@router.get("/sla/alertas")
def sla_alertas(
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([
        models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO
    ]))
):
    ahora = utcnow()
    return [{
        "id": t.id, "numero_rma": t.numero_rma, "producto": t.producto, "estado": t.estado,
        "tecnico_nombre": t.tecnico.nombre if t.tecnico else None,
        "deadline_sla": iso_utc(t.deadline_sla),
        "horas_restantes": sla_service.horas_restantes(t, ahora),
    } for t in sla_service.alertas(db, ahora)]

@router.get("/presupuestos/pendientes")
def presupuestos_pendientes(
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([
        models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO
    ]))
):
    """Presupuestos enviados que el cliente todavía no aprobó ni rechazó, del más viejo al más nuevo."""
    from sqlalchemy.orm import joinedload
    P = models.Presupuesto
    ahora = utcnow()
    filas = (db.query(P).options(joinedload(P.ticket).joinedload(models.Ticket.cliente))
             .filter(P.estado == models.PresupuestoEstado.ENVIADO.value)
             .order_by(P.fecha_actualizacion.asc()).limit(100).all())
    return [{"id": p.ticket_id, "numero_rma": p.ticket.numero_rma, "producto": p.ticket.producto,
             "cliente": p.ticket.cliente.nombre if p.ticket.cliente else None,
             "telefono": p.ticket.cliente.telefono if p.ticket.cliente else None,
             "total": sum(i.cantidad * i.precio_cliente for i in p.items),
             "dias_esperando": max(0, (ahora - p.fecha_actualizacion).days) if p.fecha_actualizacion else 0}
            for p in filas if p.ticket]

@router.get("/retiro/pendientes")
def retiro_pendientes(
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([
        models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO
    ]))
):
    """Equipos listos para retirar, del que más espera al que menos."""
    ahora = utcnow()
    out = []
    for t in retiro_service.pendientes(db):
        i = retiro_service.info(db, t, ahora)
        out.append({"id": t.id, "numero_rma": t.numero_rma, "producto": t.producto,
                    "cliente": t.cliente.nombre if t.cliente else None,
                    "telefono": t.cliente.telefono if t.cliente else None,
                    "listo_desde": iso_utc(i["listo_desde"]), "vence": iso_utc(i["vence"]),
                    "dias_esperando": i["dias_esperando"], "dias_restantes": i["dias_restantes"],
                    "vencido": i["vencido"], "recordatorios": i["recordatorios"]})
    return out

# ── Global search ─────────────────────────────────────────────────────────────
def _parecido(columna, q: str):
    """Contiene `q` sin distinguir mayúsculas (igual en SQLite y en PostgreSQL),
    tomando % y _ como texto y no como comodines."""
    texto = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return columna.ilike(f"%{texto}%", escape="\\")


@router.get("/search/global")
def global_search(
    q: str = Query(..., max_length=200),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.get_current_user)
):
    from sqlalchemy import select
    T, C = models.Ticket, models.Comentario
    es_cliente = current_user.rol == models.UserRole.CLIENTE
    # El cliente no busca dentro de las notas internas (se podría deducir su texto)
    union = T.id == C.ticket_id
    if es_cliente:
        union = union & (C.is_internal == False)  # noqa: E712
    coinciden = (select(T.id).outerjoin(C, union)
                 .where(_parecido(T.numero_rma, q) | _parecido(T.numero_serie, q) | _parecido(T.producto, q)
                        | _parecido(T.descripcion, q) | _parecido(C.comentario, q)))
    if es_cliente:
        coinciden = coinciden.where(T.usuario_id == current_user.id)
    tickets = (con_relaciones(db.query(T)).filter(T.id.in_(coinciden))
               .order_by(T.fecha_creacion.desc(), T.id.desc()).limit(limit).all())
    return [schemas.Ticket.for_viewer(t, current_user) for t in tickets]

# ── List ──────────────────────────────────────────────────────────────────────
@router.get("/", response_model=List[schemas.Ticket])
def list_tickets(
    status: Optional[str] = None,
    tecnico_id: Optional[int] = None,
    usuario_id: Optional[int] = None,
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.get_current_user)
):
    query = con_relaciones(db.query(models.Ticket))
    if current_user.rol == models.UserRole.CLIENTE:
        query = query.filter(models.Ticket.usuario_id == current_user.id)
    if status:     query = query.filter(models.Ticket.estado     == status)
    if tecnico_id: query = query.filter(models.Ticket.tecnico_asignado == tecnico_id)
    if usuario_id: query = query.filter(models.Ticket.usuario_id == usuario_id)
    tickets = query.order_by(models.Ticket.fecha_creacion.desc(), models.Ticket.id.desc()).offset(skip).limit(limit).all()
    return [schemas.Ticket.for_viewer(t, current_user) for t in tickets]

# ── Get single ────────────────────────────────────────────────────────────────
@router.get("/{ticket_id}", response_model=schemas.Ticket)
def get_ticket(
    ticket_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.get_current_user)
):
    ticket = ticket_o_404(db, ticket_id)
    if current_user.rol == models.UserRole.CLIENTE and ticket.usuario_id != current_user.id:
        raise HTTPException(status_code=403, detail="Acceso denegado")
    return schemas.Ticket.for_viewer(ticket, current_user)

# ── Edit core fields (Feature 3) ──────────────────────────────────────────────
@router.patch("/{ticket_id}/fields", response_model=schemas.Ticket)
def edit_ticket_fields(
    ticket_id: int,
    fields: schemas.TicketEditFields,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([
        models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO
    ]))
):
    ticket = ticket_o_404(db, ticket_id)
    data = fields.model_dump(exclude_unset=True)
    changed_labels = []
    for campo, valor_nuevo in data.items():
        valor_anterior = getattr(ticket, campo, None)
        if valor_anterior != valor_nuevo:
            log_event(db, ticket_id, current_user.id,
                      models.EventoHistorial.CAMPO_EDITADO,
                      detalle=f"Campo '{campo}' modificado",
                      campo=campo, val_ant=valor_anterior, val_nuevo=valor_nuevo)
            setattr(ticket, campo, valor_nuevo)
            changed_labels.append(campo)
    ticket.fecha_actualizacion = utcnow()
    if changed_labels:
        notify_ticket_actors(
            db, ticket,
            tipo=models.TipoNotificacion.CAMPO_EDITADO,
            titulo=f"Ticket modificado: {ticket.numero_rma}",
            mensaje=f"{current_user.nombre} modificó: {', '.join(changed_labels)}",
            origen_usuario_id=current_user.id,
        )
    db.commit()
    db.refresh(ticket)
    return schemas.Ticket.from_orm_with_tecnico(ticket, current_user.id)

# ── Update status ────────────────────────────────────────────────────────────
@router.put("/{ticket_id}/status", response_model=schemas.Ticket)
def update_ticket_status(
    ticket_id: int,
    update: schemas.TicketUpdateStatus,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([
        models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO
    ]))
):
    # Los estados se configuran en Administración → Estados (no solo los de fábrica)
    cfgs = {e.valor: e for e in db.query(models.TicketStatusConfig).all()}
    cfg = cfgs.get(update.estado)
    if cfgs:
        if not cfg or not cfg.activo:
            raise HTTPException(status_code=400, detail="Estado inválido o desactivado")
    elif update.estado not in VALID_ESTADOS:
        raise HTTPException(status_code=400, detail="Estado inválido")
    ticket = ticket_o_404(db, ticket_id)
    # Guard: if the status hasn't actually changed, do nothing — no historial, no notification.
    if ticket.estado == update.estado:
        return schemas.Ticket.from_orm_with_tecnico(ticket, current_user.id)
    estado_ant = ticket.estado
    ticket.estado = update.estado
    ticket.fecha_actualizacion = utcnow()
    es_final = cfg.es_final if cfg else update.estado in (models.TicketStatus.CERRADO, models.TicketStatus.CANCELADO)
    if es_final:
        ticket.fecha_cierre = utcnow()
    else:
        ticket.fecha_cierre = None   # reabierto: deja de contar como cerrado (promedios, garantía)
    ticket.deadline_sla = calculate_sla_deadline(update.estado)
    if retiro_service.al_cambiar_estado(db, ticket) and ticket.cliente:
        avisos.notificar(db, [ticket.cliente], models.TipoNotificacion.CAMBIO_ESTADO,
                         f"Listo para retirar: {ticket.numero_rma}",
                         f"Tu {ticket.producto} está listo. {ajustes.politica_retiro(db)}", ticket_id=ticket.id)
    log_event(db, ticket_id, current_user.id,
              models.EventoHistorial.CAMBIO_ESTADO,
              detalle=f"Estado: {estado_ant} → {update.estado}",
              estado_ant=estado_ant, estado_nuevo=update.estado)
    notify_ticket_actors(
        db, ticket,
        tipo=models.TipoNotificacion.CAMBIO_ESTADO,
        titulo=f"Estado actualizado: {ticket.numero_rma}",
        mensaje=f"{current_user.nombre} cambió el estado a «{update.estado}»",
        origen_usuario_id=current_user.id,
    )
    email.cliente_cambio_estado(db, ticket)   # se envía después del commit
    db.commit()
    db.refresh(ticket)
    return schemas.Ticket.from_orm_with_tecnico(ticket, current_user.id)

# ── Assign technician ─────────────────────────────────────────────────────────
@router.put("/{ticket_id}/assign", response_model=schemas.Ticket)
def assign_technician(
    ticket_id: int,
    assignment: schemas.TicketUpdateAssignment,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([
        models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO
    ]))
):
    ticket = ticket_o_404(db, ticket_id)
    if assignment.tecnico_id:
        tech = db.query(models.Usuario).filter(models.Usuario.id == assignment.tecnico_id).first()
        if not tech:
            raise HTTPException(status_code=404, detail="Técnico no encontrado")
        # Solo personal del taller (un cliente asignado recibiría las notas internas)
        if tech.rol not in (models.UserRole.TECNICO, models.UserRole.ADMINISTRADOR) or not tech.activo:
            raise HTTPException(status_code=400, detail="Solo se puede asignar a un técnico o administrador activo")
        tech_nombre = tech.nombre
    else:
        tech_nombre = "Sin asignar"

    ant = ticket.tecnico_asignado
    tecnico_cambio = ant != assignment.tecnico_id   # ← only notify if value actually changed

    ticket.tecnico_asignado = assignment.tecnico_id
    ticket.fecha_actualizacion = utcnow()

    if tecnico_cambio:
        log_event(db, ticket_id, current_user.id,
                  models.EventoHistorial.TECNICO_ASIGNADO,
                  detalle=f"Técnico asignado: {tech_nombre}")
        # Notify the newly assigned technician directly
        if assignment.tecnico_id and assignment.tecnico_id != current_user.id:
            db.add(models.Notificacion(
                usuario_id=assignment.tecnico_id,
                ticket_id=ticket.id,
                tipo=models.TipoNotificacion.ASIGNACION,
                titulo=f"Ticket asignado: {ticket.numero_rma}",
                mensaje=f"{current_user.nombre} te asignó el ticket {ticket.numero_rma} ({ticket.producto})",
                origen_usuario_id=current_user.id,
            ))
        # Notify the ticket owner
        notify_ticket_actors(
            db, ticket,
            tipo=models.TipoNotificacion.ASIGNACION,
            titulo=f"Técnico asignado: {ticket.numero_rma}",
            mensaje=f"Técnico asignado: {tech_nombre}",
            origen_usuario_id=current_user.id,
            extra_recipient_ids=[assignment.tecnico_id],
        )
        if assignment.tecnico_id and assignment.tecnico_id != current_user.id:
            email.tecnico_asignado(db, ticket, assignment.tecnico_id, current_user.nombre)
    db.commit()
    db.refresh(ticket)
    return schemas.Ticket.from_orm_with_tecnico(ticket, current_user.id)

# ── Shipping ──────────────────────────────────────────────────────────────────
@router.put("/{ticket_id}/shipping", response_model=schemas.Ticket)
def update_shipping(
    ticket_id: int,
    shipping: schemas.TicketUpdateShipping,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([
        models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO
    ]))
):
    ticket = ticket_o_404(db, ticket_id)
    ticket.empresa_transporte  = shipping.empresa_transporte
    ticket.tracking_number     = shipping.tracking_number
    ticket.fecha_envio         = to_utc_naive(shipping.fecha_envio) if shipping.fecha_envio else utcnow()
    ticket.fecha_actualizacion = utcnow()
    db.commit()
    db.refresh(ticket)
    return schemas.Ticket.from_orm_with_tecnico(ticket, current_user.id)

# ── Historial (full, Feature 9) ───────────────────────────────────────────────
@router.get("/{ticket_id}/history", response_model=List[schemas.HistorialEntry])
def get_ticket_history(
    ticket_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.get_current_user)
):
    ticket = ticket_o_404(db, ticket_id)
    if current_user.rol == models.UserRole.CLIENTE and ticket.usuario_id != current_user.id:
        raise HTTPException(status_code=403, detail="Acceso denegado")
    query = db.query(models.HistorialEstado).filter_by(ticket_id=ticket_id)
    if current_user.rol == models.UserRole.CLIENTE:
        # Las notas internas se registran en el historial con su texto: no son para el cliente
        query = query.filter(models.HistorialEstado.tipo_evento != models.EventoHistorial.NOTA_INTERNA)
    entries = query.order_by(models.HistorialEstado.fecha.desc()).all()
    return _historial_out(entries)

# ── Diagnostic ───────────────────────────────────────────────────────────────
@router.put("/{ticket_id}/diagnostic", response_model=schemas.Ticket)
def update_diagnostic(
    ticket_id: int,
    data: schemas.TicketDiagnostic,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([
        models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO
    ]))
):
    ticket = ticket_o_404(db, ticket_id)
    old_diag = ticket.diagnostico
    new_diag = data.diagnostico   # obligatorio: antes, sin el campo se borraba el diagnóstico
    if old_diag != new_diag:
        log_event(db, ticket_id, current_user.id, models.EventoHistorial.CAMPO_EDITADO,
                  campo="diagnostico", val_ant=old_diag, val_nuevo=new_diag,
                  detalle="Diagnóstico técnico actualizado")
    ticket.diagnostico = new_diag
    ticket.fecha_actualizacion = utcnow()
    db.commit()
    db.refresh(ticket)
    return schemas.Ticket.from_orm_with_tecnico(ticket, current_user.id)

# ── Clone ticket (Feature 11) ─────────────────────────────────────────────────
@router.post("/{ticket_id}/clone", response_model=schemas.Ticket)
def clone_ticket(
    ticket_id: int,
    payload: schemas.TicketClone,
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([
        models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO
    ]))
):
    orig = ticket_o_404(db, ticket_id)

    # Por el alta normal: N° de RMA, SLA, garantía (de compra y de reparación),
    # prioridad automática y auditoría, igual que cualquier ticket nuevo
    datos = schemas.TicketCreate(
        producto_id=orig.producto_id, producto=orig.producto, numero_serie=orig.numero_serie or "",
        fecha_compra=orig.fecha_compra, descripcion=orig.descripcion or "",
        prioridad=orig.prioridad if orig.prioridad in schemas.PRIORIDADES else "Normal")
    clone = process_ticket_creation(db, datos, current_user, ip_address=request.client.host if request.client else None,
                                    cliente=orig.cliente,
                                    detalle_alta=f"Ticket creado como clon de {orig.numero_rma} por {current_user.nombre}")
    clone.clonado_de = orig.id
    if payload.relacionar and not clone.ticket_relacionado:
        clone.ticket_relacionado = orig.id
    for t in orig.tags:
        clone.tags.append(t)

    log_event(db, clone.id, current_user.id, models.EventoHistorial.TICKET_CLONADO,
              detalle=f"Clonado de {orig.numero_rma}")
    log_event(db, orig.id, current_user.id, models.EventoHistorial.TICKET_RELACIONADO,
              detalle=f"Clonado como {clone.numero_rma}")
    db.commit()
    db.refresh(clone)
    return schemas.Ticket.from_orm_with_tecnico(clone, current_user.id)

# ── Set/remove relation (Feature 11) ─────────────────────────────────────────
@router.patch("/{ticket_id}/relation", response_model=schemas.Ticket)
def set_ticket_relation(
    ticket_id: int,
    payload: schemas.TicketSetRelacion,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([
        models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO
    ]))
):
    ticket = ticket_o_404(db, ticket_id)
    nuevo = None
    if payload.ticket_relacionado_id is not None:
        nuevo = ticket_o_404(db, payload.ticket_relacionado_id)
        if nuevo.id == ticket.id:
            raise HTTPException(status_code=400, detail="Un ticket no se puede relacionar consigo mismo")
    anterior = ticket.relacionado
    ticket.ticket_relacionado = payload.ticket_relacionado_id
    tipo = models.EventoHistorial.TICKET_DESASOCIADO if nuevo is None else models.EventoHistorial.TICKET_RELACIONADO
    log_event(db, ticket_id, current_user.id, tipo,
              detalle=(f"Relacionado con {nuevo.numero_rma}" if nuevo
                       else f"Ya no está relacionado con {anterior.numero_rma}" if anterior else "Relación quitada"))
    db.commit()
    db.refresh(ticket)
    return schemas.Ticket.from_orm_with_tecnico(ticket, current_user.id)
