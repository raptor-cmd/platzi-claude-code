"""
Autenticación por JWT (Bearer) para los endpoints que modifican datos.

El token lo emite un servicio de identidad externo; aquí solo se valida.
El `sub` del token es el `user_id` (entero positivo).
"""
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

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
