from collections.abc import Mapping

from totalrecall.auth.models import AuthTokenConfig, TenantContext
from totalrecall.auth.permissions import permissions_for_roles


class AuthError(Exception):
    pass


class ConfigAuthProvider:
    def __init__(self, token_map: Mapping[str, AuthTokenConfig]) -> None:
        self._token_map = dict(token_map)

    def authenticate(self, token: str) -> TenantContext:
        config = self._token_map.get(token)
        if config is None:
            raise AuthError("Invalid bearer token.")

        return TenantContext(
            tenant_id=config.tenant_id,
            actor_id=config.actor_id,
            roles=config.roles,
            permissions=permissions_for_roles(config.roles),
        )

    def require_permission(self, context: TenantContext, permission: str) -> None:
        if permission not in context.permissions:
            raise AuthError(f"Missing permission: {permission}.")
