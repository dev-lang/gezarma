from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta, datetime, timezone
from typing import Optional
from .. import database, models, schemas, auth as auth_module

router = APIRouter(tags=["auth"])

# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_config(db: Session, clave: str, default: str) -> str:
    row = db.query(models.ConfigSistema).filter_by(clave=clave).first()
    return row.valor if row else default

def _check_rate_limit(db: Session, ip: str):
    """Raise 429 if the IP is blocked. Returns (attempts, window_seconds)."""
    max_attempts = int(_get_config(db, "login_max_intentos", "5"))
    window_secs  = int(_get_config(db, "login_ventana_segundos", "300"))  # 5 min default
    lockout_secs = int(_get_config(db, "login_bloqueo_segundos", "600"))  # 10 min default

    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=window_secs)
    recent_fails = (
        db.query(models.LoginAttempt)
        .filter(
            models.LoginAttempt.ip_address == ip,
            models.LoginAttempt.exitoso == False,
            models.LoginAttempt.fecha >= since,
        )
        .order_by(models.LoginAttempt.fecha.desc())
        .all()
    )

    if len(recent_fails) >= max_attempts:
        # Check if still in lockout window from the latest attempt
        last_fail_time = recent_fails[0].fecha
        elapsed = (datetime.utcnow() - last_fail_time).total_seconds()
        if elapsed < lockout_secs:
            remaining = int(lockout_secs - elapsed)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Demasiados intentos fallidos. Intentá de nuevo en {remaining} segundos.",
                headers={"Retry-After": str(remaining)},
            )

    return len(recent_fails)

def _record_attempt(db: Session, ip: str, username: str, success: bool):
    attempt = models.LoginAttempt(ip_address=ip, username=username, exitoso=success)
    db.add(attempt)
    db.commit()


# ── Login ──────────────────────────────────────────────────────────────────────

@router.post("/login")
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(database.get_db)
):
    ip = request.client.host if request.client else "unknown"

    # Rate-limit check before touching credentials
    _check_rate_limit(db, ip)

    user = db.query(models.Usuario).filter(models.Usuario.username == form_data.username).first()
    if not user or not auth_module.verify_password(form_data.password, user.password_hash):
        _record_attempt(db, ip, form_data.username, success=False)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
        )
    if not user.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta deshabilitada. Contactá al administrador.",
        )

    # Success — record and clear fail streak is implicit (window-based)
    _record_attempt(db, ip, form_data.username, success=True)

    token = auth_module.create_access_token(
        data={"sub": user.username, "role": user.rol},
        expires_delta=timedelta(minutes=auth_module.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {
        "access_token": token,
        "token_type":   "bearer",
        "role":         user.rol,
        "username":     user.username,
        "nombre":       user.nombre,
        "user_id":      user.id,
        "must_change_password": user.must_change_password,
    }

@router.post("/register", response_model=schemas.User)
def register(
    user_data: schemas.UserCreate,
    db: Session = Depends(database.get_db),
    current_user: Optional[models.Usuario] = Depends(auth_module.get_current_user_optional),
):
    """Public self-registration always creates a 'cliente'.
    Only a logged-in administrator (admin panel → Nuevo usuario) may set another role."""
    if current_user is not None and current_user.rol == models.UserRole.ADMINISTRADOR:
        valid_roles = {r.value for r in models.UserRole}
        if user_data.rol not in valid_roles:
            raise HTTPException(status_code=400, detail=f"Rol inválido: {sorted(valid_roles)}")
        rol = user_data.rol
    else:
        rol = models.UserRole.CLIENTE.value
    valid_tipos = {t.value for t in models.UserType}
    if user_data.tipo_cliente not in valid_tipos:
        raise HTTPException(status_code=400, detail=f"Tipo de cliente inválido: {sorted(valid_tipos)}")

    if db.query(models.Usuario).filter_by(username=user_data.username).first():
        raise HTTPException(status_code=400, detail="El nombre de usuario ya está en uso")
    if db.query(models.Usuario).filter_by(email=user_data.email).first():
        raise HTTPException(status_code=400, detail="El email ya está registrado")
    new_user = models.Usuario(
        username=user_data.username,
        password_hash=auth_module.get_password_hash(user_data.password),
        nombre=user_data.nombre,
        email=user_data.email,
        rol=rol,
        tipo_cliente=user_data.tipo_cliente,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user
