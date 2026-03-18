"""
OIDC token validation for bearer access tokens.
"""

from __future__ import annotations

from dataclasses import dataclass

import jwt
from jwt import PyJWKClient


class AuthError(Exception):
    """Raised when token validation fails."""


@dataclass
class AuthConfig:
    issuer_url: str
    allowed_client_ids: list[str]


class OIDCValidator:
    """Validates RS256 access tokens against OIDC JWKS endpoint."""

    def __init__(self, config: AuthConfig) -> None:
        self._config = config
        self._jwks_client = PyJWKClient(
            f"{self._config.issuer_url.rstrip('/')}/protocol/openid-connect/certs"
        )

    def validate(self, token: str) -> dict:
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                options={"verify_aud": False, "verify_iss": False},
            )
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"Token decode error: {exc}", flush=True)
            raise AuthError(f"Invalid or expired token: {exc}") from exc

        azp = payload.get("azp")
        aud = payload.get("aud", [])
        if isinstance(aud, str):
            aud = [aud]

        print(f"Token payload azp: {azp}, aud: {aud}, allowed: {self._config.allowed_client_ids}", flush=True)

        if azp not in self._config.allowed_client_ids and not any(
            client_id in aud for client_id in self._config.allowed_client_ids
        ):
            raise AuthError("Token audience/client is not allowed")

        return payload
