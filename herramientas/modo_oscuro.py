"""Genera frontend/css/oscuro.css: la versión oscura de cada clase de color de Tailwind que usa el frontend.

Recorre el HTML y el JS del frontend, junta todas las clases de color (con sus variantes —hover:,
has-[:checked]:, peer-checked:…— y su opacidad /50) y escribe, para cada una, la regla `.dark …`
que le corresponde según la paleta de abajo. El modo claro no se toca.

    python herramientas/modo_oscuro.py            # regenera el archivo
    python herramientas/modo_oscuro.py --revisar  # solo avisa si está desactualizado

tests/test_modo_oscuro.py falla si alguien usa una clase nueva y no regeneró el archivo, o si
aparece una variante que este script no sabe traducir.
"""
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(RAIZ, "frontend")
SALIDA = os.path.join(FRONTEND, "css", "oscuro.css")

TONOS = ("50", "100", "200", "300", "400", "500", "600", "700", "800", "900", "950")
_P = {
    "slate": "f8fafc f1f5f9 e2e8f0 cbd5e1 94a3b8 64748b 475569 334155 1e293b 0f172a 020617",
    "gray": "f9fafb f3f4f6 e5e7eb d1d5db 9ca3af 6b7280 4b5563 374151 1f2937 111827 030712",
    "zinc": "fafafa f4f4f5 e4e4e7 d4d4d8 a1a1aa 71717a 52525b 3f3f46 27272a 18181b 09090b",
    "neutral": "fafafa f5f5f5 e5e5e5 d4d4d4 a3a3a3 737373 525252 404040 262626 171717 0a0a0a",
    "stone": "fafaf9 f5f5f4 e7e5e4 d6d3d1 a8a29e 78716c 57534e 44403c 292524 1c1917 0c0a09",
    "red": "fef2f2 fee2e2 fecaca fca5a5 f87171 ef4444 dc2626 b91c1c 991b1b 7f1d1d 450a0a",
    "orange": "fff7ed ffedd5 fed7aa fdba74 fb923c f97316 ea580c c2410c 9a3412 7c2d12 431407",
    "amber": "fffbeb fef3c7 fde68a fcd34d fbbf24 f59e0b d97706 b45309 92400e 78350f 451a03",
    "yellow": "fefce8 fef9c3 fef08a fde047 facc15 eab308 ca8a04 a16207 854d0e 713f12 422006",
    "lime": "f7fee7 ecfccb d9f99d bef264 a3e635 84cc16 65a30d 4d7c0f 3f6212 365314 1a2e05",
    "green": "f0fdf4 dcfce7 bbf7d0 86efac 4ade80 22c55e 16a34a 15803d 166534 14532d 052e16",
    "emerald": "ecfdf5 d1fae5 a7f3d0 6ee7b7 34d399 10b981 059669 047857 065f46 064e3b 022c22",
    "teal": "f0fdfa ccfbf1 99f6e4 5eead4 2dd4bf 14b8a6 0d9488 0f766e 115e59 134e4a 042f2e",
    "cyan": "ecfeff cffafe a5f3fc 67e8f9 22d3ee 06b6d4 0891b2 0e7490 155e75 164e63 083344",
    "sky": "f0f9ff e0f2fe bae6fd 7dd3fc 38bdf8 0ea5e9 0284c7 0369a1 075985 0c4a6e 082f49",
    "blue": "eff6ff dbeafe bfdbfe 93c5fd 60a5fa 3b82f6 2563eb 1d4ed8 1e40af 1e3a8a 172554",
    "indigo": "eef2ff e0e7ff c7d2fe a5b4fc 818cf8 6366f1 4f46e5 4338ca 3730a3 312e81 1e1b4b",
    "violet": "f5f3ff ede9fe ddd6fe c4b5fd a78bfa 8b5cf6 7c3aed 6d28d9 5b21b6 4c1d95 2e1065",
    "purple": "faf5ff f3e8ff e9d5ff d8b4fe c084fc a855f7 9333ea 7e22ce 6b21a8 581c87 3b0764",
    "fuchsia": "fdf4ff fae8ff f5d0fe f0abfc e879f9 d946ef c026d3 a21caf 86198f 701a75 4a044e",
    "pink": "fdf2f8 fce7f3 fbcfe8 f9a8d4 f472b6 ec4899 db2777 be185d 9d174d 831843 500724",
    "rose": "fff1f2 ffe4e6 fecdd3 fda4af fb7185 f43f5e e11d48 be123c 9f1239 881337 4c0519",
}
PALETA = {c: dict(zip(TONOS, ("#" + x for x in v.split()))) for c, v in _P.items()}
GRISES = {"slate", "gray", "zinc", "neutral", "stone"}

