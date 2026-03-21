"""
Supabase JWT Verification Middleware for FastAPI.
Validates the Authorization: Bearer <token> header and extracts
the authenticated user's UUID for use in route handlers.
Supports both HS256 (Legacy) and RS256 (Asymmetric JWKS) defaults.
"""
import os
import jwt  # PyJWT
from fastapi import Depends, HTTPException, Header
from jwt import PyJWKClient

SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# For Asymmetric (RS256/ES256) JWTs, fetch the JWKS from Supabase.
jwks_url = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json" if SUPABASE_URL else None
jwk_client = PyJWKClient(jwks_url) if jwks_url else None


async def get_current_user(authorization: str = Header(...)):
    """
    FastAPI dependency that:
    1. Extracts the JWT from the Authorization header.
    2. Verifies it against the Supabase JWKS (for RS256) or JWT secret (for HS256).
    3. Returns the user's UUID (sub claim).
    """
    if not SUPABASE_URL and not SUPABASE_JWT_SECRET:
        raise HTTPException(500, "Server misconfiguration: neither SUPABASE_URL nor SUPABASE_JWT_SECRET is set")

    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Invalid authorization header format")

    token = authorization.split("Bearer ")[1]

    try:
        # First decode the unverified header to check the algorithm
        unverified_header = jwt.get_unverified_header(token)
        alg = unverified_header.get("alg")

        if alg == "HS256":
            # Symmetric Key
            if not SUPABASE_JWT_SECRET:
                raise HTTPException(500, "Server misconfiguration: HS256 token received but SUPABASE_JWT_SECRET not set")
            signing_key = SUPABASE_JWT_SECRET
        elif alg in ("RS256", "ES256"):
            # Asymmetric Key (RSA or Elliptic Curve)
            if not jwk_client:
                raise HTTPException(500, f"Server misconfiguration: {alg} token received but SUPABASE_URL not set")
            signing_key = jwk_client.get_signing_key_from_jwt(token).key
        else:
            raise HTTPException(401, f"Unsupported token algorithm: {alg}")

        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["HS256", "RS256", "ES256"],
            audience="authenticated",
        )
        user_id: str = payload.get("sub")
        if not user_id:
            raise HTTPException(401, "Token missing 'sub' claim")
        return user_id

    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token has expired. Please sign in again.")
    except jwt.InvalidTokenError as e:
        raise HTTPException(401, f"Invalid token: {e}")
