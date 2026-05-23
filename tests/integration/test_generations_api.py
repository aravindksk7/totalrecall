"""Integration tests for POST /v1/generations."""


def _generation_body(
    tenant_id: str = "tenant_test",
    provider_id: str = "stub",
    validate: bool = True,
) -> dict:
    return {
        "tenant_id": tenant_id,
        "application_id": "app_test",
        "prompt": "Generate a page object for the checkout page",
        "target": {
            "language": "typescript",
            "framework": "playwright",
            "pattern": "pom",
            "locator_strategy": "page_file",
        },
        "scope": {"domain": "checkout"},
        "provider": {"provider_id": provider_id, "model": "stub"},
        "options": {"validate": validate, "max_input_tokens": 12000},
    }


def test_generations_returns_200_with_stub_provider(client) -> None:
    response = client.post(
        "/v1/generations",
        json=_generation_body(),
        headers={"Authorization": "Bearer test-admin"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert len(body["artifacts"]) >= 1


def test_generations_response_includes_context_metadata(client) -> None:
    response = client.post(
        "/v1/generations",
        json=_generation_body(),
        headers={"Authorization": "Bearer test-admin"},
    )

    body = response.json()
    assert body["context"]["context_plan_id"] is not None
    assert isinstance(body["context"]["skill_ids"], list)
    assert isinstance(body["context"]["estimated_input_tokens"], int)


def test_generations_response_includes_validation_status(client) -> None:
    response = client.post(
        "/v1/generations",
        json=_generation_body(validate=True),
        headers={"Authorization": "Bearer test-admin"},
    )

    body = response.json()
    assert body["validation"]["status"] in ("passed", "failed", "warning", "not_run")


def test_generations_rejects_missing_auth(client) -> None:
    response = client.post("/v1/generations", json=_generation_body())

    assert response.status_code == 401


def test_generations_rejects_tenant_mismatch(client) -> None:
    body = _generation_body(tenant_id="other_tenant")
    response = client.post(
        "/v1/generations",
        json=body,
        headers={"Authorization": "Bearer test-admin"},
    )

    assert response.status_code == 403


def test_generations_rejects_invalid_request_body(client) -> None:
    response = client.post(
        "/v1/generations",
        json={"prompt": "missing required fields"},
        headers={"Authorization": "Bearer test-admin"},
    )

    assert response.status_code == 422


def test_generations_reader_token_can_generate(client) -> None:
    response = client.post(
        "/v1/generations",
        json=_generation_body(),
        headers={"Authorization": "Bearer test-reader"},
    )

    assert response.status_code == 200
