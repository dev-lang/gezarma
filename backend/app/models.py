from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum, Float, Boolean, Table, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from .database import Base
from .timeutils import utcnow

# ── Association Tables ────────────────────────────────────────────────────────
class TicketRepuesto(Base):
    __tablename__ = "ticket_repuestos"
    ticket_id   = Column(Integer, ForeignKey("tickets.id"),   primary_key=True)
    repuesto_id = Column(Integer, ForeignKey("repuestos.id"), primary_key=True)
    cantidad    = Column(Integer, default=1)
    ticket   = relationship("Ticket",   back_populates="repuestos_usados_assoc")
    repuesto = relationship("Repuesto")

ticket_tags = Table(
    "ticket_tags", Base.metadata,
    Column("ticket_id", Integer, ForeignKey("tickets.id")),
    Column("tag_id",    Integer, ForeignKey("tags.id"))
)

# ── Enums ────────────────────────────────────────────────────────────────────
class UserRole(str, enum.Enum):
    CLIENTE       = "cliente"
    TECNICO       = "tecnico"
    ADMINISTRADOR = "administrador"

class UserType(str, enum.Enum):
    PERSONA = "persona"
    EMPRESA = "empresa"

class TicketStatus(str, enum.Enum):
    NUEVO          = "Nuevo"
    REVISION       = "En revisión"
    APROBADO       = "Aprobado para RMA"
    RECIBIDO       = "Equipo recibido"
    DIAGNOSTICO    = "En diagnóstico"
    REPARACION     = "En reparación"
    ESPERA_REPUESTO= "Esperando repuestos"
    REPARADO       = "Reparado"
    ENVIADO        = "Enviado al cliente"
    CERRADO        = "Cerrado"
    CANCELADO      = "Cancelado"

# ── Event types for full audit history ───────────────────────────────────────
class EventoHistorial(str, enum.Enum):
    CAMBIO_ESTADO    = "cambio_estado"
    COMENTARIO       = "comentario"
    NOTA_INTERNA     = "nota_interna"
    TAG_AGREGADO     = "tag_agregado"
    TAG_ELIMINADO    = "tag_eliminado"
    TAG_EDITADO      = "tag_editado"
    REPUESTO_AGREGADO= "repuesto_agregado"
    CAMPO_EDITADO    = "campo_editado"
    TECNICO_ASIGNADO = "tecnico_asignado"
    TICKET_CLONADO   = "ticket_clonado"
    TICKET_RELACIONADO = "ticket_relacionado"
    TICKET_DESASOCIADO = "ticket_desasociado"
    ARCHIVO_SUBIDO   = "archivo_subido"
    ARCHIVO_ELIMINADO= "archivo_eliminado"

# ── Models ────────────────────────────────────────────────────────────────────
class Usuario(Base):
    __tablename__ = "usuarios"
    id              = Column(Integer, primary_key=True, index=True)
    username        = Column(String,  unique=True, index=True)
    password_hash   = Column(String)
    nombre          = Column(String)
    email           = Column(String,  unique=True, index=True)
    rol             = Column(String,  default=UserRole.CLIENTE)
    tipo_cliente    = Column(String,  default=UserType.PERSONA)
    activo          = Column(Boolean, default=True)
    fecha_creacion  = Column(DateTime, default=utcnow)
    telefono        = Column(String,  nullable=True)   # ← nuevo
    # Feature 1: forced password change
    must_change_password = Column(Boolean, default=False)
    # (temp_password_plain was removed: temp passwords are never stored in plain text)

    tickets_creados   = relationship("Ticket", back_populates="cliente",  foreign_keys="Ticket.usuario_id")
    tickets_asignados = relationship("Ticket", back_populates="tecnico",  foreign_keys="Ticket.tecnico_asignado")
    comentarios       = relationship("Comentario",     back_populates="usuario")
    historial_cambios = relationship("HistorialEstado", back_populates="usuario")
    favoritos         = relationship("TicketFavorito",  back_populates="usuario", cascade="all, delete-orphan")

