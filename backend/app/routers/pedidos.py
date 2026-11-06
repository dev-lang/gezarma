"""
pedidos.py — Pedidos de repuestos a proveedores (solo administradores).
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import ajustes, auth, database, models
from ..services import documentos, email, pedidos
from ..timeutils import iso_utc, utc_to_local, utcnow

router = APIRouter(prefix="/pedidos", tags=["pedidos"])
ADMIN = auth.check_role([models.UserRole.ADMINISTRADOR])


class ItemIn(BaseModel):
    repuesto_id: int
    cantidad:    int


class PedidoIn(BaseModel):
    proveedor: str = Field(..., max_length=120)
    notas:     str = Field("", max_length=1000)
    items:     List[ItemIn]


class DesdeSugeridosIn(BaseModel):
    proveedores: Optional[List[str]] = None   # None = todos


class EnviarIn(BaseModel):
    email: str = ""   # si se carga, se le manda el pedido (PDF + CSV) al proveedor


class RecepcionItem(BaseModel):
    item_id:  int
    cantidad: int


class RecibirIn(BaseModel):
    items: List[RecepcionItem]


def _out(p: models.PedidoProveedor) -> dict:
    return {
        "id": p.id, "proveedor": p.proveedor, "estado": p.estado, "notas": p.notas,
        "fecha_creacion": iso_utc(p.fecha_creacion), "fecha_envio": iso_utc(p.fecha_envio) if p.fecha_envio else None,
        "fecha_recepcion": iso_utc(p.fecha_recepcion) if p.fecha_recepcion else None,
        "creado_por": p.usuario.nombre if p.usuario else None,
        "items": [{"id": i.id, "repuesto_id": i.repuesto_id, "nombre": i.repuesto.nombre, "codigo": i.repuesto.codigo,
                   "stock": i.repuesto.stock, "cantidad": i.cantidad, "recibido": i.recibido,
                   "pendiente": pedidos.pendiente_de(i), "precio": i.precio} for i in p.items],
        "unidades": sum(i.cantidad for i in p.items),
        "costo_estimado": round(sum(i.cantidad * (i.precio or 0) for i in p.items), 2),
    }


def _pedido(db: Session, pedido_id: int) -> models.PedidoProveedor:
    p = db.query(models.PedidoProveedor).filter_by(id=pedido_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return p


@router.get("/sugeridos")
def sugeridos(db: Session = Depends(database.get_db), _: models.Usuario = Depends(ADMIN)):
    return pedidos.sugeridos(db)


@router.post("/desde-sugeridos")
def desde_sugeridos(data: DesdeSugeridosIn, db: Session = Depends(database.get_db), u: models.Usuario = Depends(ADMIN)):
    """Un borrador por proveedor con los repuestos sugeridos."""
    creados = []
    for g in pedidos.sugeridos(db):
        if data.proveedores is not None and g["proveedor"] not in data.proveedores:
            continue
        creados.append(pedidos.crear(db, g["proveedor"], g["items"], "", u))
    if not creados:
        raise HTTPException(status_code=400, detail="No hay repuestos para pedir")
    db.commit()
    return [_out(p) for p in creados]


@router.get("/")
def listar(estado: Optional[str] = Query(None), db: Session = Depends(database.get_db), _: models.Usuario = Depends(ADMIN)):
    q = db.query(models.PedidoProveedor)
    if estado == "abiertos":
        q = q.filter(models.PedidoProveedor.estado.in_(pedidos.ABIERTOS))
    elif estado:
        q = q.filter(models.PedidoProveedor.estado == estado)
    return [_out(p) for p in q.order_by(models.PedidoProveedor.id.desc()).limit(200).all()]


@router.post("/")
def crear(data: PedidoIn, db: Session = Depends(database.get_db), u: models.Usuario = Depends(ADMIN)):
    p = pedidos.crear(db, data.proveedor, [i.model_dump() for i in data.items], data.notas, u)
    db.commit()
    return _out(p)


@router.get("/{pedido_id}")
def ver(pedido_id: int, db: Session = Depends(database.get_db), _: models.Usuario = Depends(ADMIN)):
    return _out(_pedido(db, pedido_id))


@router.put("/{pedido_id}")
def editar(pedido_id: int, data: PedidoIn, db: Session = Depends(database.get_db), _: models.Usuario = Depends(ADMIN)):
    p = _pedido(db, pedido_id)
    if p.estado != "borrador":
        raise HTTPException(status_code=400, detail="Solo se edita un pedido en borrador")
    if not data.proveedor.strip():
        raise HTTPException(status_code=400, detail="Falta el proveedor")
    p.proveedor, p.notas = data.proveedor.strip(), data.notas.strip() or None
    pedidos.cargar_items(db, p, [i.model_dump() for i in data.items])
    db.commit()
    return _out(p)


def _html(db: Session, p: models.PedidoProveedor, imprimir: bool) -> str:
    ctx = {"empresa": ajustes.get(db, "empresa_nombre") or "GEZARMA",
           "empresa_datos": [l for l in (ajustes.get(db, "empresa_datos") or "").splitlines() if l.strip()],
           "t": {"numero_rma": f"Pedido N° {p.id:05d}"}, "hoy": utc_to_local(utcnow()).strftime("%d/%m/%Y %H:%M"),
           "pedido": p, "fecha": utc_to_local(p.fecha_envio or p.fecha_creacion).strftime("%d/%m/%Y")}
    return documentos._env.get_template("pedido.html").render(**ctx, titulo="Pedido de repuestos", imprimir=imprimir)


@router.get("/{pedido_id}/pdf")
def pdf(pedido_id: int, formato: Optional[str] = Query(None, pattern="^(pdf|html)$"),
        db: Session = Depends(database.get_db), _: models.Usuario = Depends(ADMIN)):
    p = _pedido(db, pedido_id)
    if (formato or ("pdf" if ajustes.get(db, "pdf_modo") == "servidor" else "html")) == "html":
        return HTMLResponse(_html(db, p, True))
    return Response(documentos.render_pdf(_html(db, p, False)), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="pedido-{p.id:05d}.pdf"'})


@router.get("/{pedido_id}/csv")
def csv(pedido_id: int, db: Session = Depends(database.get_db), _: models.Usuario = Depends(ADMIN)):
    p = _pedido(db, pedido_id)
    return Response(pedidos.csv_de(p), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="pedido-{p.id:05d}.csv"'})


@router.post("/{pedido_id}/enviar")
def enviar(pedido_id: int, data: EnviarIn, db: Session = Depends(database.get_db), u: models.Usuario = Depends(ADMIN)):
    """Marca el pedido como enviado. Con un email, se lo manda al proveedor (y si falla, no se marca)."""
    p = _pedido(db, pedido_id)
    if p.estado != "borrador":
        raise HTTPException(status_code=400, detail="El pedido ya fue enviado")
    p.fecha_envio = utcnow()
    destino = data.email.strip()
    if destino:
        if "@" not in destino:
            raise HTTPException(status_code=400, detail="Email inválido")
        if not ajustes.get(db, "email_activo"):
            raise HTTPException(status_code=400, detail="El envío de emails está desactivado (Ajustes → Email).")
        empresa = ajustes.get(db, "empresa_nombre") or "GEZARMA"
        try:
            email.enviar(db, [destino], f"Pedido de repuestos N° {p.id:05d} — {empresa}", "Pedido de repuestos",
                         [f"Hola {p.proveedor},",
                          f"Les enviamos el pedido N° {p.id:05d} ({sum(i.cantidad for i in p.items)} unidades). "
                          "Va adjunto en PDF y en CSV.",
                          *( [f"Notas: {p.notas}"] if p.notas else [] ),
                          "Por favor, confirmen disponibilidad y plazo de entrega. ¡Gracias!"],
                         adjuntos=[(f"pedido-{p.id:05d}.pdf", documentos.render_pdf(_html(db, p, False)), "application/pdf"),
                                   (f"pedido-{p.id:05d}.csv", pedidos.csv_de(p), "text/csv")])
        except email.ErrorEmail as e:
            db.rollback()
            raise HTTPException(status_code=400, detail=f"No se pudo mandar el mail: {e}")
    p.estado = "enviado"
    db.commit()
    return _out(p)


@router.post("/{pedido_id}/recibir")
def recibir(pedido_id: int, data: RecibirIn, db: Session = Depends(database.get_db), u: models.Usuario = Depends(ADMIN)):
    """Registra lo que llegó (todo o una parte) y lo suma al stock."""
    p = _pedido(db, pedido_id)
    pedidos.recibir(db, p, {i.item_id: i.cantidad for i in data.items}, u)
    db.commit()
    return _out(p)


@router.post("/{pedido_id}/cancelar")
def cancelar(pedido_id: int, db: Session = Depends(database.get_db), _: models.Usuario = Depends(ADMIN)):
    """Cancela el pedido (lo ya recibido queda en el stock)."""
    p = _pedido(db, pedido_id)
    if p.estado in ("recibido", "cancelado"):
        raise HTTPException(status_code=400, detail=f"El pedido ya está {p.estado}")
    p.estado = "cancelado"
    db.commit()
    return _out(p)
