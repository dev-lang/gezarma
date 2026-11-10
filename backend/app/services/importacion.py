"""
importacion.py — Importar productos y repuestos desde Excel (.xlsx) o CSV.

Flujo: el archivo se lee (leer), cada fila se valida contra lo que ya hay en la
base (analizar) y se muestra una vista previa; al confirmar se vuelve a leer y
validar el mismo archivo y se aplica (aplicar). Nunca se confía en la vista previa.

- Las columnas se reconocen por nombre, sin importar mayúsculas, tildes ni el
  idioma (código / codigo / code / SKU…). Las que no se reconocen se ignoran.
- Clave: repuestos por código; productos por N° de parte o, si no tiene, por
  marca + modelo. Si ya existe, se actualiza (o se omite, según la opción).
- Una celda vacía al actualizar = no se toca ese dato.
- Un cambio de stock queda como movimiento de ajuste, así el historial cierra.
"""
import csv
import io
import re
import unicodedata

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models
from . import stock_service

MAX_BYTES = 5 * 1024 * 1024
MAX_FILAS = 5000

# campo → (encabezado de la plantilla, sinónimos aceptados)
CAMPOS = {
    "repuestos": {
        "codigo":       ("Código", ["codigo", "cod", "code", "sku", "codigo interno", "part code"]),
        "nombre":       ("Nombre", ["nombre", "descripcion", "repuesto", "name", "description", "nome", "descricao", "articulo", "item"]),
        "proveedor":    ("Proveedor", ["proveedor", "supplier", "vendor", "fornecedor"]),
        "precio":       ("Precio", ["precio", "precio venta", "precio de venta", "price", "preco", "valor"]),
        "stock":        ("Stock", ["stock", "cantidad", "existencia", "existencias", "qty", "quantity", "estoque", "quantidade"]),
        "stock_minimo": ("Stock mínimo", ["stock minimo", "minimo", "stock min", "min", "minimum stock", "min stock", "estoque minimo"]),
        "categoria":    ("Categoría", ["categoria", "rubro", "category", "tipo"]),
        # "Depósito > Estante C > Cajón 4": las ubicaciones que no existan se crean
        "ubicacion_ruta": ("Ubicación", ["ubicacion", "ubicación", "lugar", "estante", "deposito", "location", "bin",
                                         "localizacao", "localização"]),
    },
    "productos": {
        "marca":        ("Marca", ["marca", "brand", "fabricante", "manufacturer"]),
        "modelo":       ("Modelo", ["modelo", "model", "producto", "product", "produto"]),
        "categoria":    ("Categoría", ["categoria", "rubro", "category", "tipo"]),
        "periodo_garantia_meses": ("Garantía (meses)", ["garantia", "garantia meses", "garantia (meses)", "meses de garantia",
                                                        "periodo garantia meses", "periodo_garantia_meses", "warranty",
                                                        "warranty months", "warranty (months)", "garantia (meses)"]),
        "numero_parte": ("N° de parte", ["n de parte", "nro de parte", "numero de parte", "numero parte", "part number",
                                         "pn", "p/n", "mpn", "numero_parte", "n° de parte", "no de parte", "numero da peca"]),
    },
}
OBLIGATORIOS = {"repuestos": ["codigo", "nombre"], "productos": ["marca", "modelo"]}
ENTEROS = {"stock", "stock_minimo", "periodo_garantia_meses"}
DECIMALES = {"precio"}
EJEMPLOS = {
    "repuestos": [["PX-X515", "Pantalla 15.6\" FHD", "Distribuidora Sur", "85000", "4", "2", "Pantallas", "Depósito > Estante A"],
                  ["BAT-X515", "Batería ASUS X515", "ElectroParts", "42000,50", "6", "2", "Baterías", "Depósito > Estante C > Cajón 4"]],
    "productos": [["ASUS", "X515 Laptop", "Notebooks", "12", "X515EA"],
                  ["Samsung", "Odyssey G5", "Monitores", "36", ""]],
}


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[_\-\.:#]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _sinonimos(tipo: str) -> dict:
    out = {}
    for campo, (encabezado, sin) in CAMPOS[tipo].items():
        for n in [campo, encabezado, *sin]:
            out[_norm(n)] = campo
    return out


# ── Lectura del archivo ──────────────────────────────────────────────────────
def leer(contenido: bytes, nombre_archivo: str) -> tuple[list, list]:
    """(encabezados, filas) con las celdas como texto. Primera fila no vacía = encabezados."""
    if len(contenido) > MAX_BYTES:
        raise HTTPException(400, "El archivo supera los 5 MB.")
    ext = (nombre_archivo or "").rsplit(".", 1)[-1].lower()
    if ext == "xlsx":
        filas = _leer_xlsx(contenido)
    elif ext in ("csv", "txt"):
        filas = _leer_csv(contenido)
    else:
        raise HTTPException(400, "Formato no soportado: subí un archivo .xlsx o .csv.")
    filas = [[("" if c is None else str(c).strip()) for c in f] for f in filas]
    filas = [f for f in filas if any(f)]
    if not filas:
        raise HTTPException(400, "El archivo está vacío.")
    encabezados, datos = filas[0], filas[1:]
    if len(datos) > MAX_FILAS:
        raise HTTPException(400, f"El archivo tiene {len(datos)} filas: el máximo es {MAX_FILAS}.")
    return encabezados, datos


def _leer_xlsx(contenido: bytes) -> list:
    from openpyxl import load_workbook
    try:
        wb = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    except Exception:
        raise HTTPException(400, "No se pudo leer el Excel. ¿Es un .xlsx válido?")
    hoja = wb.worksheets[0]
    filas = []
    for fila in hoja.iter_rows(values_only=True):
        filas.append([_celda_xlsx(c) for c in fila])
        if len(filas) > MAX_FILAS + 50:
            break
    wb.close()
    return filas


def _celda_xlsx(c):
    if isinstance(c, float) and c.is_integer():
        return str(int(c))
    return c


def _leer_csv(contenido: bytes) -> list:
    for cod in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            texto = contenido.decode(cod)
            break
        except UnicodeDecodeError:
            continue
    muestra = texto[:4096]
    try:
        dialecto = csv.Sniffer().sniff(muestra, delimiters=";,\t|")
    except csv.Error:
        dialecto = csv.excel
        dialecto.delimiter = ";" if muestra.count(";") > muestra.count(",") else ","
    return list(csv.reader(io.StringIO(texto), dialecto))


# ── Conversión de valores ────────────────────────────────────────────────────
def _numero(texto: str) -> float:
    """'1.234,50', '1234.50', '$ 1.234', '1,5' → float. ValueError si no es un número."""
    t = re.sub(r"[^\d,.\-]", "", texto)
    if not t or t in "-.,":
        raise ValueError
    if "," in t and "." in t:
        # el último separador es el decimal
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        partes = t.split(",")
        t = t.replace(",", ".") if len(partes) == 2 and len(partes[1]) != 3 else t.replace(",", "")
    elif t.count(".") > 1 or (t.count(".") == 1 and len(t.split(".")[1]) == 3 and len(t.split(".")[0]) <= 3
                               and t.split(".")[0] not in ("0", "-0")):
        t = t.replace(".", "")          # 1.234 → miles
    return float(t)


def _valor(campo: str, texto: str):
    if campo == "ubicacion_ruta":
        import re
        return " › ".join(p.strip() for p in re.split(r"\s*[>›/]\s*", texto) if p.strip())
    if campo in ENTEROS:
        n = _numero(texto)
        if not n.is_integer():
            raise ValueError("entero")
        return int(n)
    if campo in DECIMALES:
        return round(_numero(texto), 2)
    return texto


# ── Análisis ─────────────────────────────────────────────────────────────────
def _clave_producto(marca, modelo) -> str:
    return f"{_norm(marca)}|{_norm(modelo)}"


def analizar(db: Session, tipo: str, encabezados: list, filas: list, actualizar: bool = True) -> dict:
    if tipo not in CAMPOS:
        raise HTTPException(404, "Tipo de importación inexistente")
    sin = _sinonimos(tipo)
    columnas = {}            # índice → campo
    ignoradas = []
    for i, h in enumerate(encabezados):
        campo = sin.get(_norm(h))
        if campo and campo not in columnas.values():
            columnas[i] = campo
        elif h:
            ignoradas.append(h)
    faltan = [CAMPOS[tipo][c][0] for c in OBLIGATORIOS[tipo] if c not in columnas.values()]
    if faltan:
        raise HTTPException(400, f"Faltan columnas obligatorias: {', '.join(faltan)}. "
                                 "Descargá la plantilla para ver el formato.")

    if tipo == "repuestos":
        existentes = {_norm(r.codigo): r for r in db.query(models.Repuesto).all() if r.codigo}
    else:
        prods = db.query(models.Producto).all()
        existentes = {_clave_producto(p.marca, p.modelo): p for p in prods}
        por_parte = {_norm(p.numero_parte): p for p in prods if p.numero_parte}

    vistos, resultado = {}, []
    for n, fila in enumerate(filas, start=2):          # fila 1 = encabezados
        datos, errores = {}, []
        for i, campo in columnas.items():
            texto = fila[i] if i < len(fila) else ""
            if texto == "":
                continue
            try:
                datos[campo] = _valor(campo, texto)
            except ValueError:
                nombre = CAMPOS[tipo][campo][0]
                errores.append(f"{nombre}: «{texto}» no es un número entero" if campo in ENTEROS
                               else f"{nombre}: «{texto}» no es un número")
        for campo in ENTEROS | DECIMALES:
            if isinstance(datos.get(campo), (int, float)) and datos[campo] < 0:
                errores.append(f"{CAMPOS[tipo].get(campo, (campo,))[0]} no puede ser negativo")

        # Buscar si ya existe
        if tipo == "repuestos":
            clave = _norm(datos.get("codigo"))
            existente = existentes.get(clave) if clave else None
        else:
            clave = _clave_producto(datos.get("marca"), datos.get("modelo"))
            existente = (por_parte.get(_norm(datos["numero_parte"])) if datos.get("numero_parte") else None) \
                or existentes.get(clave)
        for c in OBLIGATORIOS[tipo]:
            if not datos.get(c) and not existente:
                errores.append(f"Falta {CAMPOS[tipo][c][0]}")
        if clave and clave.strip("|"):
            if clave in vistos:
                errores.append(f"Repetido: ya está en la fila {vistos[clave]}")
            else:
                vistos[clave] = n
        if tipo == "productos" and datos.get("numero_parte"):
            otro = por_parte.get(_norm(datos["numero_parte"]))
            if otro and existente and otro.id != existente.id:
                errores.append(f"El N° de parte ya lo tiene {otro.marca} {otro.modelo}")

        cambios = {}
        if existente:
            for campo, valor in datos.items():
                actual = getattr(existente, campo)
                if campo in DECIMALES and actual is not None:
                    igual = abs(float(actual) - float(valor)) < 0.005
                else:
                    igual = str(actual if actual is not None else "") == str(valor)
                if not igual:
                    cambios[campo] = [actual, valor]

        if errores:
            accion = "error"
        elif not existente:
            accion = "crear"
        elif not actualizar:
            accion = "omitir"
        else:
            accion = "actualizar" if cambios else "sin_cambios"
        resultado.append({"fila": n, "accion": accion, "datos": datos, "errores": errores,
                          "cambios": cambios, "id": existente.id if existente else None})

    resumen = {a: sum(1 for r in resultado if r["accion"] == a)
               for a in ("crear", "actualizar", "sin_cambios", "omitir", "error")}
    return {
        "tipo": tipo, "total": len(resultado), "resumen": resumen, "filas": resultado,
        "columnas": [CAMPOS[tipo][c][0] for c in columnas.values()],
        "ignoradas": ignoradas,
    }


# ── Aplicar ──────────────────────────────────────────────────────────────────
def aplicar(db: Session, analisis: dict, usuario: models.Usuario, nombre_archivo: str) -> dict:
    """Crea y actualiza las filas válidas (las con error se saltean). Una sola transacción."""
    tipo = analisis["tipo"]
    nota = f"Importación de «{nombre_archivo}» por {usuario.nombre}"
    creados = actualizados = 0
    for r in analisis["filas"]:
        if r["accion"] == "crear":
            datos = dict(r["datos"])
            if tipo == "repuestos":
                stock = datos.pop("stock", 0) or 0
                ubic = datos.pop("ubicacion_ruta", None)
                datos.setdefault("categoria", "General")
                datos.setdefault("proveedor", "")
                obj = models.Repuesto(**datos, stock=0)
                db.add(obj)
                db.flush()
                if stock:
                    _mover_stock(db, obj, stock, usuario, nota)
                if ubic:
                    _ubicar(db, obj, ubic, usuario)
            else:
                datos.setdefault("categoria", "General")
                datos.setdefault("periodo_garantia_meses", 12)
                db.add(models.Producto(**datos))
            creados += 1
        elif r["accion"] == "actualizar":
            modelo = models.Repuesto if tipo == "repuestos" else models.Producto
            obj = db.get(modelo, r["id"])
            datos = dict(r["datos"])
            stock = datos.pop("stock", None) if tipo == "repuestos" else None
            ubic = datos.pop("ubicacion_ruta", None) if tipo == "repuestos" else None
            if ubic:
                _ubicar(db, obj, ubic, usuario)
            for campo, valor in datos.items():
                setattr(obj, campo, valor)
            if stock is not None and stock != obj.stock:
                anterior = obj.stock
                _mover_stock(db, obj, stock - obj.stock, usuario, nota)
                stock_service.revisar_minimo(db, obj, anterior)
            actualizados += 1
    db.commit()
    return {"creados": creados, "actualizados": actualizados,
            "sin_cambios": analisis["resumen"]["sin_cambios"], "omitidos": analisis["resumen"]["omitir"],
            "con_error": analisis["resumen"]["error"]}


def _ubicar(db, repuesto, ruta_texto, usuario):
    from . import ubicaciones
    destino = ubicaciones.desde_texto(db, ruta_texto)
    db.flush()
    ubicaciones.mover_repuestos(db, [repuesto.id], destino.id if destino else None, usuario, motivo="importacion")


def _mover_stock(db, repuesto, delta, usuario, nota):
    anterior, nuevo = stock_service.ajustar(db, repuesto, delta)
    db.add(models.StockMovimiento(repuesto_id=repuesto.id, usuario_id=usuario.id, tipo="ajuste",
                                  cantidad=nuevo - anterior, stock_anterior=anterior, stock_nuevo=nuevo, nota=nota))


# ── Plantillas ───────────────────────────────────────────────────────────────
def plantilla(db: Session, tipo: str, formato: str, con_datos: bool) -> tuple[bytes, str]:
    """La plantilla vacía (con dos filas de ejemplo) o con los datos actuales, para editar y volver a subir."""
    if tipo not in CAMPOS:
        raise HTTPException(404, "Tipo de importación inexistente")
    campos = list(CAMPOS[tipo])
    encabezados = [CAMPOS[tipo][c][0] for c in campos]
    if con_datos:
        modelo = models.Repuesto if tipo == "repuestos" else models.Producto
        orden = models.Repuesto.codigo if tipo == "repuestos" else models.Producto.marca
        filas = [[_texto(getattr(o, c)) for c in campos] for o in db.query(modelo).order_by(orden).all()]
    else:
        filas = EJEMPLOS[tipo]
    if formato == "csv":
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")   # ; para que Excel en español lo abra en columnas
        w.writerow(encabezados)
        w.writerows([[_celda_segura(v) for v in f] for f in filas])
        return ("﻿" + buf.getvalue()).encode("utf-8"), "text/csv; charset=utf-8"
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = tipo.capitalize()
    ws.append(encabezados)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="2563EB")
    for f in filas:
        ws.append([_numero_si_puede(campos[i], _celda_segura(v)) for i, v in enumerate(f)])
    for i, h in enumerate(encabezados, start=1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = max(14, len(h) + 4)
    ws.freeze_panes = "A2"
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _texto(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.2f}".rstrip("0").rstrip(".") if v != int(v) else str(int(v))
    return str(v)


def _numero_si_puede(campo, v):
    if campo in ENTEROS | DECIMALES and v != "":
        try:
            return _valor(campo, v)
        except ValueError:
            return v
    return v


def _celda_segura(v: str) -> str:
    """Evita que una celda se interprete como fórmula al abrirla en Excel (=, +, -, @)."""
    v = str(v)
    return "'" + v if v[:1] in ("=", "+", "@") or (v[:1] == "-" and not re.fullmatch(r"-?[\d.,]+", v)) else v
