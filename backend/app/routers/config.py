"""
config.py — Admin-configurable items:
  /config/plantillas  — CRUD for diagnosis templates
  /config/estados     — CRUD for ticket status config
"""
import os

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List
from .. import database, models, schemas, auth, ajustes as ajustes_mod
from ..timeutils import utcnow

router = APIRouter(prefix="/config", tags=["config"])

# ── Diagnosis templates ────────────────────────────────────────────────────────

@router.get("/plantillas", response_model=List[schemas.Plantilla])
def list_plantillas(db: Session = Depends(database.get_db),
                    current_user: models.Usuario = Depends(auth.get_current_user)):
    return db.query(models.DiagnosticaPlantilla).order_by(
        models.DiagnosticaPlantilla.orden, models.DiagnosticaPlantilla.id).all()

@router.post("/plantillas", response_model=schemas.Plantilla)
def create_plantilla(p: schemas.PlantillaCreate,
                     db: Session = Depends(database.get_db),
                     current_user: models.Usuario = Depends(
                         auth.check_role([models.UserRole.ADMINISTRADOR]))):
    if db.query(models.DiagnosticaPlantilla).filter_by(nombre=p.nombre).first():
        raise HTTPException(400, "Ya existe una plantilla con ese nombre")
    obj = models.DiagnosticaPlantilla(**p.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj

@router.patch("/plantillas/{pid}", response_model=schemas.Plantilla)
def update_plantilla(pid: int, p: schemas.PlantillaCreate,
                     db: Session = Depends(database.get_db),
                     current_user: models.Usuario = Depends(
                         auth.check_role([models.UserRole.ADMINISTRADOR]))):
    obj = db.query(models.DiagnosticaPlantilla).filter_by(id=pid).first()
    if not obj:
        raise HTTPException(404, "Plantilla no encontrada")
    conflict = db.query(models.DiagnosticaPlantilla).filter(
        models.DiagnosticaPlantilla.nombre == p.nombre,
        models.DiagnosticaPlantilla.id != pid).first()
    if conflict:
        raise HTTPException(400, "Ya existe otra plantilla con ese nombre")
    for k, v in p.model_dump().items():
        setattr(obj, k, v)
    db.commit(); db.refresh(obj)
    return obj

@router.delete("/plantillas/{pid}", status_code=204)
def delete_plantilla(pid: int, db: Session = Depends(database.get_db),
                     current_user: models.Usuario = Depends(
                         auth.check_role([models.UserRole.ADMINISTRADOR]))):
    obj = db.query(models.DiagnosticaPlantilla).filter_by(id=pid).first()
    if not obj:
        raise HTTPException(404, "Plantilla no encontrada")
    db.delete(obj); db.commit()

# ── Ticket status config ────────────────────────────────────────────────────────

@router.get("/estados", response_model=List[schemas.StatusConfig])
def list_estados(db: Session = Depends(database.get_db),
                 current_user: models.Usuario = Depends(auth.get_current_user)):
    return db.query(models.TicketStatusConfig).order_by(
        models.TicketStatusConfig.orden, models.TicketStatusConfig.id).all()

@router.post("/estados", response_model=schemas.StatusConfig)
def create_estado(s: schemas.StatusConfigCreate,
                  db: Session = Depends(database.get_db),
                  current_user: models.Usuario = Depends(
                      auth.check_role([models.UserRole.ADMINISTRADOR]))):
    if db.query(models.TicketStatusConfig).filter_by(valor=s.valor).first():
        raise HTTPException(400, "Ya existe un estado con ese valor")
    obj = models.TicketStatusConfig(**s.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj

# Estados que usa el propio sistema (alta, retiro, envío, cierre, encuesta…)
ESTADOS_DEL_SISTEMA = {e.value for e in models.TicketStatus}


@router.patch("/estados/{sid}", response_model=schemas.StatusConfig)
def update_estado(sid: int, s: schemas.StatusConfigCreate,
                  db: Session = Depends(database.get_db),
                  current_user: models.Usuario = Depends(
                      auth.check_role([models.UserRole.ADMINISTRADOR]))):
    obj = db.query(models.TicketStatusConfig).filter_by(id=sid).first()
    if not obj:
        raise HTTPException(404, "Estado no encontrado")
    if s.valor != obj.valor:
        # El valor es lo que queda guardado en cada ticket: cambiarlo los dejaría
        # con un estado inexistente. Los de fábrica además los usa el sistema
        # (retiro, encuesta, garantía…). La etiqueta sí se puede cambiar siempre.
        if obj.valor in ESTADOS_DEL_SISTEMA:
            raise HTTPException(400, "El valor de un estado del sistema no se puede cambiar (sí su etiqueta, color y orden)")
        if db.query(models.Ticket).filter(models.Ticket.estado == obj.valor).first():
            raise HTTPException(400, f"Hay tickets con el estado '{obj.etiqueta}': no se puede cambiar su valor")
        if db.query(models.TicketStatusConfig).filter(models.TicketStatusConfig.valor == s.valor,
                                                      models.TicketStatusConfig.id != sid).first():
            raise HTTPException(400, "Ya existe un estado con ese valor")
    if obj.valor in ESTADOS_DEL_SISTEMA and s.es_final != obj.es_final:
        raise HTTPException(400, "No se puede cambiar si un estado del sistema es final")
    for k, v in s.model_dump().items():
        setattr(obj, k, v)
    db.commit(); db.refresh(obj)
    return obj

@router.delete("/estados/{sid}", status_code=204)
def delete_estado(sid: int, db: Session = Depends(database.get_db),
                  current_user: models.Usuario = Depends(
                      auth.check_role([models.UserRole.ADMINISTRADOR]))):
    obj = db.query(models.TicketStatusConfig).filter_by(id=sid).first()
    if not obj:
        raise HTTPException(404, "Estado no encontrado")
    if obj.valor in ESTADOS_DEL_SISTEMA:
        raise HTTPException(400, "Los estados del sistema no se eliminan: se pueden desactivar")
    # Prevent deleting if tickets are using this status
    in_use = db.query(models.Ticket).filter(models.Ticket.estado == obj.valor).first()
    if in_use:
        raise HTTPException(400, f"No se puede eliminar: hay tickets con el estado '{obj.etiqueta}'")
    db.delete(obj); db.commit()

# ── System Config (rate limit + general settings) ─────────────────────────────

RATE_LIMIT_KEYS = {
    "login_max_intentos":       {"default": "5",   "label": "Máx. intentos de login fallidos"},
    "login_ventana_segundos":   {"default": "300",  "label": "Ventana de tiempo (segundos)"},
    "login_bloqueo_segundos":   {"default": "600",  "label": "Tiempo de bloqueo (segundos)"},
}

@router.get("/sistema", response_model=list)
def get_config_sistema(
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([models.UserRole.ADMINISTRADOR]))
):
    result = []
    for clave, meta in RATE_LIMIT_KEYS.items():
        row = db.query(models.ConfigSistema).filter_by(clave=clave).first()
        result.append({
            "clave":   clave,
            "valor":   row.valor if row else meta["default"],
            "label":   meta["label"],
            "default": meta["default"],
        })
    return result

@router.put("/sistema/{clave}")
def update_config_sistema(
    clave: str,
    body: schemas.ConfigSistemaUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([models.UserRole.ADMINISTRADOR]))
):
    if clave not in RATE_LIMIT_KEYS:
        raise HTTPException(400, f"Clave de configuración desconocida: {clave}")
    # Validate it's a positive integer
    try:
        val = int(body.valor)
        if val < 1:
            raise ValueError()
    except ValueError:
        raise HTTPException(400, "El valor debe ser un número entero positivo")
    row = db.query(models.ConfigSistema).filter_by(clave=clave).first()
    if row:
        row.valor = str(val)
    else:
        db.add(models.ConfigSistema(clave=clave, valor=str(val)))
    db.commit()
    return {"clave": clave, "valor": str(val)}