class Producto(Base):
    __tablename__ = "productos"
    id                      = Column(Integer, primary_key=True, index=True)
    marca                   = Column(String)
    modelo                  = Column(String, index=True)
    categoria               = Column(String)
    periodo_garantia_meses  = Column(Integer, default=12)
    numero_parte            = Column(String, unique=True, nullable=True)
    tickets = relationship("Ticket", back_populates="producto_obj")

class Repuesto(Base):
    __tablename__ = "repuestos"
    id        = Column(Integer, primary_key=True, index=True)
    nombre    = Column(String)
    codigo    = Column(String, unique=True)
    stock     = Column(Integer, default=0)
    proveedor = Column(String)
    precio    = Column(Float, default=0.0)
    categoria = Column(String, nullable=True, default="General")
    stock_minimo = Column(Integer, nullable=False, default=0, server_default="0")  # 0 = sin alerta

class Tag(Base):
    __tablename__ = "tags"
    id     = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, unique=True)
    color  = Column(String, default="#3b82f6")

class DiagnosticaPlantilla(Base):
    """Diagnosis templates — editable from admin (Feature: diagnosis templates admin)."""
    __tablename__ = "diagnostica_plantillas"
    id      = Column(Integer, primary_key=True, index=True)
    nombre  = Column(String, unique=True)   # pill label
    texto   = Column(Text)                  # template body
    orden   = Column(Integer, default=0)    # display order

class TicketStatusConfig(Base):
    """Configurable ticket statuses — admins can rename, add, deactivate (Feature: status admin)."""
    __tablename__ = "ticket_status_config"
    id       = Column(Integer, primary_key=True, index=True)
    valor    = Column(String, unique=True)   # the actual value stored in tickets.estado
    etiqueta = Column(String)                # display label
    color    = Column(String, default="#6b7280")  # hex for badge
    orden    = Column(Integer, default=0)
    activo   = Column(Boolean, default=True)
    es_final = Column(Boolean, default=False)  # Cerrado/Cancelado → sets fecha_cierre

class RmaCounter(Base):
    """Persistent counter for sequential RMA number generation (Feature 12)."""
    __tablename__ = "rma_counters"
    id          = Column(Integer, primary_key=True, index=True)
    year        = Column(Integer, index=True)
    rol_prefix  = Column(String)   # e.g. "CL", "TC", "AD"
    serie       = Column(String)   # e.g. "AA", "AB", ..., "ZZ"
    last_seq    = Column(Integer, default=0)  # 1-999

