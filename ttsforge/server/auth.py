"""Local API bearer-token authentication."""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer_scheme = HTTPBearer(auto_error=False)


def valid_bearer_token(authorization: str | None, expected: str) -> bool:
    if authorization is None:
        return False
    scheme, separator, supplied = authorization.partition(" ")
    return (
        separator == " "
        and scheme.casefold() == "bearer"
        and bool(supplied)
        and hmac.compare_digest(supplied.encode(), expected.encode())
    )


def require_bearer_token(
    request: Request,
    _credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)
    ],
) -> None:
    expected = request.app.state.token
    if not valid_bearer_token(request.headers.get("authorization"), expected):
        raise HTTPException(status_code=401, detail="A valid bearer token is required.")
