# Imagen de GEZARMA (backend FastAPI + frontend estático en un solo contenedor)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencias primero: esta capa se reutiliza mientras no cambie requirements.txt
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

COPY alembic.ini ./
COPY backend ./backend
COPY frontend ./frontend

# Datos persistentes (base SQLite y adjuntos) en /data → montar un volumen ahí
ENV DATABASE_URL=sqlite:////data/rma_system.db \
    UPLOAD_DIR=/data/uploads

# Usuario sin privilegios
RUN useradd --system --uid 10001 --no-create-home gezarma \
    && mkdir -p /data \
    && chown gezarma /data
USER gezarma
VOLUME /data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=4)"

# --proxy-headers: detrás de un proxy inverso (Nginx, Caddy, Traefik) toma la IP
# real del cliente, que usa el bloqueo por intentos de login. Solo se confía en
# los proxies listados en FORWARDED_ALLOW_IPS (por defecto 127.0.0.1).
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
