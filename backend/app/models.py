from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Float, Boolean, Table, JSON, LargeBinary, UniqueConstraint
from sqlalchemy.orm import deferred, relationship
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
    Column("ticket_id", Integer, ForeignKey("tickets.id"), primary_key=True),
    Column("tag_id",    Integer, ForeignKey("tags.id"), primary_key=True)
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
    SERVICIO_EXTERNO = "En servicio técnico oficial"   # enviado a la garantía del fabricante
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
    CHECKLIST_INGRESO= "checklist_ingreso"
    FIRMA_REGISTRADA = "firma_registrada"
    TIEMPO_EDITADO   = "tiempo_editado"     # horas cargadas, movidas o corregidas desde el calendario
    UBICACION_CAMBIADA = "ubicacion_cambiada" # el equipo se guardó en otro lugar
    ENVIO_EXTERNO    = "envio_externo"      # enviado al fabricante / servicio oficial, o de vuelta

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
    # Va dentro del JWT: al cambiar o resetear la clave se incrementa y los
    # tokens anteriores dejan de valer
    token_version   = Column(Integer, nullable=False, default=0, server_default="0")
    # es-AR / es-ES / en / pt-BR; vacío = el predeterminado del taller (ver idiomas.py)
    idioma          = Column(String, nullable=True)
    # Orden, ancho y bloques ocultos del panel de control (JSON; vacío = el predeterminado). Ver services/panel.py
    panel_config    = Column(Text, nullable=True)
    demo = Column(Boolean, nullable=False, default=False, server_default="0")   # datos de ejemplo del setup (se borran juntos)

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
    demo = Column(Boolean, nullable=False, default=False, server_default="0")   # datos de ejemplo del setup (se borran juntos)
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
    demo = Column(Boolean, nullable=False, default=False, server_default="0")   # datos de ejemplo del setup (se borran juntos)
    ubicacion_id = Column(Integer, ForeignKey("ubicaciones.id", ondelete="SET NULL"), nullable=True, index=True)
    ubicacion    = relationship("Ubicacion", foreign_keys=[ubicacion_id])

    @property
    def ubicacion_ruta(self):
        from .services.ubicaciones import ruta
        return ruta(self.ubicacion) if self.ubicacion else None

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
    __table_args__ = (UniqueConstraint("year", "rol_prefix", name="uq_rma_counters_year_prefix"),)
    id          = Column(Integer, primary_key=True, index=True)
    year        = Column(Integer, index=True)
    rol_prefix  = Column(String)   # e.g. "CL", "TC", "AD"
    serie       = Column(String)   # e.g. "AA", "AB", ..., "ZZ"
    last_seq    = Column(Integer, default=0)  # 1-999

