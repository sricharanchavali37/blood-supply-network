# app/auth/routes.py

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import check_rate_limit

from app.auth.models import User, AuditLog, Role
from app.auth.schemas import (
    UserRegister,
    UserLogin,
    Token,
    TokenRefresh,
    UserResponse
)
from app.auth.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_token
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ==========================
# REGISTER
# ==========================

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserRegister,
    request: Request,
    db: Session = Depends(get_db)
):
    await check_rate_limit(request, identifier=user_data.email)

    # Check if email already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Validate role exists
    role = db.query(Role).filter(Role.id == user_data.role_id).first()
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role_id"
        )

    # Prevent self-assignment of privileged roles (by name, not ID)
    if role.name == "Super Admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot self-assign admin role"
        )

    try:
        hashed_password = hash_password(user_data.password)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password hashing failed",
        )

    new_user = User(
        email=user_data.email,
        password_hash=hashed_password,
        full_name=user_data.full_name,
        role_id=user_data.role_id,
        is_active=True,
    )
    db.add(new_user)
    db.flush()
    ip_address = getattr(request.client, "host", None) if request.client else None
    audit_log = AuditLog(
        user_id=new_user.id,
        action="USER_REGISTERED",
        entity_type="user",
        entity_id=new_user.id,
        details={"email": new_user.email},
        ip_address=ip_address,
    )
    db.add(audit_log)
    try:
        db.commit()
        db.refresh(new_user)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed",
        )
    return new_user


# ==========================
# LOGIN
# ==========================

@router.post("/login", response_model=Token)
async def login(
    credentials: UserLogin,
    request: Request,
    db: Session = Depends(get_db)
):
    await check_rate_limit(request, identifier=credentials.email)

    user = db.query(User).filter(User.email == credentials.email).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        valid = verify_password(credentials.password, user.password_hash)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication error",
        )
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    try:
        access_token = create_access_token(
            data={
                "sub": user.id,
                "email": user.email,
                "role_id": user.role_id
            }
        )
        refresh_token = create_refresh_token(
            data={
                "sub": user.id,
                "email": user.email,
                "role_id": user.role_id
            }
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token generation failed",
        )

    ip_address = getattr(request.client, "host", None) if request.client else None
    audit_log = AuditLog(
        user_id=user.id,
        action="USER_LOGIN",
        entity_type="user",
        entity_id=user.id,
        details={"email": user.email},
        ip_address=ip_address,
    )
    db.add(audit_log)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login recording failed",
        )

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )


# ==========================
# REFRESH TOKEN
# ==========================

@router.post("/refresh", response_model=Token)
async def refresh(
    token_data: TokenRefresh,
    request: Request,
    db: Session = Depends(get_db)
):
    await check_rate_limit(request)

    token_payload = verify_token(token_data.refresh_token, token_type="refresh")

    if token_payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == token_payload.user_id).first()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )

    access_token = create_access_token(
        data={
            "sub": user.id,
            "email": user.email,
            "role_id": user.role_id
        }
    )

    refresh_token = create_refresh_token(
        data={
            "sub": user.id,
            "email": user.email,
            "role_id": user.role_id
        }
    )

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )
