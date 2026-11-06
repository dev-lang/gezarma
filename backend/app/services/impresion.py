"""
impresion.py — Código de barras y diseño de etiquetas / tickets para impresoras térmicas.

Por qué el código de barras se arma así
---------------------------------------
Una térmica imprime puntos blancos o negros, sin grises, a 203 o 300 dpi. Para
que un Code128 se lea, todas las barras del mismo ancho tienen que salir con la
misma cantidad de puntos. Por eso:

- El ancho de barra es un número ENTERO de puntos de la impresora configurada.
- Las barras se dibujan como formas vectoriales, no como imagen: una imagen se
  reescala y, según cómo cae sobre la grilla de puntos, las barras quedan
  desparejas. Un vector se rasteriza directo a la grilla de la impresora.
- Hay dos representaciones del mismo patrón, porque cada motor dibuja bien una:
  · PDF del servidor (xhtml2pdf): tabla HTML con celdas de ancho en mm.
    (su SVG sale al 75 % del tamaño por un tema de unidades px/pt).
  · Navegador (Chrome): SVG en línea con viewBox en unidades de barra.
    (Chrome redondea las celdas de tabla a píxeles CSS).
Verificado con dos rasterizadores (pdfium y poppler) sin suavizado, a 203 y 300
dpi y con 8 alineaciones distintas respecto de la grilla: siempre legible.
"""
import math

import barcode

MM_POR_PULGADA = 25.4
MODULO_IDEAL_MM = 0.25      # ≈ 10 mil: lo que leen bien hasta los lectores baratos
MODULO_MAX_MM = 0.34
ZONA_SILENCIO_MODULOS = 10  # margen blanco que necesitan los lectores a cada lado

ETIQUETAS = {"62x29": (62, 29), "50x25": (50, 25), "40x30": (40, 30), "58x40": (58, 40), "100x50": (100, 50)}
# Área imprimible de las ticketeras según el ancho del rollo
TICKETERA_IMPRIMIBLE_MM = {"58": 48, "80": 72}


def _patron(texto: str) -> str:
    return barcode.get("code128", texto).build()[0]   # '1101001000…' (1 = barra)


def codigo_barras(texto: str, dpi: int, ancho_disponible_mm: float, alto_mm: float):
    """Code128 de `texto` para una impresora de `dpi`, o None si no entra en el ancho.

    Elige el ancho de barra más cercano a 0,25 mm que sea un número entero de
    puntos (mínimo 2) y que entre, con su zona de silencio, en el ancho disponible.
    """
    patron = _patron(texto)
    total_modulos = len(patron) + 2 * ZONA_SILENCIO_MODULOS
    mm_por_punto = MM_POR_PULGADA / dpi
    candidatos = range(max(2, math.floor(MODULO_MAX_MM / mm_por_punto)), 1, -1)
    # Primero el más fino que llegue a ~0,25 mm; si no entra, los más finos que eso
    # (mínimo 2 puntos). Ej.: 203 dpi → 2 puntos (0,25 mm); 300 dpi → 3 (0,254) y si
    # no entra, 2 (0,169).
    def orden(p):
        mm = p * mm_por_punto
        return (0, p) if mm >= MODULO_IDEAL_MM - 0.005 else (1, -p)
    candidatos = sorted(candidatos, key=orden)
    for puntos in candidatos:
        modulo = puntos * mm_por_punto
        ancho = total_modulos * modulo
        if ancho <= ancho_disponible_mm + 1e-6:
            return {
                "texto": texto, "ancho_mm": round(ancho, 4), "alto_mm": alto_mm,
                "modulo_mm": round(modulo, 4), "puntos_por_barra": puntos,
                "tabla": _tabla(patron, modulo, alto_mm, ancho),
                "svg": _svg(patron, modulo, alto_mm, total_modulos),
            }
    return None


def _corridas(patron: str):
    corr, actual, n = [], patron[0], 0
    for c in patron:
        if c == actual:
            n += 1
        else:
            corr.append((actual, n))
            actual, n = c, 1
    corr.append((actual, n))
    return [("0", ZONA_SILENCIO_MODULOS)] + corr + [("0", ZONA_SILENCIO_MODULOS)]


def _tabla(patron, modulo, alto, ancho) -> str:
    celdas = "".join(
        f'<td style="width:{n * modulo:.4f}mm;height:{alto}mm;padding:0;'
        f'background-color:{"#000" if c == "1" else "#fff"};"></td>'
        for c, n in _corridas(patron))
    return (f'<table style="width:{ancho:.4f}mm;border-collapse:collapse;table-layout:fixed;" '
            f'cellpadding="0" cellspacing="0"><tr>{celdas}</tr></table>')


def _svg(patron, modulo, alto, total_modulos) -> str:
    rects = "".join(f'<rect x="{i + ZONA_SILENCIO_MODULOS}" y="0" width="1" height="1"/>'
                    for i, c in enumerate(patron) if c == "1")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_modulos * modulo:.4f}mm" height="{alto}mm" '
            f'viewBox="0 0 {total_modulos} 1" preserveAspectRatio="none" shape-rendering="crispEdges" '
            f'style="display:block">{rects}</svg>')


# ── Etiqueta ─────────────────────────────────────────────────────────────────
def _pt_a_mm(pt):
    return pt * MM_POR_PULGADA / 72


