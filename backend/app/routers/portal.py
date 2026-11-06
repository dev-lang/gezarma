"""
portal.py — Portal del cliente: sus equipos, con todas sus reparaciones,
los documentos que puede descargar y lo que tiene pendiente de hacer.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import auth, database, models
from ..services import encuestas, retiro
from ..timeutils import iso_utc

router = APIRouter(prefix="/portal", tags=["portal"])


def _documentos(t: models.Ticket) -> list:
    """Documentos que el cliente puede bajar de este ticket (ver routers/documentos.py)."""
    docs = ["ingreso"]
    pres = t.presupuesto
    if pres and pres.estado != models.PresupuestoEstado.BORRADOR:
        docs.append("presupuesto")
    if t.estado in (models.TicketStatus.ENVIADO.value, models.TicketStatus.CERRADO.value) or t.firma("entrega"):
        docs.append("remito")
    return docs


@router.get("/equipos")
def mis_equipos(db: Session = Depends(database.get_db),
                current_user: models.Usuario = Depends(auth.get_current_user)):
    """Los equipos del usuario (agrupados por N° de serie), de la reparación más reciente a la más vieja."""
    estados = {e.valor: e for e in db.query(models.TicketStatusConfig).all()}
    tickets = (db.query(models.Ticket).filter(models.Ticket.usuario_id == current_user.id)
               .order_by(models.Ticket.fecha_creacion.desc()).all())
    equipos, pendientes = {}, []
    for t in tickets:
        cfg = estados.get(t.estado)
        pres = t.presupuesto
        acciones = []
        if pres and pres.estado == models.PresupuestoEstado.ENVIADO:
            acciones.append({"tipo": "presupuesto", "texto": "Presupuesto para aprobar"})
        if t.estado == retiro.estado_retiro(db) and t.fecha_listo:
            acciones.append({"tipo": "retiro", "texto": "Listo para retirar",
                             "vence": iso_utc(retiro.vence(db, t))})
        if encuestas.pendiente(db, t):
            acciones.append({"tipo": "encuesta", "texto": "Calificá la reparación"})
        rep = {
            "id": t.id, "numero_rma": t.numero_rma, "estado": t.estado,
            "estado_etiqueta": cfg.etiqueta if cfg else t.estado, "color": cfg.color if cfg else "#6b7280",
            "final": bool(cfg and cfg.es_final), "en_garantia": bool(t.en_garantia),
            "fecha_ingreso": iso_utc(t.fecha_creacion), "fecha_cierre": iso_utc(t.fecha_cierre) if t.fecha_cierre else None,
            "descripcion": t.descripcion, "documentos": _documentos(t), "acciones": acciones,
            "encuesta": t.encuesta.puntaje if t.encuesta else None,
        }
        clave = (t.numero_serie or "").strip().upper() or f"sin-serie-{t.id}"
        eq = equipos.setdefault(clave, {"numero_serie": t.numero_serie, "producto": t.producto, "reparaciones": []})
        eq["reparaciones"].append(rep)
        pendientes += [{**a, "ticket_id": t.id, "numero_rma": t.numero_rma, "producto": t.producto} for a in acciones]
    lista = list(equipos.values())
    return {
        "equipos": lista,
        "pendientes": pendientes,
        "resumen": {"equipos": len(lista), "reparaciones": len(tickets),
                    "en_curso": sum(1 for e in lista for r in e["reparaciones"] if not r["final"])},
    }
