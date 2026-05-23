from pydantic import BaseModel, Field


class AuthTokenConfig(BaseModel):
    tenant_id: str
    actor_id: str
    roles: list[str] = Field(default_factory=list)


class TenantContext(BaseModel):
    tenant_id: str
    actor_id: str
    roles: list[str]
    permissions: list[str]
