"""
envios.py — Equipos enviados a la garantía del fabricante o a un servicio oficial.

Enviar: queda el envío abierto, el ticket pasa a "En servicio técnico oficial" y a la
ubicación "Fuera del taller". Volver: se registra el resultado (reparado, reemplazado con
serie nueva, rechazado o sin falla), el ticket pasa a "Equipo recibido" para revisarlo y
se guarda donde se indique (o queda sin ubicación). Un ticket puede tener varios envíos,
pero uno abierto a la vez. El cliente solo ve el estado, no los datos del envío.
"""
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..timeutils import iso_utc, utcnow
from . import estados, ubicaciones
from .ticket_service import log_event

RESULTADOS = {"reparado": "Reparado por el fabricante", "reemplazado": "Reemplazado por uno nuevo",
              "rechazado": "Rechazado (sin cobertura)", "sin_falla": "Sin falla"}
ESTADO_ENVIADO = models.TicketStatus.SERVICIO_EXTERNO.value
ESTADO_VUELTA = models.TicketStatus.RECIBIDO.value


def _error(msg: str, status: int = 400):
    raise HTTPException(status_code=status, detail=msg)


def abierto(db: Session, ticket_id: int):
    return db.query(models.EnvioExterno).filter_by(ticket_id=ticket_id, estado="enviado").first()


def _texto(v, largo):
    v = (v or "").strip()
    return v[:largo] or None


def enviar(db: Session, t: models.Ticket, usuario: models.Usuario, datos: dict) -> models.EnvioExterno:
    if estados.es_final(db, t.estado):
        _error("El ticket está cerrado: reabrilo antes de enviarlo.")
    if abierto(db, t.id):
        _error("Ya hay un envío abierto para este equipo: registrá primero la vuelta.")
    destino = _texto(datos.get("destino"), 120)
    if not destino:
        _error("Indicá a quién se manda (fabricante o servicio oficial).")
    fecha = datos.get("fecha_envio") or utcnow()
    if fecha > utcnow():
        _error("La fecha de envío no puede ser futura.")
    estimada = datos.get("fecha_estimada")
    if estimada and estimada < fecha:
        _error("La fecha estimada de vuelta tiene que ser posterior al envío.")
    e = models.EnvioExterno(
        ticket_id=t.id, destino=destino, numero_caso=_texto(datos.get("numero_caso"), 60), fecha_envio=fecha,
        transportista=_texto(datos.get("transportista"), 80), guia=_texto(datos.get("guia"), 80),
        contenido=_texto(datos.get("contenido"), 120) or "Equipo completo", accesorios=_texto(datos.get("accesorios"), 300),
        fecha_estimada=estimada, nota=_texto(datos.get("nota"), 2000), usuario_envio_id=usuario.id)
    db.add(e)
    db.flush()
    caso = f" (caso {e.numero_caso})" if e.numero_caso else ""
    guia = f", guía {e.guia}" if e.guia else ""
    log_event(db, t.id, usuario.id, models.EventoHistorial.ENVIO_EXTERNO,
              detalle=f"Enviado a {destino}{caso}: {e.contenido}{guia}")
    estados.cambiar(db, t, ESTADO_ENVIADO, usuario, detalle=f"Estado: {t.estado} → {ESTADO_ENVIADO} (enviado a {destino})")
    ubicaciones.mover_ticket(db, t, ubicaciones.externa(db).id, usuario, motivo="envio", permitir_externa=True)
    return e


def editar(db: Session, e: models.EnvioExterno, datos: dict) -> models.EnvioExterno:
    for campo, largo in (("destino", 120), ("numero_caso", 60), ("transportista", 80), ("guia", 80),
                         ("contenido", 120), ("accesorios", 300), ("nota", 2000)):
        if campo in datos and datos[campo] is not None:
            v = _texto(datos[campo], largo)
            if campo == "destino" and not v:
                _error("Indicá a quién se manda (fabricante o servicio oficial).")
            setattr(e, campo, v)
    if datos.get("fecha_estimada", ...) is not ...:
        if datos["fecha_estimada"] and datos["fecha_estimada"] < e.fecha_envio:
            _error("La fecha estimada de vuelta tiene que ser posterior al envío.")
        e.fecha_estimada = datos["fecha_estimada"]
    if e.estado == "recibido":
        for campo, largo in (("comprobante", 80), ("serie_nueva", 80), ("nota_recepcion", 2000)):
            if campo in datos and datos[campo] is not None:
                setattr(e, campo, _texto(datos[campo], largo))
    return e


