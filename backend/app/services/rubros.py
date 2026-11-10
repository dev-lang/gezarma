"""
rubros.py — Lo típico de cada tipo de taller, para la configuración inicial.

Cada rubro propone estados extra, el checklist de ingreso (accesorios y
preguntas Sí / No), categorías de productos, plantillas de diagnóstico, los
plazos de SLA y el tamaño de etiqueta. Si se eligen varios, se suma todo y
para los plazos se toma el más largo (para no tener alertas de más).
Los datos de ejemplo (productos, repuestos y fallas) son para "Probar con
datos de ejemplo"; se marcan como demo y se borran juntos (ver setup.py).
"""

# Plantillas de diagnóstico que trae una instalación nueva (main.seed_data).
# Si el taller no eligió Computación y siguen sin tocar, el setup las quita.
SEMILLA_PLANTILLAS = [
    ("No enciende",  "No enciende. Se verificó fuente de alimentación y placa base. Sin tensión en conector de batería."),
    ("Batería",      "Falla de batería confirmada. Capacidad de ciclos agotada. Se procede a reemplazo bajo garantía."),
    ("Pantalla",     "Pantalla con daño físico (rotura de cristal / retroiluminación fallida). Requiere reemplazo de módulo LCD completo."),
    ("Teclado",      "Teclado con teclas sin respuesta / daño por líquido. Se realizó limpieza con IPA 99%. Requiere reemplazo de membrana."),
    ("Disco",        "Unidad de almacenamiento con sectores defectuosos detectados. Se realizó respaldo de datos y reemplazo de unidad."),
    ("Líquido",      "Equipo ingresó con daño por líquido. Corrosión en placa base. Se realizó limpieza ultrasónica."),
    ("Sin falla",    "Equipo revisado. No se detectaron fallas de hardware. Se realizó reinstalación de sistema operativo y actualización de drivers."),
]

# Estados que algunos rubros suman: (color, orden). Los de siempre ya están en main.seed_data.
ESTADOS_EXTRA = {
    "Respaldo de datos": ("#0891b2", 4),
    "En prueba":         ("#65a30d", 6),
}

# Los accesorios que trae el checklist sin configurar (igual que el default del ajuste)
ACCESORIOS_BASE = ["Cargador", "Cable", "Caja", "Funda"]

