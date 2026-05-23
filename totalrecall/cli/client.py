"""Thin HTTP client for the TotalRecall API, used by CLI commands."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class ApiError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status
        self.detail = detail


class TotalRecallClient:
    def __init__(self, base_url: str, token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token

    def _request(self, method: str, path: str, body: Any = None) -> Any:
        url = f"{self._base_url}{path}"
        data = json.dumps(body).encode() if body is not None else None
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(body_text).get("detail", body_text)
            except Exception:
                detail = body_text
            raise ApiError(exc.code, detail) from exc

    def generate(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/v1/generations", payload)

    def search_catalogue(self, params: dict[str, Any]) -> dict[str, Any]:
        qs = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
        path = f"/v1/catalogue?{qs}" if qs else "/v1/catalogue"
        return self._request("GET", path)

    def get_catalogue_entry(self, entity_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/catalogue/{entity_id}")

    def delete_memory(
        self, entity_id: str, application_id: str, reason: str | None
    ) -> dict[str, Any]:
        return self._request(
            "DELETE",
            f"/v1/memories/{entity_id}",
            {"application_id": application_id, "reason": reason},
        )

    def trigger_learning_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/v1/learning/runs", payload)

    def get_learning_run(self, run_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/learning/runs/{run_id}")

    def list_learning_runs(self, application_id: str | None = None) -> list[dict[str, Any]]:
        path = "/v1/learning/runs"
        if application_id:
            path += f"?application_id={application_id}"
        return self._request("GET", path)