def _recortar(texto: str, max_chars: int) -> str:
    texto = (texto or "").strip()
    return texto if len(texto) <= max_chars else texto[:max(1, max_chars - 1)] + "…"


def disenio_etiqueta(tamano: str, dpi: int, rma: str, lineas: list) -> dict:
    """Medidas de la etiqueta: QR, texto y código de barras según tamaño y dpi.

    `lineas` son las líneas de texto (además del RMA), en orden de importancia:
    si no entran todas al lado del QR, se descartan las últimas.
    """
    ancho, alto = ETIQUETAS[tamano]
    margen_v, margen_h = 1.2, 1.5
    util_w, util_h = ancho - 2 * margen_h, alto - 2 * margen_v
    escala = min(alto / 29, ancho / 62)
    fuente = max(5.5, min(10.0, 6.3 * escala))           # pt
    alto_barras = max(4.0, min(9.0, util_h * 0.22))
    bc = codigo_barras(rma, dpi, util_w, alto_barras)
    reservado = (bc["alto_mm"] + 0.8) if bc else 0
    qr = round(min(util_h - reservado, util_w * 0.42), 2)
    ancho_texto = util_w - qr - 1.5
    interlineado = _pt_a_mm(fuente) * 1.25

    def entra_en(ancho_mm):   # cuerpo (pt) con el que el RMA entra en ese ancho (Courier: 0,6 em)
        return ancho_mm / (max(1, len(rma)) * 0.6) * 72 / MM_POR_PULGADA

    # Si sobra alto debajo del QR (etiquetas más altas que anchas), el RMA va abajo,
    # a todo el ancho y más grande; si no, al lado del QR, achicado para que entre.
    fuente_rma_abajo = min(fuente * 1.8, entra_en(util_w))
    rma_abajo = util_h - reservado - qr >= _pt_a_mm(fuente_rma_abajo) * 1.3 + 0.8
    if rma_abajo:
        fuente_rma = fuente_rma_abajo
        max_lineas = int(qr // interlineado)
    else:
        fuente_rma = min(fuente * (1.3 if bc else 1.6), entra_en(ancho_texto))
        max_lineas = max(0, int((qr - _pt_a_mm(fuente_rma) * 1.3) // interlineado))
    chars = max(6, int(ancho_texto / (_pt_a_mm(fuente) * 0.52)))
    return {
        "ancho_mm": ancho, "alto_mm": alto, "margen_v": margen_v, "margen_h": margen_h,
        "qr_mm": qr, "fuente_pt": round(fuente, 2), "fuente_rma_pt": round(fuente_rma, 2),
        "rma_abajo": rma_abajo,
        "lineas": [_recortar(l, chars) for l in lineas if l][:max_lineas],
        "barras": bc,
    }


# ── Ticket (ticketera de rollo continuo) ─────────────────────────────────────
def lineas_de(texto: str, ancho_mm: float, fuente_pt: float) -> int:
    """Estimación (por exceso) de cuántos renglones ocupa un texto. Usa un ancho de
    letra promedio de 0,62 em: alcanza incluso para textos en mayúsculas."""
    chars = max(8, int(ancho_mm / (_pt_a_mm(fuente_pt) * 0.62)))
    total = 0
    for parrafo in (texto or "").splitlines() or [""]:
        total += max(1, math.ceil(len(parrafo) / chars))
    return total


def disenio_ticket(ancho_rollo: str, dpi: int, rma: str) -> dict:
    imprimible = TICKETERA_IMPRIMIBLE_MM[ancho_rollo]
    fuente = 8.0 if ancho_rollo == "58" else 9.0
    return {
        "ancho_mm": int(ancho_rollo), "imprimible_mm": imprimible,
        "margen_h": (int(ancho_rollo) - imprimible) / 2,
        "fuente_pt": fuente, "qr_mm": 30 if ancho_rollo == "58" else 36,
        "barras": codigo_barras(rma, dpi, imprimible, 9.0),
    }


def largo_ticket(d: dict, bloques: list) -> float:
    """Largo total del ticket en mm, a partir de los mismos bloques que se imprimen.
    Se estima por exceso: sobra un poco de papel, pero el contenido nunca se parte
    en dos tickets."""
    f = d["fuente_pt"]
    w = d["imprimible_mm"]
    renglon = _pt_a_mm(f) * 1.3
    mm = 6.0   # márgenes de página (3 mm arriba y abajo)
    for b in bloques:
        t = b["tipo"]
        if t in ("titulo", "grande"):
            mm += lineas_de(b["texto"], w, f * 1.6) * _pt_a_mm(f * 1.6) * 1.3
        elif t == "texto":
            mm += lineas_de(b["texto"], w, f) * renglon
        elif t == "par":
            mm += lineas_de(f"{b['etiqueta']}: {b['texto']}", w, f) * renglon
        elif t == "separador":
            mm += 2.4 + 0.5
        elif t == "qr":
            mm += d["qr_mm"] + 1.5
        elif t == "barras" and d["barras"]:
            mm += d["barras"]["alto_mm"] + 3.0
        elif t == "firma":
            mm += 10 + 0.8 + renglon
        elif t == "firma_img":
            mm += 2.0 + b["firma"]["alto_mm"] + 0.8 + renglon * (2 if b["firma"]["aclaracion"] else 1)
    return round(mm + 4.0, 1)   # + 4 mm de margen de seguridad
