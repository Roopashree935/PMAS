# ─── Auth primitives (no database required) ──────────────────
from uuid import uuid4

import pytest
from fastapi import HTTPException

from auth import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = hash_password("correct-horse-battery")
    assert hashed != "correct-horse-battery"
    assert verify_password("correct-horse-battery", hashed)


def test_wrong_password_rejected():
    hashed = hash_password("correct-horse-battery")
    assert verify_password("wrong-password", hashed) is False


def test_malformed_hash_rejected_not_raised():
    # A corrupt hash must return False, not raise (verify_password guard)
    assert verify_password("anything", "not-a-bcrypt-hash") is False


def test_token_roundtrip():
    user_id = uuid4()
    token = create_access_token(user_id, "patient")
    payload = decode_access_token(token)
    assert payload["sub"] == str(user_id)
    assert payload["role"] == "patient"


def test_expired_token_rejected(monkeypatch):
    monkeypatch.setattr("auth.JWT_EXPIRY_HOURS", -1)
    token = create_access_token(uuid4(), "patient")
    with pytest.raises(HTTPException) as excinfo:
        decode_access_token(token)
    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Token expired"


def test_garbage_token_rejected():
    with pytest.raises(HTTPException) as excinfo:
        decode_access_token("not.a.jwt")
    assert excinfo.value.status_code == 401
