"""
panel.py — Disposición del panel de control de cada usuario: orden de los bloques,
ancho (completo, mitad o cuarto) y cuáles oculta.

- Cada usuario guarda la suya (usuarios.panel_config, JSON).
- Quien no armó la suya ve la del equipo (ajuste interno "panel_predeterminado",
  la define un administrador) o, si no hay, la de fábrica (la define el frontend).
- Los bloques que un rol no puede ver los filtra el frontend; acá solo se valida
  la forma. La lista de tickets no se puede ocultar.
"""
import json

from fastapi import HTTPException

from .. import ajustes, models

RESUMEN = ("resumen_total", "resumen_nuevos", "resumen_proceso", "resumen_cerrados")
BLOQUES = ("guia", *RESUMEN, "grafico_estados", "grafico_productos", "grafico_tecnicos", "tiempo_promedio",
           "para_hoy", "alertas", "portal", "satisfaccion", "horas", "tickets")
ANCHOS = ("completo", "mitad", "cuarto")
NO_OCULTABLES = {"tickets"}
# Bloques que se partieron en varios: "resumen" (las 4 tarjetas juntas) → una tarjeta por bloque
PARTIDOS = {"resumen": RESUMEN}


def _expandir(bloques):
    for b in bloques:
        if isinstance(b, dict) and b.get("id") in PARTIDOS:
            ancho = b.get("ancho", "completo")
            if ancho not in ANCHOS:
                raise HTTPException(400, f"Ancho inválido: {ancho}")
            for nuevo in PARTIDOS[b["id"]]:
                yield {**b, "id": nuevo, "ancho": "cuarto"}
        else:
            yield b


def validar(bloques) -> list:
    if not isinstance(bloques, list) or not bloques:
        raise HTTPException(400, "La disposición del panel está vacía.")
    vistos, limpio = set(), []
    for b in _expandir(bloques):
        if not isinstance(b, dict):
            raise HTTPException(400, "Formato inválido.")
        bid = b.get("id")
        if bid not in BLOQUES:
            raise HTTPException(400, f"Bloque desconocido: {bid}")
        if bid in vistos:
            continue
        vistos.add(bid)
        ancho = b.get("ancho", "completo")
        if ancho not in ANCHOS:
            raise HTTPException(400, f"Ancho inválido: {ancho}")
        visible = bool(b.get("visible", True)) or bid in NO_OCULTABLES
        limpio.append({"id": bid, "visible": visible, "ancho": ancho})
    return limpio


def _leer(texto):
    if not texto:
        return None
    try:
        return validar(json.loads(texto))
    except (ValueError, HTTPException):
        return None          # algo guardado que ya no vale: se usa el predeterminado


def del_usuario(db, u: models.Usuario) -> dict:
    propio = _leer(u.panel_config)
    equipo = _leer(ajustes.get(db, "panel_predeterminado"))
    return {"bloques": propio or equipo, "propio": propio is not None, "equipo": equipo,
            "bloques_conocidos": list(BLOQUES), "anchos": list(ANCHOS)}


def guardar(db, u: models.Usuario, bloques) -> dict:
    u.panel_config = json.dumps(validar(bloques), ensure_ascii=False)
    return del_usuario(db, u)


def restablecer(db, u: models.Usuario) -> dict:
    u.panel_config = None
    return del_usuario(db, u)


def guardar_equipo(db, bloques) -> list:
    limpio = validar(bloques)
    ajustes.set(db, "panel_predeterminado", json.dumps(limpio, ensure_ascii=False))
    return limpio


def borrar_equipo(db):
    ajustes.set(db, "panel_predeterminado", "")


def accesos(db, u: models.Usuario) -> dict:
    """Los datos de la barra de accesos del panel: favoritos, horas de hoy y equipos afuera."""
    from ..timeutils import utcnow
    from . import horas
    T = models.TiempoTrabajo
    ini, fin = horas.limites_dia(horas.hoy())
    ahora = utcnow()
    minutos = sum(horas.minutos(r, ahora) for r in db.query(T).filter(
        T.usuario_id == u.id, T.inicio >= ini, T.inicio < fin))
    afuera = db.query(models.EnvioExterno).filter_by(estado="enviado").all()
    return {
        "favoritos": db.query(models.TicketFavorito).filter_by(usuario_id=u.id).count(),
        "horas_hoy_min": round(minutos),
        "afuera": len(afuera),
        "atrasados": sum(1 for e in afuera if e.fecha_estimada and e.fecha_estimada < ahora),
    }
