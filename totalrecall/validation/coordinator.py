"""Validation coordinator: runs structural and policy checks on generated artifacts."""

import ast
import re

from totalrecall.generation.models import (
    ArtifactType,
    GeneratedArtifact,
    Language,
    ValidationDiagnostic,
    ValidationStatus,
    ValidationSummary,
)
from totalrecall.skills.models import SkillDefinition, SkillValidatorType
from totalrecall.validation.worker import PlaywrightValidationWorker


class ValidationCoordinator:
    """Runs the validation pipeline for a set of generated artifacts.

    Phase 8 scope: structural presence checks, Python AST parse, POM pattern check,
    and optional TypeScript Playwright validation through the companion worker.
    """

    def __init__(self, playwright_worker: PlaywrightValidationWorker | None = None) -> None:
        self._playwright_worker = playwright_worker

    def validate(
        self,
        artifacts: list[GeneratedArtifact],
        skill: SkillDefinition | None,
    ) -> ValidationSummary:
        if not artifacts:
            return ValidationSummary(
                status=ValidationStatus.FAILED,
                diagnostics=[
                    ValidationDiagnostic(
                        code="NO_ARTIFACTS",
                        message="Generation produced no artifacts",
                        severity=ValidationStatus.FAILED,
                    )
                ],
            )

        diagnostics: list[ValidationDiagnostic] = []
        diagnostics.extend(self._check_structure(artifacts, skill))
        diagnostics.extend(self._check_python_syntax(artifacts))
        diagnostics.extend(self._check_java_syntax(artifacts))
        diagnostics.extend(self._check_playwright_worker(artifacts, skill))

        if any(d.severity == ValidationStatus.FAILED for d in diagnostics):
            overall = ValidationStatus.FAILED
        elif any(d.severity == ValidationStatus.WARNING for d in diagnostics):
            overall = ValidationStatus.WARNING
        else:
            overall = ValidationStatus.PASSED

        return ValidationSummary(status=overall, diagnostics=diagnostics)

    def _check_structure(
        self,
        artifacts: list[GeneratedArtifact],
        skill: SkillDefinition | None,
    ) -> list[ValidationDiagnostic]:
        diagnostics: list[ValidationDiagnostic] = []

        if skill is None:
            return diagnostics

        structure_validators = [
            v for v in skill.validators if v.type == SkillValidatorType.STRUCTURE
        ]
        if not structure_validators:
            return diagnostics

        artifact_types = {a.artifact_type for a in artifacts}
        required_types = {of.artifact_type for of in skill.output_files}
        missing_types = required_types - artifact_types

        for missing in missing_types:
            diagnostics.append(
                ValidationDiagnostic(
                    code="MISSING_ARTIFACT_TYPE",
                    message=f"Expected artifact of type '{missing}' but none was generated",
                    severity=ValidationStatus.WARNING,
                    details={
                        "required_type": missing,
                        "produced_types": sorted(str(t) for t in artifact_types),
                    },
                )
            )

        for validator in structure_validators:
            for rule in validator.rules:
                diagnostics.extend(self._check_rule(rule, artifacts))

        return diagnostics

    def _check_rule(
        self, rule: str, artifacts: list[GeneratedArtifact]
    ) -> list[ValidationDiagnostic]:
        if rule == "page_object_class_required":
            page_objects = [a for a in artifacts if a.artifact_type == ArtifactType.PAGE_OBJECT]
            for artifact in page_objects:
                if not re.search(r"\bclass\s+\w+", artifact.content):
                    return [
                        ValidationDiagnostic(
                            code="POM_CLASS_MISSING",
                            message=f"Page object '{artifact.path}' must define a class",
                            path=artifact.path,
                            severity=ValidationStatus.FAILED,
                        )
                    ]

        if rule == "pytest_test_functions_required":
            test_specs = [a for a in artifacts if a.artifact_type == ArtifactType.TEST_SPEC]
            for artifact in test_specs:
                if "def test_" not in artifact.content:
                    return [
                        ValidationDiagnostic(
                            code="NO_TEST_FUNCTIONS",
                            message=(
                                f"Test spec '{artifact.path}' must define"
                                " at least one test_ function"
                            ),
                            path=artifact.path,
                            severity=ValidationStatus.FAILED,
                        )
                    ]

        if rule == "locator_in_constructor_required":
            page_objects = [a for a in artifacts if a.artifact_type == ArtifactType.PAGE_OBJECT]
            for artifact in page_objects:
                if (
                    artifact.language == Language.TYPESCRIPT
                    and "constructor" not in artifact.content
                ):
                    return [
                        ValidationDiagnostic(
                            code="CONSTRUCTOR_MISSING",
                            message=(
                                f"Playwright page object '{artifact.path}' should define"
                                " a constructor with locators"
                            ),
                            path=artifact.path,
                            severity=ValidationStatus.WARNING,
                        )
                    ]

        if rule == "fixture_required":
            fixtures = [a for a in artifacts if a.artifact_type == ArtifactType.FIXTURE]
            if not fixtures:
                return [
                    ValidationDiagnostic(
                        code="FIXTURE_MISSING",
                        message="Pytest skill requires at least one fixture artifact",
                        severity=ValidationStatus.WARNING,
                    )
                ]

        return []

    def _check_python_syntax(
        self, artifacts: list[GeneratedArtifact]
    ) -> list[ValidationDiagnostic]:
        diagnostics: list[ValidationDiagnostic] = []
        python_artifacts = [a for a in artifacts if a.language == Language.PYTHON]

        for artifact in python_artifacts:
            try:
                ast.parse(artifact.content)
            except SyntaxError as exc:
                diagnostics.append(
                    ValidationDiagnostic(
                        code="PYTHON_SYNTAX_ERROR",
                        message=f"Python syntax error in '{artifact.path}': {exc.msg}",
                        path=artifact.path,
                        severity=ValidationStatus.FAILED,
                        details={"line": exc.lineno, "offset": exc.offset},
                    )
                )
        return diagnostics

    def _check_playwright_worker(
        self,
        artifacts: list[GeneratedArtifact],
        skill: SkillDefinition | None,
    ) -> list[ValidationDiagnostic]:
        if self._playwright_worker is None or skill is None:
            return []
        if skill.language != Language.TYPESCRIPT or skill.framework.value != "playwright":
            return []

        typescript_artifacts = [a for a in artifacts if a.language == Language.TYPESCRIPT]
        if not typescript_artifacts:
            return []

        try:
            summary = self._playwright_worker.validate(typescript_artifacts)
        except Exception as exc:
            return [
                ValidationDiagnostic(
                    code="TYPESCRIPT_WORKER_ERROR",
                    message=f"Playwright validation worker raised an unexpected error: {exc}",
                    severity=ValidationStatus.WARNING,
                )
            ]

        if summary.status == ValidationStatus.FAILED and not summary.diagnostics:
            return [
                ValidationDiagnostic(
                    code="TYPESCRIPT_WORKER_FAILED",
                    message="Playwright validation worker reported failure without diagnostics",
                    severity=ValidationStatus.FAILED,
                )
            ]
        return summary.diagnostics

    def _check_java_syntax(
        self, artifacts: list[GeneratedArtifact]
    ) -> list[ValidationDiagnostic]:
        """Boundary for future JVM-based Java validation (JUnit/TestNG).

        The Python service cannot execute a JVM; each Java artifact receives a WARNING so
        callers know validation was incomplete rather than incorrectly reporting PASSED.
        Full validation will be delegated to a JVM worker in a future phase.
        """
        diagnostics: list[ValidationDiagnostic] = []
        java_artifacts = [a for a in artifacts if a.language == Language.JAVA]

        for artifact in java_artifacts:
            diagnostics.append(
                ValidationDiagnostic(
                    code="JAVA_VALIDATION_NOT_SUPPORTED",
                    message=(
                        f"Java artifact '{artifact.path}' cannot be validated without the JVM "
                        "worker. Validation deferred — artifact may still be syntactically valid."
                    ),
                    path=artifact.path,
                    severity=ValidationStatus.WARNING,
                )
            )
        return diagnostics
