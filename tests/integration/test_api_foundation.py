def test_health_endpoint_returns_service_metadata(client) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "totalrecall"
    assert response.headers["X-Request-ID"]


def test_protected_endpoint_rejects_missing_token(client) -> None:
    response = client.get("/v1/whoami")

    assert response.status_code == 401


def test_whoami_returns_tenant_context_for_valid_token(client) -> None:
    response = client.get("/v1/whoami", headers={"Authorization": "Bearer test-admin"})

    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] == "tenant_test"
    assert body["actor_id"] == "actor_admin"
    assert "memory:delete" in body["permissions"]


def test_flags_endpoint_returns_request_scoped_snapshot(client) -> None:
    response = client.get("/v1/flags", headers={"Authorization": "Bearer test-reader"})

    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] == "tenant_test"
    assert body["flags"]["values"]["memory.adapter"] == "stub"
    assert body["request_id"]