@router.delete("/login-attempts")
def clear_login_attempts(
    ip: str = None,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([models.UserRole.ADMINISTRADOR]))
):
    """Clear failed login attempts (optionally for a specific IP)."""
    q = db.query(models.LoginAttempt).filter(models.LoginAttempt.exitoso == False)
    if ip:
        q = q.filter(models.LoginAttempt.ip_address == ip)
    deleted = q.delete()
    db.commit()
    return {"deleted": deleted}

@router.get("/login-attempts/stats")
def get_login_attempts_stats(
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([models.UserRole.ADMINISTRADOR]))
):
    """Show IPs with recent failed attempts."""
    from sqlalchemy import func
    from datetime import timedelta
    window = int(
        (db.query(models.ConfigSistema).filter_by(clave="login_ventana_segundos").first() or type('', (), {'valor': '300'})()).valor
    )
    since = utcnow() - timedelta(seconds=window)
    rows = (
        db.query(
            models.LoginAttempt.ip_address,
            func.count(models.LoginAttempt.id).label("intentos")
        )
        .filter(models.LoginAttempt.exitoso == False, models.LoginAttempt.fecha >= since)
        .group_by(models.LoginAttempt.ip_address)
        .order_by(func.count(models.LoginAttempt.id).desc())
        .all()
    )
    return [{"ip": r.ip_address, "intentos": r.intentos} for r in rows]


