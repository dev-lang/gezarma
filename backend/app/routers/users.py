import secrets, string
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import List
from .. import database, models, schemas, auth, idiomas
from .auth import email_en_uso

router = APIRouter(prefix="/users", tags=["users"])

def _gen_temp_password(length=10) -> str:
    chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))

@router.get("/", response_model=List[schemas.User])
def list_users(
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([models.UserRole.ADMINISTRADOR]))
):
    return db.query(models.Usuario).all()

@router.get("/tecnicos")
def list_tecnicos(
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.get_current_user)
):
    tecnicos = db.query(models.Usuario).filter(
        models.Usuario.rol == models.UserRole.TECNICO,
        models.Usuario.activo == True
    ).all()
    if current_user.rol == models.UserRole.CLIENTE:
        # Al cliente, sin datos de contacto del personal
        return [{"id": u.id, "nombre": u.nombre, "rol": u.rol} for u in tecnicos]
    return [schemas.User.model_validate(u) for u in tecnicos]

@router.patch("/{user_id}", response_model=schemas.User)
def update_user(
    user_id: int,
    user_update: schemas.UserUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([models.UserRole.ADMINISTRADOR]))
):
    db_user = db.query(models.Usuario).filter(models.Usuario.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if db_user.username == "admin":
        if user_update.rol and user_update.rol != models.UserRole.ADMINISTRADOR:
            raise HTTPException(status_code=400, detail="No se puede cambiar el rol del administrador principal")
        if user_update.activo is False:
            raise HTTPException(status_code=400, detail="No se puede deshabilitar al administrador principal")
    valid_roles = {r.value for r in models.UserRole}
    if user_update.rol and user_update.rol not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Rol inválido: {sorted(valid_roles)}")
    data = user_update.model_dump(exclude_unset=True)
    if "email" in data:
        data["email"] = (data["email"] or "").strip().lower() or None
        if data["email"] and email_en_uso(db, data["email"], excepto_id=user_id):
            raise HTTPException(status_code=400, detail="El email ya está en uso por otro usuario")
    for k, v in data.items():
        setattr(db_user, k, v)
    db.commit()
    db.refresh(db_user)
    return db_user

@router.patch("/{user_id}/profile", response_model=schemas.User)
def update_user_profile(
    user_id: int,
    profile: schemas.UserUpdateProfile,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.get_current_user)
):
    """Admin can edit any user; a user can edit their own profile."""
    if current_user.id != user_id and current_user.rol != models.UserRole.ADMINISTRADOR:
        raise HTTPException(status_code=403, detail="Sin permisos para editar este usuario")
    db_user = db.query(models.Usuario).filter(models.Usuario.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    data = profile.model_dump(exclude_unset=True)
    # Sin email = NULL (los clientes de mostrador pueden no tener; "" chocaría entre ellos)
    if "email" in data:
        data["email"] = (data["email"] or "").strip().lower() or None
    if data.get("email") and email_en_uso(db, data["email"], excepto_id=user_id):
        raise HTTPException(status_code=400, detail="El email ya está en uso por otro usuario")
    # Validate telefono format
    if "telefono" in data and data["telefono"]:
        import re as _re
        clean = _re.sub(r"[\s\-\(\)]", "", data["telefono"])
        if not _re.match(r"^\+?\d{6,20}$", clean):
            raise HTTPException(status_code=400, detail="Formato de teléfono inválido. Use solo números, opcionalmente con + al inicio.")
        data["telefono"] = clean  # store normalized
    for k, v in data.items():
        setattr(db_user, k, v)
    db.commit()
    db.refresh(db_user)
    return db_user

@router.post("/{user_id}/reset-password")
def reset_password(
    user_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([models.UserRole.ADMINISTRADOR]))
):
    """Generate a temp password. User will be forced to change on next login."""
    db_user = db.query(models.Usuario).filter(models.Usuario.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if db_user.username == "admin" and current_user.id != db_user.id:
        raise HTTPException(status_code=400, detail="No se puede resetear la clave del administrador principal desde otro usuario")

    temp_pw = _gen_temp_password()
    db_user.password_hash       = auth.get_password_hash(temp_pw)
    db_user.must_change_password = True
    db_user.token_version = (db_user.token_version or 0) + 1   # cierra sus sesiones abiertas
    # The plain temp password is only returned in this response; it is never stored.
    db.commit()
    return {"temp_password": temp_pw, "username": db_user.username,
            "message": "Contraseña temporal generada. El usuario deberá cambiarla en el próximo login."}

@router.put("/me/idioma")
def cambiar_idioma(
    data: dict,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.get_current_user)
):
    """El idioma de la interfaz, los mails y los documentos de este usuario (null = el del taller)."""
    pedido = data.get("idioma")
    codigo = idiomas.normalizar(pedido)
    if pedido and not codigo:
        raise HTTPException(status_code=400, detail="Idioma no disponible")
    current_user.idioma = codigo
    db.commit()
    return {"idioma": codigo}

