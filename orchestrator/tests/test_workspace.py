"""Tests for workspace management."""

from unittest.mock import patch

from orchestrator.workspace import slug_from_identifier


def test_slug_basic() -> None:
    assert slug_from_identifier("TS-42", "OAuth Login Flow") == "ts-42-oauth-login-flow"


def test_slug_special_chars() -> None:
    assert slug_from_identifier("TS-1", "Add API key (v2) support!") == "ts-1-add-api-key-v2-support"


def test_slug_max_length() -> None:
    slug = slug_from_identifier("TS-99", "A" * 100)
    assert len(slug) <= 60


def test_slug_strips_trailing_dashes() -> None:
    slug = slug_from_identifier("TS-1", "test---")
    assert not slug.endswith("-")


def test_slug_lowercase() -> None:
    slug = slug_from_identifier("TS-1", "CamelCase Title")
    assert slug == slug.lower()