class Ticket(Base):
    __tablename__ = "tickets"
    id              = Column(Integer, primary_key=True, index=True)
    numero_rma      = Column(String, unique=True, index=True)
    usuario_id      = Column(Integer, ForeignKey("usuarios.id"), index=True)
    producto_id     = Column(Integer, ForeignKey("productos.id"), nullable=True)
    producto        = Column(String)
    numero_serie    = Column(String, index=True)
    fecha_compra    = Column(DateTime)
    en_garantia     = Column(Boolean, default=True)
    descripcion     = Column(Text)
    estado          = Column(String, default=TicketStatus.NUEVO, index=True)
    prioridad       = Column(String, default="Normal")
    diagnostico     = Column(Text, nullable=True)
    tecnico_asignado= Column(Integer, ForeignKey("usuarios.id"), nullable=True, index=True)

    # SLA y Tiempos
    fecha_creacion      = Column(DateTime, default=utcnow, index=True)
    fecha_actualizacion = Column(DateTime, default=utcnow, onupdate=utcnow)
    fecha_cierre        = Column(DateTime, nullable=True)
    deadline_sla        = Column(DateTime, nullable=True, index=True)
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

    # Recepción: accesorios, estado físico, si enciende y si tiene bloqueo
    # (dict; ver schemas.ChecklistIngreso). La clave de desbloqueo NO se guarda.
    checklist_ingreso = Column(JSON, nullable=True)

    # Retiro: desde cuándo está listo para retirar, último aviso al cliente y
    # si ya se avisó al taller que venció el plazo de guarda
    fecha_listo            = Column(DateTime, nullable=True)
    retiro_ultimo_aviso    = Column(DateTime, nullable=True)
    retiro_recordatorios   = Column(Integer, nullable=False, default=0, server_default="0")
    retiro_vencido_avisado = Column(Boolean, nullable=False, default=False, server_default="0")

    # Reingreso del mismo equipo dentro de la garantía de la reparación
    reingreso_de       = Column(Integer, ForeignKey("tickets.id"), nullable=True)
    reingreso_garantia = Column(Boolean, nullable=False, default=False, server_default="0")

    # Dónde está guardado el equipo y desde cuándo (los cambios quedan en ubicacion_movimientos)
    ubicacion_id    = Column(Integer, ForeignKey("ubicaciones.id", ondelete="SET NULL"), nullable=True, index=True)
    ubicacion_fecha = Column(DateTime, nullable=True)
    demo = Column(Boolean, nullable=False, default=False, server_default="0")   # datos de ejemplo del setup (se borran juntos)

    cliente      = relationship("Usuario", back_populates="tickets_creados",  foreign_keys=[usuario_id])
    tecnico      = relationship("Usuario", back_populates="tickets_asignados", foreign_keys=[tecnico_asignado])
    producto_obj = relationship("Producto", back_populates="tickets")
    origen       = relationship("Ticket", foreign_keys=[clonado_de],         remote_side="Ticket.id", uselist=False)
    relacionado  = relationship("Ticket", foreign_keys=[ticket_relacionado],  remote_side="Ticket.id", uselist=False)
    reingreso_origen = relationship("Ticket", foreign_keys=[reingreso_de],    remote_side="Ticket.id", uselist=False)

    comentarios          = relationship("Comentario",      back_populates="ticket")
    historial            = relationship("HistorialEstado", back_populates="ticket")
    adjuntos             = relationship("Adjunto",         back_populates="ticket")
    favoritos            = relationship("TicketFavorito",  back_populates="ticket", cascade="all, delete-orphan")
    tags                 = relationship("Tag",             secondary=ticket_tags)
    repuestos_usados_assoc = relationship("TicketRepuesto", back_populates="ticket", cascade="all, delete-orphan")
    presupuesto          = relationship("Presupuesto", back_populates="ticket", uselist=False,
                                        cascade="all, delete-orphan")
    firmas               = relationship("Firma", back_populates="ticket", cascade="all, delete-orphan")
    encuesta             = relationship("Encuesta", back_populates="ticket", uselist=False,
                                        cascade="all, delete-orphan")
    tiempos              = relationship("TiempoTrabajo", back_populates="ticket", cascade="all, delete-orphan")
    ubicacion            = relationship("Ubicacion", foreign_keys=[ubicacion_id])
    envios_externos      = relationship("EnvioExterno", back_populates="ticket", cascade="all, delete-orphan",
                                        order_by="EnvioExterno.fecha_envio")

    def firma(self, momento: str):
        return next((f for f in self.firmas if f.momento == momento), None)

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
            obj.ubicacion_id = rep.ubicacion_id
            obj.ubicacion_ruta = rep.ubicacion_ruta
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
    ticket_id   = Column(Integer, ForeignKey("tickets.id"), index=True)
    usuario_id  = Column(Integer, ForeignKey("usuarios.id"))
    comentario  = Column(Text)
    is_internal = Column(Boolean, default=False)
    fecha       = Column(DateTime, default=utcnow)
    ticket  = relationship("Ticket",   back_populates="comentarios")
    usuario = relationship("Usuario",  back_populates="comentarios")

