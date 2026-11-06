from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
from .database import engine, Base, SessionLocal, run_migrations
from .routers import auth as auth_router, tickets, comments, users, products, parts, stock, export as export_router, tags as tags_router, config as config_router, budget as budget_router, notifications as notif_router, favorites as fav_router, public as public_router, documentos as documentos_router, recepcion as recepcion_router, encuestas as encuestas_router
from . import models, auth, config
from . import ajustes as ajustes_mod
from .services import sla as sla_service

UPLOAD_DIR  = config.UPLOAD_DIR
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: migraciones de la base y datos iniciales (seed_data está más abajo)
    run_migrations()
    seed_data()
    tarea_sla = sla_service.iniciar()   # revisión periódica de SLA
    yield
    if tarea_sla:
        tarea_sla.cancel()

app = FastAPI(title="GEZARMA API", lifespan=lifespan)
# El frontend se sirve desde esta misma app, así que no necesita CORS.
# Solo hace falta si otro origen consume la API (CORS_ORIGINS en .env; vacío = sin CORS).
if config.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS, allow_credentials=True,
        allow_methods=["*"], allow_headers=["*"],
    )

@app.middleware("http")
async def _recordar_base_url(request, call_next):
    # Para armar links (mails, QR) cuando no hay URL pública configurada
    ajustes_mod.request_base_url.set(str(request.base_url))
    return await call_next(request)

app.include_router(auth_router.router)
app.include_router(tickets.router)
app.include_router(comments.router)
app.include_router(users.router)
app.include_router(products.router)
app.include_router(parts.router)
app.include_router(stock.router)
app.include_router(export_router.router)
app.include_router(tags_router.router)
app.include_router(config_router.router)
app.include_router(budget_router.router)
app.include_router(notif_router.router)
app.include_router(fav_router.router)
app.include_router(public_router.router)
app.include_router(documentos_router.router)
app.include_router(recepcion_router.router)
app.include_router(encuestas_router.router)

@app.get("/")
def read_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

@app.get("/seguimiento")
def read_seguimiento():
    """Página pública de seguimiento de reparaciones (sin login)."""
    return FileResponse(os.path.join(FRONTEND_DIR, "seguimiento.html"))

app.mount("/js",       StaticFiles(directory=os.path.join(FRONTEND_DIR, "js")),       name="js")
app.mount("/partials", StaticFiles(directory=os.path.join(FRONTEND_DIR, "partials")), name="partials")
# Attachments are NOT served statically: they go through
# GET /tickets/{id}/attachments/{adj_id}/download, which checks permissions.

DEFAULT_TAGS = [
    ("Garantía",         "#3b82f6"),
    ("DOA",              "#ef4444"),
    ("Falla Intermitente","#f59e0b"),
    ("Daño Físico",      "#8b5cf6"),
    ("Error Firmware",   "#06b6d4"),
    ("Líquido",          "#0ea5e9"),
    ("Sin falla",        "#22c55e"),
]

