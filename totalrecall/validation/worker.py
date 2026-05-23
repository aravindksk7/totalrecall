"""Contracts and subprocess client for the Playwright validation worker."""

import json
import subprocess
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from pydantic import Field, ValidationError

from totalrecall.contracts import ContractModel
from totalrecall.generation.models import (
    GeneratedArtifact,
    ValidationDiagnostic,
    ValidationStatus,
    ValidationSummary,
)


class PlaywrightWorkerRequest(ContractModel):
    request_id: str = Field(min_length=1)
    artifacts: list[GeneratedArtifact] = Field(default_factory=list)


class PlaywrightWorkerResponse(ContractModel):
    status: ValidationStatus
    diagnostics: list[ValidationDiagnostic] = Field(default_factory=list)


class PlaywrightValidationWorker(Protocol):
    def validate(
        self,
        artifacts: list[GeneratedArtifact],
        request_id: str | None = None,
    ) -> ValidationSummary:
        """Validate TypeScript Playwright artifacts and return diagnostics."""


class SubprocessPlaywrightWorkerClient:
    """Calls the companion worker over stdin/stdout JSON.

    The worker is intentionally process-boundary only. The Python service owns the
    stable contract and does not import Node or Playwright packages directly.
    """

    def __init__(
        self,
        command: Sequence[str],
        *,
        timeout_seconds: int = 10,
        cwd: Path | None = None,
    ) -> None:
        if not command:
            raise ValueError("Playwright worker command must not be empty")
        if timeout_seconds < 1:
            raise ValueError("Playwright worker timeout must be >= 1 second")
        self._command = tuple(command)
        self._timeout_seconds = timeout_seconds
        self._cwd = cwd

    def validate(
        self,
        artifacts: list[GeneratedArtifact],
        request_id: str | None = None,
    ) -> ValidationSummary:
        worker_request = PlaywrightWorkerRequest(
            request_id=request_id or f"validation_{uuid.uuid4().hex}",
            artifacts=artifacts,
        )
        payload = worker_request.model_dump_json()

        try:
            completed = subprocess.run(
                list(self._command),
                input=payload,
                text=True,
                capture_output=True,
                timeout=self._timeout_seconds,
                cwd=self._cwd,
                check=False,
            )
        except FileNotFoundError as exc:
            return _worker_warning(
                "TYPESCRIPT_WORKER_UNAVAILABLE",
                f"Playwright validation worker command was not found: {exc.filename}",
                {"command": list(self._command)},
            )
        except subprocess.TimeoutExpired:
            return _worker_warning(
                "TYPESCRIPT_WORKER_TIMEOUT",
                "Playwright validation worker timed out",
                {"timeout_seconds": self._timeout_seconds},
            )

        if completed.returncode != 0:
            return _worker_warning(
                "TYPESCRIPT_WORKER_FAILED",
                f"Playwright validation worker exited with status {completed.returncode}",
                {
                    "stderr": completed.stderr[-2000:],
                    "stdout": completed.stdout[-2000:],
                },
            )

        try:
            raw = json.loads(completed.stdout)
            worker_response = PlaywrightWorkerResponse.model_validate(raw)
        except (json.JSONDecodeError, ValidationError) as exc:
            return _worker_warning(
                "TYPESCRIPT_WORKER_BAD_RESPONSE",
                "Playwright validation worker returned an invalid response",
                {"error": str(exc), "stdout": completed.stdout[-2000:]},
            )

        diagnostics = worker_response.diagnostics
        if worker_response.status == ValidationStatus.FAILED and not diagnostics:
            diagnostics = [
                ValidationDiagnostic(
                    code="TYPESCRIPT_WORKER_FAILED",
                    message="Playwright validation worker reported failure without diagnostics",
                    severity=ValidationStatus.FAILED,
                )
            ]
        return ValidationSummary(status=worker_response.status, diagnostics=diagnostics)


def _worker_warning(
    code: str,
    message: str,
    details: dict,
) -> ValidationSummary:
    return ValidationSummary(
        status=ValidationStatus.WARNING,
        diagnostics=[
            ValidationDiagnostic(
                code=code,
                message=message,
                severity=ValidationStatus.WARNING,
                details=details,
            )
        ],
    )
