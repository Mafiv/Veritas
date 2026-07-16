"""Unit tests for Better Auth bootstrap endpoint."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.v1.endpoints.auth import BootstrapRequest


def test_bootstrap_request_validates_email():
    body = BootstrapRequest(
        auth_user_id="ba_user_1",
        email="ada@example.com",
        full_name="Ada Lovelace",
    )
    assert body.auth_user_id == "ba_user_1"
    assert body.email == "ada@example.com"


def test_bootstrap_request_rejects_short_name():
    with pytest.raises(ValidationError):
        BootstrapRequest(auth_user_id="x", email="a@b.com", full_name="")


def test_bootstrap_request_rejects_whitespace_only_name():
    with pytest.raises(ValidationError):
        BootstrapRequest(auth_user_id="x", email="a@b.com", full_name="   ")


def test_bootstrap_request_strips_full_name():
    body = BootstrapRequest(
        auth_user_id="ba_user_1",
        email="ada@example.com",
        full_name="  Ada Lovelace  ",
    )
    assert body.full_name == "Ada Lovelace"
