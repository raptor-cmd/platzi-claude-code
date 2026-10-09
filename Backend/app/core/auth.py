"""
Autenticación por JWT (Bearer) para los endpoints que modifican datos.

Los tokens pueden venir de un servicio de identidad externo o de una sesión
anónima (`create_anonymous_token`); aquí se validan igual. El `sub` del token
es el `user_id` (entero positivo).

Los ids anónimos viven en un rango reservado para no chocar con usuarios reales.
"""
import secrets
import time
from collections import defaultdict, deque

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

ANONYMOUS_ID_MIN = 1_000_000_000
ANONYMOUS_ID_MAX = 2_000_000_000  # cabe en el Integer de 32 bits de la DB

# auto_error=False para devolver 401 (y no 403) cuando falta el header
bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    """
    Valida el JWT y devuelve {'id': user_id}.

    Raises:
        HTTPException 401 si falta el token, es inválido/expirado o el
        servidor no tiene JWT_SECRET configurado (fail closed).
    """
    if credentials is None:
        raise _unauthorized("Authentication required")
    if not settings.jwt_secret:
        raise _unauthorized("Authentication is not configured")

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp"]},
        )
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, ValueError, TypeError):
        raise _unauthorized("Invalid or expired token")

    if user_id <= 0:
        raise _unauthorized("Invalid or expired token")

    return {"id": user_id}


def create_anonymous_token() -> dict:
    """Crea un usuario anónimo nuevo y devuelve su JWT firmado."""
    if not settings.jwt_secret:
        raise _unauthorized("Authentication is not configured")

    user_id = ANONYMOUS_ID_MIN + secrets.randbelow(ANONYMOUS_ID_MAX - ANONYMOUS_ID_MIN)
    ttl = settings.anonymous_token_ttl_seconds
    token = jwt.encode(
        {"sub": str(user_id), "exp": int(time.time()) + ttl, "anon": True},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return {"access_token": token, "token_type": "bearer", "user_id": user_id, "expires_in": ttl}


# Rate limit en memoria por IP (suficiente para desarrollo; no sirve con varios workers)
_token_requests: dict[str, deque] = defaultdict(deque)


def anonymous_rate_limit(request: Request) -> None:
    """Dependency: limita la emisión de tokens anónimos por IP."""
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window = _token_requests[ip]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= settings.anonymous_tokens_per_minute:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many anonymous sessions, try again later",
        )
    window.append(now)