def seed_data():
    config.warn_insecure_defaults()
    db = SessionLocal()
    if not db.query(models.Usuario).filter_by(username="admin").first():
        admin = models.Usuario(
            username="admin",
            password_hash=auth.get_password_hash(config.ADMIN_PASSWORD),
            nombre="Administrador GEZARMA",
            email=config.ADMIN_EMAIL,
            rol=models.UserRole.ADMINISTRADOR,
            tipo_cliente=models.UserType.EMPRESA,
            # Con la clave por defecto del repo, se obliga a cambiarla en el primer login
            must_change_password=config.USING_DEFAULT_ADMIN_PASSWORD,
        )
        db.add(admin)

    if not db.query(models.Producto).first():
        for p in [
            {"marca":"ASUS","modelo":"X515 Laptop","categoria":"Notebooks","periodo_garantia_meses":12},
            {"marca":"Logitech","modelo":"G502 Hero","categoria":"Periféricos","periodo_garantia_meses":24},
            {"marca":"Samsung","modelo":"Odyssey G5","categoria":"Monitores","periodo_garantia_meses":36},
        ]:
            db.add(models.Producto(**p))

    if not db.query(models.Repuesto).first():
        for p in [
            {"nombre":"Pantalla LED 15.6","codigo":"LCD-156-01","stock":5,"proveedor":"ImportGZ","precio":120.0},
            {"nombre":"Batería ASUS X515","codigo":"BAT-AS-515","stock":10,"proveedor":"ASUS Latam","precio":45.0},
        ]:
            db.add(models.Repuesto(**p))

    for nombre, color in DEFAULT_TAGS:
        if not db.query(models.Tag).filter_by(nombre=nombre).first():
            db.add(models.Tag(nombre=nombre, color=color))

    # Seed diagnosis templates
    DEFAULT_PLANTILLAS = [
        ("No enciende",  "No enciende. Se verificó fuente de alimentación y placa base. Sin tensión en conector de batería.", 0),
        ("Batería",      "Falla de batería confirmada. Capacidad de ciclos agotada. Se procede a reemplazo bajo garantía.", 1),
        ("Pantalla",     "Pantalla con daño físico (rotura de cristal / retroiluminación fallida). Requiere reemplazo de módulo LCD completo.", 2),
        ("Teclado",      "Teclado con teclas sin respuesta / daño por líquido. Se realizó limpieza con IPA 99%. Requiere reemplazo de membrana.", 3),
        ("Disco",        "Unidad de almacenamiento con sectores defectuosos detectados. Se realizó respaldo de datos y reemplazo de unidad.", 4),
        ("Líquido",      "Equipo ingresó con daño por líquido. Corrosión en placa base. Se realizó limpieza ultrasónica.", 5),
        ("Sin falla",    "Equipo revisado. No se detectaron fallas de hardware. Se realizó reinstalación de sistema operativo y actualización de drivers.", 6),
    ]
    for nombre, texto, orden in DEFAULT_PLANTILLAS:
        if not db.query(models.DiagnosticaPlantilla).filter_by(nombre=nombre).first():
            db.add(models.DiagnosticaPlantilla(nombre=nombre, texto=texto, orden=orden))

    # Seed ticket status config
    DEFAULT_ESTADOS = [
        ("Nuevo",               "Nuevo",               "#3b82f6", 0,  False),
        ("En revisión",         "En revisión",          "#f59e0b", 1,  False),
        ("Aprobado para RMA",   "Aprobado para RMA",    "#10b981", 2,  False),
        ("Equipo recibido",     "Equipo recibido",      "#6366f1", 3,  False),
        ("En diagnóstico",      "En diagnóstico",       "#06b6d4", 4,  False),
        ("En reparación",       "En reparación",        "#8b5cf6", 5,  False),
        ("Esperando repuestos", "Esperando repuestos",  "#f97316", 6,  False),
        ("Reparado",            "Reparado",             "#14b8a6", 7,  False),
        ("Enviado al cliente",  "Enviado al cliente",   "#0ea5e9", 8,  False),
        ("Cerrado",             "Cerrado",              "#6b7280", 9,  True),
        ("Cancelado",           "Cancelado",            "#ef4444", 10, True),
    ]
    for valor, etiqueta, color, orden, es_final in DEFAULT_ESTADOS:
        if not db.query(models.TicketStatusConfig).filter_by(valor=valor).first():
            db.add(models.TicketStatusConfig(
                valor=valor, etiqueta=etiqueta, color=color,
                orden=orden, es_final=es_final, activo=True))

    db.commit()
    db.close()

    # Seed budget templates
    db2 = SessionLocal()
    DEFAULT_PLANTILLAS_PRESUPUESTO = [
        ("Diagnóstico",        "Diagnóstico técnico del equipo",           15.0,  30.0,  "Servicio", 0),
        ("Limpieza general",   "Limpieza interna y externa del equipo",    10.0,  25.0,  "Servicio", 1),
        ("Cambio de pantalla", "Reemplazo de módulo LCD/pantalla",         80.0, 150.0,  "Repuesto", 2),
        ("Cambio de batería",  "Reemplazo de batería",                     30.0,  70.0,  "Repuesto", 3),
        ("Mano de obra",       "Mano de obra por hora técnica",            20.0,  50.0,  "Servicio", 4),
        ("Cambio de teclado",  "Reemplazo de teclado",                     25.0,  60.0,  "Repuesto", 5),
        ("Reinstalación SO",   "Reinstalación de sistema operativo",        5.0,  40.0,  "Servicio", 6),
    ]
    for nombre, desc, costo, precio, cat, orden in DEFAULT_PLANTILLAS_PRESUPUESTO:
        if not db2.query(models.PlantillaPresupuesto).filter_by(nombre=nombre).first():
            db2.add(models.PlantillaPresupuesto(
                nombre=nombre, descripcion=desc, costo_interno=costo,
                precio_cliente=precio, categoria=cat, orden=orden, activo=True,
            ))
    db2.commit()
    db2.close()