# ── Paleta oscura ───────────────────────────────────────────────────────────────────────────────
TARJETA = "#1e293b"   # bg-white
FONDO = "#0f172a"     # bg-gray-50 (fondo de la página)

# Grises: fondo, texto y borde. Los textos dan ≥ 4,5:1 sobre las tarjetas, sobre bg-gray-100 y sobre los fondos suaves (bg-blue-50).
GRIS_BG = {"white": TARJETA, "50": FONDO, "100": "#334155", "200": "#334155", "300": "#475569", "800": FONDO}
# Al pasar el mouse sobre una fila de una tarjeta, se aclara apenas (en vez de oscurecerse hacia el fondo)
GRIS_BG_HOVER = {"50": "#263347", "100": "#334155"}
# Fondos grises translúcidos (bg-gray-50/50: filas alternadas, pies de tarjeta): un punto entre fondo y tarjeta
GRIS_BG_SUAVE = {"50": "#172234", "100": "#2a3649"}
GRIS_TEXTO = {"black": "#e2e8f0", "950": "#e2e8f0", "900": "#e2e8f0", "800": "#e2e8f0", "700": "#cbd5e1",
              "600": "#b8c3d1", "500": "#adb9c8", "400": "#a4b2c3", "300": "#9cabbe"}
GRIS_BORDE = {"white": TARJETA, "50": TARJETA, "100": TARJETA, "200": "#334155", "300": "#475569", "400": "#64748b"}

# Fondos suaves de color (bg-*-50 y bg-*-100/200) y sus bordes. Los colores que no están acá se calculan.
TINTE_50 = {"blue": "#1e3a5f", "green": "#14281e", "emerald": "#0f2a22", "amber": "#2d1f07", "yellow": "#2a2507",
            "orange": "#2d1607", "red": "#2d0f0f", "rose": "#2d0f18", "indigo": "#1a1a3e", "violet": "#1f1535",
            "purple": "#1e102e", "teal": "#0f2828", "cyan": "#0c2730", "sky": "#0c2433"}
TINTE_100 = {"blue": "#1e40af55", "green": "#14532d", "emerald": "#064e3b", "amber": "#78350f66", "yellow": "#713f1266",
             "orange": "#7c2d1266", "red": "#7f1d1d66", "rose": "#88133766", "indigo": "#312e81", "violet": "#4c1d95",
             "purple": "#581c87", "teal": "#134e4a", "cyan": "#164e63", "sky": "#0c4a6e"}
BORDE_SUAVE = {"blue": "#1e3a8a", "green": "#166534", "emerald": "#065f46", "amber": "#92400e", "yellow": "#854d0e",
               "orange": "#9a3412", "red": "#991b1b", "rose": "#9f1239", "indigo": "#3730a3", "violet": "#5b21b6",
               "purple": "#6b21a8", "teal": "#115e59", "cyan": "#155e75", "sky": "#075985"}


def _rgb(h):
    h = h.lstrip("#")[:6]
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _hex(rgb):
    return "#" + "".join(f"{round(x):02x}" for x in rgb)


def _mezcla(a, b, t):
    """t de a, (1 - t) de b."""
    return _hex(tuple(x * t + y * (1 - t) for x, y in zip(_rgb(a), _rgb(b))))


