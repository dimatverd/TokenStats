"""SQLAlchemy models for authentication."""

from datetime import UTC, datetime

import enum

from sqlalchemy import Boolean, Column, DateTime, Enum as SAEnum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db import Base


def _utcnow():
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    api_keys = relationship("APIKeyStore", back_populates="user", cascade="all, delete-orphan")


class ProviderType(str, enum.Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"


class APIKeyStore(Base):
    __tablename__ = "api_keys"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_user_provider"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    provider = Column(SAEnum(ProviderType), nullable=False)
    encrypted_key = Column(String(1024), nullable=False)
    key_hint = Column(String(20), nullable=True)
    label = Column(String(100), nullable=True)
    tier = Column(String(20), nullable=True)  # Anthropic tier
    is_valid = Column(Boolean, default=True, nullable=False)
    validated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow, nullable=False)

    user = relationship("User", back_populates="api_keys")