RUBROS = {
    "celulares": dict(
        nombre="Celulares y tablets",
        descripcion="Smartphones, tablets y relojes inteligentes.",
        icono="telefono",
        estados=["Respaldo de datos"],
        accesorios=["Cargador", "Cable", "Funda", "Chip / SIM", "Tarjeta de memoria", "Lápiz"],
        controles=["¿Tiene la pantalla rota?", "¿Se desvinculó la cuenta Google / iCloud?",
                   "¿Se retiraron el chip y la memoria?", "¿Tiene signos de humedad?"],
        categorias=["Celulares", "Tablets", "Smartwatches"],
        plantillas=[
            ("Pantalla rota", "Módulo de pantalla con daño físico (vidrio y/o display). Se reemplaza el módulo completo y se prueba el táctil en toda la superficie."),
            ("Batería agotada", "Batería con capacidad reducida o hinchada. Se reemplaza y se verifica la carga y el consumo en reposo."),
            ("Pin de carga", "Conector de carga con suciedad o pines dañados. Se limpia o reemplaza el flex de carga y se prueba con cargador original."),
            ("Placa", "Falla en placa principal (consumo anormal / no da imagen). Se diagnostica con fuente regulada; requiere reparación a nivel componente."),
            ("Humedad", "Equipo con ingreso de líquido. Se desarma, se limpia la placa con ultrasonido e IPA y se prueban todas las funciones."),
            ("Software", "Falla de software (reinicios / no inicia el sistema). Se reinstala el firmware oficial. Se informó al cliente la pérdida de datos no respaldados."),
        ],
        sla=(24, 24, 2), etiqueta="50x25",
        demo=dict(
            productos=[("Samsung", "Galaxy A54", "Celulares", 12), ("Apple", "iPhone 12", "Celulares", 12),
                       ("Lenovo", "Tab M10", "Tablets", 12)],
            repuestos=[("Módulo pantalla Galaxy A54", "EJ-CEL-PAN-A54", "Distribuidora Móvil", 85000, 3, 2),
                       ("Batería iPhone 12", "EJ-CEL-BAT-IP12", "Distribuidora Móvil", 42000, 1, 2),
                       ("Flex de carga USB-C genérico", "EJ-CEL-FLEX-C", "Distribuidora Móvil", 9500, 8, 3)],
            fallas=["Se le cayó y la pantalla quedó negra, vibra al encender.", "La batería dura medio día y se calienta.",
                    "No carga, hay que mover el cable."],
        ),
    ),
    "computacion": dict(
        nombre="Computación",
        descripcion="Notebooks, PC de escritorio, monitores e impresoras.",
        icono="notebook",
        estados=["Respaldo de datos"],
        accesorios=["Cargador", "Cable de alimentación", "Mouse", "Bolso o funda", "Disco externo"],
        controles=["¿Hay datos para resguardar?", "¿Tiene golpes o bisagras flojas?", "¿Le faltan teclas?"],
        categorias=["Notebooks", "PC de escritorio", "Monitores", "Impresoras"],
        plantillas=SEMILLA_PLANTILLAS,
        sla=(24, 48, 5), etiqueta="62x29",
        demo=dict(
            productos=[("Lenovo", "IdeaPad 3 15", "Notebooks", 12), ("HP", "LaserJet M111", "Impresoras", 12),
                       ("Dell", "OptiPlex 3080", "PC de escritorio", 12)],
            repuestos=[("Disco SSD 480 GB", "EJ-PC-SSD-480", "Mayorista Informática", 38000, 6, 2),
                       ("Teclado IdeaPad 3", "EJ-PC-TEC-IP3", "Mayorista Informática", 27000, 1, 1),
                       ("Pasta térmica 4 g", "EJ-PC-PASTA", "Mayorista Informática", 6500, 10, 4)],
            fallas=["Está muy lenta y aparecen ventanas de publicidad.", "No enciende, la luz del cargador prende.",
                    "La impresora arruga las hojas."],
        ),
    ),
    "consolas": dict(
        nombre="Consolas y videojuegos",
        descripcion="Consolas de mesa y portátiles, joysticks y accesorios.",
        icono="play",
        estados=[],
        accesorios=["Joystick", "Cable HDMI", "Cable de alimentación", "Juego o disco", "Base o dock"],
        controles=["¿Lee discos?", "¿Tiene los sellos de garantía intactos?", "¿Se apaga sola o recalienta?"],
        categorias=["Consolas", "Joysticks", "Consolas portátiles"],
        plantillas=[
            ("Lector", "Lectora óptica que no lee o hace ruido. Se limpia la lente y se calibra; si no responde, se reemplaza el lector."),
            ("Puerto HDMI", "Puerto HDMI dañado (sin imagen o intermitente). Se reemplaza el conector y se prueba en varias resoluciones."),
            ("Recalentamiento", "Se apaga por temperatura. Se limpia el disipador y los ventiladores y se cambia la pasta térmica."),
            ("Stick drift", "Joystick con desplazamiento sin tocarlo (drift). Se reemplaza el módulo analógico y se calibra."),
            ("Fuente", "Fuente de alimentación sin salida o con caídas. Se repara o reemplaza la fuente."),
        ],
        sla=(24, 48, 5), etiqueta="62x29",
        demo=dict(
            productos=[("Sony", "PlayStation 5", "Consolas", 12), ("Nintendo", "Switch OLED", "Consolas portátiles", 12),
                       ("Sony", "DualSense", "Joysticks", 6)],
            repuestos=[("Módulo analógico DualSense", "EJ-CON-STICK", "Gamer Parts", 7000, 12, 4),
                       ("Conector HDMI PS5", "EJ-CON-HDMI-PS5", "Gamer Parts", 15000, 2, 2)],
            fallas=["El joystick se mueve solo hacia la izquierda.", "No da imagen por HDMI.", "Se apaga sola a los 20 minutos de juego."],
        ),
    ),
    "electro": dict(
        nombre="Electrodomésticos",
        descripcion="Pequeños electrodomésticos, línea blanca y climatización.",
        icono="engranaje",
        estados=["En prueba"],
        accesorios=["Cable de alimentación", "Accesorios del equipo", "Control remoto", "Manual"],
        controles=["¿Funciona en parte?", "¿El cable está en buen estado?", "¿Pierde agua o gas?"],
        categorias=["Pequeños electrodomésticos", "Línea blanca", "Climatización"],
        plantillas=[
            ("Motor", "Motor sin giro o con ruido. Se revisan carbones y rulemanes; se reparan o se reemplaza el motor."),
            ("Resistencia", "Resistencia cortada (no calienta). Se reemplaza y se prueba la temperatura de trabajo."),
            ("Plaqueta", "Plaqueta de control con falla (no responde o muestra error). Se repara o reemplaza la plaqueta."),
            ("Termostato", "Termostato o sensor fuera de rango. Se reemplaza y se verifica el corte."),
            ("Pérdida", "Pérdida de agua o de gas. Se localiza la fuga, se reemplaza la junta o el componente y se prueba."),
        ],
        sla=(48, 72, 7), etiqueta="62x29",
        demo=dict(
            productos=[("Philips", "Airfryer HD9252", "Pequeños electrodomésticos", 12),
                       ("Drean", "Next 8.14", "Línea blanca", 12), ("BGH", "Split 3000 frigorías", "Climatización", 12)],
            repuestos=[("Resistencia airfryer 1400 W", "EJ-EL-RES-1400", "Repuestos del Hogar", 14000, 2, 1),
                       ("Bomba de desagote lavarropas", "EJ-EL-BOMBA", "Repuestos del Hogar", 22000, 3, 1)],
            fallas=["No calienta, el ventilador gira.", "No desagota y muestra un error en el display.", "Tira aire pero no enfría."],
        ),
    ),
    "audio_tv": dict(
        nombre="Audio y TV",
        descripcion="Televisores, equipos de audio y proyectores.",
        icono="ojo",
        estados=["En prueba"],
        accesorios=["Control remoto", "Base o soporte", "Cable de alimentación"],
        controles=["¿Da imagen?", "¿Da sonido?", "¿Tiene la pantalla marcada o rota?"],
        categorias=["Televisores", "Audio", "Proyectores"],
        plantillas=[
            ("Fuente", "Fuente de alimentación con falla (no enciende / se apaga). Se reparan los componentes dañados."),
            ("Retroiluminación", "Hay sonido pero no imagen (retroiluminación LED). Se reemplaza la tira LED completa."),
            ("Placa main", "Placa principal con falla (se reinicia / no reconoce entradas). Se repara o reemplaza la main."),
            ("Sin sonido", "Sin audio. Se revisa el amplificador y los parlantes; se repara la etapa de salida."),
        ],
        sla=(48, 72, 7), etiqueta="62x29",
        demo=dict(
            productos=[("Samsung", "Smart TV 50\" UN50", "Televisores", 12), ("JBL", "Partybox 110", "Audio", 12)],
            repuestos=[("Kit tiras LED 50\"", "EJ-TV-LED-50", "Electrónica Sur", 32000, 2, 1),
                       ("Fuente TV 50\" genérica", "EJ-TV-FUENTE", "Electrónica Sur", 28000, 1, 1)],
            fallas=["Se escucha el sonido pero la pantalla queda negra.", "Enciende y se apaga solo a los pocos segundos."],
        ),
    ),
    "herramientas": dict(
        nombre="Herramientas eléctricas",
        descripcion="Taladros, amoladoras y herramientas a batería.",
        icono="llave",
        estados=["En prueba"],
        accesorios=["Batería", "Cargador", "Maletín", "Mechas o discos"],
        controles=["¿Gira?", "¿Hace chispas o huele a quemado?"],
        categorias=["Taladros", "Amoladoras", "Herramientas a batería"],
        plantillas=[
            ("Carbones", "Carbones gastados (chispea o corta). Se reemplazan y se limpia el colector."),
            ("Rulemanes", "Rulemanes con juego o ruido. Se reemplazan y se lubrica."),
            ("Inducido", "Inducido quemado. Se reemplaza el inducido y se prueba en carga."),
            ("Gatillo", "Gatillo / interruptor con falla (no arranca o no regula). Se reemplaza."),
            ("Batería", "Batería que no carga o dura poco. Se prueban las celdas; se reemplaza el pack."),
        ],
        sla=(48, 48, 5), etiqueta="62x29",
        demo=dict(
            productos=[("Bosch", "GSB 13 RE", "Taladros", 12), ("DeWalt", "DCF887 20V", "Herramientas a batería", 36)],
            repuestos=[("Juego de carbones Bosch", "EJ-HE-CARB", "Herramientas Oeste", 4500, 10, 4),
                       ("Gatillo taladro universal", "EJ-HE-GAT", "Herramientas Oeste", 8000, 4, 2)],
            fallas=["Chispea mucho y huele a quemado.", "La batería carga pero se corta enseguida."],
        ),
    ),
    "general": dict(
        nombre="General",
        descripcion="Lo básico para cualquier taller; lo demás lo cargás vos.",
        icono="portapapeles",
        estados=[],
        accesorios=ACCESORIOS_BASE,
        controles=[],
        categorias=[],
        plantillas=[],
        sla=(24, 48, 5), etiqueta="62x29",
        demo=dict(
            productos=[("Genérico", "Equipo de ejemplo", "General", 12)],
            repuestos=[("Repuesto de ejemplo", "EJ-GEN-01", "Proveedor de ejemplo", 10000, 5, 2)],
            fallas=["No enciende.", "Hace un ruido raro al usarlo."],
        ),
    ),
}


