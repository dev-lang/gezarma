"""Modo oscuro: cada clase de color del frontend tiene su versión oscura y los colores dan buen contraste."""
import importlib.util
import os

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("modo_oscuro", os.path.join(RAIZ, "herramientas", "modo_oscuro.py"))
mo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mo)


def test_oscuro_css_al_dia():
    """Si falla: se usó una clase de color nueva → correr  python herramientas/modo_oscuro.py"""
    actual = open(mo.SALIDA, encoding="utf-8").read()
    assert mo.generar() == actual, "frontend/css/oscuro.css está desactualizado: correr python herramientas/modo_oscuro.py"


def test_cada_clase_tiene_version_oscura():
    vistas, _ = mo.clases_usadas()
    css = open(mo.SALIDA, encoding="utf-8").read()
    faltan = []
    for clase, (variantes, prop, color, tono, op) in vistas.items():
        if mo.selector(variantes, clase) is None or prop in ("accent", "shadow"):
            continue
        base = "border" if prop.startswith("border") else prop
        if mo.oscuro(base, color, tono, op) is not None and "." + mo.escapar(clase) not in css:
            faltan.append(clase)
    assert not faltan, faltan


def test_variantes_conocidas():
    sel, media = mo.selector(("has-[:checked]",), "has-[:checked]:bg-blue-50")
    assert sel == ".has-\\[\\:checked\\]\\:bg-blue-50:has(:checked)" and media is None
    assert mo.selector(("peer-checked",), "peer-checked:text-violet-700")[0] == ".peer:checked ~ .peer-checked\\:text-violet-700"
    assert mo.selector(("group-hover",), "group-hover:text-blue-600")[0] == ".group:hover .group-hover\\:text-blue-600"
    assert mo.selector(("aria-[current=page]",), "x")[0] == ".x[aria-current=page]"
    assert mo.selector(("sm",), "sm:bg-white")[1] == "(min-width: 640px)"
    assert mo.selector(("after",), "after:bg-white") is None      # la perilla de los interruptores sigue blanca
    try:
        mo.selector(("algo-raro",), "algo-raro:bg-white")
        assert False, "una variante desconocida tiene que avisar"
    except mo.VarianteDesconocida:
        pass


def test_contraste_de_la_paleta_oscura():
    """Textos ≥ 4,5:1 sobre la tarjeta; los de color, también sobre su propio fondo suave."""
    for tono in ("300", "400", "500", "600", "700", "800", "900"):
        assert mo.contraste(mo.oscuro("text", "gray", tono, None), mo.TARJETA) >= 4.5, tono
    assert mo.contraste(mo.oscuro("text", "gray", "500", None), mo.oscuro("bg", "gray", "100", None)) >= 4.5
    for tono in ("300", "400", "500"):   # p. ej. la letra del atajo en la sección activa de Administración
        assert mo.contraste(mo.oscuro("text", "gray", tono, None), mo.oscuro("bg", "blue", "50", None)) >= 4.5, tono
    for color in mo.PALETA:
        if color in mo.GRISES:
            continue
        for tono in ("500", "600", "700", "800", "900"):
            texto = mo.oscuro("text", color, tono, None)
            assert mo.contraste(texto, mo.TARJETA) >= 4.5, (color, tono)
        # texto oscuro de color (700+) sobre el fondo suave del mismo color (insignias, avisos)
        fondo = mo.oscuro("bg", color, "50", None)[:7]
        assert mo.contraste(mo.oscuro("text", color, "700", None), fondo) >= 4.5, color


def test_las_paginas_cargan_el_modo_oscuro(client):
    for ruta in ("/", "/seguimiento"):
        assert '/css/oscuro.css' in client.get(ruta).text, ruta
    r = client.get("/css/oscuro.css")
    assert r.status_code == 200 and "color-scheme: dark" in r.text


def test_botones_de_color_con_texto_legible():
    """Texto blanco solo sobre fondos que den ≥ 4,5:1 (en los dos modos)."""
    import re
    malos = []
    for ruta in mo.archivos():
        texto = open(ruta, encoding="utf-8").read()
        for clase in re.findall(r'class="([^"]*)"', texto):
          for pedazo in re.split(r"\$\{|\}|\?|'| : ", clase):   # cada alternativa de un ${cond ? '…' : '…'} por separado
            tokens = pedazo.split()
            if "text-white" not in tokens:
                continue
            for t in tokens:
                m = re.fullmatch(r"bg-([a-z]+)-(\d+)", t)
                if m and m.group(1) in mo.PALETA and m.group(1) not in mo.GRISES:
                    if mo.contraste("#ffffff", mo.PALETA[m.group(1)][m.group(2)]) < 4.5:
                        malos.append((os.path.relpath(ruta, RAIZ), t))
    assert not malos, malos
