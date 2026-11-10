"""
setup.py — Configuración inicial del taller (ver services/setup.py). Solo administradores.

  GET    /setup             qué pasos se hicieron, si está terminado, datos de ejemplo
  PUT    /setup             {paso} lo marca hecho · {terminado} · {pospuesto}
  GET    /setup/rubros      los tipos de taller con lo que trae cada uno
  POST   /setup/rubros      {rubros: [...], quitar_ejemplos} aplica lo típico de esos rubros
  POST   /setup/demo        carga datos de ejemplo (solo sin tickets reales)
  DELETE /setup/demo        borra los datos de ejemplo
"""
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import ajustes, auth, database, models
from ..services import rubros, setup as S

router = APIRouter(prefix="/setup", tags=["setup"])
ADMIN = auth.check_role([models.UserRole.ADMINISTRADOR])


class Marca(BaseModel):
    paso: Optional[str] = None
    terminado: Optional[bool] = None
    pospuesto: Optional[bool] = None


class Rubros(BaseModel):
    rubros: List[str]
    quitar_ejemplos: bool = False


@router.get("")
def estado(db: Session = Depends(database.get_db), u: models.Usuario = Depends(ADMIN)):
    return S.estado(db, u)


@router.put("")
def marcar(data: Marca, db: Session = Depends(database.get_db), u: models.Usuario = Depends(ADMIN)):
    S.marcar(db, data.paso, data.terminado, data.pospuesto)
    db.commit()
    ajustes.invalidar_cache()
    return S.estado(db, u)


@router.get("/rubros")
def listar_rubros(u: models.Usuario = Depends(ADMIN)):
    return rubros.listado()


@router.post("/rubros")
def aplicar(data: Rubros, db: Session = Depends(database.get_db), u: models.Usuario = Depends(ADMIN)):
    res = S.aplicar_rubros(db, data.rubros, data.quitar_ejemplos)
    S.marcar(db, paso="rubro")
    db.commit()
    ajustes.invalidar_cache()
    return res


@router.post("/demo", status_code=201)
def crear_demo(db: Session = Depends(database.get_db), u: models.Usuario = Depends(ADMIN)):
    res = S.crear_demo(db, u)
    db.commit()
    return res


@router.delete("/demo")
def borrar_demo(db: Session = Depends(database.get_db), u: models.Usuario = Depends(ADMIN)):
    res = S.borrar_demo(db)
    db.commit()
    return res