# ── Ajustes del sistema (documentos, email, SLA, seguimiento) ────────────────
@router.get("/ajustes")
def listar_ajustes(
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([models.UserRole.ADMINISTRADOR])),
):
    return ajustes_mod.listado(db)


@router.put("/ajustes")
def guardar_ajustes(
    body: dict,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([models.UserRole.ADMINISTRADOR])),
):
    """Recibe {clave: valor, ...}. Valida todo antes de guardar: o se guarda todo o nada."""
    errores = {}
    for clave, valor in body.items():
        if clave not in ajustes_mod.DEFS:
            errores[clave] = "Ajuste desconocido"
            continue
        try:
            ajustes_mod.set(db, clave, valor)
        except ValueError as e:
            errores[clave] = str(e)
    if errores:
        db.rollback()
        ajustes_mod.invalidar_cache()
        raise HTTPException(400, {"mensaje": "Hay valores inválidos", "errores": errores})
    db.commit()
    ajustes_mod.invalidar_cache()   # que el resto de la app vea los valores nuevos ya mismo
    return ajustes_mod.listado(db)


@router.get("/ajustes/publicos")
def ajustes_publicos(db: Session = Depends(database.get_db),
                     current_user: models.Usuario = Depends(auth.get_current_user)):
    """Lo que el frontend necesita saber sin ser admin."""
    return {"pdf_modo": ajustes_mod.get(db, "pdf_modo"),
            "seguimiento_publico": ajustes_mod.get(db, "seguimiento_publico"),
            "sla_aviso_horas": ajustes_mod.get(db, "sla_aviso_horas"),
            "etiqueta_tamano": ajustes_mod.get(db, "etiqueta_tamano"),
            "encuesta_activa": ajustes_mod.get(db, "encuesta_activa")}


# ── Marca del taller: nombre y logo (barra, ingreso, favicon) ────────────────
LOGO_MAX = 2 * 1024 * 1024
LOGO_LADO = 512


def _logo_path() -> str:
    from .. import config as cfg
    return os.path.join(cfg.UPLOAD_DIR, "marca", "logo.png")


@router.get("/marca")
def marca(db: Session = Depends(database.get_db)):
    """Público: lo necesita la pantalla de ingreso antes de iniciar sesión."""
    ruta = _logo_path()
    return {"nombre": ajustes_mod.get(db, "empresa_nombre") or "GEZARMA",
            "logo": int(os.path.getmtime(ruta)) if os.path.exists(ruta) else None,
            "registro_publico": ajustes_mod.get(db, "registro_publico"),
            "seguimiento_publico": ajustes_mod.get(db, "seguimiento_publico")}


