"""
budget.py — Presupuesto management for tickets.
  /budget/tickets/{ticket_id}/presupuesto   — CRUD for a ticket's budget
  /budget/tickets/{ticket_id}/presupuesto/estado — state transitions
  /budget/plantillas                         — admin budget item templates
  /budget/stats/financiero                   — financial statistics
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from typing import List, Optional
from datetime import datetime
import json

from .. import database, models, schemas, auth
from ..services.ticket_service import log_event, notify_ticket_actors
from ..services import stock_service, email
from ..timeutils import utcnow, utc_to_local

router = APIRouter(prefix="/budget", tags=["budget"])

# ── Helpers ───────────────────────────────────────────────────────────────────

def _snapshot_items(items) -> list:
    return [
        {
            "descripcion":    i.descripcion,
            "cantidad":       i.cantidad,
            "costo_interno":  i.costo_interno,
            "precio_cliente": i.precio_cliente,
            "costo_total":    i.cantidad * i.costo_interno,
            "precio_total":   i.cantidad * i.precio_cliente,
            "repuesto_id":    i.repuesto_id,
        }
        for i in items
    ]

def _presupuesto_out(p: models.Presupuesto, user: models.Usuario) -> schemas.PresupuestoOut:
    """Serialize a budget. Clients never receive internal cost, profit or version history."""
    interno = user.rol != models.UserRole.CLIENTE
    items_out = [
        schemas.PresupuestoItemOut(
            id=i.id,
            descripcion=i.descripcion,
            cantidad=i.cantidad,
            costo_interno=i.costo_interno if interno else None,
            precio_cliente=i.precio_cliente,
            costo_total=i.cantidad * i.costo_interno if interno else None,
            precio_total=i.cantidad * i.precio_cliente,
            repuesto_id=i.repuesto_id,
            repuesto_codigo=(i.repuesto.codigo if i.repuesto else None) if interno else None,
            stock_disponible=(i.repuesto.stock if i.repuesto else None) if interno else None,
        )
        for i in p.items
    ]
    versiones_out = [
        schemas.PresupuestoVersionOut(
            id=v.id,
            version=v.version,
            estado=v.estado,
            notas=v.notas,
            items_snapshot=v.items_snapshot,
            usuario_nombre=v.usuario.nombre if v.usuario else None,
            fecha=v.fecha,
        )
        for v in p.versiones
    ] if interno else []
    return schemas.PresupuestoOut(
        id=p.id,
        ticket_id=p.ticket_id,
        estado=p.estado,
        version=p.version,
        notas=p.notas,
        items=items_out,
        costo_total=p.costo_total if interno else None,
        precio_total=p.precio_total,
        ganancia=p.ganancia if interno else None,
        versiones=versiones_out,
        creador_nombre=p.creador.nombre if p.creador else None,
        fecha_creacion=p.fecha_creacion,
        fecha_actualizacion=p.fecha_actualizacion,
    )

def _save_version(db: Session, presupuesto: models.Presupuesto, usuario_id: int):
    """Snapshot the current state of a presupuesto before modifying it."""
    version = models.PresupuestoVersion(
        presupuesto_id=presupuesto.id,
        version=presupuesto.version,
        estado=presupuesto.estado,
        notas=presupuesto.notas,
        items_snapshot=_snapshot_items(presupuesto.items),
        usuario_id=usuario_id,
    )
    db.add(version)

VALID_ESTADOS = {e.value for e in models.PresupuestoEstado}

# Valid state transitions
TRANSITIONS = {
    models.PresupuestoEstado.BORRADOR:  [models.PresupuestoEstado.ENVIADO],
    models.PresupuestoEstado.ENVIADO:   [models.PresupuestoEstado.APROBADO, models.PresupuestoEstado.RECHAZADO, models.PresupuestoEstado.BORRADOR],
    models.PresupuestoEstado.APROBADO:  [],
    models.PresupuestoEstado.RECHAZADO: [models.PresupuestoEstado.BORRADOR],
}

# ── Ítems vinculados a repuestos ─────────────────────────────────────────────

def _crear_items(db: Session, presupuesto: models.Presupuesto, items) -> None:
    for item in items:
        data = item.model_dump()
        if data.get("repuesto_id"):
            rep = db.query(models.Repuesto).filter_by(id=data["repuesto_id"]).first()
            if not rep:
                raise HTTPException(400, f"Repuesto inexistente (id {data['repuesto_id']})")
            if data["cantidad"] < 1 or float(data["cantidad"]) != int(data["cantidad"]):
                raise HTTPException(400, f"La cantidad de «{rep.nombre}» debe ser un número entero mayor a 0")
            data["descripcion"] = data["descripcion"] or rep.nombre
        elif not (data.get("descripcion") or "").strip():
            raise HTTPException(400, "Cada ítem necesita una descripción")
        db.add(models.PresupuestoItem(presupuesto_id=presupuesto.id, **data))


def _descontar_repuestos(db: Session, ticket: models.Ticket, presupuesto: models.Presupuesto,
                         usuario_id: int) -> None:
    """Al aprobarse: los ítems vinculados a repuestos se agregan al ticket y se
    descuentan del stock. Si no alcanza, el stock queda negativo y se avisa
    (no se le rechaza la aprobación al cliente)."""
    for item in presupuesto.items:
        if item.repuesto_id and item.repuesto:
            stock_service.agregar_al_ticket(
                db, ticket, item.repuesto, int(item.cantidad), usuario_id, permitir_negativo=True,
                nota=f"Presupuesto aprobado ({ticket.numero_rma})")


# ── Ticket Presupuesto CRUD ───────────────────────────────────────────────────

@router.get("/tickets/{ticket_id}/presupuesto", response_model=schemas.PresupuestoOut)
def get_presupuesto(
    ticket_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.get_current_user),
):
    ticket = db.query(models.Ticket).filter_by(id=ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Ticket no encontrado")

    # Clients can only see their own tickets
    if current_user.rol == models.UserRole.CLIENTE and ticket.usuario_id != current_user.id:
        raise HTTPException(403, "Sin acceso")

    if not ticket.presupuesto:
        raise HTTPException(404, "Este ticket no tiene presupuesto")
    # El borrador es del taller: el cliente lo ve recién cuando se lo envían
    if current_user.rol == models.UserRole.CLIENTE and ticket.presupuesto.estado == models.PresupuestoEstado.BORRADOR:
        raise HTTPException(404, "Este ticket no tiene presupuesto")

    return _presupuesto_out(ticket.presupuesto, current_user)


@router.post("/tickets/{ticket_id}/presupuesto", response_model=schemas.PresupuestoOut)
def create_presupuesto(
    ticket_id: int,
    body: schemas.PresupuestoCreate,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(
        auth.check_role([models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO])
    ),
):
    ticket = db.query(models.Ticket).filter_by(id=ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Ticket no encontrado")
    if ticket.presupuesto:
        raise HTTPException(400, "El ticket ya tiene un presupuesto. Usá PATCH para modificarlo.")

    presupuesto = models.Presupuesto(
        ticket_id=ticket_id,
        estado=models.PresupuestoEstado.BORRADOR,
        version=1,
        notas=body.notas,
        creado_por=current_user.id,
        actualizado_por=current_user.id,
    )
    db.add(presupuesto)
    db.flush()  # get ID

    _crear_items(db, presupuesto, body.items)

    log_event(db, ticket_id, current_user.id, "presupuesto_creado", "Presupuesto creado")
    db.commit()
    db.refresh(presupuesto)
    return _presupuesto_out(presupuesto, current_user)


@router.patch("/tickets/{ticket_id}/presupuesto", response_model=schemas.PresupuestoOut)
def update_presupuesto(
    ticket_id: int,
    body: schemas.PresupuestoUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(
        auth.check_role([models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO])
    ),
):
    ticket = db.query(models.Ticket).filter_by(id=ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Ticket no encontrado")
    presupuesto = ticket.presupuesto
    if not presupuesto:
        raise HTTPException(404, "No hay presupuesto para este ticket")

    # Only draft/sent can be edited
    if presupuesto.estado == models.PresupuestoEstado.APROBADO:
        raise HTTPException(400, "No se puede modificar un presupuesto aprobado")

    # Save version snapshot before changes
    _save_version(db, presupuesto, current_user.id)
    presupuesto.version += 1

    if body.notas is not None:
        presupuesto.notas = body.notas

    if body.items is not None:
        # Delete old items and replace
        for item in list(presupuesto.items):
            db.delete(item)
        db.flush()
        _crear_items(db, presupuesto, body.items)

    presupuesto.actualizado_por = current_user.id
    presupuesto.fecha_actualizacion = utcnow()

    # If it was sent and is being edited, revert to draft
    if presupuesto.estado == models.PresupuestoEstado.ENVIADO:
        presupuesto.estado = models.PresupuestoEstado.BORRADOR

    log_event(db, ticket_id, current_user.id, "presupuesto_modificado", f"Presupuesto actualizado a versión {presupuesto.version}")
    db.commit()
    db.refresh(presupuesto)
    return _presupuesto_out(presupuesto, current_user)


@router.delete("/tickets/{ticket_id}/presupuesto", status_code=204)
def delete_presupuesto(
    ticket_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(
        auth.check_role([models.UserRole.ADMINISTRADOR])
    ),
):
    ticket = db.query(models.Ticket).filter_by(id=ticket_id).first()
    if not ticket or not ticket.presupuesto:
        raise HTTPException(404, "Presupuesto no encontrado")
    if ticket.presupuesto.estado == models.PresupuestoEstado.APROBADO:
        raise HTTPException(400, "No se puede eliminar un presupuesto aprobado")
    db.delete(ticket.presupuesto)
    db.commit()


@router.patch("/tickets/{ticket_id}/presupuesto/estado", response_model=schemas.PresupuestoOut)
def update_estado_presupuesto(
    ticket_id: int,
    body: schemas.PresupuestoEstadoUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.get_current_user),
):
    if body.estado not in VALID_ESTADOS:
        raise HTTPException(400, f"Estado inválido: {body.estado}")

    ticket = db.query(models.Ticket).filter_by(id=ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Ticket no encontrado")
    if current_user.rol == models.UserRole.CLIENTE and ticket.usuario_id != current_user.id:
        raise HTTPException(403, "Sin acceso")

    presupuesto = ticket.presupuesto
    if not presupuesto:
        raise HTTPException(404, "No hay presupuesto para este ticket")

    nuevo = body.estado
    actual = presupuesto.estado

    allowed = [t.value for t in TRANSITIONS.get(actual, [])]
    if nuevo not in allowed:
        raise HTTPException(400, f"Transición no permitida: {actual} → {nuevo}")

    # Clients can only approve/reject; tecnico/admin can do any valid transition
    # (tecnico can also approve/reject for workflow flexibility).
    if current_user.rol == models.UserRole.CLIENTE and nuevo not in (
        models.PresupuestoEstado.APROBADO, models.PresupuestoEstado.RECHAZADO
    ):
        raise HTTPException(403, "El cliente solo puede aprobar o rechazar el presupuesto")

    _save_version(db, presupuesto, current_user.id)
    presupuesto.version += 1
    presupuesto.estado = nuevo
    presupuesto.actualizado_por = current_user.id
    presupuesto.fecha_actualizacion = utcnow()

    log_event(db, ticket_id, current_user.id, "presupuesto_estado", f"Presupuesto: {actual} → {nuevo}")
    if nuevo == models.PresupuestoEstado.APROBADO:
        _descontar_repuestos(db, ticket, presupuesto, current_user.id)
    if nuevo == models.PresupuestoEstado.ENVIADO:
        email.cliente_presupuesto(db, ticket)   # se envía después del commit
    estado_labels = {
        "enviado":   "enviado al cliente para aprobación",
        "aprobado":  "aprobado ✓",
        "rechazado": "rechazado",
        "borrador":  "devuelto a borrador",
    }
    notify_ticket_actors(
        db, ticket,
        tipo=models.TipoNotificacion.PRESUPUESTO,
        titulo=f"Presupuesto {estado_labels.get(nuevo, nuevo)}: {ticket.numero_rma}",
        mensaje=f"{current_user.nombre} cambió el presupuesto a «{nuevo}»",
        origen_usuario_id=current_user.id,
    )
    db.commit()
    db.refresh(presupuesto)
    return _presupuesto_out(presupuesto, current_user)


@router.get("/tickets/{ticket_id}/presupuesto/versiones",
            response_model=List[schemas.PresupuestoVersionOut])
def get_versiones(
    ticket_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(
        auth.check_role([models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO])
    ),
):
    ticket = db.query(models.Ticket).filter_by(id=ticket_id).first()
    if not ticket or not ticket.presupuesto:
        raise HTTPException(404, "Presupuesto no encontrado")
    versiones = (
        db.query(models.PresupuestoVersion)
        .filter_by(presupuesto_id=ticket.presupuesto.id)
        .order_by(models.PresupuestoVersion.id.desc())
        .all()
    )
    return [
        schemas.PresupuestoVersionOut(
            id=v.id, version=v.version, estado=v.estado, notas=v.notas,
            items_snapshot=v.items_snapshot,
            usuario_nombre=v.usuario.nombre if v.usuario else None,
            fecha=v.fecha,
        )
        for v in versiones
    ]


# ── Budget Item Templates (Admin) ─────────────────────────────────────────────

@router.get("/plantillas", response_model=List[schemas.PlantillaPresupuestoOut])
def list_plantillas(
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(
        auth.check_role([models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO])
    ),
):
    plantillas = (
        db.query(models.PlantillaPresupuesto)
        .order_by(models.PlantillaPresupuesto.orden, models.PlantillaPresupuesto.id)
        .all()
    )
    return [schemas.PlantillaPresupuestoOut.de(p) for p in plantillas]


def _validar_producto(db: Session, producto_id):
    if producto_id is not None and not db.query(models.Producto).filter_by(id=producto_id).first():
        raise HTTPException(400, "El producto elegido no existe")


@router.post("/plantillas", response_model=schemas.PlantillaPresupuestoOut)
def create_plantilla(
    body: schemas.PlantillaPresupuestoCreate,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(
        auth.check_role([models.UserRole.ADMINISTRADOR])
    ),
):
    if db.query(models.PlantillaPresupuesto).filter_by(nombre=body.nombre).first():
        raise HTTPException(400, "Ya existe una plantilla con ese nombre")
    _validar_producto(db, body.producto_id)
    obj = models.PlantillaPresupuesto(**body.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return schemas.PlantillaPresupuestoOut.de(obj)


@router.patch("/plantillas/{pid}", response_model=schemas.PlantillaPresupuestoOut)
def update_plantilla(
    pid: int,
    body: schemas.PlantillaPresupuestoCreate,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(
        auth.check_role([models.UserRole.ADMINISTRADOR])
    ),
):
    obj = db.query(models.PlantillaPresupuesto).filter_by(id=pid).first()
    if not obj:
        raise HTTPException(404, "Plantilla no encontrada")
    conflict = db.query(models.PlantillaPresupuesto).filter(
        models.PlantillaPresupuesto.nombre == body.nombre,
        models.PlantillaPresupuesto.id != pid,
    ).first()
    if conflict:
        raise HTTPException(400, "Ya existe otra plantilla con ese nombre")
    _validar_producto(db, body.producto_id)
    for k, v in body.model_dump().items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return schemas.PlantillaPresupuestoOut.de(obj)


@router.delete("/plantillas/{pid}", status_code=204)
def delete_plantilla(
    pid: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(
        auth.check_role([models.UserRole.ADMINISTRADOR])
    ),
):
    obj = db.query(models.PlantillaPresupuesto).filter_by(id=pid).first()
    if not obj:
        raise HTTPException(404, "Plantilla no encontrada")
    db.delete(obj)
    db.commit()


# ── Financial Statistics ──────────────────────────────────────────────────────

@router.get("/stats/financiero", response_model=schemas.FinancialStats)
def get_financial_stats(
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(
        auth.check_role([models.UserRole.ADMINISTRADOR])
    ),
):
    # Get presupuestos aprobados linked to closed tickets
    presupuestos = (
        db.query(models.Presupuesto)
        .join(models.Ticket, models.Presupuesto.ticket_id == models.Ticket.id)
        .filter(
            models.Presupuesto.estado == models.PresupuestoEstado.APROBADO,
        )
        .all()
    )

    total_ganancia = 0.0
    total_costo = 0.0
    total_ingreso = 0.0
    ganancias_por_mes: dict = {}
    ingresos_por_mes: dict = {}
    costos_por_mes: dict = {}

    for p in presupuestos:
        g = p.ganancia
        c = p.costo_total
        i = p.precio_total
        total_ganancia += g
        total_costo += c
        total_ingreso += i

        mes_key = utc_to_local(p.fecha_actualizacion).strftime("%Y-%m")
        ganancias_por_mes[mes_key] = ganancias_por_mes.get(mes_key, 0.0) + g
        ingresos_por_mes[mes_key] = ingresos_por_mes.get(mes_key, 0.0) + i
        costos_por_mes[mes_key] = costos_por_mes.get(mes_key, 0.0) + c

    n = len(presupuestos) or 1
    margen = (total_ganancia / total_ingreso * 100) if total_ingreso else 0.0

    return schemas.FinancialStats(
        ganancia_total=round(total_ganancia, 2),
        costo_total=round(total_costo, 2),
        ingreso_total=round(total_ingreso, 2),
        margen_promedio=round(margen, 2),
        ganancia_promedio_ticket=round(total_ganancia / n, 2),
        costo_promedio_ticket=round(total_costo / n, 2),
        tickets_con_presupuesto=len(presupuestos),
        ganancias_por_mes={k: round(v, 2) for k, v in sorted(ganancias_por_mes.items())},
        ingresos_por_mes={k: round(v, 2) for k, v in sorted(ingresos_por_mes.items())},
        costos_por_mes={k: round(v, 2) for k, v in sorted(costos_por_mes.items())},
    )
