"""Pydantic schemas for auth endpoints."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, description="Minimum 8 characters")


class RegisterResponse(BaseModel):
    id: int
    email: str
    created_at: datetime
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class ErrorResponse(BaseModel):
    detail: str
    code: str | None = None


class AddProviderRequest(BaseModel):
    provider: str  # "anthropic" | "openai" | "google"
    api_key: str
    label: str | None = None
    tier: str | None = None  # Required for Anthropic


class ProviderKeyResponse(BaseModel):
    id: int
    provider: str
    key_hint: str | None
    label: str | None
    tier: str | None
    is_valid: bool
    validated_at: datetime | None

    model_config = {"from_attributes": True}
