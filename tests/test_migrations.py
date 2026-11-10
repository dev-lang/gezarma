"""Migraciones: base nueva, base creada antes de Alembic, y coherencia con los modelos."""
import sqlite3

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from backend.app.config import ROOT_DIR
from backend.app.database import run_migrations


def _cfg(url):
    cfg = Config(str(ROOT_DIR / "alembic.ini"))
    cfg.attributes["configure_logger"] = False
    cfg.attributes["url"] = url
    return cfg


def _version(path):
    return sqlite3.connect(path).execute("select version_num from alembic_version").fetchone()[0]


def test_base_nueva_queda_igual_a_los_modelos(tmp_path):
    db = tmp_path / "nueva.db"
    eng = create_engine(f"sqlite:///{db}")
    assert run_migrations(eng) == []          # sin diferencias con models.py
    assert _version(db) == "0017"


def test_base_previa_a_alembic_se_marca_y_migra_sin_perder_datos(tmp_path):
    db = tmp_path / "vieja.db"
    url = f"sqlite:///{db}"
    # Simula una base creada por el código original: esquema 0001 sin tabla alembic_version
    command.upgrade(_cfg(url), "0001")
    con = sqlite3.connect(db)
    con.execute("drop table alembic_version")
    con.execute("insert into usuarios (username, password_hash, nombre, email, rol, activo, "
                "temp_password_plain) values ('viejo', 'h', 'V', 'v@x', 'cliente', 1, 'Clave123')")
    con.commit(); con.close()

    eng = create_engine(url)
    assert run_migrations(eng) == []
    assert _version(db) == "0017"
    cols = {c["name"] for c in inspect(eng).get_columns("usuarios")}
    assert "temp_password_plain" not in cols   # la clave en texto plano desaparece
    assert sqlite3.connect(db).execute("select username from usuarios").fetchall() == [("viejo",)]


def test_base_intermedia_sin_la_columna_se_marca_en_0002(tmp_path):
    db = tmp_path / "intermedia.db"
    url = f"sqlite:///{db}"
    # Simula una base creada antes de Alembic pero sin temp_password_plain: esquema 0002
    command.upgrade(_cfg(url), "0002")
    sqlite3.connect(db).execute("drop table alembic_version").connection.commit()
    assert run_migrations(create_engine(url)) == []
    assert _version(db) == "0017"


def test_downgrade_y_upgrade(tmp_path):
    url = f"sqlite:///{tmp_path / 'ida_vuelta.db'}"
    cfg = _cfg(url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    assert run_migrations(create_engine(url)) == []
