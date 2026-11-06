"""
idiomas.py — Traducción de los textos del sistema.

El sistema está escrito en español rioplatense (es-AR) y ese texto es la clave:
cada idioma tiene un diccionario JSON en traducciones/<código>.json con
{"texto original": "traducción"}. Las partes variables van como {0}, {1}…
("Hola {0}," → "Hi {0},"); al traducir se reconocen y lo que va en el lugar
de {0} se traduce a su vez si también está en el diccionario.

Lo usan:
- el frontend (mismo diccionario, servido en /i18n/<código>.js; ver js/i18n.js),
- los mensajes de error de la API (según el encabezado Accept-Language),
- los mails y los documentos (en el idioma del cliente o del taller).

Lo que no está en el diccionario queda en español: nunca se rompe nada.
"""
import html as _html
import json
import re
from functools import lru_cache
from pathlib import Path

BASE = "es-AR"
IDIOMAS = {
    "es-AR": "Español (Argentina)",
    "es-ES": "Español (España)",
    "en": "English",
    "pt-BR": "Português (Brasil)",
}
_DIR = Path(__file__).resolve().parent / "traducciones"
_PH = re.compile(r"\{(\d+)\}")


def normalizar(codigo) -> str | None:
    """'en-US' → 'en', 'pt' → 'pt-BR', 'es-MX' → 'es-AR'… None si no es uno de los nuestros."""
    if not codigo:
        return None
    c = str(codigo).strip().replace("_", "-")
    for k in IDIOMAS:
        if c.lower() == k.lower():
            return k
    base = c.split("-")[0].lower()
    return {"en": "en", "pt": "pt-BR", "es": BASE}.get(base)


def desde_header(accept_language: str | None) -> str:
    """El primer idioma soportado del encabezado Accept-Language (o el base)."""
    for parte in (accept_language or "").split(","):
        cod = normalizar(parte.split(";")[0])
        if cod:
            return cod
    return BASE


def _anclas(literal: str) -> list:
    return [w for w in re.findall(r"[^\W\d_]+", literal.lower()) if len(w) >= 3]


def _patron_valido(clave: str) -> bool:
    """Un patrón tiene que tener texto propio suficiente: "{0} de {1}" agarraría cualquier cosa."""
    literal = _PH.sub(" ", clave)
    if any(len(w) >= 4 for w in re.findall(r"[^\W\d_]+", literal)):
        return True
    return bool(re.match(r"^[^{]*[^\W\d_]{2,}[.:]\s*\{0\}", clave))   # "Rol: {0}", "mín. {0}"


@lru_cache(maxsize=None)
def diccionario(codigo: str):
    """(exactos, patrones, índice) del idioma; vacío para el idioma base."""
    exactos, patrones = {}, []
    ruta = _DIR / f"{codigo}.json"
    if codigo != BASE and ruta.exists():
        for k, v in json.loads(ruta.read_text(encoding="utf-8")).items():
            if not v or v == k:
                continue
            if _PH.search(k):
                if _patron_valido(k):
                    partes = _PH.split(k)   # literal, n, literal, n, …
                    rx = "".join(re.escape(p) if i % 2 == 0 else f"(?P<p{p}>.+?)" for i, p in enumerate(partes))
                    literal = "".join(partes[0::2])
                    try:
                        patrones.append((len(literal), re.compile(rx, re.S), v, _anclas(literal)))
                    except re.error:   # p. ej. el mismo {0} dos veces
                        continue
            else:
                exactos[" ".join(k.split())] = v
    patrones.sort(key=lambda p: -p[0])
    indice = {}
    for n, p in enumerate(patrones):
        for a in p[3] or [""]:
            indice.setdefault(a, []).append(n)
    return exactos, patrones, indice


def tr(texto, idioma: str | None, _prof: int = 0):
    """Traduce un texto (o lo devuelve igual). Respeta espacios al principio y al final."""
    if not texto or not isinstance(texto, str) or not idioma or idioma == BASE:
        return texto
    exactos, patrones, indice = diccionario(idioma)
    nucleo = texto.strip()
    if not nucleo:
        return texto
    ini, fin = texto[: len(texto) - len(texto.lstrip())], texto[len(texto.rstrip()):]
    clave = " ".join(nucleo.split())
    if clave in exactos:
        return ini + exactos[clave] + fin
    if _prof > 2:
        return texto
    if " · " in clave:   # "Ingresó el 3/11 · en garantía": se traduce cada parte
        partes = clave.split(" · ")
        trad = [tr(x, idioma, _prof + 1) for x in partes]
        if trad != partes:
            return ini + " · ".join(trad) + fin
    palabras = set(re.findall(r"[^\W\d_]+", clave.lower()))
    candidatos = sorted({n for w in palabras for n in indice.get(w, ())} | set(indice.get("", ())))
    for n in candidatos:
        _, rx, destino, _a = patrones[n]
        m = rx.fullmatch(clave)
        if m:
            valores = {k[1:]: tr(v, idioma, _prof + 1) for k, v in m.groupdict().items()}
            return ini + _PH.sub(lambda x: valores.get(x.group(1), x.group(0)), destino) + fin
    return texto


_TEXTO_HTML = re.compile(r"(<(script|style)\b.*?</\2>)|>([^<]+)<", re.S | re.I)


def traducir_html(doc: str, idioma: str | None) -> str:
    """Traduce el texto visible de un HTML ya armado (mails, documentos)."""
    if not idioma or idioma == BASE:
        return doc

    def cambiar(m):
        if m.group(1):
            return m.group(1)
        crudo = m.group(3)
        if not crudo.strip():
            return m.group(0)
        nuevo = tr(_html.unescape(crudo), idioma)
        if nuevo == _html.unescape(crudo):
            return m.group(0)
        return ">" + _html.escape(nuevo, quote=False) + "<"
    return _TEXTO_HTML.sub(cambiar, doc)


def js(codigo: str) -> str:
    """El diccionario como script para el navegador."""
    ruta = _DIR / f"{codigo}.json"
    datos = ruta.read_text(encoding="utf-8") if codigo != BASE and ruta.exists() else "{}"
    return f"window.I18N_IDIOMA={json.dumps(codigo)};window.I18N_DICT={datos};\n"


def de_usuario(db, usuario) -> str:
    """Idioma para escribirle a un usuario: el que eligió o el del taller."""
    cod = normalizar(getattr(usuario, "idioma", None)) if usuario is not None else None
    if cod:
        return cod
    from . import ajustes
    return normalizar(ajustes.get(db, "idioma_predeterminado")) or BASE
