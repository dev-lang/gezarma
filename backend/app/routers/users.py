import secrets, string
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from .. import database, models, schemas, auth

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

@router.get("/tecnicos", response_model=List[schemas.User])
def list_tecnicos(
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(auth.get_current_user)
):
    return db.query(models.Usuario).filter(
        models.Usuario.rol == models.UserRole.TECNICO,
        models.Usuario.activo == True
    ).all()

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
        data["email"] = (data["email"] or "").strip() or None
    # Check email uniqueness if changing
    if data.get("email"):
        exists = db.query(models.Usuario).filter(
            models.Usuario.email == data["email"],
            models.Usuario.id != user_id
        ).first()
        if exists:
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
    # The plain temp password is only returned in this response; it is never stored.
    db.commit()
    return {"temp_password": temp_pw, "username": db_user.username,
            "message": f"Contraseña temporal generada. El usuario deberá cambiarla en el próximo login."}

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
    db.commit()
    return {"message": "Contraseña actualizada correctamente"}

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
    db.delete(user)
    db.commit()
    return None
