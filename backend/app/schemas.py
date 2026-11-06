from pydantic import BaseModel, validator
from typing import Optional, List, Dict
from datetime import datetime

# ── Tags ─────────────────────────────────────────────────────────────────────
class TagBase(BaseModel):
    nombre: str
    color:  str = "#3b82f6"

class TagCreate(TagBase):
    pass

class Tag(TagBase):
    id: int
    class Config:
        from_attributes = True

# ── Users ────────────────────────────────────────────────────────────────────
class UserBase(BaseModel):
    username:     str
    nombre:       str
    email:        str
    rol:          str = "cliente"
    tipo_cliente: str = "persona"

class UserCreate(UserBase):
    password: str
    @validator("password")
    def pw_min_length(cls, v):
        if len(v) < 6:
            raise ValueError("La contraseña debe tener al menos 6 caracteres")
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
    id:                   int
    activo:               bool
    fecha_creacion:       datetime
    telefono:             Optional[str] = None
    must_change_password: bool = False
    class Config:
        from_attributes = True

# ── Spare Parts ───────────────────────────────────────────────────────────────
class SparePart(BaseModel):
    id:        int
    nombre:    str
    codigo:    str
    stock:     int
    proveedor: str
    precio:    float
    categoria: Optional[str] = "General"
    class Config:
        from_attributes = True

class SparePartCreate(BaseModel):
    nombre:    str
    codigo:    str
    stock:     int = 0
    proveedor: str
    precio:    float = 0.0
    categoria: Optional[str] = "General"

class SparePartUpdate(BaseModel):
    nombre:    Optional[str]   = None
    codigo:    Optional[str]   = None
    stock:     Optional[int]   = None
    proveedor: Optional[str]   = None
    precio:    Optional[float] = None
    categoria: Optional[str]   = None

class SparePartWithQty(SparePart):
    cantidad: int = 1

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
    class Config:
        from_attributes = True

# ── Tickets ───────────────────────────────────────────────────────────────────
class TicketBase(BaseModel):
    producto_id:  Optional[int] = None
    producto:     Optional[str] = None
    numero_serie: str
    fecha_compra: datetime
    descripcion:  str
    prioridad:    str = "Normal"

class TicketCreate(TicketBase):
    pass

class TicketUpdateStatus(BaseModel):
    estado: str

class TicketUpdatePriority(BaseModel):
    prioridad: str

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

class TicketAddPart(BaseModel):
    part_id:  int
    cantidad: int = 1

class TicketEditFields(BaseModel):
    """Admin/tecnico can edit core ticket fields (Feature 3)."""
    descripcion:  Optional[str] = None
    numero_serie: Optional[str] = None
    prioridad:    Optional[str] = None
    diagnostico:  Optional[str] = None

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
    fecha_creacion:       datetime
    fecha_actualizacion:  datetime
    fecha_cierre:         Optional[datetime] = None
    deadline_sla:         Optional[datetime] = None
    en_garantia:          bool
    diagnostico:          Optional[str] = None
    empresa_transporte:   Optional[str] = None
    tracking_number:      Optional[str] = None
    fecha_envio:          Optional[datetime] = None
    clonado_de:           Optional[int]  = None
    ticket_relacionado:   Optional[int]  = None
    rma_clonado_de:       Optional[str]  = None
    rma_relacionado:      Optional[str]  = None
    tags:                 List[Tag]              = []
    repuestos_usados:     List[SparePartWithQty] = []

    @classmethod
    def from_orm_with_tecnico(cls, obj, current_user_id: int = None):
        data = cls.from_orm(obj)
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
        if current_user_id is not None:
            data.es_favorito = any(
                f.usuario_id == current_user_id for f in (obj.favoritos or [])
            )
        return data

    class Config:
        from_attributes = True

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
    fecha:          datetime

    @classmethod
    def from_orm_with_nombre(cls, obj):
        data = cls.from_orm(obj)
        if obj.usuario:
            data.usuario_nombre = obj.usuario.nombre
        return data

    class Config:
        from_attributes = True

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
    fecha:           datetime

    class Config:
        from_attributes = True

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
    fecha:          datetime
    class Config:
        from_attributes = True

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
    class Config:
        from_attributes = True

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
    class Config:
        from_attributes = True

# ── Budget / Presupuesto ──────────────────────────────────────────────────────

class PresupuestoItemBase(BaseModel):
    descripcion:    str
    cantidad:       float = 1
    costo_interno:  float = 0.0
    precio_cliente: float = 0.0

class PresupuestoItemCreate(PresupuestoItemBase):
    pass

class PresupuestoItemOut(PresupuestoItemBase):
    id:           int
    costo_interno: Optional[float] = None   # None for clients
    costo_total:  Optional[float] = None    # None for clients
    precio_total: float
    class Config:
        from_attributes = True

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
    fecha:          datetime
    class Config:
        from_attributes = True

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
    fecha_creacion:  datetime
    fecha_actualizacion: datetime
    class Config:
        from_attributes = True

# ── Plantilla Presupuesto ─────────────────────────────────────────────────────

class PlantillaPresupuestoBase(BaseModel):
    nombre:         str
    descripcion:    str
    costo_interno:  float = 0.0
    precio_cliente: float = 0.0
    categoria:      Optional[str] = "General"
    activo:         bool = True
    orden:          int = 0

class PlantillaPresupuestoCreate(PlantillaPresupuestoBase):
    pass

class PlantillaPresupuestoOut(PlantillaPresupuestoBase):
    id: int
    class Config:
        from_attributes = True

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
    fecha:              datetime
    origen_nombre:      Optional[str] = None
    class Config:
        from_attributes = True

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
    class Config:
        from_attributes = True

class ConfigSistemaUpdate(BaseModel):
    valor: str

# ── Rate Limit Info ───────────────────────────────────────────────────────────
class RateLimitStatus(BaseModel):
    ip_address:      str
    intentos_recientes: int
    bloqueado:       bool
    segundos_restantes: Optional[int] = None
