# ─── Account recovery (#40) — Phase 1 & 2 unit coverage ────────
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from auth import create_access_token, decode_access_token, _token_revoked
from schemas import ReissueRequest, ReissueResponse

MARKER = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


def _payload_at(dt):
    return {"iat": int(dt.timestamp())}


def test_token_not_revoked_without_marker():
    assert _token_revoked({"iat": 1}, None) is False


def test_token_minted_before_marker_is_revoked():
    payload = _payload_at(MARKER - timedelta(hours=1))
    assert _token_revoked(payload, MARKER) is True


def test_token_minted_after_marker_is_valid():
    payload = _payload_at(MARKER + timedelta(hours=1))
    assert _token_revoked(payload, MARKER) is False


def test_naive_marker_is_treated_as_utc():
    # SQLite returns naive datetimes; Postgres is timezone-aware
    payload = _payload_at(datetime(2026, 9, 30, 11, 0, tzinfo=timezone.utc))
    assert _token_revoked(payload, datetime(2026, 9, 30, 12, 0)) is True


def test_payload_without_iat_is_not_revoked():
    assert _token_revoked({}, MARKER) is False


def test_fresh_token_roundtrip_unaffected():
    uid = uuid4()
    token = create_access_token(uid, "patient")
    payload = decode_access_token(token)
    assert payload["sub"] == str(uid)
    # A token minted NOW with a marker set NOW is not revoked (>= comparison)
    assert _token_revoked(payload, datetime.now(timezone.utc) - timedelta(seconds=5)) is False


def test_reissue_request_validates_phone():
    with pytest.raises(ValidationError):
        ReissueRequest(phone_number="12345")  # must be 10 digits
    ok = ReissueRequest(phone_number="9800000000")
    assert ok.phone_number == "9800000000"


def test_reissue_response_defaults():
    r = ReissueResponse(user_id="abc", activation_code="012345")
    assert r.activation_expires_hours == 24
    assert r.study_id is None