class Ticket(Base):
    __tablename__ = "tickets"
    id              = Column(Integer, primary_key=True, index=True)
    numero_rma      = Column(String, unique=True, index=True)
    usuario_id      = Column(Integer, ForeignKey("usuarios.id"))
    producto_id     = Column(Integer, ForeignKey("productos.id"), nullable=True)
    producto        = Column(String)
    numero_serie    = Column(String, index=True)
    fecha_compra    = Column(DateTime)
    en_garantia     = Column(Boolean, default=True)
    descripcion     = Column(Text)
    estado          = Column(String, default=TicketStatus.NUEVO)
    prioridad       = Column(String, default="Normal")
    diagnostico     = Column(Text, nullable=True)
    tecnico_asignado= Column(Integer, ForeignKey("usuarios.id"), nullable=True)

    # SLA y Tiempos
    fecha_creacion      = Column(DateTime, default=utcnow)
    fecha_actualizacion = Column(DateTime, default=utcnow, onupdate=utcnow)
    fecha_cierre        = Column(DateTime, nullable=True)
    deadline_sla        = Column(DateTime, nullable=True)
    # Último aviso de SLA enviado: para qué vencimiento y de qué nivel
    # ("por_vencer" o "vencido"), así cada aviso sale una sola vez
    sla_aviso_deadline  = Column(DateTime, nullable=True)
    sla_aviso_nivel     = Column(String, nullable=True)

    # Envíos
    empresa_transporte = Column(String, nullable=True)
    tracking_number    = Column(String, nullable=True)
    fecha_envio        = Column(DateTime, nullable=True)

    # Feature 11: ticket cloning / relations
    clonado_de        = Column(Integer, ForeignKey("tickets.id"), nullable=True)
    ticket_relacionado= Column(Integer, ForeignKey("tickets.id"), nullable=True)

    cliente      = relationship("Usuario", back_populates="tickets_creados",  foreign_keys=[usuario_id])
    tecnico      = relationship("Usuario", back_populates="tickets_asignados", foreign_keys=[tecnico_asignado])
    producto_obj = relationship("Producto", back_populates="tickets")
    origen       = relationship("Ticket", foreign_keys=[clonado_de],         remote_side="Ticket.id", uselist=False)
    relacionado  = relationship("Ticket", foreign_keys=[ticket_relacionado],  remote_side="Ticket.id", uselist=False)

    comentarios          = relationship("Comentario",      back_populates="ticket")
    historial            = relationship("HistorialEstado", back_populates="ticket")
    adjuntos             = relationship("Adjunto",         back_populates="ticket")
    favoritos            = relationship("TicketFavorito",  back_populates="ticket", cascade="all, delete-orphan")
    tags                 = relationship("Tag",             secondary=ticket_tags)
    repuestos_usados_assoc = relationship("TicketRepuesto", back_populates="ticket", cascade="all, delete-orphan")
    presupuesto          = relationship("Presupuesto", back_populates="ticket", uselist=False,
                                        cascade="all, delete-orphan")

    @property
    def repuestos_usados(self):
        result = []
        for assoc in self.repuestos_usados_assoc:
            rep = assoc.repuesto
            class RepuestoConCantidad: pass
            obj = RepuestoConCantidad()
            obj.id       = rep.id
            obj.nombre   = rep.nombre
            obj.codigo   = rep.codigo
            obj.proveedor= rep.proveedor
            obj.precio   = rep.precio
            obj.stock    = rep.stock
            obj.stock_minimo = rep.stock_minimo
            obj.categoria = rep.categoria
            obj.cantidad = assoc.cantidad
            result.append(obj)
        return result

class TicketFavorito(Base):
    """Per-user ticket bookmark/star."""
    __tablename__ = "tickets_favoritos"
    id         = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), index=True)
    ticket_id  = Column(Integer, ForeignKey("tickets.id"),  index=True)
    fecha      = Column(DateTime, default=utcnow)

    usuario = relationship("Usuario", back_populates="favoritos")
    ticket  = relationship("Ticket")

    __table_args__ = (
        # One favourite entry per user per ticket
        __import__("sqlalchemy").UniqueConstraint("usuario_id", "ticket_id", name="uq_favorito_usuario_ticket"),
    )


class Comentario(Base):
    __tablename__ = "comentarios"
    id          = Column(Integer, primary_key=True, index=True)
    ticket_id   = Column(Integer, ForeignKey("tickets.id"))
    usuario_id  = Column(Integer, ForeignKey("usuarios.id"))
    comentario  = Column(Text)
    is_internal = Column(Boolean, default=False)
    fecha       = Column(DateTime, default=utcnow)
    ticket  = relationship("Ticket",   back_populates="comentarios")
    usuario = relationship("Usuario",  back_populates="comentarios")

class StockMovimiento(Base):
    __tablename__ = "stock_movimientos"
    id             = Column(Integer, primary_key=True, index=True)
    repuesto_id    = Column(Integer, ForeignKey("repuestos.id"))
    ticket_id      = Column(Integer, ForeignKey("tickets.id"),   nullable=True)
    usuario_id     = Column(Integer, ForeignKey("usuarios.id"))
    tipo           = Column(String)
    cantidad       = Column(Integer)
    stock_anterior = Column(Integer)
    stock_nuevo    = Column(Integer)
    nota           = Column(String, nullable=True)
    fecha          = Column(DateTime, default=utcnow)
    repuesto = relationship("Repuesto")
    ticket   = relationship("Ticket")
    usuario  = relationship("Usuario")

