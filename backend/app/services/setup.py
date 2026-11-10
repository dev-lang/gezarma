"""
setup.py — Configuración inicial del taller (asistente de primer uso).

- estado(db, admin): qué pasos se hicieron, si está terminado o se dejó para
  después, y si se pueden cargar o borrar los datos de ejemplo.
- aplicar_rubros(db, ids, quitar_ejemplos): suma lo típico de cada rubro
  (estados, checklist, categorías, plantillas, plazos de SLA). Se puede
  aplicar dos veces: no duplica nada ni pisa lo que el taller ya cambió.
- crear_demo / borrar_demo: datos de ejemplo marcados con `demo` (clientes,
  productos, repuestos, una ubicación y tickets en distintos estados). Solo
  se ofrecen mientras no haya tickets reales; al borrarlos, lo de ejemplo que
  el taller usó en algo real se conserva (deja de ser "de ejemplo").
Los demás pasos (datos del taller, cuenta, técnicos, impresión, mail) usan los
endpoints de siempre.
"""
import os
import secrets
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import ajustes, auth, models, schemas
from ..timeutils import now_local, utcnow
from . import rubros as R

PASOS = ("taller", "cuenta", "rubro", "equipo", "catalogo", "impresion", "avisos")

# Lo que trae una instalación nueva y no es del taller (main.seed_data)
PRODUCTOS_SEMILLA = {("ASUS", "X515 Laptop"), ("Logitech", "G502 Hero"), ("Samsung", "Odyssey G5")}
REPUESTOS_SEMILLA = {"LCD-156-01", "BAT-AS-515"}


def _lista(clave: str, db: Session) -> list:
    return [x.strip() for x in (ajustes.get(db, clave) or "").split(",") if x.strip()]


def _lineas(texto: str) -> list:
    return [l.strip() for l in (texto or "").splitlines() if l.strip()]


def hay_tickets_reales(db: Session) -> bool:
    return db.query(models.Ticket.id).filter(models.Ticket.demo.is_(False)).first() is not None


def estado(db: Session, admin: models.Usuario) -> dict:
    demo = db.query(models.Ticket.id).filter(models.Ticket.demo.is_(True)).count()
    reales = hay_tickets_reales(db)
    ids = R.validar(_lista("setup_rubros", db))
    return {
        "terminado": bool(ajustes.get(db, "setup_terminado")),
        "pospuesto": bool(ajustes.get(db, "setup_pospuesto")),
        "pasos": [p for p in _lista("setup_pasos", db) if p in PASOS],
        "rubros": ids,
        "etiqueta_sugerida": R.combinar(ids)["etiqueta"] if ids else None,
        "demo": {"tickets": demo, "puede_crear": not reales and not demo, "puede_borrar": demo > 0},
        "hay_tickets_reales": reales,
        "ejemplos_de_fabrica": _ejemplos_libres(db),
        "admin_clave_por_defecto": bool(admin.must_change_password),
    }


def marcar(db: Session, paso: str = None, terminado: bool = None, pospuesto: bool = None):
    if paso is not None:
        if paso not in PASOS:
            raise HTTPException(400, "Paso desconocido")
        hechos = _lista("setup_pasos", db)
        if paso not in hechos:
            ajustes.set(db, "setup_pasos", ",".join(hechos + [paso]))
    if terminado is not None:
        ajustes.set(db, "setup_terminado", bool(terminado))
        if terminado:
            ajustes.set(db, "setup_pospuesto", False)
    if pospuesto is not None:
        ajustes.set(db, "setup_pospuesto", bool(pospuesto))


# ── Rubros ───────────────────────────────────────────────────────────────────
def _ejemplos_libres(db: Session) -> dict:
    """Los productos y repuestos de fábrica que todavía no se usaron en nada."""
    prods = [p for p in db.query(models.Producto).all()
             if (p.marca, p.modelo) in PRODUCTOS_SEMILLA and not p.demo and not _producto_usado(db, p.id)]
    reps = [r for r in db.query(models.Repuesto).filter(models.Repuesto.codigo.in_(REPUESTOS_SEMILLA)).all()
            if not _repuesto_usado(db, r.id)]
    return {"productos": len(prods), "repuestos": len(reps)}


def _producto_usado(db: Session, pid: int) -> bool:
    return db.query(models.Ticket.id).filter(models.Ticket.producto_id == pid).first() is not None


def _repuesto_usado(db: Session, rid: int) -> bool:
    """Si el repuesto figura en tickets, presupuestos, pedidos o movimientos de stock de tickets."""
    consultas = (
        db.query(models.TicketRepuesto.ticket_id).filter(models.TicketRepuesto.repuesto_id == rid),
        db.query(models.StockMovimiento.id).filter(models.StockMovimiento.repuesto_id == rid,
                                                  models.StockMovimiento.ticket_id.isnot(None)),
        db.query(models.PresupuestoItem.id).filter(models.PresupuestoItem.repuesto_id == rid),
        db.query(models.PedidoItem.id).filter(models.PedidoItem.repuesto_id == rid),
    )
    return any(q.first() is not None for q in consultas)


