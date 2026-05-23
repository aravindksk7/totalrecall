import sys
from pathlib import Path

from totalrecall.generation.models import (
    ArtifactType,
    GeneratedArtifact,
    Language,
    ValidationStatus,
)
from totalrecall.validation.worker import SubprocessPlaywrightWorkerClient


def _artifact() -> GeneratedArtifact:
    return GeneratedArtifact(
        path="pages/login.page.ts",
        language=Language.TYPESCRIPT,
        artifact_type=ArtifactType.PAGE_OBJECT,
        content="export class LoginPage { constructor() {} }",
    )


def _write_script(tmp_path: Path, source: str) -> Path:
    script = tmp_path / "worker.py"
    script.write_text(source, encoding="utf-8")
    return script


def test_subprocess_worker_client_returns_worker_diagnostics(tmp_path: Path) -> None:
    script = _write_script(
        tmp_path,
        """
import json
import sys

payload = json.loads(sys.stdin.read())
assert payload["artifacts"][0]["path"] == "pages/login.page.ts"
json.dump({
    "status": "failed",
    "diagnostics": [{
        "code": "PLAYWRIGHT_IMPORT_MISSING",
        "message": "missing import",
        "path": "tests/login.spec.ts",
        "severity": "failed",
        "details": {}
    }]
}, sys.stdout)
""",
    )
    client = SubprocessPlaywrightWorkerClient([sys.executable, str(script)])

    summary = client.validate([_artifact()], request_id="req_1")

    assert summary.status == ValidationStatus.FAILED
    assert summary.diagnostics[0].code == "PLAYWRIGHT_IMPORT_MISSING"


def test_subprocess_worker_client_warns_on_bad_response(tmp_path: Path) -> None:
    script = _write_script(tmp_path, "import sys\nsys.stdout.write('not json')\n")
    client = SubprocessPlaywrightWorkerClient([sys.executable, str(script)])

    summary = client.validate([_artifact()])

    assert summary.status == ValidationStatus.WARNING
    assert summary.diagnostics[0].code == "TYPESCRIPT_WORKER_BAD_RESPONSE"


def test_subprocess_worker_client_warns_on_nonzero_exit(tmp_path: Path) -> None:
    script = _write_script(
        tmp_path,
        "import sys\nsys.stderr.write('boom')\nsys.exit(2)\n",
    )
    client = SubprocessPlaywrightWorkerClient([sys.executable, str(script)])

    summary = client.validate([_artifact()])

    assert summary.status == ValidationStatus.WARNING
    assert summary.diagnostics[0].code == "TYPESCRIPT_WORKER_FAILED"


def test_subprocess_worker_client_rejects_empty_command() -> None:
    try:
        SubprocessPlaywrightWorkerClient([])
    except ValueError as exc:
        assert "must not be empty" in str(exc)
    else:
        raise AssertionError("empty command should be rejected")
