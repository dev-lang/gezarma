# GEZARMA

Sistema de gestión de **RMA** (devoluciones, garantías y reparaciones) para un servicio técnico: los clientes cargan sus reclamos y siguen el estado del equipo, y el taller diagnostica, repara, presupuesta y despacha, con historial completo de cada caso.

Backend en **FastAPI** + SQLAlchemy (SQLite por defecto) y frontend en HTML/JS sin build, servido por la misma app.

![Panel de control](docs/capturas/02-dashboard.png)

## Funcionalidades

- **Tickets RMA** con número correlativo, estados configurables, prioridad, SLA, técnico asignado, etiquetas, tickets clonados/relacionados y datos de envío.
- **Diagnóstico** con plantillas, **repuestos usados** con descuento de stock y **adjuntos** (PDF, TXT, JPG, PNG; hasta 10 MB por ticket).
- **Comentarios** con el cliente y **notas internas** solo para el taller.
- **Presupuestos** con versiones: el taller ve costo, precio y ganancia; el cliente ve el precio y lo aprueba o rechaza.
- **Stock de repuestos** con historial de movimientos.
- **Notificaciones** in-app, **favoritos**, búsqueda global y **historial/auditoría** de cada cambio.
- **Panel de administración**: usuarios, productos, repuestos, etiquetas, estados, plantillas, finanzas, seguridad del login y **exportación** a CSV/Excel.
- Bloqueo por intentos fallidos de login y cambio de contraseña obligatorio tras un reset.

## Capturas

| Detalle del ticket (taller) | Detalle del ticket (cliente) |
|---|---|
| ![Detalle visto por el taller](docs/capturas/03-detalle-taller.png) | ![Detalle visto por el cliente](docs/capturas/04-detalle-cliente.png) |
| Estado, técnico, diagnóstico, repuestos, nota interna y presupuesto con costo y ganancia. | El mismo ticket para el cliente: sin nota interna y el presupuesto solo con el precio. |

| Administración | Login |
|---|---|
| ![Panel de administración](docs/capturas/05-admin.png) | ![Login](docs/capturas/01-login.png) |

*(Datos de demostración ficticios.)*

## Roles y permisos

| Acción | Cliente | Técnico | Administrador |
|---|:---:|:---:|:---:|
| Registrarse por su cuenta | ✅ | — | — |
| Crear tickets | ✅ | ✅ | ✅ |
| Ver tickets | solo los suyos | todos | todos |
| Comentar | ✅ | ✅ | ✅ |
| Notas internas | — | ✅ | ✅ |
| Subir / descargar adjuntos | en sus tickets | ✅ | ✅ |
| Borrar adjuntos | — | ✅ | ✅ |
| Cambiar estado, asignar técnico, diagnóstico, etiquetas, repuestos, envío | — | ✅ | ✅ |
| Crear, editar y enviar presupuestos | — | ✅ | ✅ |
| Ver costo interno y ganancia | — | ✅ | ✅ |
| Aprobar / rechazar presupuesto | los suyos | ✅ | ✅ |
| Dashboard con estadísticas, favoritos | — | ✅ | ✅ |
| Exportar tickets, productos y repuestos | — | ✅ | ✅ |
| Administrar usuarios, productos, repuestos, stock, etiquetas, estados y plantillas | — | — | ✅ |
| Finanzas, seguridad del login, exportar usuarios | — | — | ✅ |

El registro público siempre crea usuarios **cliente**. Los técnicos y administradores los crea un administrador desde *Administración → Usuarios → Nuevo usuario*.

## Instalación

### Con Docker (recomendado)

```bash
git clone https://github.com/dev-lang/gezarma.git
cd gezarma
cp .env.example .env          # completá al menos SECRET_KEY y ADMIN_PASSWORD
docker compose up -d --build
```

La app queda en <http://localhost:8000> (el puerto se cambia con `PORT` en `.env`). La base de datos y los adjuntos se guardan en el volumen `gezarma-data`, así que sobreviven a reconstruir o borrar el contenedor.

Para actualizar: `git pull && docker compose up -d --build`. Las migraciones de la base corren solas al arrancar.

### Local (sin Docker)

Requiere Python 3.11 o superior.

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
cp .env.example .env           # opcional
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

Se ejecuta desde la raíz del repo. Por defecto la base (`rma_system.db`) y los adjuntos (`uploads/`) quedan en esa misma carpeta.

> El frontend carga Tailwind CSS y Chart.js desde CDN, así que el navegador necesita acceso a internet.

### Primer ingreso

Usuario **`admin`** con la contraseña de `ADMIN_PASSWORD`. Si no la definiste, la contraseña es `admin123` y el sistema pide cambiarla en el primer login. Ese usuario solo se crea si la base está vacía; cambiar `ADMIN_PASSWORD` después no modifica la clave de un admin existente.

## Configuración