class StockMovimiento(Base):
    __tablename__ = "stock_movimientos"
    id             = Column(Integer, primary_key=True, index=True)
    repuesto_id    = Column(Integer, ForeignKey("repuestos.id"), index=True)
    ticket_id      = Column(Integer, ForeignKey("tickets.id"),   nullable=True, index=True)
    usuario_id     = Column(Integer, ForeignKey("usuarios.id"))
    tipo           = Column(String)
    cantidad       = Column(Integer)
    stock_anterior = Column(Integer)
    stock_nuevo    = Column(Integer)
    nota           = Column(String, nullable=True)
    fecha          = Column(DateTime, default=utcnow)
    # Recepción de un pedido a proveedor (para poder anularla corrigiendo el pedido)
    pedido_item_id = Column(Integer, ForeignKey("pedido_items.id"), nullable=True)
    # Los movimientos no se borran: se anulan con un movimiento inverso
    anula_id       = Column(Integer, ForeignKey("stock_movimientos.id"), nullable=True)
    anulado        = Column(Boolean, nullable=False, default=False, server_default="0")
    repuesto = relationship("Repuesto")
    ticket   = relationship("Ticket")
    usuario  = relationship("Usuario")
    pedido_item = relationship("PedidoItem")

class HistorialEstado(Base):
    """Full audit trail — records every meaningful change on a ticket."""
    __tablename__ = "historial_estados"
    id              = Column(Integer, primary_key=True, index=True)
    ticket_id       = Column(Integer, ForeignKey("tickets.id"), index=True)
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
    ticket_id       = Column(Integer, ForeignKey("tickets.id"), index=True)
    nombre_archivo  = Column(String)          # original filename shown to user
    nombre_guardado = Column(String)          # UUID-prefixed safe filename on disk
    ruta_archivo    = Column(String)          # full path on disk
    tamanio         = Column(Integer, default=0)   # bytes
    mime_type       = Column(String, default="")
    fecha           = Column(DateTime, default=utcnow)
    categoria       = Column(String, nullable=True)   # "ingreso" = foto del estado al recibirlo
    ticket = relationship("Ticket", back_populates="adjuntos")


class PedidoProveedor(Base):
    """Pedido de repuestos a un proveedor: borrador → enviado → parcial / recibido (o cancelado)."""
    __tablename__ = "pedidos_proveedor"
    id              = Column(Integer, primary_key=True, index=True)
    proveedor       = Column(String, nullable=False, index=True)
    estado          = Column(String, nullable=False, default="borrador", index=True)
    notas           = Column(Text, nullable=True)
    fecha_creacion  = Column(DateTime, default=utcnow)
    fecha_envio     = Column(DateTime, nullable=True)
    fecha_recepcion = Column(DateTime, nullable=True)
    creado_por      = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    items   = relationship("PedidoItem", back_populates="pedido", cascade="all, delete-orphan",
                           order_by="PedidoItem.id")
    usuario = relationship("Usuario")


class PedidoItem(Base):
    __tablename__ = "pedido_items"
    id          = Column(Integer, primary_key=True, index=True)
    pedido_id   = Column(Integer, ForeignKey("pedidos_proveedor.id", ondelete="CASCADE"), nullable=False, index=True)
    repuesto_id = Column(Integer, ForeignKey("repuestos.id"), nullable=False)
    cantidad    = Column(Integer, nullable=False)
    recibido    = Column(Integer, nullable=False, default=0, server_default="0")
    precio      = Column(Float, nullable=True)   # costo unitario al armar el pedido
    pedido   = relationship("PedidoProveedor", back_populates="items")
    repuesto = relationship("Repuesto")