@router.post("/change-password")
def change_password(
    data: dict,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.get_current_user)
):
    """User changes their own password (forced or voluntary).
    Requires the current password, so a stolen token alone can't take over the account."""
    current_pw = data.get("current_password") or ""
    new_pw     = data.get("new_password") or ""
    if not auth.verify_password(current_pw, current_user.password_hash):
        raise HTTPException(status_code=400, detail="La contraseña actual es incorrecta")
    if len(new_pw) < 6:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 6 caracteres")
    if auth.password_too_long(new_pw):
        raise HTTPException(status_code=400, detail="La contraseña no puede superar los 72 bytes")
    if new_pw == current_pw:
        raise HTTPException(status_code=400, detail="La nueva contraseña debe ser distinta de la actual")
    current_user.password_hash       = auth.get_password_hash(new_pw)
    current_user.must_change_password = False
    # Las demás sesiones (y un token robado) dejan de valer; esta sigue con un token nuevo
    current_user.token_version = (current_user.token_version or 0) + 1
    db.commit()
    return {"message": "Contraseña actualizada correctamente", "access_token": auth.token_para(current_user),
            "token_type": "bearer"}

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.check_role([models.UserRole.ADMINISTRADOR]))
):
    user = db.query(models.Usuario).filter(models.Usuario.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if user.username == "admin":
        raise HTTPException(status_code=400, detail="No se puede eliminar al administrador principal")
    db.query(models.Ticket).filter(models.Ticket.tecnico_asignado == user_id).update(
        {models.Ticket.tecnico_asignado: None}
    )
    # Lo suyo que no es historia del taller se borra con el usuario
    db.query(models.Notificacion).filter(models.Notificacion.usuario_id == user_id).delete()
    db.query(models.TicketFavorito).filter(models.TicketFavorito.usuario_id == user_id).delete()
    db.delete(user)
    try:
        db.commit()
    except IntegrityError:
        # Tiene tickets, comentarios, historial…: borrarlo dejaría registros sin autor
        db.rollback()
        raise HTTPException(status_code=400, detail="El usuario tiene actividad registrada (tickets, comentarios, "
                                                    "historial…). Deshabilitalo en lugar de eliminarlo.")
    return None


# ── Panel de control: disposición de cada usuario (services/panel.py) ────────
from pydantic import BaseModel as _BM
from ..services import panel as panel_service


class _Panel(_BM):
    bloques: list


@router.get("/me/panel")
def mi_panel(db: Session = Depends(database.get_db), current_user: models.Usuario = Depends(auth.get_current_user)):
    return panel_service.del_usuario(db, current_user)


@router.put("/me/panel")
def guardar_mi_panel(data: _Panel, db: Session = Depends(database.get_db),
                     current_user: models.Usuario = Depends(auth.get_current_user)):
    res = panel_service.guardar(db, current_user, data.bloques)
    db.commit()
    return res


@router.delete("/me/panel")
def restablecer_mi_panel(db: Session = Depends(database.get_db), current_user: models.Usuario = Depends(auth.get_current_user)):
    res = panel_service.restablecer(db, current_user)
    db.commit()
    return res


@router.put("/me/panel/equipo")
def panel_del_equipo(data: _Panel, db: Session = Depends(database.get_db),
                     current_user: models.Usuario = Depends(auth.check_role([models.UserRole.ADMINISTRADOR]))):
    """Lo que ven los que no armaron su panel (técnicos nuevos, por ejemplo)."""
    bloques = panel_service.guardar_equipo(db, data.bloques)
    db.commit()
    from .. import ajustes
    ajustes.invalidar_cache()
    return {"equipo": bloques}


@router.delete("/me/panel/equipo")
def borrar_panel_del_equipo(db: Session = Depends(database.get_db),
                            current_user: models.Usuario = Depends(auth.check_role([models.UserRole.ADMINISTRADOR]))):
    panel_service.borrar_equipo(db)
    db.commit()
    from .. import ajustes
    ajustes.invalidar_cache()
    return {"equipo": None}
