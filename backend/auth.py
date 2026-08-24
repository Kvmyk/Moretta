"""
OIDC token validation for bearer access tokens.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import jwt
from jwt import PyJWKClient


class AuthError(Exception):
    """Raised when token validation fails."""


@dataclass
class AuthConfig:
    issuer_url: str
    allowed_client_ids: list[str]
    admin_roles: list[str] = field(default_factory=list)


class OIDCValidator:
    """Validates RS256 access tokens against an OIDC JWKS endpoint."""

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
                issuer=self._config.issuer_url.rstrip("/"),
                # Keycloak issues `aud: ["account"]` for public clients and puts the
                # real client id in `azp`, so the audience is checked explicitly
                # below against aud *and* azp instead of by PyJWT.
                options={
                    "verify_aud": False,
                    "verify_iss": True,
                    "verify_exp": True,
                    "verify_signature": True,
                    "require": ["exp", "iat", "iss"],
                },
            )
        except jwt.InvalidIssuerError:
            raise AuthError("Token issuer is not trusted")
        except jwt.ExpiredSignatureError:
            raise AuthError("Token has expired")
        except jwt.MissingRequiredClaimError as exc:
            raise AuthError(f"Token is missing a required claim: {exc}")
        except Exception as exc:
            raise AuthError(f"Invalid or expired token: {exc}") from exc

        self._verify_client(payload)
        return payload

    def _verify_client(self, payload: dict) -> None:
        """Ensure the token was issued to one of the allowed OIDC clients."""
        allowed = set(self._config.allowed_client_ids)
        if not allowed:
            raise AuthError("No allowed OIDC clients are configured")

        azp = payload.get("azp")
        if azp:
            if azp not in allowed:
                raise AuthError("Token authorized party (azp) is not allowed")
            return

        # No azp claim: fall back to the audience list.
        aud = payload.get("aud", [])
        audiences = {aud} if isinstance(aud, str) else set(aud or [])
        if not audiences & allowed:
            raise AuthError("Token audience is not allowed")

    def is_admin(self, payload: dict) -> bool:
        """Check whether the token carries one of the configured admin roles."""
        admin_roles = set(self._config.admin_roles)
        if not admin_roles:
            return False
        return bool(admin_roles & extract_roles(payload))


def extract_roles(payload: dict) -> set[str]:
    """Collect realm and client roles from a Keycloak access token payload."""
    roles: set[str] = set()

    realm_access = payload.get("realm_access")
    if isinstance(realm_access, dict):
        roles.update(str(role) for role in realm_access.get("roles", []) or [])

    resource_access = payload.get("resource_access")
    if isinstance(resource_access, dict):
        for client_entry in resource_access.values():
            if isinstance(client_entry, dict):
                roles.update(str(role) for role in client_entry.get("roles", []) or [])

    return roles