class HistorialEstado(Base):
    """Full audit trail — records every meaningful change on a ticket."""
    __tablename__ = "historial_estados"
    id              = Column(Integer, primary_key=True, index=True)
    ticket_id       = Column(Integer, ForeignKey("tickets.id"))
    tipo_evento     = Column(String, default=EventoHistorial.CAMBIO_ESTADO)
    estado_anterior = Column(String, nullable=True)
    estado_nuevo    = Column(String, nullable=True)
    campo           = Column(String, nullable=True)   # field name for CAMPO_EDITADO
    valor_anterior  = Column(Text,   nullable=True)
    valor_nuevo     = Column(Text,   nullable=True)
    detalle         = Column(String, nullable=True)   # human-readable description
    usuario_id      = Column(Integer, ForeignKey("usuarios.id"))
    fecha           = Column(DateTime, default=utcnow)
    ticket  = relationship("Ticket",  back_populates="historial")
    usuario = relationship("Usuario", back_populates="historial_cambios")

class Adjunto(Base):
    __tablename__ = "adjuntos"
    id              = Column(Integer, primary_key=True, index=True)
    ticket_id       = Column(Integer, ForeignKey("tickets.id"))
    nombre_archivo  = Column(String)          # original filename shown to user
    nombre_guardado = Column(String)          # UUID-prefixed safe filename on disk
    ruta_archivo    = Column(String)          # full path on disk
    tamanio         = Column(Integer, default=0)   # bytes
    mime_type       = Column(String, default="")
    fecha           = Column(DateTime, default=utcnow)
    ticket = relationship("Ticket", back_populates="adjuntos")

# ── Budget Models ─────────────────────────────────────────────────────────────

class PresupuestoEstado(str, enum.Enum):
    BORRADOR  = "borrador"
    ENVIADO   = "enviado"
    APROBADO  = "aprobado"
    RECHAZADO = "rechazado"

class PresupuestoItem(Base):
    __tablename__ = "presupuesto_items"
    id              = Column(Integer, primary_key=True, index=True)
    presupuesto_id  = Column(Integer, ForeignKey("presupuestos.id", ondelete="CASCADE"))
    descripcion     = Column(String)
    cantidad        = Column(Float, default=1)
    costo_interno   = Column(Float, default=0.0)
    precio_cliente  = Column(Float, default=0.0)
    # Si el ítem es un repuesto del catálogo: se descuenta del stock al aprobar el presupuesto
    repuesto_id     = Column(Integer, ForeignKey("repuestos.id"), nullable=True)
    presupuesto     = relationship("Presupuesto", back_populates="items")
    repuesto        = relationship("Repuesto")

    @property
    def costo_total(self):
        return self.cantidad * self.costo_interno

    @property
    def precio_total(self):
        return self.cantidad * self.precio_cliente

class Presupuesto(Base):
    __tablename__ = "presupuestos"
    id              = Column(Integer, primary_key=True, index=True)
    ticket_id       = Column(Integer, ForeignKey("tickets.id", ondelete="CASCADE"))
    estado          = Column(String, default=PresupuestoEstado.BORRADOR)
    version         = Column(Integer, default=1)
    notas           = Column(Text, nullable=True)
    fecha_creacion  = Column(DateTime, default=utcnow)
    fecha_actualizacion = Column(DateTime, default=utcnow, onupdate=utcnow)
    creado_por      = Column(Integer, ForeignKey("usuarios.id"))
    actualizado_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)

    ticket      = relationship("Ticket", back_populates="presupuesto")
    items       = relationship("PresupuestoItem", back_populates="presupuesto",
                               cascade="all, delete-orphan")
    versiones   = relationship("PresupuestoVersion", back_populates="presupuesto",
                               cascade="all, delete-orphan", order_by="PresupuestoVersion.id.desc()")
    creador     = relationship("Usuario", foreign_keys=[creado_por])
    actualizador = relationship("Usuario", foreign_keys=[actualizado_por])

    @property
    def costo_total(self):
        return sum(i.cantidad * i.costo_interno for i in self.items)

    @property
    def precio_total(self):
        return sum(i.cantidad * i.precio_cliente for i in self.items)

    @property
    def ganancia(self):
        return self.precio_total - self.costo_total