class TiempoTrabajo(Base):
    """Un tramo de trabajo de un técnico (fin vacío = en curso): sobre un ticket o,
    sin ticket, en una tarea del taller (categoria: capacitación, limpieza…)."""
    __tablename__ = "tiempos_trabajo"
    id         = Column(Integer, primary_key=True, index=True)
    ticket_id  = Column(Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=True, index=True)
    categoria  = Column(String, nullable=True)   # solo si no hay ticket (ver services/horas.py)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    inicio     = Column(DateTime, nullable=False, default=utcnow, index=True)
    fin        = Column(DateTime, nullable=True)
    nota       = Column(String, nullable=True)
    manual     = Column(Boolean, nullable=False, default=False, server_default="0")
    editado    = Column(Boolean, nullable=False, default=False, server_default="0")
    ticket  = relationship("Ticket", back_populates="tiempos")
    usuario = relationship("Usuario")


class Ubicacion(Base):
    """Lugar donde se guardan equipos y repuestos, en árbol: Depósito → Estante B → B3.
    tipo "externa" = fuera del taller (fabricante, servicio oficial): la usa el sistema."""
    __tablename__ = "ubicaciones"
    id       = Column(Integer, primary_key=True, index=True)
    nombre   = Column(String(60), nullable=False)
    padre_id = Column(Integer, ForeignKey("ubicaciones.id", ondelete="RESTRICT"), nullable=True, index=True)
    codigo   = Column(String(20), unique=True, index=True)      # lo que lleva la etiqueta: U-0001
    tipo     = Column(String(10), nullable=False, default="taller", server_default="taller")
    nota     = Column(String(200), nullable=True)
    activa   = Column(Boolean, nullable=False, default=True, server_default="1")
    orden    = Column(Integer, nullable=False, default=0, server_default="0")
    demo = Column(Boolean, nullable=False, default=False, server_default="0")   # datos de ejemplo del setup (se borran juntos)
    padre    = relationship("Ubicacion", remote_side="Ubicacion.id")


class UbicacionMovimiento(Base):
    """Cada vez que un equipo o un repuesto cambia de lugar (no se borran)."""
    __tablename__ = "ubicacion_movimientos"
    id          = Column(Integer, primary_key=True, index=True)
    ticket_id   = Column(Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=True, index=True)
    repuesto_id = Column(Integer, ForeignKey("repuestos.id", ondelete="CASCADE"), nullable=True, index=True)
    desde_id    = Column(Integer, ForeignKey("ubicaciones.id", ondelete="SET NULL"), nullable=True)
    hacia_id    = Column(Integer, ForeignKey("ubicaciones.id", ondelete="SET NULL"), nullable=True)
    usuario_id  = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    motivo      = Column(String(30), nullable=True)   # manual, escaneo, mostrador, lote, envio, regreso, importacion
    fecha       = Column(DateTime, default=utcnow, index=True)
    desde   = relationship("Ubicacion", foreign_keys=[desde_id])
    hacia   = relationship("Ubicacion", foreign_keys=[hacia_id])
    usuario = relationship("Usuario")


