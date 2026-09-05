import time

import jwt as pyjwt
import pytest

from app.auth import create_access_token, decode_token, hash_password, verify_password
from app.config import settings


def test_password_hash_roundtrip():
    h = hash_password("s3cret!")
    assert h != "s3cret!" and verify_password("s3cret!", h)


def test_password_wrong_rejected():
    assert not verify_password("wrong", hash_password("right"))


def test_token_roundtrip_carries_user_id():
    tok = create_access_token(42)
    assert decode_token(tok) == 42


def test_token_expired_raises():
    import app.auth as auth_mod
    tok = auth_mod._encode({"sub": "1", "exp": int(time.time()) - 10})
    with pytest.raises(pyjwt.PyJWTError):
        decode_token(tok)


def test_token_garbage_raises():
    with pytest.raises(pyjwt.PyJWTError):
        decode_token("not-a-jwt")
