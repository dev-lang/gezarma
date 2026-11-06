"""
export.py — CSV and XLSX export endpoints for all four main entities.
GET /export/{entidad}?formato=csv|xlsx
entidad: tickets | productos | repuestos | usuarios
         (English aliases accepted: users | products | parts — used by the admin panel)
"""
import io, csv
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from .. import database, models, auth

router = APIRouter(prefix="/export", tags=["export"])

ENTIDADES = {"tickets", "productos", "repuestos", "usuarios"}
ALIASES   = {"users": "usuarios", "products": "productos", "parts": "repuestos"}
FORMATOS  = {"csv", "xlsx"}


def _to_xlsx(headers: list, rows: list, sheet_name: str) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name

    # Header row
    ws.append(headers)
    for cell in ws[1]:
        cell.font      = Font(bold=True, color="FFFFFF")
        cell.fill      = PatternFill("solid", fgColor="1D4ED8")
        cell.alignment = Alignment(horizontal="center")

    for row in rows:
        ws.append(row)

    # Auto-width (approximate)
    for col in ws.columns:
        max_len = max(len(str(c.value or "")) for c in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 50)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _to_csv(headers: list, rows: list) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_ALL)
    w.writerow(headers)
    w.writerows(rows)
    return buf.getvalue()


@router.get("/{entidad}")
def export_data(
    entidad: str,
    formato: str = Query("csv", pattern="^(csv|xlsx)$"),
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([
        models.UserRole.ADMINISTRADOR, models.UserRole.TECNICO
    ]))
):
    entidad = ALIASES.get(entidad, entidad)
    if entidad not in ENTIDADES:
        raise HTTPException(status_code=404, detail=f"Entidad inválida. Opciones: {sorted(ENTIDADES)}")

    today = datetime.now().strftime("%Y-%m-%d")

    # ── TICKETS ────────────────────────────────────────────────────────────────
    if entidad == "tickets":
        items = db.query(models.Ticket).order_by(models.Ticket.fecha_creacion.desc()).all()
        headers = ["ID", "RMA", "Producto", "Nº Serie", "Estado", "Prioridad",
                   "Cliente", "Técnico", "Garantía", "Descripción", "Diagnóstico",
                   "Transporte", "Tracking", "Clonado de", "Relacionado con",
                   "Fecha Creación", "Fecha Actualización", "Fecha Cierre"]
        rows = []
        for t in items:
            rows.append([
                t.id, t.numero_rma, t.producto or "", t.numero_serie,
                t.estado, t.prioridad,
                t.cliente.nombre  if t.cliente  else "",
                t.tecnico.nombre  if t.tecnico  else "",
                "Sí" if t.en_garantia else "No",
                t.descripcion or "",
                t.diagnostico or "",
                t.empresa_transporte or "", t.tracking_number or "",
                t.origen.numero_rma    if t.origen     else "",
                t.relacionado.numero_rma if t.relacionado else "",
                t.fecha_creacion.strftime("%d/%m/%Y %H:%M") if t.fecha_creacion else "",
                t.fecha_actualizacion.strftime("%d/%m/%Y %H:%M") if t.fecha_actualizacion else "",
                t.fecha_cierre.strftime("%d/%m/%Y %H:%M") if t.fecha_cierre else "",
            ])
        filename = f"tickets_rma_{today}"

    # ── PRODUCTOS ──────────────────────────────────────────────────────────────
    elif entidad == "productos":
        items = db.query(models.Producto).order_by(models.Producto.marca).all()
        headers = ["ID", "Marca", "Modelo", "Categoría", "Garantía (meses)", "Nº de Parte"]
        rows = [[p.id, p.marca, p.modelo, p.categoria,
                 p.periodo_garantia_meses, p.numero_parte or ""] for p in items]
        filename = f"productos_{today}"

    # ── REPUESTOS ──────────────────────────────────────────────────────────────
    elif entidad == "repuestos":
        items = db.query(models.Repuesto).order_by(models.Repuesto.nombre).all()
        headers = ["ID", "Código", "Nombre", "Proveedor", "Stock", "Precio"]
        rows = [[r.id, r.codigo, r.nombre, r.proveedor, r.stock, r.precio] for r in items]
        filename = f"repuestos_{today}"

    # ── USUARIOS ───────────────────────────────────────────────────────────────
    else:
        if current_user.rol != models.UserRole.ADMINISTRADOR:
            raise HTTPException(status_code=403, detail="Solo administradores pueden exportar usuarios")
        items = db.query(models.Usuario).order_by(models.Usuario.rol, models.Usuario.nombre).all()
        headers = ["ID", "Usuario", "Nombre", "Email", "Rol", "Tipo Cliente", "Activo", "Fecha Creación"]
        rows = [[
            u.id, u.username, u.nombre, u.email, u.rol,
            u.tipo_cliente, "Sí" if u.activo else "No",
            u.fecha_creacion.strftime("%d/%m/%Y") if u.fecha_creacion else ""
        ] for u in items]
        filename = f"usuarios_{today}"

    if formato == "xlsx":
        content     = _to_xlsx(headers, rows, entidad.capitalize())
        media_type  = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        disposition = f"attachment; filename={filename}.xlsx"
        return StreamingResponse(
            io.BytesIO(content),
            media_type=media_type,
            headers={"Content-Disposition": disposition}
        )
    else:
        # utf-8-sig adds a BOM so Excel opens accents (ñ, á…) correctly
        content     = _to_csv(headers, rows).encode("utf-8-sig")
        media_type  = "text/csv; charset=utf-8"
        disposition = f"attachment; filename={filename}.csv"
        return StreamingResponse(
            io.BytesIO(content),
            media_type=media_type,
            headers={"Content-Disposition": disposition}
        )