@router.get("/logo")
def logo():
    ruta = _logo_path()
    if not os.path.exists(ruta):
        raise HTTPException(404, "El taller no cargó un logo")
    return FileResponse(ruta, media_type="image/png",
                        headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"})


@router.put("/logo")
async def subir_logo(archivo: UploadFile = File(...),
                     current_user: models.Usuario = Depends(auth.check_role([models.UserRole.ADMINISTRADOR]))):
    """PNG, JPG o WEBP de hasta 2 MB. Se vuelve a guardar como PNG de hasta 512 px
    (no se guarda el archivo original: así no puede llevar nada más que la imagen)."""
    from io import BytesIO
    from PIL import Image, UnidentifiedImageError
    datos = await archivo.read(LOGO_MAX + 1)
    if len(datos) > LOGO_MAX:
        raise HTTPException(400, "El logo puede pesar hasta 2 MB.")
    try:
        img = Image.open(BytesIO(datos))
        if img.format not in ("PNG", "JPEG", "WEBP"):
            raise HTTPException(400, "El logo tiene que ser una imagen PNG, JPG o WEBP.")
        img.load()
    except (UnidentifiedImageError, OSError):
        raise HTTPException(400, "El logo tiene que ser una imagen PNG, JPG o WEBP.")
    img = img.convert("RGBA")
    img.thumbnail((LOGO_LADO, LOGO_LADO))
    ruta = _logo_path()
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    tmp = ruta + ".tmp"
    img.save(tmp, "PNG", optimize=True)
    os.replace(tmp, ruta)
    return {"logo": int(os.path.getmtime(ruta))}


@router.delete("/logo", status_code=204)
def borrar_logo(current_user: models.Usuario = Depends(auth.check_role([models.UserRole.ADMINISTRADOR]))):
    ruta = _logo_path()
    if os.path.exists(ruta):
        os.replace(ruta, ruta + ".anterior")      # se puede recuperar a mano si fue un error
    return Response(status_code=204)


# ── Guía de primer uso (dashboard del administrador) ─────────────────────────
PRODUCTOS_DE_EJEMPLO = {("ASUS", "X515 Laptop"), ("Logitech", "G502 Hero"), ("Samsung", "Odyssey G5")}


@router.get("/guia")
def guia(db: Session = Depends(database.get_db),
         current_user: models.Usuario = Depends(auth.check_role([models.UserRole.ADMINISTRADOR]))):
    """Los pasos para dejar el sistema listo, con cuáles ya están hechos."""
    from .. import config as cfg
    smtp = (ajustes_mod.get(db, "smtp_host") if ajustes_mod.get(db, "smtp_origen") == "panel" else cfg.SMTP_HOST)
    productos_propios = any((p.marca, p.modelo) not in PRODUCTOS_DE_EJEMPLO
                            for p in db.query(models.Producto.marca, models.Producto.modelo).all())
    tecnico = db.query(models.Usuario.id).filter_by(rol=models.UserRole.TECNICO.value, activo=True).first()
    pasos = [
        {"id": "taller", "titulo": "Cargá los datos del taller",
         "detalle": "Nombre y contacto para los documentos y los mails.",
         "hecho": (ajustes_mod.get(db, "empresa_nombre") or "GEZARMA") != "GEZARMA" or bool(ajustes_mod.get(db, "empresa_datos"))},
        {"id": "email", "titulo": "Configurá el email",
         "detalle": "Para avisarle al cliente cada cambio de estado y mandarle el presupuesto.",
         "hecho": bool(ajustes_mod.get(db, "email_activo") and smtp)},
        {"id": "productos", "titulo": "Cargá tus productos",
         "detalle": "Marca, modelo y garantía de lo que reparás (los que vienen son de ejemplo).",
         "hecho": productos_propios},
        {"id": "tecnico", "titulo": "Sumá un técnico",
         "detalle": "Cada técnico tiene su usuario y ve los tickets que tiene asignados.",
         "hecho": bool(tecnico)},
        {"id": "impresora", "titulo": "Probá la impresora",
         "detalle": "Imprimí una etiqueta de prueba para revisar el tamaño y que el código de barras se lea.",
         "hecho": bool(ajustes_mod.get(db, "guia_impresion_probada"))},
    ]
    return {"oculta": bool(ajustes_mod.get(db, "guia_oculta")), "pasos": pasos,
            "completa": all(p["hecho"] for p in pasos)}


@router.put("/guia")
def guia_ocultar(data: dict, db: Session = Depends(database.get_db),
                 current_user: models.Usuario = Depends(auth.check_role([models.UserRole.ADMINISTRADOR]))):
    ajustes_mod.set(db, "guia_oculta", bool(data.get("oculta")))
    db.commit()
    return {"oculta": bool(data.get("oculta"))}


# ── Email: prueba y estado ───────────────────────────────────────────────────
@router.post("/email/prueba")
def email_prueba(
    body: dict,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([models.UserRole.ADMINISTRADOR])),
):
    """Manda un mail de prueba ya mismo con la configuración guardada y devuelve el error real si falla."""
    from ..services import email
    destino = (body.get("destino") or "").strip()
    if "@" not in destino:
        raise HTTPException(400, "Ingresá un email de destino válido")
    try:
        email.enviar(db, [destino], "Prueba de email de GEZARMA", "La configuración de email funciona",
                     ["Si recibiste este mensaje, el sistema ya puede enviar notificaciones por email.",
                      "Acordate de activar «Enviar notificaciones por email» en Ajustes si todavía no lo hiciste."
                      if not ajustes_mod.get(db, "email_activo") else
                      "Las notificaciones por email están activadas."])
    except email.ErrorEmail as e:
        raise HTTPException(400, str(e))
    return {"mensaje": f"Mail de prueba enviado a {destino}."}


@router.get("/email/estado")
def email_estado(current_user: models.Usuario = Depends(auth.check_role([models.UserRole.ADMINISTRADOR]))):
    from ..services import email
    from ..timeutils import iso_utc
    e = email.estado
    return {"ultimo_ok": iso_utc(e["ultimo_ok"]) if e["ultimo_ok"] else None,
            "ultimo_error": e["ultimo_error"],
            "ultimo_error_fecha": iso_utc(e["ultimo_error_fecha"]) if e["ultimo_error_fecha"] else None}
