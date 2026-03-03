"""
Lightweight optional API key guard for mutating dashboard/pipeline endpoints.
If OVERRIDE_API_KEY is set in .env, all requests to guarded routes must send:
    X-Api-Key: <value>
If the env var is empty (dev mode), all requests pass through.

Supabase JWT verification supports:
  - ES256 via JWKS URL (supabase_jwks_url) — preferred for new projects
  - HS256 via JWT secret (supabase_jwt_secret) — legacy fallback
"""
import logging
import jwt
from jwt import PyJWKClient
from fastapi import Header, HTTPException
from app.config import get_settings

logger = logging.getLogger(__name__)

# Module-level JWKS client — caches keys so we don't hit the endpoint every request
_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient | None:
    global _jwks_client
    url = get_settings().supabase_jwks_url
    if not url:
        return None
    if _jwks_client is None:
        _jwks_client = PyJWKClient(url, cache_keys=True)
    return _jwks_client


def require_api_key(x_api_key: str = Header(default="")):
    """FastAPI dependency — inject into any route that mutates state."""
    key = get_settings().override_api_key
    if key and x_api_key != key:
        raise HTTPException(status_code=403, detail="Invalid or missing X-Api-Key header")


def require_supabase_token(authorization: str = Header(default="")):
    """FastAPI dependency — validates Supabase JWT on protected endpoints.

    Tries ES256 via JWKS first, falls back to HS256 secret, skips in dev mode.
    """
    settings = get_settings()
    jwks_url = settings.supabase_jwks_url
    hs256_secret = settings.supabase_jwt_secret

    # Dev mode — no auth configured
    if not jwks_url and not hs256_secret:
        return

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.removeprefix("Bearer ")

    # ES256 via JWKS (preferred)
    if jwks_url:
        try:
            client = _get_jwks_client()
            signing_key = client.get_signing_key_from_jwt(token)
            jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256"],
                audience="authenticated",
            )
            return
        except jwt.PyJWTError as e:
            raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
        except Exception as e:
            logger.warning(f"JWKS verification error: {e}")
            raise HTTPException(status_code=401, detail="Token verification failed")

    # HS256 fallback (legacy Supabase projects)
    try:
        jwt.decode(token, hs256_secret, algorithms=["HS256"], audience="authenticated")
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