def _quitar_ejemplos_de_fabrica(db: Session) -> dict:
    n = {"productos": 0, "repuestos": 0}
    for p in db.query(models.Producto).all():
        if (p.marca, p.modelo) in PRODUCTOS_SEMILLA and not p.demo and not _producto_usado(db, p.id):
            db.query(models.PlantillaPresupuesto).filter_by(producto_id=p.id).update({"producto_id": None})
            db.delete(p)
            n["productos"] += 1
    for r in db.query(models.Repuesto).filter(models.Repuesto.codigo.in_(REPUESTOS_SEMILLA)).all():
        if not _repuesto_usado(db, r.id):
            db.query(models.StockMovimiento).filter_by(repuesto_id=r.id).delete()
            db.delete(r)
            n["repuestos"] += 1
    return n


def _sumar_lineas(db: Session, clave: str, nuevas: list) -> int:
    actuales = _lineas(ajustes.get(db, clave))
    agregar = [x for x in nuevas if x not in actuales]
    if agregar:
        ajustes.set(db, clave, "\n".join(actuales + agregar))
    return len(agregar)


def aplicar_rubros(db: Session, ids: list, quitar_ejemplos: bool = False) -> dict:
    ids = R.validar(ids)
    if not ids:
        raise HTTPException(400, "Elegí al menos un tipo de taller.")
    c = R.combinar(ids)
    res = {"estados": [], "plantillas_agregadas": 0, "plantillas_quitadas": 0, "accesorios": 0,
           "controles": 0, "categorias": 0, "ejemplos_quitados": {"productos": 0, "repuestos": 0}}

    # Estados: se crean los que falten; si estaban desactivados, se activan
    for valor in c["estados"]:
        e = db.query(models.TicketStatusConfig).filter_by(valor=valor).first()
        color, orden = R.ESTADOS_EXTRA[valor]
        if not e:
            db.add(models.TicketStatusConfig(valor=valor, etiqueta=valor, color=color, orden=orden, es_final=False, activo=True))
            res["estados"].append(valor)
        elif not e.activo:
            e.activo = True
            res["estados"].append(valor)

    # Checklist: si el taller nunca tocó los accesorios, se reemplazan por los del rubro
    def_acc = ajustes.DEFS["checklist_accesorios"]["default"]
    if (ajustes.get(db, "checklist_accesorios") or "").strip() == def_acc.strip():
        ajustes.set(db, "checklist_accesorios", "\n".join(c["accesorios"]))
        res["accesorios"] = len(c["accesorios"])
    else:
        res["accesorios"] = _sumar_lineas(db, "checklist_accesorios", c["accesorios"])
    res["controles"] = _sumar_lineas(db, "checklist_controles", c["controles"])
    res["categorias"] = _sumar_lineas(db, "producto_categorias", c["categorias"])

    # Plantillas de diagnóstico: las de fábrica sin tocar que no son de estos rubros, se quitan
    deseadas = dict(c["plantillas"])
    for nombre, texto in R.SEMILLA_PLANTILLAS:
        if deseadas.get(nombre) == texto:
            continue
        p = db.query(models.DiagnosticaPlantilla).filter_by(nombre=nombre).first()
        if p and (p.texto or "") == texto:
            db.delete(p)
            res["plantillas_quitadas"] += 1
    db.flush()
    orden = (max([p.orden or 0 for p in db.query(models.DiagnosticaPlantilla).all()] or [-1]) + 1)
    for nombre, texto in c["plantillas"]:
        if not db.query(models.DiagnosticaPlantilla).filter_by(nombre=nombre).first():
            db.add(models.DiagnosticaPlantilla(nombre=nombre, texto=texto, orden=orden))
            orden += 1
            res["plantillas_agregadas"] += 1

    # Plazos de SLA (el aviso tiene que quedar por debajo del plazo más corto)
    nuevo, diag, rep = c["sla"]
    ajustes.set(db, "sla_horas_nuevo", nuevo)
    ajustes.set(db, "sla_horas_diagnostico", diag)
    ajustes.set(db, "sla_dias_reparacion", rep)
    if ajustes.get(db, "sla_aviso_horas") >= min(nuevo, diag):
        ajustes.set(db, "sla_aviso_horas", max(1, min(nuevo, diag) // 6))
    res["sla"] = {"horas_nuevo": nuevo, "horas_diagnostico": diag, "dias_reparacion": rep}

    if quitar_ejemplos:
        res["ejemplos_quitados"] = _quitar_ejemplos_de_fabrica(db)
    ajustes.set(db, "setup_rubros", ",".join(ids))
    res["etiqueta_sugerida"] = c["etiqueta"]
    return res


# ── Datos de ejemplo ─────────────────────────────────────────────────────────
CLIENTES_DEMO = [
    ("Laura Gómez", "persona", "1155550101"),
    ("Martín Díaz", "persona", "1155550102"),
    ("Taller Norte S.A.", "empresa", "1155550103"),
]


def crear_demo(db: Session, admin: models.Usuario) -> dict:
    from . import envios, estados, ubicaciones
    from .ticket_service import process_ticket_creation
    if hay_tickets_reales(db):
        raise HTTPException(400, "Ya hay tickets reales: los datos de ejemplo solo se cargan en un sistema nuevo.")
    if db.query(models.Ticket.id).filter(models.Ticket.demo.is_(True)).first():
        raise HTTPException(400, "Los datos de ejemplo ya están cargados.")
    ids = R.validar(_lista("setup_rubros", db)) or ["general"]
    sufijo = secrets.token_hex(2)

    clientes = []
    for nombre, tipo, tel in CLIENTES_DEMO:
        u = models.Usuario(username=f"ejemplo_{nombre.split()[0].lower()}_{sufijo}", nombre=f"{nombre} (ejemplo)",
                           email=None, rol=models.UserRole.CLIENTE.value, tipo_cliente=tipo, telefono=tel,
                           password_hash=auth.get_password_hash(secrets.token_urlsafe(24)), demo=True)
        db.add(u)
        clientes.append(u)

    productos, fallas = [], []
    for i in ids[:3]:
        d = R.RUBROS[i]["demo"]
        for marca, modelo, cat, meses in d["productos"][:2]:
            p = models.Producto(marca=marca, modelo=modelo, categoria=cat, periodo_garantia_meses=meses, demo=True)
            db.add(p)
            productos.append(p)
        fallas += d["fallas"]
        for nombre, codigo, prov, precio, stock, minimo in d["repuestos"]:
            if not db.query(models.Repuesto.id).filter_by(codigo=codigo).first():
                db.add(models.Repuesto(nombre=nombre, codigo=codigo, proveedor=prov, precio=precio, stock=stock,
                                       stock_minimo=minimo, categoria="Ejemplo", demo=True))
    db.flush()

    # Una ubicación de ejemplo (si el taller todavía no armó las suyas)
    estante = None
    if not db.query(models.Ubicacion.id).filter(models.Ubicacion.tipo != "externa").first():
        dep = ubicaciones.crear(db, "Depósito (ejemplo)")
        dep.demo = True
        estante = ubicaciones.crear(db, "Estante 1", padre_id=dep.id)
        estante.demo = True

    # Tickets en distintos momentos de la reparación
    plan = [None, "En diagnóstico", "Esperando repuestos", "Reparado", "Cerrado", "externo"]
    hoy = now_local()
    creados = []
    for n, destino in enumerate(plan):
        prod = productos[n % len(productos)]
        cli = clientes[n % len(clientes)]
        compra = hoy - timedelta(days=120 + 150 * (n % 3))
        datos = schemas.TicketCreate(numero_serie=f"EJ{sufijo.upper()}{n + 1:03d}", fecha_compra=compra,
                                     descripcion=fallas[n % len(fallas)], producto=f"{prod.marca} {prod.modelo}",
                                     producto_id=prod.id)
        t = process_ticket_creation(db, datos, admin, cliente=cli, detalle_alta="Ticket de ejemplo (configuración inicial)")
        t.demo = True
        if destino == "externo":
            envios.enviar(db, t, admin, {"destino": f"{prod.marca} — servicio oficial", "numero_caso": f"CASO-{1000 + n}",
                                         "transportista": "Correo", "guia": f"EJ{n:04d}", "contenido": "Equipo completo",
                                         "fecha_envio": utcnow() - timedelta(days=12),
                                         "fecha_estimada": utcnow() - timedelta(days=2)})
        else:
            if destino:
                for paso in ("En diagnóstico", destino):
                    estados.cambiar(db, t, paso, admin)
            if estante and destino not in (None, "Cerrado"):
                ubicaciones.mover_ticket(db, t, estante.id, admin, motivo="manual")
        if n == 1:
            db.add(models.Comentario(ticket_id=t.id, usuario_id=admin.id, is_internal=True,
                                     comentario="Comentario interno de ejemplo: solo lo ve el taller."))
        creados.append(t)
    db.flush()
    return {"tickets": len(creados), "clientes": len(clientes), "productos": len(productos)}


def borrar_demo(db: Session) -> dict:
    """Borra todo lo marcado como ejemplo. Lo que el taller usó en algo real se conserva."""
    T = models.Ticket
    tickets = db.query(T).filter(T.demo.is_(True)).all()
    ids = [t.id for t in tickets]
    borrados = {"tickets": 0, "clientes": 0, "productos": 0, "repuestos": 0, "ubicaciones": 0}
    conservados = {"clientes": 0, "productos": 0, "repuestos": 0, "ubicaciones": 0}
    if ids:
        # Tickets reales que apuntan a uno de ejemplo (clonado, relacionado, reingreso)
        for col in (T.clonado_de, T.ticket_relacionado, T.reingreso_de):
            db.query(T).filter(col.in_(ids), T.demo.is_(False)).update({col: None}, synchronize_session=False)
        for adj in db.query(models.Adjunto).filter(models.Adjunto.ticket_id.in_(ids)).all():
            ruta = adj.ruta_archivo
            try:
                if ruta and os.path.isfile(ruta):
                    os.remove(ruta)
            except OSError:
                pass
            db.delete(adj)
        for M in (models.Comentario, models.HistorialEstado, models.Notificacion):
            db.query(M).filter(M.ticket_id.in_(ids)).delete(synchronize_session=False)
        # Movimientos de stock de un repuesto real hechos en un ticket de ejemplo: quedan, sin el ticket
        reales = db.query(models.Repuesto.id).filter(models.Repuesto.demo.is_(False))
        db.query(models.StockMovimiento).filter(models.StockMovimiento.ticket_id.in_(ids),
                                                models.StockMovimiento.repuesto_id.in_(reales)
                                                ).update({"ticket_id": None}, synchronize_session=False)
        db.query(models.StockMovimiento).filter(models.StockMovimiento.ticket_id.in_(ids)).delete(synchronize_session=False)
        db.execute(models.ticket_tags.delete().where(models.ticket_tags.c.ticket_id.in_(ids)))
        db.query(models.UbicacionMovimiento).filter(models.UbicacionMovimiento.ticket_id.in_(ids)).delete(synchronize_session=False)
        for t in tickets:
            db.delete(t)
        borrados["tickets"] = len(ids)
        db.flush()

    for r in db.query(models.Repuesto).filter(models.Repuesto.demo.is_(True)).all():
        if _repuesto_usado(db, r.id):
            r.demo = False
            conservados["repuestos"] += 1
        else:
            db.query(models.StockMovimiento).filter_by(repuesto_id=r.id).delete()
            db.query(models.UbicacionMovimiento).filter_by(repuesto_id=r.id).delete()
            db.delete(r)
            borrados["repuestos"] += 1
    for p in db.query(models.Producto).filter(models.Producto.demo.is_(True)).all():
        if _producto_usado(db, p.id):
            p.demo = False
            conservados["productos"] += 1
        else:
            db.query(models.PlantillaPresupuesto).filter_by(producto_id=p.id).update({"producto_id": None})
            db.delete(p)
            borrados["productos"] += 1
    db.flush()

    # Ubicaciones de ejemplo: de las de adentro hacia afuera; si guardan algo real, se quedan
    ubic = db.query(models.Ubicacion).filter(models.Ubicacion.demo.is_(True)).all()
    for u in sorted(ubic, key=lambda x: -_profundidad(x)):
        ocupada = (db.query(models.Ticket.id).filter_by(ubicacion_id=u.id).first()
                   or db.query(models.Repuesto.id).filter_by(ubicacion_id=u.id).first()
                   or db.query(models.Ubicacion.id).filter_by(padre_id=u.id).first())
        if ocupada:
            u.demo = False
            conservados["ubicaciones"] += 1
        else:
            db.query(models.UbicacionMovimiento).filter(
                (models.UbicacionMovimiento.desde_id == u.id) | (models.UbicacionMovimiento.hacia_id == u.id)
            ).update({"desde_id": None, "hacia_id": None}, synchronize_session=False)
            db.delete(u)
            db.flush()
            borrados["ubicaciones"] += 1

    for u in db.query(models.Usuario).filter(models.Usuario.demo.is_(True)).all():
        usado = (db.query(models.Ticket.id).filter((models.Ticket.usuario_id == u.id) | (models.Ticket.tecnico_asignado == u.id)).first()
                 or db.query(models.Comentario.id).filter_by(usuario_id=u.id).first())
        if usado:
            u.demo = False
            conservados["clientes"] += 1
        else:
            for M in (models.Notificacion, models.TicketFavorito):
                db.query(M).filter(M.usuario_id == u.id).delete(synchronize_session=False)
            db.delete(u)
            borrados["clientes"] += 1
    return {"borrados": borrados, "conservados": conservados}


def _profundidad(u: models.Ubicacion) -> int:
    n = 0
    while u.padre is not None and n < 50:
        u, n = u.padre, n + 1
    return n
