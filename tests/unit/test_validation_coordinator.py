from totalrecall.generation.models import (
    ArtifactType,
    GeneratedArtifact,
    Language,
    ValidationDiagnostic,
    ValidationStatus,
    ValidationSummary,
)
from totalrecall.skills.models import (
    SkillDefinition,
    SkillOutputFile,
    SkillStatus,
    SkillValidator,
    SkillValidatorType,
)
from totalrecall.validation.coordinator import ValidationCoordinator


def _make_artifact(
    artifact_type: ArtifactType = ArtifactType.PAGE_OBJECT,
    language: Language = Language.TYPESCRIPT,
    content: str = "export class CheckoutPage { constructor() {} }",
    path: str = "pages/checkout.page.ts",
) -> GeneratedArtifact:
    return GeneratedArtifact(
        path=path, artifact_type=artifact_type, language=language, content=content
    )


def _playwright_skill() -> SkillDefinition:
    return SkillDefinition(
        skill_id="playwright-typescript-pom",
        version="1.0.0",
        language=Language.TYPESCRIPT,
        framework="playwright",
        output_files=[
            SkillOutputFile(
                artifact_type=ArtifactType.PAGE_OBJECT,
                path_template="pages/{domain}/{route}.page.ts",
                template_ref="playwright/page_object.ts",
            ),
            SkillOutputFile(
                artifact_type=ArtifactType.TEST_SPEC,
                path_template="tests/{domain}/{route}.spec.ts",
                template_ref="playwright/test_spec.ts",
            ),
        ],
        validators=[
            SkillValidator(
                type=SkillValidatorType.STRUCTURE,
                rules=["page_object_class_required", "locator_in_constructor_required"],
            )
        ],
        status=SkillStatus.ACTIVE,
    )


def _pytest_skill() -> SkillDefinition:
    return SkillDefinition(
        skill_id="pytest-python-pom",
        version="1.0.0",
        language=Language.PYTHON,
        framework="pytest",
        output_files=[
            SkillOutputFile(
                artifact_type=ArtifactType.TEST_SPEC,
                path_template="tests/{domain}/test_{route}.py",
                template_ref="pytest/test_spec.py",
            )
        ],
        validators=[
            SkillValidator(
                type=SkillValidatorType.STRUCTURE,
                rules=["pytest_test_functions_required"],
            )
        ],
        status=SkillStatus.ACTIVE,
    )


def test_coordinator_passes_valid_playwright_artifacts() -> None:
    coordinator = ValidationCoordinator()
    page_obj_content = (
        "export class CheckoutPage { constructor(p) { this.btn = p.getByRole('button'); } }"
    )
    artifacts = [
        _make_artifact(ArtifactType.PAGE_OBJECT, Language.TYPESCRIPT, page_obj_content),
        _make_artifact(
            ArtifactType.TEST_SPEC,
            Language.TYPESCRIPT,
            "test('checkout', async () => {});",
            "tests/checkout.spec.ts",
        ),
    ]
    summary = coordinator.validate(artifacts, _playwright_skill())

    assert summary.status == ValidationStatus.PASSED


def test_coordinator_fails_when_no_artifacts() -> None:
    coordinator = ValidationCoordinator()
    summary = coordinator.validate([], None)

    assert summary.status == ValidationStatus.FAILED
    assert any(d.code == "NO_ARTIFACTS" for d in summary.diagnostics)


def test_coordinator_warns_on_missing_artifact_type() -> None:
    coordinator = ValidationCoordinator()
    artifacts = [
        _make_artifact(
            ArtifactType.PAGE_OBJECT,
            Language.TYPESCRIPT,
            "export class P { constructor() {} }",
        )
    ]
    summary = coordinator.validate(artifacts, _playwright_skill())

    assert summary.status in (ValidationStatus.WARNING, ValidationStatus.PASSED)
    codes = [d.code for d in summary.diagnostics]
    assert "MISSING_ARTIFACT_TYPE" in codes


def test_coordinator_fails_when_page_object_has_no_class() -> None:
    coordinator = ValidationCoordinator()
    artifacts = [
        _make_artifact(content="export function getPage() {}", language=Language.TYPESCRIPT)
    ]
    summary = coordinator.validate(artifacts, _playwright_skill())

    assert summary.status == ValidationStatus.FAILED
    assert any(d.code == "POM_CLASS_MISSING" for d in summary.diagnostics)