def luminancia(h):
    def canal(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(x) for x in _rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a, b):
    la, lb = sorted((luminancia(a), luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _tinte50(c):
    return TINTE_50.get(c) or _mezcla(PALETA[c]["900"], FONDO, 0.3)


def _tinte100(c):
    return TINTE_100.get(c) or _mezcla(PALETA[c]["900"], TARJETA, 0.7)


def _borde_suave(c):
    return BORDE_SUAVE.get(c) or PALETA[c]["800"]


def _alfa(color, op):
    """Aplica la opacidad /NN de la clase (solo cuando es casi opaca: los fondos oscuros ya son suaves)."""
    if op is None or op >= 80:
        return color if op is None or op == 100 else f"{color[:7]}{round(op * 2.55):02x}"
    return color


def oscuro(prop, color, tono, op, hover=False):
    """Color de la versión oscura, o None si la clase se ve bien como está."""
    gris = color in GRISES or color in ("white", "black")
    clave = color if color in ("white", "black") else tono
    if prop == "bg" or prop in ("from", "via", "to"):
        if gris:
            if hover and clave in GRIS_BG_HOVER:
                return GRIS_BG_HOVER[clave]
            if op is not None and op < 80 and clave in GRIS_BG_SUAVE:
                return GRIS_BG_SUAVE[clave]
            v = GRIS_BG.get(clave)
            return _alfa(v, op) if v else None
        if tono == "50":
            return _alfa(_tinte50(color), op)
        if tono in ("100", "200"):
            return _alfa(_tinte100(color), op)
        return None
    if prop in ("text", "placeholder", "fill", "stroke", "decoration", "caret"):
        if gris:
            return GRIS_TEXTO.get(clave)
        if tono in ("500", "600"):
            return PALETA[color]["400"]
        if tono in ("700", "800", "900", "950"):
            return PALETA[color]["300"]
        return None
    if prop in ("border", "ring", "divide", "outline", "ring-offset"):
        if gris:
            return GRIS_BORDE.get(clave)
        if tono in ("50", "100", "200"):
            return _borde_suave(color)
        if tono == "300":
            return PALETA[color]["700"]
        return None
    return None


# ── Lectura de las clases ───────────────────────────────────────────────────────────────────────
COLORES = "|".join(sorted(PALETA, key=len, reverse=True))
PROPS = ("ring-offset|border-[trblxyse]|border|bg|text|ring|divide|outline|placeholder|from|via|to|"
         "fill|stroke|decoration|caret|accent|shadow")
VARIANTE = r"(?:[a-z0-9-]+(?:-\[[^\]\s'\"`]+\])?|\[[^\]\s'\"`]+\]):"
RE_VARIANTE = re.compile(VARIANTE)
RE_CLASE = re.compile(
    rf"(?<![\w\-:/\[\]$.])((?:{VARIANTE})*)({PROPS})-(?:(white|black)|({COLORES})-(50|[1-9]00|950))"
    rf"(?:/(\d{{1,3}}))?(?![\w\-/\[])")
# Clases armadas con plantillas: bg-${c}-100 → se generan para todos los colores
RE_DINAMICA = re.compile(rf"(?<![\w\-])((?:{VARIANTE})*)({PROPS})-\$\{{[^}}]+\}}-(50|[1-9]00|950)(?![\w\-])")

PSEUDO = {
    "hover": ":hover", "focus": ":focus", "focus-visible": ":focus-visible", "focus-within": ":focus-within",
    "active": ":active", "disabled": ":disabled", "enabled": ":enabled", "checked": ":checked",
    "indeterminate": ":indeterminate", "invalid": ":invalid", "required": ":required", "read-only": ":read-only",
    "first": ":first-child", "last": ":last-child", "odd": ":nth-child(odd)", "even": ":nth-child(even)",
    "only": ":only-child", "empty": ":empty", "open": "[open]", "target": ":target", "visited": ":visited",
    "placeholder-shown": ":placeholder-shown", "first-of-type": ":first-of-type", "last-of-type": ":last-of-type",
}
ELEMENTO = {"placeholder": "::placeholder", "file": "::file-selector-button"}
SIN_OSCURO = {"after", "before", "print", "selection", "marker"}  # pseudo-elementos decorativos e impresión
MEDIA = {"sm": "(min-width: 640px)", "md": "(min-width: 768px)", "lg": "(min-width: 1024px)",
         "xl": "(min-width: 1280px)", "2xl": "(min-width: 1536px)",
         "max-sm": "not all and (min-width: 640px)", "max-md": "not all and (min-width: 768px)",
         "max-lg": "not all and (min-width: 1024px)", "max-xl": "not all and (min-width: 1280px)"}


class VarianteDesconocida(ValueError):
    pass


def _arbitrario(v):
    return v.replace("_", " ")


def _condicion(v):
    """Una variante de estado (hover, has-[…], aria-…, data-[…]) → el pedazo de selector que agrega."""
    if v in PSEUDO:
        return PSEUDO[v]
    m = re.fullmatch(r"has-\[(.+)\]", v)
    if m:
        return f":has({_arbitrario(m.group(1))})"
    m = re.fullmatch(r"aria-\[(.+)\]", v)
    if m:
        return f"[aria-{_arbitrario(m.group(1))}]"
    m = re.fullmatch(r"aria-([a-z-]+)", v)
    if m:
        return f'[aria-{m.group(1)}="true"]'
    m = re.fullmatch(r"data-\[(.+)\]", v)
    if m:
        return f"[data-{_arbitrario(m.group(1))}]"
    m = re.fullmatch(r"\[(&?)(:.+|\[.+\])\]", v)
    if m:
        return _arbitrario(m.group(2))
    raise VarianteDesconocida(v)


def escapar(clase):
    return re.sub(r"([^a-zA-Z0-9_-])", r"\\\1", clase)


def selector(variantes, clase):
    """(selector, media o None) como los arma Tailwind 3; None si la clase no necesita versión oscura."""
    sel, antes, media, final = "." + escapar(clase), "", None, ""
    for v in variantes:
        if v in SIN_OSCURO:
            return None
        if v in MEDIA:
            media = MEDIA[v]
            continue
        m = re.fullmatch(r"\[@media(.+)\]", v)
        if m:
            media = _arbitrario(m.group(1))
            continue
        if v in ELEMENTO:
            final = ELEMENTO[v]
            continue
        m = re.fullmatch(r"(group|peer)-(.+)", v)
        if m:
            cond = _condicion(m.group(2))
            antes += f".{m.group(1)}{cond} " + ("~ " if m.group(1) == "peer" else "")
            continue
        sel += _condicion(v)
    return antes + sel + final, media


def archivos():
    for raiz, _, nombres in os.walk(FRONTEND):
        if os.path.join(FRONTEND, "css") in raiz:
            continue
        for n in sorted(nombres):
            if n.endswith((".html", ".js")):
                yield os.path.join(raiz, n)


def clases_usadas():
    """{clase completa: (variantes, prop, color, tono, opacidad)} + combinaciones fondo claro/texto oscuro."""
    vistas, juntas = {}, set()
    for ruta in sorted(archivos()):
        texto = open(ruta, encoding="utf-8").read()
        for m in RE_CLASE.finditer(texto):
            pre, prop, bn, color, tono, op = m.groups()
            vistas[m.group(0)] = (tuple(v[:-1] for v in RE_VARIANTE.findall(pre)), prop, bn or color, tono or "", int(op) if op else None)
        for m in RE_DINAMICA.finditer(texto):
            pre, prop, tono = m.groups()
            for color in PALETA:
                if color in GRISES:
                    continue
                c = f"{pre}{prop}-{color}-{tono}"
                vistas.setdefault(c, (tuple(v[:-1] for v in RE_VARIANTE.findall(pre)), prop, color, tono, None))
        # Fondo de color fuerte con texto oscuro (el botón amarillo de Favoritos): el texto queda oscuro
        for cadena in re.findall(r"""class(?:Name)?\s*[=:+]\s*[`'"]([^`'"]*)[`'"]|[`'"]([^`'"\n]{0,400})[`'"]""", texto):
            tokens = set((cadena[0] or cadena[1]).split())
            fondos = [t for t in tokens if re.fullmatch(rf"bg-(?:{COLORES})-(?:300|400|500)", t)]
            textos = [t for t in tokens if re.fullmatch(rf"text-(?:{COLORES})-(?:700|800|900|950)", t)]
            for f in fondos:
                if f.split("-")[1] in ("amber", "yellow", "lime") or f.endswith(("-300", "-400")):
                    juntas.update((f, t) for t in textos)
    return vistas, juntas


CSS_PROP = {
    "bg": "background-color", "text": "color", "border": "border-color", "border-t": "border-top-color",
    "border-b": "border-bottom-color", "border-l": "border-left-color", "border-r": "border-right-color",
    "border-x": "border-left-color: {v} !important; border-right-color", "border-y": "border-top-color: {v} !important; border-bottom-color",
    "border-s": "border-inline-start-color", "border-e": "border-inline-end-color",
    "ring": "--tw-ring-color", "ring-offset": "--tw-ring-offset-color", "outline": "outline-color",
    "placeholder": "color", "fill": "fill", "stroke": "stroke", "decoration": "text-decoration-color",
    "caret": "caret-color", "divide": "border-color",
    "from": "--tw-gradient-from: {v} var(--tw-gradient-from-position) !important; --tw-gradient-to: transparent var(--tw-gradient-to-position) !important; --tw-gradient-stops",
    "via": "--tw-gradient-to: transparent var(--tw-gradient-to-position) !important; --tw-gradient-stops",
    "to": "--tw-gradient-to",
}
VALOR_STOPS = {"from": "var(--tw-gradient-from), var(--tw-gradient-to)",
               "via": "var(--tw-gradient-from), {v} var(--tw-gradient-via-position), var(--tw-gradient-to)",
               "to": "{v} var(--tw-gradient-to-position)"}

BASE = """/* ── Base del modo oscuro (compartida por la app y la página de seguimiento) ── */
html.dark { color-scheme: dark; }
.dark body { background: #0f172a; color: #e2e8f0; }
.dark *, .dark ::before, .dark ::after { border-color: #334155; }
.dark input, .dark textarea, .dark select { background: #0f172a !important; color: #e2e8f0 !important; border-color: #334155 !important; }
.dark input::placeholder, .dark textarea::placeholder { color: #8f9eb2 !important; }
.dark input:disabled, .dark textarea:disabled, .dark select:disabled { background: #1e293b !important; color: #8f9eb2 !important; }
.dark .shadow, .dark .shadow-sm { box-shadow: 0 1px 3px rgba(0,0,0,.5) !important; }
.dark .shadow-md, .dark .shadow-lg, .dark .shadow-xl, .dark .shadow-2xl { box-shadow: 0 4px 20px rgba(0,0,0,.6) !important; }
.dark nav { background: #0c1628 !important; }
.dark ::-webkit-scrollbar-corner { background: transparent; }
/* Etiquetas con el color que eligió el taller: el texto se aclara para que se lea sobre fondo oscuro */
.dark .color-propio { color: color-mix(in srgb, var(--c) 55%, #fff) !important; }
"""


def generar():
    vistas, juntas = clases_usadas()
    reglas, medias = [], {}
    for clase in sorted(vistas):
        variantes, prop, color, tono, op = vistas[clase]
        try:
            r = selector(variantes, clase)
        except VarianteDesconocida as e:
            raise VarianteDesconocida(f"{clase}: no sé traducir la variante «{e}» (agregarla en herramientas/modo_oscuro.py)")
        if r is None:
            continue
        sel, media = r
        if prop == "accent" or prop == "shadow":
            continue
        base = "border" if prop.startswith("border") else prop
        v = oscuro(base, color, tono, op, hover="hover" in variantes or "group-hover" in variantes)
        if v is None:
            if base != "border":
                continue
            # Los bordes de color fuerte se repiten tal cual: si no, les ganaría la regla general de .dark *
            v = PALETA[color][tono] if tono else ("#ffffff" if color == "white" else "#000000")
            if op is not None and op < 100:
                v += f"{round(op * 2.55):02x}"
        if prop == "divide":
            sel = f"{sel} > :not([hidden]) ~ :not([hidden])"
        decl = CSS_PROP[prop].replace("{v}", v)
        if prop in VALOR_STOPS:
            linea = f"{decl}: {VALOR_STOPS[prop].replace('{v}', v)} !important"
        else:
            linea = f"{decl}: {v} !important"
        regla = f".dark {sel} {{ {linea}; }}"
        (medias.setdefault(media, []) if media else reglas).append(regla)
    pares = [f".dark .{escapar(f)}.{escapar(t)} {{ color: {PALETA[t.split('-')[1]][t.split('-')[2]]} !important; }}"
             for f, t in sorted(juntas)]
    partes = [
        "/* Generado por herramientas/modo_oscuro.py — no editar a mano: correr el script después de usar colores nuevos. */",
        BASE,
        f"/* ── {len(reglas) + sum(len(x) for x in medias.values())} clases de color usadas en el frontend ── */",
        *reglas,
    ]
    for media in sorted(medias):
        partes.append(f"@media {media} {{")
        partes += ["  " + r for r in medias[media]]
        partes.append("}")
    if pares:
        partes.append("/* Fondo de color fuerte con texto oscuro: el texto no se aclara */")
        partes += pares
    return "\n".join(partes) + "\n"


def main():
    css = generar()
    actual = open(SALIDA, encoding="utf-8").read() if os.path.exists(SALIDA) else ""
    if "--revisar" in sys.argv:
        if css != actual:
            print("frontend/css/oscuro.css está desactualizado: correr python herramientas/modo_oscuro.py")
            return 1
        print("oscuro.css al día")
        return 0
    os.makedirs(os.path.dirname(SALIDA), exist_ok=True)
    with open(SALIDA, "w", encoding="utf-8", newline="\n") as f:
        f.write(css)
    print(f"oscuro.css: {css.count(chr(10))} líneas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
