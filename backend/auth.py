"""
Supabase JWT Verification Middleware for FastAPI.
Validates the Authorization: Bearer <token> header and extracts
the authenticated user's UUID for use in route handlers.
"""
import os

import jwt  # PyJWT
from fastapi import Depends, HTTPException, Header

SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")


async def get_current_user(authorization: str = Header(...)):
    """
    FastAPI dependency that:
    1. Extracts the JWT from the Authorization header.
    2. Verifies it against the Supabase JWT secret.
    3. Returns the user's UUID (sub claim).

    Usage:
        @app.get("/api/protected")
        async def protected(user_id: str = Depends(get_current_user)):
            ...
    """
    if not SUPABASE_JWT_SECRET:
        raise HTTPException(500, "Server misconfiguration: JWT secret not set")

    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Invalid authorization header format")

    token = authorization.split("Bearer ")[1]

    try:
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
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
