"""
exports.py — CSV and Excel export endpoints (Feature 2)
"""
import io, csv
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from .. import database, models, auth
from datetime import datetime

router = APIRouter(prefix="/export", tags=["export"])

ADMIN_ROLES = [models.UserRole.ADMINISTRADOR]

# ── helpers ──────────────────────────────────────────────────────────────────
def _csv_response(rows: list, headers: list, filename: str):
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    writer.writerow(headers)
    writer.writerows(rows)
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue().encode("utf-8-sig")]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

def _xlsx_response(wb: Workbook, filename: str):
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return StreamingResponse(
        iter([output.read()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

def _style_header(ws):
    for cell in ws[1]:
        cell.font      = Font(bold=True, color="FFFFFF")
        cell.fill      = PatternFill("solid", fgColor="1D4ED8")
        cell.alignment = Alignment(horizontal="center")

# ── Tickets ───────────────────────────────────────────────────────────────────
def _ticket_headers():
    return ["ID","RMA","Estado","Prioridad","Producto","Serie","Garantía",
            "Técnico","Cliente","Descripción","Diagnóstico","Empresa Transporte",
            "Tracking","Fecha Creación","Fecha Cierre"]

def _ticket_rows(db: Session):
    tickets = db.query(models.Ticket).all()
    rows = []
    for t in tickets:
        tecnico  = t.tecnico.nombre   if t.tecnico  else ""
        cliente  = t.cliente.nombre   if t.cliente  else ""
        rows.append([
            t.id, t.numero_rma, t.estado, t.prioridad,
            t.producto or "", t.numero_serie,
            "Sí" if t.en_garantia else "No",
            tecnico, cliente,
            t.descripcion or "", t.diagnostico or "",
            t.empresa_transporte or "", t.tracking_number or "",
            t.fecha_creacion.strftime("%d/%m/%Y %H:%M") if t.fecha_creacion else "",
            t.fecha_cierre.strftime("%d/%m/%Y %H:%M") if t.fecha_cierre else "",
        ])
    return rows

@router.get("/tickets")
def export_tickets(
    formato: str = Query("csv", enum=["csv", "xlsx"]),
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role(ADMIN_ROLES))
):
    date_str = datetime.now().strftime("%Y%m%d")
    headers  = _ticket_headers()
    rows     = _ticket_rows(db)
    if formato == "xlsx":
        wb = Workbook(); ws = wb.active; ws.title = "Tickets"
        ws.append(headers); _style_header(ws)
        for r in rows: ws.append(r)
        return _xlsx_response(wb, f"tickets_{date_str}.xlsx")
    return _csv_response(rows, headers, f"tickets_{date_str}.csv")

# ── Users ────────────────────────────────────────────────────────────────────
def _user_headers():
    return ["ID","Usuario","Nombre","Email","Rol","Tipo","Activo","Fecha Creación"]

def _user_rows(db: Session):
    return [[
        u.id, u.username, u.nombre, u.email, u.rol,
        u.tipo_cliente or "", "Sí" if u.activo else "No",
        u.fecha_creacion.strftime("%d/%m/%Y") if u.fecha_creacion else ""
    ] for u in db.query(models.Usuario).all()]

@router.get("/users")
def export_users(
    formato: str = Query("csv", enum=["csv", "xlsx"]),
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role(ADMIN_ROLES))
):
    date_str = datetime.now().strftime("%Y%m%d")
    headers  = _user_headers()
    rows     = _user_rows(db)
    if formato == "xlsx":
        wb = Workbook(); ws = wb.active; ws.title = "Usuarios"
        ws.append(headers); _style_header(ws)
        for r in rows: ws.append(r)
        return _xlsx_response(wb, f"usuarios_{date_str}.xlsx")
    return _csv_response(rows, headers, f"usuarios_{date_str}.csv")

# ── Products ────────────────────────────────────────────────────────────────
def _product_headers():
    return ["ID","Marca","Modelo","Categoría","Garantía (meses)","Nº Parte"]

def _product_rows(db: Session):
    return [[
        p.id, p.marca, p.modelo, p.categoria,
        p.periodo_garantia_meses, p.numero_parte or ""
    ] for p in db.query(models.Producto).all()]

@router.get("/products")
def export_products(
    formato: str = Query("csv", enum=["csv", "xlsx"]),
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role(ADMIN_ROLES))
):
    date_str = datetime.now().strftime("%Y%m%d")
    headers  = _product_headers()
    rows     = _product_rows(db)
    if formato == "xlsx":
        wb = Workbook(); ws = wb.active; ws.title = "Productos"
        ws.append(headers); _style_header(ws)
        for r in rows: ws.append(r)
        return _xlsx_response(wb, f"productos_{date_str}.xlsx")
    return _csv_response(rows, headers, f"productos_{date_str}.csv")

# ── Repuestos ────────────────────────────────────────────────────────────────
def _parts_headers():
    return ["ID","Código","Nombre","Proveedor","Stock","Precio"]

def _parts_rows(db: Session):
    return [[
        p.id, p.codigo, p.nombre, p.proveedor, p.stock, p.precio
    ] for p in db.query(models.Repuesto).all()]

@router.get("/parts")
def export_parts(
    formato: str = Query("csv", enum=["csv", "xlsx"]),
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role(ADMIN_ROLES))
):
    date_str = datetime.now().strftime("%Y%m%d")
    headers  = _parts_headers()
    rows     = _parts_rows(db)
    if formato == "xlsx":
        wb = Workbook(); ws = wb.active; ws.title = "Repuestos"
        ws.append(headers); _style_header(ws)
        for r in rows: ws.append(r)
        return _xlsx_response(wb, f"repuestos_{date_str}.xlsx")
    return _csv_response(rows, headers, f"repuestos_{date_str}.csv")
