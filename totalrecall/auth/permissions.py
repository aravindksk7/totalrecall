from collections.abc import Iterable

READ_CATALOGUE = "catalogue:read"
GENERATE = "generation:create"
DELETE_MEMORY = "memory:delete"
PROMOTE_LEARNING = "learning:promote"
WRITE_MEMORY = "memory:write"
PUBLISH_SKILL = "skill:publish"

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "reader": frozenset({READ_CATALOGUE}),
    "generator": frozenset({READ_CATALOGUE, GENERATE}),
    "maintainer": frozenset({READ_CATALOGUE, GENERATE, WRITE_MEMORY, PROMOTE_LEARNING}),
    "admin": frozenset(
        {
            READ_CATALOGUE,
            GENERATE,
            DELETE_MEMORY,
            PROMOTE_LEARNING,
            WRITE_MEMORY,
            PUBLISH_SKILL,
        }
    ),
}


def permissions_for_roles(roles: Iterable[str]) -> list[str]:
    permissions: set[str] = set()
    for role in roles:
        permissions.update(ROLE_PERMISSIONS.get(role, frozenset()))
    return sorted(permissions)


def has_permission(roles: Iterable[str], permission: str) -> bool:
    return permission in permissions_for_roles(roles)
