"""Importar productos y repuestos desde .xlsx y .csv."""
import io
import uuid

import pytest
from openpyxl import Workbook, load_workbook

from backend.app.services.importacion import _numero


def _xlsx(filas):
    wb = Workbook()
    for f in filas:
        wb.active.append(f)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _csv(filas, sep=";", cod="utf-8"):
    return "\n".join(sep.join(str(c) for c in f) for f in filas).encode(cod)


def _subir(client, admin, tipo, contenido, nombre, previa=True, actualizar=True):
    url = f"/importar/{tipo}/vista-previa" if previa else f"/importar/{tipo}"
    return client.post(url, headers=admin, files={"archivo": (nombre, contenido)},
                       data={"actualizar": "true" if actualizar else "false"})


@pytest.mark.parametrize("texto,valor", [("1.234,50", 1234.5), ("1234.50", 1234.5), ("$ 85.000", 85000), ("1,5", 1.5),
                                         ("12", 12), ("1,234.5", 1234.5), ("0.75", 0.75), ("-3", -3)])
def test_numeros_en_formato_argentino_e_internacional(texto, valor):
    assert _numero(texto) == valor


def test_repuestos_desde_xlsx_crea_actualiza_y_registra_stock(client, admin):
    cod = f"IMP-{uuid.uuid4().hex[:5]}"
    client.post("/parts/", headers=admin, json={"nombre": "Viejo", "codigo": cod + "-A", "stock": 2, "proveedor": "x", "precio": 10})
    archivo = _xlsx([
        ["Código", "Descripción", "Proveedor", "Precio", "Stock", "Stock mínimo", "Columna rara"],
        [cod + "-A", "Pantalla nueva", "Sur", 1500.5, 5, 1, "x"],   # existe: cambia nombre, precio y stock
        [cod + "-B", "Batería", "Sur", "42.000,50", 3, None, None],   # nuevo
        [cod + "-C", "Sin precio", None, "abc", None, None, None],   # error
        [cod + "-B", "Repetido", None, None, None, None, None],     # error: repetido
    ])
    p = _subir(client, admin, "repuestos", archivo, "rep.xlsx").json()
    assert p["resumen"] == {"crear": 1, "actualizar": 1, "sin_cambios": 0, "omitir": 0, "error": 2}
    assert p["ignoradas"] == ["Columna rara"]
    errores = {f["fila"]: f["errores"] for f in p["filas"] if f["errores"]}
    assert "no es un número" in errores[4][0] and "Repetido" in errores[5][0]
    a = next(f for f in p["filas"] if f["fila"] == 2)
    assert a["cambios"]["stock"] == [2, 5] and a["cambios"]["nombre"] == ["Viejo", "Pantalla nueva"]
    # La vista previa no cambió nada
    assert not any(r["codigo"] == cod + "-B" for r in client.get("/parts/", headers=admin).json())

    r = _subir(client, admin, "repuestos", archivo, "rep.xlsx", previa=False).json()
    assert r == {"creados": 1, "actualizados": 1, "sin_cambios": 0, "omitidos": 0, "con_error": 2}
    partes = {x["codigo"]: x for x in client.get("/parts/", headers=admin).json()}
    assert partes[cod + "-A"]["stock"] == 5 and partes[cod + "-A"]["precio"] == 1500.5
    assert partes[cod + "-B"]["precio"] == 42000.5 and partes[cod + "-B"]["stock"] == 3
    # Los cambios de stock quedan en el historial (si no, no cierra)
    for codigo, cantidad in ((cod + "-A", 3), (cod + "-B", 3)):
        movs = client.get("/stock/history", params={"repuesto_id": partes[codigo]["id"]}, headers=admin).json()
        imp = [m for m in movs if "Importación" in (m.get("nota") or "")]
        assert len(imp) == 1 and imp[0]["cantidad"] == cantidad
    # Volver a subir lo mismo: nada para cambiar
    again = _subir(client, admin, "repuestos", archivo, "rep.xlsx").json()
    assert again["resumen"]["sin_cambios"] == 2 and again["resumen"]["crear"] == 0


def test_productos_desde_csv_con_punto_y_coma_y_latin1(client, admin):
    marca = f"Marca{uuid.uuid4().hex[:4]}"
    archivo = _csv([["Marca", "Modelo", "Categoría", "Garantía (meses)", "N° de parte"],
                    [marca, "Modelo Ñ", "Monitores", "36", ""],
                    [marca, "Otro", "", "doce", ""]], cod="cp1252")
    p = _subir(client, admin, "productos", archivo, "productos.csv").json()
    assert p["resumen"]["crear"] == 1 and p["resumen"]["error"] == 1
    _subir(client, admin, "productos", archivo, "productos.csv", previa=False)
    prods = [x for x in client.get("/products/", headers=admin).json() if x["marca"] == marca]
    assert [(x["modelo"], x["periodo_garantia_meses"]) for x in prods] == [("Modelo Ñ", 36)]
    # Sin "actualizar": lo existente se omite
    archivo2 = _csv([["marca", "modelo", "garantia"], [marca, "modelo ñ", "24"]], sep=",")
    p2 = _subir(client, admin, "productos", archivo2, "p.csv", actualizar=False).json()
    assert p2["resumen"]["omitir"] == 1
    p3 = _subir(client, admin, "productos", archivo2, "p.csv").json()
    assert p3["resumen"]["actualizar"] == 1 and p3["filas"][0]["cambios"]["periodo_garantia_meses"] == [36, 24]


def test_columnas_obligatorias_formato_y_permisos(client, admin, make_user):
    r = _subir(client, admin, "repuestos", _csv([["Nombre", "Precio"], ["x", "1"]]), "a.csv")
    assert r.status_code == 400 and "Código" in r.json()["detail"]
    assert _subir(client, admin, "repuestos", b"x", "a.pdf").status_code == 400
    assert _subir(client, admin, "clientes", _csv([["a"], ["b"]]), "a.csv").status_code == 404
    h, _ = make_user(rol="tecnico")
    assert client.post("/importar/repuestos/vista-previa", headers=h,
                       files={"archivo": ("a.csv", b"codigo;nombre\nx;y")}).status_code == 403


def test_plantillas_y_exportar_para_editar(client, admin):
    r = client.get("/importar/repuestos/plantilla", headers=admin)
    assert r.status_code == 200 and "spreadsheetml" in r.headers["content-type"]
    ws = load_workbook(io.BytesIO(r.content)).active
    assert [c.value for c in ws[1]][:2] == ["Código", "Nombre"] and ws.max_row == 3
    csv_txt = client.get("/importar/productos/plantilla", params={"formato": "csv", "con_datos": True}, headers=admin).content.decode("utf-8-sig")
    assert csv_txt.splitlines()[0] == "Marca;Modelo;Categoría;Garantía (meses);N° de parte"
    # Lo exportado se puede volver a subir sin cambios
    p = _subir(client, admin, "productos", csv_txt.encode("utf-8"), "productos.csv").json()
    assert p["resumen"]["error"] == 0 and p["resumen"]["crear"] == 0
