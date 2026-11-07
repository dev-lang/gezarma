from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta, datetime, timezone
from typing import Optional
from .. import database, models, schemas, idiomas, auth as auth_module
from ..timeutils import utcnow

router = APIRouter(tags=["auth"])

# ── Helpers ────────────────────────────────────────────────────────────────────

def email_en_uso(db: Session, email: str, excepto_id: int = None) -> bool:
    """Sin distinguir mayúsculas (USER@x.com y user@x.com son el mismo email)."""
    from sqlalchemy import func
    if not email:
        return False
    q = db.query(models.Usuario).filter(func.lower(models.Usuario.email) == email.strip().lower())
    if excepto_id is not None:
        q = q.filter(models.Usuario.id != excepto_id)
    return q.first() is not None


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
        elapsed = (utcnow() - last_fail_time).total_seconds()
        if elapsed < lockout_secs:
            remaining = int(lockout_secs - elapsed)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Demasiados intentos fallidos. Intentá de nuevo en {remaining} segundos.",
                headers={"Retry-After": str(remaining)},
            )

    return len(recent_fails)

def _check_cuenta(db: Session, username: str):
    """Límite por cuenta (además del de IP): frena el probar claves desde muchas IPs.
    Umbral más alto que el de IP para que bloquear a otro (p. ej. al admin) no sea fácil."""
    max_attempts = int(_get_config(db, "login_max_intentos", "5")) * 3
    window_secs  = int(_get_config(db, "login_ventana_segundos", "300"))
    since = utcnow() - timedelta(seconds=window_secs)
    fallos = (db.query(models.LoginAttempt)
              .filter(models.LoginAttempt.username == username, models.LoginAttempt.exitoso == False,  # noqa: E712
                      models.LoginAttempt.fecha >= since).count())
    if fallos >= max_attempts:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="Demasiados intentos fallidos para esta cuenta. Probá de nuevo en unos minutos.",
                            headers={"Retry-After": str(window_secs)})


# Altas públicas por IP (en memoria, por proceso): frena la creación masiva de cuentas
_REGISTROS_MAX, _REGISTROS_VENTANA = 10, 3600
_registros = {}


def _check_registro(ip: str):
    import time
    ahora = time.monotonic()
    recientes = [t for t in _registros.get(ip, []) if ahora - t < _REGISTROS_VENTANA]
    if len(recientes) >= _REGISTROS_MAX:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="Demasiadas cuentas creadas desde esta conexión. Probá más tarde.")
    recientes.append(ahora)
    _registros[ip] = recientes


def reiniciar_limites() -> None:   # para tests
    _registros.clear()


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
    _check_cuenta(db, form_data.username)

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

    token = auth_module.token_para(user)
    return {
        "access_token": token,
        "token_type":   "bearer",
        "role":         user.rol,
        "username":     user.username,
        "nombre":       user.nombre,
        "user_id":      user.id,
        "must_change_password": user.must_change_password,
        "idioma":       user.idioma,
    }

@router.post("/register", response_model=schemas.User)
def register(
    user_data: schemas.UserCreate,
    request: Request,
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

    es_admin = current_user is not None and current_user.rol == models.UserRole.ADMINISTRADOR
    if not es_admin:
        from .. import ajustes as ajustes_mod
        if not ajustes_mod.get(db, "registro_publico"):
            raise HTTPException(status_code=403, detail="El registro de clientes está desactivado: pedile al taller que te cree la cuenta.")
        _check_registro(request.client.host if request.client else "desconocida")
    user_data.email = (user_data.email or "").strip().lower()
    if db.query(models.Usuario).filter_by(username=user_data.username).first():
        raise HTTPException(status_code=400, detail="El nombre de usuario ya está en uso")
    if email_en_uso(db, user_data.email):
        raise HTTPException(status_code=400, detail="El email ya está registrado")
    new_user = models.Usuario(
        username=user_data.username,
        password_hash=auth_module.get_password_hash(user_data.password),
        nombre=user_data.nombre,
        email=user_data.email,
        rol=rol,
        tipo_cliente=user_data.tipo_cliente,
        idioma=idiomas.normalizar(user_data.idioma),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user