class PresupuestoVersion(Base):
    """Snapshot of a presupuesto before each modification."""
    __tablename__ = "presupuesto_versiones"
    id              = Column(Integer, primary_key=True, index=True)
    presupuesto_id  = Column(Integer, ForeignKey("presupuestos.id", ondelete="CASCADE"))
    version         = Column(Integer)
    estado          = Column(String)
    notas           = Column(Text, nullable=True)
    items_snapshot  = Column(JSON)   # list of item dicts at time of snapshot
    usuario_id      = Column(Integer, ForeignKey("usuarios.id"))
    fecha           = Column(DateTime, default=utcnow)

    presupuesto = relationship("Presupuesto", back_populates="versiones")
    usuario     = relationship("Usuario")

class PlantillaPresupuesto(Base):
    """Budget item templates configurable from admin."""
    __tablename__ = "plantillas_presupuesto"
    id              = Column(Integer, primary_key=True, index=True)
    nombre          = Column(String, unique=True)
    descripcion     = Column(String)
    costo_interno   = Column(Float, default=0.0)
    precio_cliente  = Column(Float, default=0.0)
    categoria       = Column(String, nullable=True, default="General")
    activo          = Column(Boolean, default=True)
    orden           = Column(Integer, default=0)

class TipoNotificacion(str, enum.Enum):
    COMENTARIO      = "comentario"
    CAMBIO_ESTADO   = "cambio_estado"
    CAMPO_EDITADO   = "campo_editado"
    PRESUPUESTO     = "presupuesto"
    ASIGNACION      = "asignacion"
    REPUESTO        = "repuesto"

class Notificacion(Base):
    """In-app notification for assigned technician or ticket owner."""
    __tablename__ = "notificaciones"
    id              = Column(Integer, primary_key=True, index=True)
    usuario_id      = Column(Integer, ForeignKey("usuarios.id"), index=True)  # recipient
    ticket_id       = Column(Integer, ForeignKey("tickets.id"), nullable=True)
    tipo            = Column(String, default=TipoNotificacion.COMENTARIO)
    titulo          = Column(String)
    mensaje         = Column(Text)
    leida           = Column(Boolean, default=False, index=True)
    fecha           = Column(DateTime, default=utcnow, index=True)
    origen_usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)  # who triggered it

    usuario         = relationship("Usuario", foreign_keys=[usuario_id])
    ticket          = relationship("Ticket")
    origen_usuario  = relationship("Usuario", foreign_keys=[origen_usuario_id])

class Auditoria(Base):
    __tablename__ = "auditoria"
    id          = Column(Integer, primary_key=True, index=True)
    usuario_id  = Column(Integer, ForeignKey("usuarios.id"))
    accion      = Column(String)
    detalle     = Column(Text)
    ip_address  = Column(String)
    fecha       = Column(DateTime, default=utcnow)

class ConfigSistema(Base):
    """Key-value system configuration settable from admin panel."""
    __tablename__ = "config_sistema"
    id    = Column(Integer, primary_key=True, index=True)
    clave = Column(String, unique=True, index=True)
    valor = Column(String)

class LoginAttempt(Base):
    """Track failed login attempts per IP for brute-force protection."""
    __tablename__ = "login_attempts"
    id         = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String, index=True)
    username   = Column(String)
    fecha      = Column(DateTime, default=utcnow)
    exitoso    = Column(Boolean, default=False)