def test_coordinator_warns_on_missing_constructor_in_ts_page_object() -> None:
    coordinator = ValidationCoordinator()
    artifacts = [
        _make_artifact(content="export class CheckoutPage {}", language=Language.TYPESCRIPT),
        _make_artifact(
            ArtifactType.TEST_SPEC,
            Language.TYPESCRIPT,
            "test('x', () => {});",
            "tests/x.spec.ts",
        ),
    ]
    summary = coordinator.validate(artifacts, _playwright_skill())

    codes = [d.code for d in summary.diagnostics]
    assert "CONSTRUCTOR_MISSING" in codes


def test_coordinator_fails_python_syntax_error() -> None:
    coordinator = ValidationCoordinator()
    bad_python = "def test_checkout(\n    # unclosed paren"
    artifacts = [
        _make_artifact(
            ArtifactType.TEST_SPEC,
            Language.PYTHON,
            bad_python,
            "tests/test_checkout.py",
        )
    ]
    summary = coordinator.validate(artifacts, None)

    assert summary.status == ValidationStatus.FAILED
    assert any(d.code == "PYTHON_SYNTAX_ERROR" for d in summary.diagnostics)


def test_coordinator_passes_valid_python_syntax() -> None:
    coordinator = ValidationCoordinator()
    good_python = (
        "class CheckoutPage:\n"
        "    def __init__(self):\n"
        "        pass\n\n"
        "def test_checkout():\n"
        "    pass\n"
    )
    artifacts = [
        _make_artifact(
            ArtifactType.TEST_SPEC, Language.PYTHON, good_python, "tests/test_checkout.py"
        )
    ]
    summary = coordinator.validate(artifacts, _pytest_skill())

    assert summary.status == ValidationStatus.PASSED


def test_coordinator_fails_when_pytest_spec_has_no_test_functions() -> None:
    coordinator = ValidationCoordinator()
    artifacts = [
        _make_artifact(
            ArtifactType.TEST_SPEC,
            Language.PYTHON,
            "class CheckoutPage:\n    pass\n",
            "tests/test_checkout.py",
        )
    ]
    summary = coordinator.validate(artifacts, _pytest_skill())

    assert summary.status == ValidationStatus.FAILED
    assert any(d.code == "NO_TEST_FUNCTIONS" for d in summary.diagnostics)


def test_coordinator_with_no_skill_skips_structural_checks() -> None:
    coordinator = ValidationCoordinator()
    artifacts = [_make_artifact(content="export class P {}", language=Language.TYPESCRIPT)]
    summary = coordinator.validate(artifacts, None)

    assert summary.status == ValidationStatus.PASSED


class _FakePlaywrightWorker:
    def __init__(self, summary: ValidationSummary) -> None:
        self.summary = summary
        self.calls: list[list[GeneratedArtifact]] = []

    def validate(
        self,
        artifacts: list[GeneratedArtifact],
        request_id: str | None = None,
    ) -> ValidationSummary:
        self.calls.append(artifacts)
        return self.summary


class _RaisingPlaywrightWorker:
    def validate(
        self,
        artifacts: list[GeneratedArtifact],
        request_id: str | None = None,
    ) -> ValidationSummary:
        raise RuntimeError("worker failed")


def test_coordinator_includes_playwright_worker_diagnostics() -> None:
    worker = _FakePlaywrightWorker(
        ValidationSummary(
            status=ValidationStatus.FAILED,
            diagnostics=[
                ValidationDiagnostic(
                    code="PLAYWRIGHT_IMPORT_MISSING",
                    message="missing import",
                    path="tests/login.spec.ts",
                    severity=ValidationStatus.FAILED,
                )
            ],
        )
    )
    coordinator = ValidationCoordinator(playwright_worker=worker)
    artifacts = [
        _make_artifact(content="export class LoginPage { constructor() {} }"),
        _make_artifact(
            ArtifactType.TEST_SPEC,
            Language.TYPESCRIPT,
            "test('login', async () => {});",
            "tests/login.spec.ts",
        ),
    ]

    summary = coordinator.validate(artifacts, _playwright_skill())

    assert summary.status == ValidationStatus.FAILED
    assert worker.calls == [artifacts]
    assert any(d.code == "PLAYWRIGHT_IMPORT_MISSING" for d in summary.diagnostics)


