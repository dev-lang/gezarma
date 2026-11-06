"""Ajustes del sistema (panel de administración)."""
import sqlite3

from conftest import DB_PATH


def _ajuste(client, admin, clave):
    return next(a for a in client.get("/config/ajustes", headers=admin).json() if a["clave"] == clave)


def test_solo_admin(client, make_user):
    tec, _ = make_user("tecnico")
    assert client.get("/config/ajustes", headers=tec).status_code == 403
    assert client.put("/config/ajustes", headers=tec, json={"pdf_modo": "navegador"}).status_code == 403


def test_valores_por_defecto_y_guardado(client, admin):
    assert _ajuste(client, admin, "pdf_modo")["valor"] == "servidor"
    r = client.put("/config/ajustes", headers=admin, json={"pdf_modo": "navegador", "sla_aviso_horas": "12"})
    assert r.status_code == 200
    assert _ajuste(client, admin, "pdf_modo")["valor"] == "navegador"
    assert _ajuste(client, admin, "sla_aviso_horas")["valor"] == 12
    client.put("/config/ajustes", headers=admin, json={"pdf_modo": "servidor", "sla_aviso_horas": 24})


def test_valores_invalidos_no_guardan_nada(client, admin):
    r = client.put("/config/ajustes", headers=admin,
                   json={"pdf_modo": "navegador", "smtp_port": "abc", "public_url": "rma.com", "inventado": 1})
    assert r.status_code == 400
    errores = r.json()["detail"]["errores"]
    assert set(errores) == {"smtp_port", "public_url", "inventado"}
    assert _ajuste(client, admin, "pdf_modo")["valor"] == "servidor"   # tampoco se guardó lo válido


def test_password_smtp_se_guarda_cifrada_y_no_se_devuelve(client, admin):
    client.put("/config/ajustes", headers=admin, json={"smtp_password": "MiClaveSMTP!"})
    a = _ajuste(client, admin, "smtp_password")
    assert a["cargado"] is True and "MiClaveSMTP" not in str(a)
    crudo = sqlite3.connect(DB_PATH).execute(
        "select valor from config_sistema where clave='smtp_password'").fetchone()[0]
    assert "MiClaveSMTP" not in crudo
    # Reenviar el placeholder no la pisa
    client.put("/config/ajustes", headers=admin, json={"smtp_password": a["valor"]})
    from backend.app import ajustes, database
    db = database.SessionLocal()
    try:
        assert ajustes.get(db, "smtp_password") == "MiClaveSMTP!"
    finally:
        db.close()


def test_ajustes_publicos_para_cualquier_usuario(client, make_user):
    cli, _ = make_user()
    r = client.get("/config/ajustes/publicos", headers=cli).json()
    assert r["pdf_modo"] in ("servidor", "navegador") and "smtp_password" not in r
