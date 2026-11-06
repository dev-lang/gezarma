from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import DATABASE_URL

SQLALCHEMY_DATABASE_URL = DATABASE_URL

# check_same_thread solo aplica (y solo es necesario) con SQLite
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_migrations(bind=None) -> list:
    """Lleva la base a la última versión con Alembic (se llama al arrancar la app).

    - Base nueva: se crea entera con las migraciones.
    - Base creada antes de usar Alembic (sin tabla alembic_version): se marca en
      la versión que corresponde a su esquema y desde ahí se aplican las demás.
    Al final se compara el esquema real con los modelos y se avisa si difieren.
    """
    import logging
    from alembic import command
    from alembic.autogenerate import compare_metadata
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from sqlalchemy import inspect

    from .config import ROOT_DIR

    log = logging.getLogger("uvicorn.error")
    eng = bind if bind is not None else engine   # `bind` permite migrar otra base (tests)
    cfg = Config(str(ROOT_DIR / "alembic.ini"))
    cfg.attributes["configure_logger"] = False   # no pisar la config de logs de uvicorn
    cfg.attributes["url"] = eng.url.render_as_string(hide_password=False)

    insp = inspect(eng)
    tables = set(insp.get_table_names())
    if "alembic_version" not in tables and "usuarios" in tables:
        cols = {c["name"] for c in insp.get_columns("usuarios")}
        # 0002 quitó usuarios.temp_password_plain: si ya no está, la base es de después
        base_rev = "0001" if "temp_password_plain" in cols else "0002"
        log.info("Base existente sin historial de migraciones: se marca en la versión %s", base_rev)
        command.stamp(cfg, base_rev)

    command.upgrade(cfg, "head")

    with eng.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    if diff:
        log.warning("El esquema de la base no coincide del todo con los modelos (%d diferencias). "
                    "Revisá con: alembic check. Detalle: %s", len(diff), diff[:5])
    return diff
