from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_validator
from typing import Annotated, Optional, List, Dict
from datetime import datetime

from .timeutils import iso_utc

# Instante guardado en UTC: en el JSON sale con zona ("...Z") para que el
# navegador lo muestre en la hora local del usuario. (fecha_compra NO usa este
# tipo: es una fecha de calendario.)
UTCDateTime = Annotated[datetime, PlainSerializer(iso_utc, return_type=str, when_used="json")]

# ── Tags ─────────────────────────────────────────────────────────────────────
class TagBase(BaseModel):
    nombre: str
    color:  str = "#3b82f6"

class TagCreate(TagBase):
    pass

class Tag(TagBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

# ── Users ────────────────────────────────────────────────────────────────────
class UserBase(BaseModel):
    username:     str
    nombre:       str
    email:        str
    rol:          str = "cliente"
    tipo_cliente: str = "persona"

class UserCreate(UserBase):
    password: str
    idioma:   Optional[str] = None
    # Solo lo usa un administrador: la clave es temporal y se cambia en el primer ingreso
    cambiar_clave: bool = False
    @field_validator("password")
    @classmethod
    def pw_min_length(cls, v):
        if len(v) < 6:
            raise ValueError("La contraseña debe tener al menos 6 caracteres")
        if len(v.encode("utf-8")) > 72:
            raise ValueError("La contraseña no puede superar los 72 bytes")
        return v

class UserUpdate(BaseModel):
    nombre:       Optional[str] = None
    email:        Optional[str] = None
    rol:          Optional[str] = None
    activo:       Optional[bool] = None
    tipo_cliente: Optional[str] = None
    telefono:     Optional[str] = None

class UserUpdateProfile(BaseModel):
    """For editing own profile or admin editing a user's profile fields."""
    nombre:   Optional[str] = None
    email:    Optional[str] = None
    telefono: Optional[str] = None

class UserResetPassword(BaseModel):
    """Admin resets a user password; returns the temp password."""
    pass

class User(UserBase):
    email:                Optional[str] = None   # los clientes cargados en mostrador pueden no tener
    id:                   int
    activo:               bool
    fecha_creacion:       UTCDateTime
    telefono:             Optional[str] = None
    must_change_password: bool = False
    idioma:               Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

# ── Spare Parts ───────────────────────────────────────────────────────────────
class SparePart(BaseModel):
    id:        int
    nombre:    str
    codigo:    str
    stock:     int
    proveedor: str
    precio:    float
    categoria: Optional[str] = "General"
    stock_minimo: int = 0
    ubicacion_id:   Optional[int] = None
    ubicacion_ruta: Optional[str] = None      # "Estante C › Cajón 4"
    model_config = ConfigDict(from_attributes=True)

class SparePartCreate(BaseModel):
    nombre:    str
    codigo:    str
    stock:     int = 0
    proveedor: str
    precio:    float = 0.0
    categoria: Optional[str] = "General"
    stock_minimo: int = 0
    ubicacion_id: Optional[int] = None        # si no viene, no se toca

class SparePartUpdate(BaseModel):
    nombre:    Optional[str]   = None
    codigo:    Optional[str]   = None
    stock:     Optional[int]   = None
    proveedor: Optional[str]   = None
    precio:    Optional[float] = None
    categoria: Optional[str]   = None
    stock_minimo: Optional[int] = None

class SparePartWithQty(SparePart):
    cantidad: int = 1
    # Internal data: None when the viewer is a client (see Ticket.for_viewer)
    stock:     Optional[int] = None
    proveedor: Optional[str] = None
    precio:    Optional[float] = None
    stock_minimo: Optional[int] = None

# ── Products ──────────────────────────────────────────────────────────────────
class ProductBase(BaseModel):
    marca:                   str
    modelo:                  str
    categoria:               str
    periodo_garantia_meses:  int = 12
    numero_parte:            Optional[str] = None

class ProductCreate(ProductBase):
    pass

class ProductUpdate(BaseModel):
    marca:                   Optional[str] = None
    modelo:                  Optional[str] = None
    categoria:               Optional[str] = None
    periodo_garantia_meses:  Optional[int] = None
    numero_parte:            Optional[str] = None

class Product(ProductBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

# ── Recepción (checklist de ingreso) ──────────────────────────────────────────
ACCESORIOS_COMUNES = ["Cargador", "Cable", "Caja", "Funda", "Batería", "Control remoto", "Tarjeta de memoria", "Chip / SIM"]


class ChecklistIngreso(BaseModel):
    """Lo que trae el equipo y cómo llega. De la clave de desbloqueo solo se
    registra si tiene: la clave se le pide al cliente cuando hace falta."""
    accesorios:       List[str] = []
    accesorios_otros: str = ""
    estado_fisico:    str = ""
    enciende:         Optional[bool] = None   # None = no se probó
    tiene_bloqueo:    Optional[bool] = None   # None = no se sabe
    # Preguntas extra del taller (Ajustes → checklist_controles): {"¿Lee discos?": true}
    controles:        Dict[str, Optional[bool]] = {}

    @field_validator("accesorios")
    @classmethod
    def _accesorios(cls, v):
        limpios = []
        for a in v:
            a = (a or "").strip()[:40]
            if a and a not in limpios:
                limpios.append(a)
        if len(limpios) > 20:
            raise ValueError("Demasiados accesorios (máximo 20)")
        return limpios

    @field_validator("accesorios_otros", "estado_fisico")
    @classmethod
    def _texto(cls, v):
        v = (v or "").strip()
        if len(v) > 500:
            raise ValueError("Máximo 500 caracteres")
        return v

    @field_validator("controles")
    @classmethod
    def _controles(cls, v):
        limpios = {}
        for k, val in (v or {}).items():
            k = (k or "").strip()[:80]
            if k:
                limpios[k] = val
        if len(limpios) > 20:
            raise ValueError("Demasiadas preguntas (máximo 20)")
        return limpios


class FirmaInfo(BaseModel):
    momento:    str
    aclaracion: Optional[str] = None
    fecha:      UTCDateTime
    model_config = ConfigDict(from_attributes=True)


class EncuestaInfo(BaseModel):
    puntaje:    int
    comentario: Optional[str] = None
    fecha:      UTCDateTime
    model_config = ConfigDict(from_attributes=True)


class EncuestaIn(BaseModel):
    puntaje:    int
    comentario: str = ""


PRIORIDADES = ("Baja", "Normal", "Alta", "Urgente")


def _prioridad_valida(v):
    if v is None:
        return v
    v = {"Media": "Normal"}.get(str(v).strip(), str(v).strip())   # "Media" = nombre viejo de Normal
    if v not in PRIORIDADES:
        raise ValueError(f"Prioridad inválida. Opciones: {', '.join(PRIORIDADES)}")
    return v


# ── Tickets ───────────────────────────────────────────────────────────────────
class TicketBase(BaseModel):
    producto_id:  Optional[int] = None
    producto:     Optional[str] = None
    numero_serie: str
    fecha_compra: datetime
    descripcion:  str
    prioridad:    str = "Normal"

    @field_validator("prioridad")
    @classmethod
    def _v_prioridad(cls, v):
        return _prioridad_valida(v)

class TicketCreate(TicketBase):
    pass

class TicketUpdateStatus(BaseModel):
    estado: str

class TicketUpdatePriority(BaseModel):
    prioridad: str

    @field_validator("prioridad")
    @classmethod
    def _v_prioridad(cls, v):
        return _prioridad_valida(v)

class TicketUpdateAssignment(BaseModel):
    tecnico_id: Optional[int] = None

class TicketUpdateShipping(BaseModel):
    empresa_transporte: str
    tracking_number:    str
    fecha_envio:        Optional[datetime] = None

class TicketAddTag(BaseModel):
    tag_nombre: str

class TicketSetTags(BaseModel):
    """Replace all tags on a ticket (for editing)."""
    tag_nombres: List[str]

class TicketPartQty(BaseModel):
    cantidad: int = Field(..., ge=1, le=100000)


class TicketDiagnostic(BaseModel):
    diagnostico: str = Field(..., max_length=20000)


class TicketAddPart(BaseModel):
    part_id:  int
    cantidad: int = 1

class TicketEditFields(BaseModel):
    """Admin/tecnico can edit core ticket fields (Feature 3)."""
    descripcion:  Optional[str] = None
    numero_serie: Optional[str] = None
    prioridad:    Optional[str] = None
    diagnostico:  Optional[str] = None

    @field_validator("prioridad")
    @classmethod
    def _v_prioridad(cls, v):
        return _prioridad_valida(v)

class TicketClone(BaseModel):
    """Clone a ticket, optionally linking it (Feature 11)."""
    relacionar: bool = True

class TicketSetRelacion(BaseModel):
    ticket_relacionado_id: Optional[int] = None

class Ticket(TicketBase):
    id:                   int
    numero_rma:           str
    usuario_id:           int
    usuario_nombre:       Optional[str] = None
    usuario_rol:          Optional[str] = None
    usuario_email:        Optional[str] = None
    usuario_telefono:     Optional[str] = None
    es_favorito:          bool = False
    estado:               str
    tecnico_asignado:     Optional[int] = None
    tecnico_nombre:       Optional[str] = None
    fecha_creacion:       UTCDateTime
    fecha_actualizacion:  UTCDateTime
    fecha_cierre:         Optional[UTCDateTime] = None
    deadline_sla:         Optional[UTCDateTime] = None
    en_garantia:          bool
    diagnostico:          Optional[str] = None
    empresa_transporte:   Optional[str] = None
    tracking_number:      Optional[str] = None
    fecha_envio:          Optional[UTCDateTime] = None
    clonado_de:           Optional[int]  = None
    ticket_relacionado:   Optional[int]  = None
    rma_clonado_de:       Optional[str]  = None
    rma_relacionado:      Optional[str]  = None
    reingreso_de:         Optional[int]  = None
    reingreso_garantia:   bool           = False
    rma_reingreso_de:     Optional[str]  = None
    tags:                 List[Tag]              = []
    repuestos_usados:     List[SparePartWithQty] = []
    checklist_ingreso:    Optional[ChecklistIngreso] = None
    firmas:               List[FirmaInfo]        = []
    encuesta:             Optional[EncuestaInfo] = None
    # Dónde está guardado y, si está en el fabricante, el envío abierto (solo para el taller)
    ubicacion_id:         Optional[int] = None
    ubicacion_ruta:       Optional[str] = None
    ubicacion_fecha:      Optional[UTCDateTime] = None
    envio_abierto:        Optional[dict] = None

    @classmethod
    def from_orm_with_tecnico(cls, obj, current_user_id: int = None):
        data = cls.model_validate(obj)
        if obj.ubicacion:
            from .services.ubicaciones import ruta
            data.ubicacion_ruta = ruta(obj.ubicacion)
        if obj.estado == "En servicio técnico oficial":
            e = next((x for x in obj.envios_externos if x.estado == "enviado"), None)
            if e:
                from .timeutils import iso_utc
                data.envio_abierto = {"id": e.id, "destino": e.destino, "numero_caso": e.numero_caso,
                                      "fecha_envio": iso_utc(e.fecha_envio),
                                      "fecha_estimada": iso_utc(e.fecha_estimada) if e.fecha_estimada else None}
        if obj.tecnico:
            data.tecnico_nombre = obj.tecnico.nombre
        if obj.cliente:
            data.usuario_nombre    = obj.cliente.nombre
            data.usuario_rol       = obj.cliente.rol
            data.usuario_email     = obj.cliente.email
            data.usuario_telefono  = obj.cliente.telefono
        if obj.origen:
            data.rma_clonado_de = obj.origen.numero_rma
        if obj.relacionado:
            data.rma_relacionado = obj.relacionado.numero_rma
        if obj.reingreso_origen:
            data.rma_reingreso_de = obj.reingreso_origen.numero_rma
        if current_user_id is not None:
            data.es_favorito = any(
                f.usuario_id == current_user_id for f in (obj.favoritos or [])
            )
        return data

    @classmethod
    def for_viewer(cls, obj, user):
        """Serialize a ticket for `user`. Clients don't get internal parts data
        (stock, supplier, cost price) — only name, code and quantity."""
        data = cls.from_orm_with_tecnico(obj, user.id)
        if user.rol == "cliente":
            for r in data.repuestos_usados:
                r.stock = r.proveedor = r.precio = r.stock_minimo = None
                r.ubicacion_id = r.ubicacion_ruta = None
            data.ubicacion_id = data.ubicacion_ruta = data.ubicacion_fecha = data.envio_abierto = None
        return data

    model_config = ConfigDict(from_attributes=True)

# ── Comments ──────────────────────────────────────────────────────────────────
class CommentBase(BaseModel):
    comentario:  str
    is_internal: bool = False

class CommentCreate(CommentBase):
    pass

class Comment(CommentBase):
    id:             int
    ticket_id:      int
    usuario_id:     int
    usuario_nombre: Optional[str] = None
    fecha:          UTCDateTime

    @classmethod
    def from_orm_with_nombre(cls, obj):
        data = cls.model_validate(obj)
        if obj.usuario:
            data.usuario_nombre = obj.usuario.nombre
        return data

    model_config = ConfigDict(from_attributes=True)

# ── History ───────────────────────────────────────────────────────────────────
class HistorialEntry(BaseModel):
    id:              int
    ticket_id:       int
    tipo_evento:     str
    estado_anterior: Optional[str] = None
    estado_nuevo:    Optional[str] = None
    campo:           Optional[str] = None
    valor_anterior:  Optional[str] = None
    valor_nuevo:     Optional[str] = None
    detalle:         Optional[str] = None
    usuario_nombre:  Optional[str] = None
    fecha:           UTCDateTime

    model_config = ConfigDict(from_attributes=True)

# ── Stock ─────────────────────────────────────────────────────────────────────
class StockMovimientoOut(BaseModel):
    id:             int
    repuesto_id:    int
    repuesto_nombre:Optional[str] = None
    ticket_id:      Optional[int] = None
    ticket_rma:     Optional[str] = None
    usuario_nombre: Optional[str] = None
    tipo:           str
    cantidad:       int
    stock_anterior: int
    stock_nuevo:    int
    nota:           Optional[str] = None
    fecha:          UTCDateTime
    anulado:        bool = False
    anula_id:       Optional[int] = None
    model_config = ConfigDict(from_attributes=True)

class StockMovimientoUpdate(BaseModel):
    nota: Optional[str] = None

# ── Diagnosis templates ──────────────────────────────────────────────────────
class PlantillaBase(BaseModel):
    nombre: str
    texto:  str
    orden:  int = 0

class PlantillaCreate(PlantillaBase):
    pass

class Plantilla(PlantillaBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

# ── Ticket Status Config ──────────────────────────────────────────────────────
class StatusConfigBase(BaseModel):
    valor:    str
    etiqueta: str
    color:    str = "#6b7280"
    orden:    int = 0
    activo:   bool = True
    es_final: bool = False

class StatusConfigCreate(StatusConfigBase):
    pass

class StatusConfig(StatusConfigBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

# ── Budget / Presupuesto ──────────────────────────────────────────────────────

class PresupuestoItemBase(BaseModel):
    descripcion:    str = ""
    cantidad:       float = 1
    costo_interno:  float = 0.0
    precio_cliente: float = 0.0
    repuesto_id:    Optional[int] = None   # ítem vinculado a un repuesto del catálogo

class PresupuestoItemCreate(PresupuestoItemBase):
    pass

class PresupuestoItemOut(PresupuestoItemBase):
    id:           int
    costo_interno: Optional[float] = None   # None for clients
    costo_total:  Optional[float] = None    # None for clients
    precio_total: float
    repuesto_codigo:  Optional[str] = None  # None for clients
    stock_disponible: Optional[int] = None  # None for clients
    model_config = ConfigDict(from_attributes=True)

class PresupuestoCreate(BaseModel):
    notas: Optional[str] = None
    items: List[PresupuestoItemCreate] = []

class PresupuestoUpdate(BaseModel):
    notas: Optional[str] = None
    items: Optional[List[PresupuestoItemCreate]] = None

class PresupuestoEstadoUpdate(BaseModel):
    estado: str

class PresupuestoVersionOut(BaseModel):
    id:             int
    version:        int
    estado:         str
    notas:          Optional[str] = None
    items_snapshot: Optional[list] = None
    usuario_nombre: Optional[str] = None
    fecha:          UTCDateTime
    model_config = ConfigDict(from_attributes=True)

class PresupuestoOut(BaseModel):
    id:              int
    ticket_id:       int
    estado:          str
    version:         int
    notas:           Optional[str] = None
    items:           List[PresupuestoItemOut] = []
    costo_total:     Optional[float] = None   # None for clients
    precio_total:    float
    ganancia:        Optional[float] = None   # None for clients
    versiones:       List[PresupuestoVersionOut] = []   # empty for clients
    creador_nombre:  Optional[str] = None
    fecha_creacion:  UTCDateTime
    fecha_actualizacion: UTCDateTime
    model_config = ConfigDict(from_attributes=True)

# ── Plantilla Presupuesto ─────────────────────────────────────────────────────

class PlantillaPresupuestoBase(BaseModel):
    nombre:         str
    descripcion:    str
    costo_interno:  float = 0.0
    precio_cliente: float = 0.0
    categoria:      Optional[str] = "General"
    activo:         bool = True
    orden:          int = 0
    producto_id:    Optional[int] = None   # ítem típico de ese modelo

class PlantillaPresupuestoCreate(PlantillaPresupuestoBase):
    pass

class PlantillaPresupuestoOut(PlantillaPresupuestoBase):
    id: int
    producto_nombre: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def de(cls, obj):
        out = cls.model_validate(obj)
        if obj.producto:
            out.producto_nombre = f"{obj.producto.marca} {obj.producto.modelo}"
        return out

# ── Financial Stats ───────────────────────────────────────────────────────────

class FinancialStats(BaseModel):
    ganancia_total:          float
    costo_total:             float
    ingreso_total:           float
    margen_promedio:         float
    ganancia_promedio_ticket: float
    costo_promedio_ticket:   float
    tickets_con_presupuesto: int
    ganancias_por_mes:       Dict[str, float]
    ingresos_por_mes:        Dict[str, float]
    costos_por_mes:          Dict[str, float]

# ── Notifications ─────────────────────────────────────────────────────────────

class NotificacionOut(BaseModel):
    id:                 int
    ticket_id:          Optional[int] = None
    ticket_rma:         Optional[str] = None
    tipo:               str
    titulo:             str
    mensaje:            str
    leida:              bool
    fecha:              UTCDateTime
    origen_nombre:      Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class NotificacionMarkRead(BaseModel):
    ids: List[int] = []   # empty = mark all

# ── Dashboard ─────────────────────────────────────────────────────────────────
class DashboardStats(BaseModel):
    total_tickets:                   int
    abiertos:                        int
    cerrados:                        int
    en_reparacion:                   int
    tiempo_promedio_reparacion_horas: float
    fallas_por_producto:             Dict[str, int]
    tickets_por_estado:              Dict[str, int]
    tickets_por_tecnico:             Dict[str, int]

# ── System Config ─────────────────────────────────────────────────────────────
class ConfigSistemaItem(BaseModel):
    clave: str
    valor: str
    model_config = ConfigDict(from_attributes=True)

class ConfigSistemaUpdate(BaseModel):
    valor: str

# ── Rate Limit Info ───────────────────────────────────────────────────────────
class RateLimitStatus(BaseModel):
    ip_address:      str
    intentos_recientes: int
    bloqueado:       bool
    segundos_restantes: Optional[int] = None