Todo se configura con variables de entorno o con un archivo `.env` en la raíz (ver [`.env.example`](.env.example)). Nada es obligatorio: sin configuración, la app usa los valores por defecto.

| Variable | Por defecto | Para qué sirve |
|---|---|---|
| `SECRET_KEY` | clave de ejemplo del repo | Firma las sesiones (JWT). **Definila siempre en producción**. Generá una con `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Cambiarla cierra todas las sesiones abiertas. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` (1 día) | Duración de la sesión. |
| `CORS_ORIGINS` | `*` | Orígenes externos que pueden llamar a la API, separados por coma. El frontend se sirve desde la misma app, así que normalmente conviene dejarla **vacía** (CORS desactivado). |
| `ADMIN_PASSWORD` | `admin123` | Contraseña del `admin` inicial (solo al crear la base). |
| `ADMIN_EMAIL` | `admin@gezatek.com.ar` | Email del `admin` inicial. |
| `DATABASE_URL` | `sqlite:///./rma_system.db` | Base de datos (cualquier URL de SQLAlchemy). En Docker está fija a `/data`. |
| `UPLOAD_DIR` | `uploads` | Carpeta de adjuntos. En Docker está fija a `/data/uploads`. |
| `PORT` | `8000` | Puerto publicado por Docker Compose. |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | IP(s) del proxy inverso en el que se confía para conocer la IP real del cliente (ver *Deploy*). |

Al arrancar, la app avisa en el log si la `SECRET_KEY` o `CORS_ORIGINS` quedaron con valores inseguros.

## Deploy

Para exponerla a internet, poné la app detrás de un **proxy inverso con HTTPS** (Caddy, Nginx, Traefik, Nginx Proxy Manager…). Ejemplo con Caddy, que obtiene el certificado solo:

```caddy
rma.tudominio.com {
    reverse_proxy 127.0.0.1:8000
}
```

Checklist:

- `SECRET_KEY` larga y aleatoria, y `ADMIN_PASSWORD` propia (o cambiar la del admin en el primer login).
- `CORS_ORIGINS` vacía.
- `FORWARDED_ALLOW_IPS` con la IP desde la que el proxy llega a la app. Así el bloqueo por intentos fallidos de login usa la IP real de cada cliente y no la del proxy (que bloquearía a todos a la vez). Con Docker y el proxy en el mismo host, suele ser el gateway de la red de Docker: `docker network inspect gezarma_default` → `Gateway`.
- No publicar el puerto 8000 directo a internet si hay proxy: en `docker-compose.yml` se puede usar `"127.0.0.1:8000:8000"`.

### Backups

Hay que respaldar la base y los adjuntos. Con Docker (frená la app para que la copia de SQLite sea consistente):

```bash
docker compose stop
docker run --rm -v gezarma_gezarma-data:/data -v "$PWD":/backup alpine \
  tar czf /backup/gezarma-$(date +%F).tgz -C /data .
docker compose start
```

Sin Docker, alcanza con copiar `rma_system.db` y la carpeta `uploads/` con la app detenida.

Si en lugar del volumen usás una carpeta del host (por ejemplo en un NAS: `./data:/data`), esa carpeta tiene que pertenecer al usuario del contenedor: `sudo chown -R 10001 ./data`.

## Desarrollo

### Migraciones de la base

El esquema se maneja con [Alembic](https://alembic.sqlalchemy.org/). La app aplica las migraciones pendientes al arrancar; una base creada antes de usar Alembic se reconoce y se actualiza sola, sin perder datos.

Después de cambiar `backend/app/models.py`:

```bash
alembic revision --autogenerate -m "descripcion del cambio"   # genera la migración en backend/migrations/versions/
alembic upgrade head                                          # la aplica (o reiniciá la app)
alembic check                                                 # confirma que base y modelos coinciden
```

Conviene revisar la migración generada antes de commitearla.

### Tests

```bash
pip install -r requirements-dev.txt
pytest
```

Usan una base y una carpeta de adjuntos temporales: no tocan los datos locales. Cubren permisos por rol, adjuntos, presupuestos, exportación, contraseñas y migraciones.

### Estructura

```
backend/
  app/
    main.py            arranque, rutas estáticas, datos iniciales
    config.py          configuración (variables de entorno / .env)
    database.py        conexión y migraciones al arrancar
    models.py          modelos SQLAlchemy
    schemas.py         esquemas Pydantic (entrada/salida de la API)
    auth.py            contraseñas (bcrypt), JWT y permisos por rol
    routers/           endpoints por área (tickets, presupuestos, stock, …)
    services/          lógica de tickets (número RMA, SLA, notificaciones)
  migrations/          migraciones de Alembic
frontend/
  index.html, partials/, js/
tests/                 tests de pytest
docs/capturas/         capturas de este README
```

La documentación interactiva de la API está en `/docs` (Swagger) con la app corriendo.