def recibir(db: Session, e: models.EnvioExterno, usuario: models.Usuario, datos: dict) -> models.EnvioExterno:
    if e.estado != "enviado":
        _error("Ese envío ya se registró como recibido.")
    resultado = datos.get("resultado")
    if resultado not in RESULTADOS:
        _error("Elegí qué pasó: reparado, reemplazado, rechazado o sin falla.")
    fecha = datos.get("fecha_recepcion") or utcnow()
    if fecha > utcnow():
        _error("La fecha de recepción no puede ser futura.")
    if fecha < e.fecha_envio:
        _error("La fecha de recepción no puede ser anterior al envío.")
    serie = _texto(datos.get("serie_nueva"), 80)
    if resultado == "reemplazado" and not serie:
        _error("Si lo reemplazaron, anotá el número de serie del equipo nuevo.")
    t = e.ticket
    e.estado, e.fecha_recepcion, e.resultado = "recibido", fecha, resultado
    e.serie_nueva = serie if resultado == "reemplazado" else None
    e.comprobante = _texto(datos.get("comprobante"), 80)
    e.nota_recepcion = _texto(datos.get("nota_recepcion"), 2000)
    e.usuario_recepcion_id = usuario.id
    dias = max(0, (fecha - e.fecha_envio).days)
    log_event(db, t.id, usuario.id, models.EventoHistorial.ENVIO_EXTERNO,
              detalle=f"Volvió de {e.destino} después de {dias} días: {RESULTADOS[resultado]}"
                      + (f", comprobante {e.comprobante}" if e.comprobante else ""))
    if e.serie_nueva and e.serie_nueva != t.numero_serie:
        log_event(db, t.id, usuario.id, models.EventoHistorial.CAMPO_EDITADO,
                  detalle=f"Número de serie: {t.numero_serie} → {e.serie_nueva} (reemplazo del fabricante)",
                  campo="numero_serie", val_ant=t.numero_serie, val_nuevo=e.serie_nueva)
        t.numero_serie = e.serie_nueva
    estados.cambiar(db, t, ESTADO_VUELTA, usuario, detalle=f"Estado: {t.estado} → {ESTADO_VUELTA} (volvió de {e.destino})")
    ubicaciones.mover_ticket(db, t, datos.get("ubicacion_id") or None, usuario, motivo="regreso", permitir_externa=True)
    return e


def salida(e: models.EnvioExterno, ahora: datetime = None) -> dict:
    ahora = ahora or utcnow()
    fin = e.fecha_recepcion or ahora
    t = e.ticket
    return {
        "id": e.id, "ticket_id": e.ticket_id, "numero_rma": t.numero_rma if t else None,
        "producto": t.producto if t else None, "numero_serie": t.numero_serie if t else None,
        "cliente": t.cliente.nombre if t and t.cliente else None,
        "destino": e.destino, "numero_caso": e.numero_caso, "fecha_envio": iso_utc(e.fecha_envio),
        "transportista": e.transportista, "guia": e.guia, "contenido": e.contenido, "accesorios": e.accesorios,
        "fecha_estimada": iso_utc(e.fecha_estimada) if e.fecha_estimada else None, "nota": e.nota,
        "estado": e.estado, "fecha_recepcion": iso_utc(e.fecha_recepcion) if e.fecha_recepcion else None,
        "resultado": e.resultado, "resultado_texto": RESULTADOS.get(e.resultado), "serie_nueva": e.serie_nueva,
        "comprobante": e.comprobante, "nota_recepcion": e.nota_recepcion,
        "enviado_por": e.usuario_envio.nombre if e.usuario_envio else None,
        "recibido_por": e.usuario_recepcion.nombre if e.usuario_recepcion else None,
        "dias": max(0, (fin - e.fecha_envio).days),
        "atrasado": bool(e.estado == "enviado" and e.fecha_estimada and e.fecha_estimada < ahora),
    }
