"""Registro, roles, sesión, contraseñas."""
import sqlite3
import uuid

from backend.app import auth
from conftest import DB_PATH, login


def _register(client, headers=None, **extra):
    name = f"u_{uuid.uuid4().hex[:8]}"
    body = {"username": name, "nombre": name, "email": f"{name}@test.com", "password": "secret1", **extra}
    return client.post("/register", headers=headers or {}, json=body)


def test_registro_publico_siempre_crea_cliente(client):
    r = _register(client, rol="administrador")
    assert r.status_code == 200
    assert r.json()["rol"] == "cliente"


def test_admin_puede_crear_tecnico(client, admin):
    r = _register(client, headers=admin, rol="tecnico")
    assert r.status_code == 200
    assert r.json()["rol"] == "tecnico"


def test_admin_no_puede_crear_rol_inexistente(client, admin):
    assert _register(client, headers=admin, rol="superusuario").status_code == 400


def test_registro_rechaza_tipo_cliente_invalido(client):
    assert _register(client, tipo_cliente="marciano").status_code == 400


def test_token_de_usuario_deshabilitado_deja_de_servir(client, admin, make_user):
    headers, user = make_user()
    assert client.get("/tickets/", headers=headers).status_code == 200
    client.patch(f"/users/{user['id']}", headers=admin, json={"activo": False})
    assert client.get("/tickets/", headers=headers).status_code == 401


def test_cambio_de_clave_exige_la_actual(client, make_user):
    headers, user = make_user(password="secret1")
    url = "/users/change-password"
    assert client.post(url, headers=headers, json={"new_password": "nueva123"}).status_code == 400
    assert client.post(url, headers=headers,
                       json={"current_password": "mala", "new_password": "nueva123"}).status_code == 400
    assert client.post(url, headers=headers,
                       json={"current_password": "secret1", "new_password": "secret1"}).status_code == 400
    assert client.post(url, headers=headers,
                       json={"current_password": "secret1", "new_password": "nueva123"}).status_code == 200
    assert login(client, user["username"], "nueva123") is not None


def test_reset_de_clave_flujo_forzado_y_nada_guardado_en_texto_plano(client, admin, make_user):
    _, user = make_user()
    temp = client.post(f"/users/{user['id']}/reset-password", headers=admin).json()["temp_password"]
    cols = [r[1] for r in sqlite3.connect(DB_PATH).execute("pragma table_info(usuarios)")]
    assert "temp_password_plain" not in cols

    r = client.post("/login", data={"username": user["username"], "password": temp})
    assert r.json()["must_change_password"] is True
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = client.post("/users/change-password", headers=headers,
                    json={"current_password": temp, "new_password": "final123"})
    assert r.status_code == 200
    r = client.post("/login", data={"username": user["username"], "password": "final123"})
    assert r.json()["must_change_password"] is False


def test_clave_de_mas_de_72_bytes_se_rechaza(client):
    assert _register(client, password="ñ" * 40).status_code == 422   # 80 bytes


def test_hashes_viejos_de_passlib_siguen_validando():
    # Hash generado por passlib (bcrypt) para "secret1"
    old = "$2b$12$IeldtF7RYxdxhFhcpLRVfuU8tuhJpWzvd7Wi.5dMYIOHarhzgSTrm"
    assert auth.verify_password("secret1", old)
    assert not auth.verify_password("otra", old)
    assert not auth.verify_password("secret1", "no-es-un-hash")


def test_admin_inicial_usa_ADMIN_PASSWORD(client):
    assert login(client, "admin", "admin123") is None   # la clave por defecto no aplica
