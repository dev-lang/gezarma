"""
importacion.py — Importar productos y repuestos desde .xlsx o .csv (solo administrador).

  GET  /importar/{tipo}/plantilla?formato=xlsx|csv&con_datos=1   plantilla (o los datos actuales)
  POST /importar/{tipo}/vista-previa   (archivo, actualizar)     qué pasaría con cada fila
  POST /importar/{tipo}                (archivo, actualizar)     importa las filas válidas

tipo: productos | repuestos. Ver services/importacion.py.
"""
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import auth, database, models
from ..services import importacion

router = APIRouter(prefix="/importar", tags=["importar"])
ADMIN = auth.check_role([models.UserRole.ADMINISTRADOR])
VISTA_MAX_FILAS = 500


def _analizar(db, tipo, archivo: UploadFile, actualizar: bool):
    contenido = archivo.file.read(importacion.MAX_BYTES + 1)
    encabezados, filas = importacion.leer(contenido, archivo.filename)
    return importacion.analizar(db, tipo, encabezados, filas, actualizar)


@router.get("/{tipo}/plantilla")
def plantilla(tipo: str, formato: str = Query("xlsx", pattern="^(xlsx|csv)$"), con_datos: bool = False,
              db: Session = Depends(database.get_db), _: models.Usuario = Depends(ADMIN)):
    contenido, mime = importacion.plantilla(db, tipo, formato, con_datos)
    nombre = f"{tipo}{'' if con_datos else '-plantilla'}.{formato}"
    return Response(contenido, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.post("/{tipo}/vista-previa")
def vista_previa(tipo: str, archivo: UploadFile = File(...), actualizar: bool = Form(True),
                 db: Session = Depends(database.get_db), _: models.Usuario = Depends(ADMIN)):
    a = _analizar(db, tipo, archivo, actualizar)
    # Para la pantalla alcanza con las primeras filas (los errores van todos)
    errores = [f for f in a["filas"] if f["accion"] == "error"]
    resto = [f for f in a["filas"] if f["accion"] != "error"][:max(0, VISTA_MAX_FILAS - len(errores))]
    a["filas"] = sorted(errores + resto, key=lambda f: f["fila"])
    a["recortada"] = a["total"] > len(a["filas"])
    return a


@router.post("/{tipo}")
def importar(tipo: str, archivo: UploadFile = File(...), actualizar: bool = Form(True),
             db: Session = Depends(database.get_db), u: models.Usuario = Depends(ADMIN)):
    a = _analizar(db, tipo, archivo, actualizar)
    return importacion.aplicar(db, a, u, archivo.filename or "archivo")
