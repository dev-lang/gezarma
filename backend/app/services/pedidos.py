"""
pedidos.py — Pedidos de repuestos a proveedores.

- Sugeridos: los repuestos en o bajo su stock mínimo, agrupados por proveedor,
  descontando lo que ya está pedido y sin recibir. La cantidad sugerida lleva
  el stock al doble del mínimo.
- Al recibir (todo o una parte), se suma al stock con un movimiento de
  reposición que dice de qué pedido viene.
"""
import csv
import io

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..timeutils import utcnow
from . import stock_service

ABIERTOS = ("borrador", "enviado", "parcial")


def pendiente_de(item: models.PedidoItem) -> int:
    return max(0, item.cantidad - item.recibido)


def en_pedido(db: Session) -> dict:
    """repuesto_id → unidades pedidas que todavía no llegaron."""
    out = {}
    items = (db.query(models.PedidoItem).join(models.PedidoProveedor)
             .filter(models.PedidoProveedor.estado.in_(ABIERTOS)).all())
    for i in items:
        out[i.repuesto_id] = out.get(i.repuesto_id, 0) + pendiente_de(i)
    return out


def sugeridos(db: Session) -> list:
    pedidos = en_pedido(db)
    grupos = {}
    for r in stock_service.alertas(db):
        objetivo = max(r.stock_minimo * 2, 1)
        falta = objetivo - r.stock - pedidos.get(r.id, 0)
        if falta <= 0:
            continue
        proveedor = (r.proveedor or "").strip() or "Sin proveedor"
        grupos.setdefault(proveedor, []).append({
            "repuesto_id": r.id, "nombre": r.nombre, "codigo": r.codigo, "stock": r.stock,
            "stock_minimo": r.stock_minimo, "en_pedido": pedidos.get(r.id, 0), "cantidad": falta, "precio": r.precio})
    return [{"proveedor": p, "items": its} for p, its in sorted(grupos.items())]


def _repuesto(db: Session, repuesto_id: int) -> models.Repuesto:
    r = db.query(models.Repuesto).filter_by(id=repuesto_id).first()
    if not r:
        raise HTTPException(status_code=400, detail=f"Repuesto {repuesto_id} inexistente")
    return r


def cargar_items(db: Session, pedido: models.PedidoProveedor, items: list) -> None:
    """Reemplaza los ítems (solo en borrador). items: [{repuesto_id, cantidad}]"""
    vistos = set()
    pedido.items.clear()
    for it in items:
        if it["cantidad"] <= 0:
            raise HTTPException(status_code=400, detail="Las cantidades tienen que ser mayores a 0")
        if it["repuesto_id"] in vistos:
            raise HTTPException(status_code=400, detail="Hay un repuesto repetido en el pedido")
        vistos.add(it["repuesto_id"])
        r = _repuesto(db, it["repuesto_id"])
        pedido.items.append(models.PedidoItem(repuesto_id=r.id, cantidad=it["cantidad"], precio=r.precio))
    if not pedido.items:
        raise HTTPException(status_code=400, detail="El pedido no tiene repuestos")


def crear(db: Session, proveedor: str, items: list, notas: str, usuario: models.Usuario) -> models.PedidoProveedor:
    proveedor = (proveedor or "").strip()
    if not proveedor:
        raise HTTPException(status_code=400, detail="Falta el proveedor")
    p = models.PedidoProveedor(proveedor=proveedor, notas=(notas or "").strip() or None, creado_por=usuario.id)
    db.add(p)
    cargar_items(db, p, items)
    return p


def recibir(db: Session, pedido: models.PedidoProveedor, cantidades: dict, usuario: models.Usuario) -> int:
    """cantidades: item_id → unidades que llegaron. Devuelve el total recibido."""
    if pedido.estado not in ("enviado", "parcial"):
        raise HTTPException(status_code=400, detail="Solo se recibe un pedido enviado")
    por_id = {i.id: i for i in pedido.items}
    total = 0
    for item_id, cant in cantidades.items():
        item = por_id.get(item_id)
        if not item:
            raise HTTPException(status_code=400, detail=f"El ítem {item_id} no es de este pedido")
        if cant < 0 or cant > pendiente_de(item):
            raise HTTPException(status_code=400,
                                detail=f"{item.repuesto.nombre}: se pueden recibir hasta {pendiente_de(item)} unidades")
        if not cant:
            continue
        r = item.repuesto
        anterior, nuevo = stock_service.ajustar(db, r, cant)
        item.recibido += cant
        db.add(models.StockMovimiento(repuesto_id=r.id, usuario_id=usuario.id, tipo="reposicion", cantidad=cant,
                                      stock_anterior=anterior, stock_nuevo=nuevo, pedido_item_id=item.id,
                                      nota=f"Pedido N° {pedido.id} a {pedido.proveedor}"))
        total += cant
    if not total:
        raise HTTPException(status_code=400, detail="No se cargó ninguna cantidad recibida")
    completo = all(pendiente_de(i) == 0 for i in pedido.items)
    pedido.estado = "recibido" if completo else "parcial"
    if completo:
        pedido.fecha_recepcion = utcnow()
    return total


def csv_de(pedido: models.PedidoProveedor) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Código", "Repuesto", "Cantidad"])
    for i in pedido.items:
        w.writerow([i.repuesto.codigo, i.repuesto.nombre, i.cantidad])
    return ("﻿" + buf.getvalue()).encode("utf-8")   # BOM: Excel lo abre con los acentos bien