class EnvioExterno(Base):
    """Un envío del equipo (o de una parte) al fabricante o a un servicio oficial, y su vuelta."""
    __tablename__ = "envios_externos"
    id              = Column(Integer, primary_key=True, index=True)
    ticket_id       = Column(Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    destino         = Column(String(120), nullable=False)      # fabricante o servicio oficial
    numero_caso     = Column(String(60), nullable=True)        # RMA / caso del fabricante
    fecha_envio     = Column(DateTime, nullable=False, default=utcnow)
    transportista   = Column(String(80), nullable=True)
    guia            = Column(String(80), nullable=True)
    contenido       = Column(String(120), nullable=True)       # equipo completo, solo la placa…
    accesorios      = Column(String(300), nullable=True)
    fecha_estimada  = Column(DateTime, nullable=True)
    nota            = Column(Text, nullable=True)
    estado          = Column(String(10), nullable=False, default="enviado", server_default="enviado", index=True)
    fecha_recepcion = Column(DateTime, nullable=True)
    resultado       = Column(String(15), nullable=True)        # reparado, reemplazado, rechazado, sin_falla
    serie_nueva     = Column(String(80), nullable=True)
    comprobante     = Column(String(80), nullable=True)
    nota_recepcion  = Column(Text, nullable=True)
    usuario_envio_id     = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    usuario_recepcion_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    ticket            = relationship("Ticket", back_populates="envios_externos")
    usuario_envio     = relationship("Usuario", foreign_keys=[usuario_envio_id])
    usuario_recepcion = relationship("Usuario", foreign_keys=[usuario_recepcion_id])


class TiempoCambio(Base):
    """Registro de cada alta, edición, movimiento o borrado de horas hecho a mano
    (quién, cuándo, antes y después). Sobrevive al borrado del tramo."""
    __tablename__ = "tiempo_cambios"
    id          = Column(Integer, primary_key=True, index=True)
    registro_id = Column(Integer, ForeignKey("tiempos_trabajo.id", ondelete="SET NULL"), nullable=True, index=True)
    tecnico_id  = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)   # dueño de las horas
    usuario_id  = Column(Integer, ForeignKey("usuarios.id"), nullable=False)               # quién hizo el cambio
    fecha       = Column(DateTime, nullable=False, default=utcnow)
    accion      = Column(String, nullable=False)   # alta / edicion / movido / borrado
    antes       = Column(JSON, nullable=True)
    despues     = Column(JSON, nullable=True)
    usuario = relationship("Usuario", foreign_keys=[usuario_id])


class Encuesta(Base):
    """Calificación del cliente al cerrar el ticket (una por ticket)."""
    __tablename__ = "encuestas"
    id         = Column(Integer, primary_key=True, index=True)
    ticket_id  = Column(Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, unique=True)
    puntaje    = Column(Integer, nullable=False)        # 1 a 5
    comentario = Column(Text, nullable=True)
    fecha      = Column(DateTime, default=utcnow, index=True)
    origen     = Column(String, nullable=True)          # "cuenta" | "seguimiento"
    ticket = relationship("Ticket", back_populates="encuesta")


class Firma(Base):
    """Firma del cliente en pantalla, al dejar el equipo ("ingreso") o al
    retirarlo ("entrega"). Una por momento: firmar de nuevo la reemplaza."""
    __tablename__ = "firmas"
    __table_args__ = (UniqueConstraint("ticket_id", "momento", name="uq_firmas_ticket_momento"),)
    id             = Column(Integer, primary_key=True, index=True)
    ticket_id      = Column(Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    momento        = Column(String, nullable=False)
    # PNG en blanco y negro. Diferida: solo se lee al mostrar o imprimir la firma
    # (los listados de tickets cargan las firmas para saber si están, no la imagen)
    imagen         = deferred(Column(LargeBinary, nullable=False))
    ancho          = Column(Integer, nullable=False)
    alto           = Column(Integer, nullable=False)
    aclaracion     = Column(String, nullable=True)
    fecha          = Column(DateTime, default=utcnow)
    registrado_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    ticket = relationship("Ticket", back_populates="firmas")

# ── Budget Models ─────────────────────────────────────────────────────────────

class PresupuestoEstado(str, enum.Enum):
    BORRADOR  = "borrador"
    ENVIADO   = "enviado"
    APROBADO  = "aprobado"
    RECHAZADO = "rechazado"

class PresupuestoItem(Base):
    __tablename__ = "presupuesto_items"
    id              = Column(Integer, primary_key=True, index=True)
    presupuesto_id  = Column(Integer, ForeignKey("presupuestos.id", ondelete="CASCADE"), index=True)
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
    ticket_id       = Column(Integer, ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
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
    # Ítem típico de un modelo: se sugiere primero al presupuestar ese producto
    producto_id     = Column(Integer, ForeignKey("productos.id", ondelete="SET NULL"), nullable=True, index=True)
    producto        = relationship("Producto")

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
    username   = Column(String, index=True)
    fecha      = Column(DateTime, default=utcnow)
    exitoso    = Column(Boolean, default=False)
