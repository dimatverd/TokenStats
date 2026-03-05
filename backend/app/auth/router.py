"""Auth router: registration, login, token refresh, provider keys."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.encryption import encrypt_key
from app.auth.models import APIKeyStore, ProviderType, RefreshTokenBlacklist, User
from app.auth.schemas import (
    AddProviderRequest,
    LoginRequest,
    ProviderKeyResponse,
    RefreshTokenRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
)
from app.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.config import settings
from app.db import get_db
from app.providers.registry import get_provider

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email}


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # Check if email already exists
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        email=body.email.lower(),
        hashed_password=hash_password(body.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return RegisterResponse(
        id=user.id,
        email=user.email,
        created_at=user.created_at,
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/token", response_model=TokenResponse)
async def refresh_token(body: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(body.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
        user_id = int(payload["sub"])
        jti = payload.get("jti")
    except (Exception, KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    if not jti:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    # Check blacklist — reject already-used tokens (replay protection)
    blacklisted = await db.execute(select(RefreshTokenBlacklist).where(RefreshTokenBlacklist.jti == jti))
    if blacklisted.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token already used")

    result = await db.execute(select(User).where(User.id == user_id, User.is_active.is_(True)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # Revoke the used refresh token before issuing new ones
    db.add(RefreshTokenBlacklist(jti=jti, user_id=user.id))
    await db.commit()

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(_: User = Depends(get_current_user)):
    """Invalidate session — client must discard stored tokens."""


# ── Provider key management ──────────────────────────────


@router.post("/providers", response_model=ProviderKeyResponse, status_code=status.HTTP_201_CREATED)
async def add_provider(
    body: AddProviderRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Validate provider type
    try:
        provider_type = ProviderType(body.provider)
    except ValueError:
        raise HTTPException(
            status_code=422, detail=f"Invalid provider: {body.provider}. Must be: anthropic, openai, google"
        )

    # Anthropic requires tier
    if provider_type == ProviderType.ANTHROPIC and not body.tier:
        raise HTTPException(status_code=422, detail="Tier is required for Anthropic (tier1-tier4, build, scale)")

    # Check if already added
    result = await db.execute(
        select(APIKeyStore).where(APIKeyStore.user_id == user.id, APIKeyStore.provider == provider_type)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Provider {body.provider} already configured")

    # Validate the key
    provider = get_provider(body.provider)
    if not provider:
        raise HTTPException(status_code=422, detail=f"Unknown provider: {body.provider}")

    validation = await provider.validate_key(body.api_key, tier=body.tier)
    if not validation.is_valid:
        raise HTTPException(status_code=400, detail=validation.error or "Key validation failed")
    if not validation.is_read_only:
        raise HTTPException(status_code=400, detail="Key is not read-only")

    # Encrypt and store
    key_hint = body.api_key[-4:] if len(body.api_key) > 4 else "****"
    api_key_record = APIKeyStore(
        user_id=user.id,
        provider=provider_type,
        encrypted_key=encrypt_key(body.api_key),
        key_hint=key_hint,
        label=body.label,
        tier=body.tier,
        is_valid=True,
        validated_at=datetime.now(UTC),
    )
    db.add(api_key_record)
    await db.commit()
    await db.refresh(api_key_record)
    return api_key_record


@router.get("/providers", response_model=list[ProviderKeyResponse])
async def list_providers(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(APIKeyStore).where(APIKeyStore.user_id == user.id))
    return result.scalars().all()


@router.delete("/providers/{provider}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        provider_type = ProviderType(provider)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")

    result = await db.execute(
        select(APIKeyStore).where(APIKeyStore.user_id == user.id, APIKeyStore.provider == provider_type)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail=f"Provider {provider} not found")

    await db.delete(record)
    await db.commit()
