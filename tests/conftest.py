"""Configuración común de los tests.

Cada corrida usa una base SQLite y una carpeta de adjuntos temporales, así que
no toca la base local (rma_system.db) ni uploads/. Las variables de entorno se
fijan ANTES de importar la app, porque la config se lee al importarla.
"""
import os
import tempfile
import uuid

_TMP = tempfile.mkdtemp(prefix="gezarma-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
os.environ["UPLOAD_DIR"] = os.path.join(_TMP, "uploads")
os.environ["SECRET_KEY"] = "clave-de-test"
os.environ["ADMIN_PASSWORD"] = "admin-test-123"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.app.main import app  # noqa: E402

ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]
DB_PATH = os.path.join(_TMP, "test.db")


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def login(client, username, password):
    """Headers de autorización, o None si el login falla."""
    r = client.post("/login", data={"username": username, "password": password})
    if r.status_code != 200:
        return None
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def admin(client):
    return login(client, "admin", ADMIN_PASSWORD)


@pytest.fixture
def make_user(client, admin):
    """Crea un usuario con nombre único y devuelve (headers, datos)."""
    def _make(rol="cliente", password="secret1"):
        name = f"{rol[:3]}_{uuid.uuid4().hex[:8]}"
        body = {"username": name, "nombre": name, "email": f"{name}@test.com",
                "password": password, "rol": rol}
        r = client.post("/register", headers=admin, json=body)
        assert r.status_code == 200, r.text
        return login(client, name, password), r.json()
    return _make


@pytest.fixture
def make_ticket(client):
    def _make(headers, serie="SN1"):
        r = client.post("/tickets/", headers=headers, json={
            "numero_serie": serie, "fecha_compra": "2026-01-01T00:00:00",
            "descripcion": "no enciende", "producto": "Notebook X"})
        assert r.status_code == 200, r.text
        return r.json()
    return _make


@pytest.fixture
def upload(client):
    def _upload(headers, ticket_id, name="nota.txt", content=b"hola"):
        return client.post(f"/tickets/{ticket_id}/attachments", headers=headers,
                           files={"file": (name, content, "text/plain")})
    return _upload