def validar(ids) -> list:
    ids = [i for i in dict.fromkeys(ids or []) if i in RUBROS]
    return ids


def combinar(ids: list) -> dict:
    """Lo que proponen los rubros elegidos, sumado (sin repetir)."""
    def unir(campo):
        vistos = []
        for i in ids:
            for x in RUBROS[i][campo]:
                if x not in vistos:
                    vistos.append(x)
        return vistos
    plantillas, nombres = [], set()
    for i in ids:
        for nombre, texto in RUBROS[i]["plantillas"]:
            if nombre not in nombres:
                nombres.add(nombre)
                plantillas.append((nombre, texto))
    slas = [RUBROS[i]["sla"] for i in ids] or [RUBROS["general"]["sla"]]
    etiquetas = {RUBROS[i]["etiqueta"] for i in ids}
    return {
        "estados": unir("estados"),
        "accesorios": unir("accesorios"),
        "controles": unir("controles"),
        "categorias": unir("categorias"),
        "plantillas": plantillas,
        "sla": tuple(max(s[k] for s in slas) for k in range(3)),
        "etiqueta": etiquetas.pop() if len(etiquetas) == 1 else "62x29",
    }


def listado() -> list:
    """Para la pantalla: cada rubro con un resumen de lo que trae."""
    return [{"id": i, "nombre": r["nombre"], "descripcion": r["descripcion"], "icono": r["icono"],
             "estados": r["estados"], "accesorios": r["accesorios"], "controles": r["controles"],
             "categorias": r["categorias"], "plantillas": [n for n, _ in r["plantillas"]],
             "sla": {"horas_nuevo": r["sla"][0], "horas_diagnostico": r["sla"][1], "dias_reparacion": r["sla"][2]},
             "etiqueta": r["etiqueta"]}
            for i, r in RUBROS.items()]
