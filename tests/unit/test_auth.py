import pytest

from totalrecall.auth.models import AuthTokenConfig
from totalrecall.auth.permissions import DELETE_MEMORY, READ_CATALOGUE
from totalrecall.auth.provider import AuthError, ConfigAuthProvider


def test_auth_provider_builds_tenant_context_with_permissions() -> None:
    provider = ConfigAuthProvider(
        {
            "token": AuthTokenConfig(
                tenant_id="tenant_a",
                actor_id="actor_a",
                roles=["admin"],
            )
        }
    )

    context = provider.authenticate("token")

    assert context.tenant_id == "tenant_a"
    assert context.actor_id == "actor_a"
    assert DELETE_MEMORY in context.permissions
    assert READ_CATALOGUE in context.permissions


def test_auth_provider_rejects_unknown_token() -> None:
    provider = ConfigAuthProvider({})

    with pytest.raises(AuthError):
        provider.authenticate("missing")
