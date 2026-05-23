import json
import shutil
import subprocess
from pathlib import Path

import pytest

from totalrecall.generation.models import ValidationStatus
from totalrecall.validation.worker import (
    PlaywrightWorkerRequest,
    PlaywrightWorkerResponse,
)

ROOT = Path(__file__).resolve().parents[2]
WORKER_DIR = ROOT / "workers" / "playwright"


def test_playwright_worker_sample_request_matches_python_contract() -> None:
    payload = json.loads(
        (WORKER_DIR / "contracts" / "validation-request.sample.json").read_text(
            encoding="utf-8"
        )
    )

    request = PlaywrightWorkerRequest.model_validate(payload)

    assert request.request_id == "validation_sample"
    assert request.artifacts[0].path == "pages/login.page.ts"


def test_playwright_worker_sample_response_matches_python_contract() -> None:
    payload = json.loads(
        (WORKER_DIR / "contracts" / "validation-response.sample.json").read_text(
            encoding="utf-8"
        )
    )

    response = PlaywrightWorkerResponse.model_validate(payload)

    assert response.status == ValidationStatus.PASSED


def test_playwright_worker_cli_validates_sample_request() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")

    request_text = (WORKER_DIR / "contracts" / "validation-request.sample.json").read_text(
        encoding="utf-8"
    )
    completed = subprocess.run(
        [node, str(WORKER_DIR / "dist" / "cli.js")],
        input=request_text,
        text=True,
        capture_output=True,
        cwd=ROOT,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    response = PlaywrightWorkerResponse.model_validate_json(completed.stdout)
    assert response.status == ValidationStatus.PASSED


def test_playwright_worker_cli_reports_playwright_spec_errors() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")

    payload = json.loads(
        (WORKER_DIR / "contracts" / "validation-request.sample.json").read_text(
            encoding="utf-8"
        )
    )
    payload["artifacts"][1]["content"] = "test('login', async () => {});"
    completed = subprocess.run(
        [node, str(WORKER_DIR / "dist" / "cli.js")],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=ROOT,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    response = PlaywrightWorkerResponse.model_validate_json(completed.stdout)
    assert response.status == ValidationStatus.FAILED
    assert {diag.code for diag in response.diagnostics} == {"PLAYWRIGHT_IMPORT_MISSING"}