def test_coordinator_skips_playwright_worker_for_non_playwright_skill() -> None:
    worker = _FakePlaywrightWorker(ValidationSummary(status=ValidationStatus.FAILED))
    coordinator = ValidationCoordinator(playwright_worker=worker)
    artifacts = [
        _make_artifact(
            ArtifactType.TEST_SPEC,
            Language.PYTHON,
            "def test_login():\n    pass\n",
            "tests/test_login.py",
        )
    ]

    summary = coordinator.validate(artifacts, _pytest_skill())

    assert summary.status == ValidationStatus.PASSED
    assert worker.calls == []


def test_coordinator_warns_when_playwright_worker_raises() -> None:
    coordinator = ValidationCoordinator(playwright_worker=_RaisingPlaywrightWorker())
    artifacts = [
        _make_artifact(content="export class LoginPage { constructor() {} }"),
        _make_artifact(
            ArtifactType.TEST_SPEC,
            Language.TYPESCRIPT,
            "test('login', async () => {});",
            "tests/login.spec.ts",
        ),
    ]

    summary = coordinator.validate(artifacts, _playwright_skill())

    assert summary.status == ValidationStatus.WARNING
    assert any(d.code == "TYPESCRIPT_WORKER_ERROR" for d in summary.diagnostics)


# --- Java validator placeholder ---

def test_coordinator_warns_on_java_artifact() -> None:
    coordinator = ValidationCoordinator()
    artifact = _make_artifact(
        artifact_type=ArtifactType.TEST_SPEC,
        language=Language.JAVA,
        content="public class LoginTest { @Test public void testLogin() {} }",
        path="src/test/java/LoginTest.java",
    )
    summary = coordinator.validate([artifact], None)

    assert summary.status == ValidationStatus.WARNING
    assert any(d.code == "JAVA_VALIDATION_NOT_SUPPORTED" for d in summary.diagnostics)


def test_coordinator_emits_one_warning_per_java_artifact() -> None:
    coordinator = ValidationCoordinator()
    artifacts = [
        _make_artifact(
            artifact_type=ArtifactType.PAGE_OBJECT,
            language=Language.JAVA,
            content="public class LoginPage {}",
            path="src/main/java/LoginPage.java",
        ),
        _make_artifact(
            artifact_type=ArtifactType.TEST_SPEC,
            language=Language.JAVA,
            content="public class LoginTest { @Test public void testLogin() {} }",
            path="src/test/java/LoginTest.java",
        ),
    ]
    summary = coordinator.validate(artifacts, None)

    java_warnings = [d for d in summary.diagnostics if d.code == "JAVA_VALIDATION_NOT_SUPPORTED"]
    assert len(java_warnings) == 2


def test_coordinator_no_java_warning_for_non_java_artifacts() -> None:
    coordinator = ValidationCoordinator()
    artifacts = [
        _make_artifact(content="export class P { constructor() {} }", language=Language.TYPESCRIPT),
    ]
    summary = coordinator.validate(artifacts, None)

    assert not any(d.code == "JAVA_VALIDATION_NOT_SUPPORTED" for d in summary.diagnostics)


def test_coordinator_java_warning_does_not_suppress_python_checks() -> None:
    """Mixed Java + bad Python: Python syntax error is still reported alongside Java warning."""
    coordinator = ValidationCoordinator()
    artifacts = [
        _make_artifact(
            artifact_type=ArtifactType.PAGE_OBJECT,
            language=Language.JAVA,
            content="public class LoginPage {}",
            path="src/main/java/LoginPage.java",
        ),
        _make_artifact(
            artifact_type=ArtifactType.TEST_SPEC,
            language=Language.PYTHON,
            content="def test_login(\n    # unclosed",
            path="tests/test_login.py",
        ),
    ]
    summary = coordinator.validate(artifacts, None)

    codes = {d.code for d in summary.diagnostics}
    assert "JAVA_VALIDATION_NOT_SUPPORTED" in codes
    assert "PYTHON_SYNTAX_ERROR" in codes
    assert summary.status == ValidationStatus.FAILED
