from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from ttsforge.server.auth import valid_bearer_token


def test_bearer_auth_requires_exact_scheme_and_token() -> None:
    assert valid_bearer_token("Bearer secret", "secret")
    assert valid_bearer_token("bearer secret", "secret")
    assert not valid_bearer_token(None, "secret")
    assert not valid_bearer_token("Bearer wrong", "secret")
    assert not valid_bearer_token("Basic secret", "secret")
    assert not valid_bearer_token("Bearer", "secret")
    assert not valid_bearer_token("Bearer café", "secret")
