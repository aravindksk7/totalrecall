"""End-to-end testgen pipeline test using all stub adapters."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from totalrecall.context.planner import ContextPlanner
from totalrecall.generation.models import (
    AutomationPattern,
    Framework,
    GenerationOptions,
    GenerationRequest,
    GenerationScope,
    GenerationTarget,
    GenerationStatus,
    Language,
    LocatorStrategy,
)
from totalrecall.generation.orchestrator import GenerationOrchestrator
from totalrecall.providers.gateway import ProviderGateway
from totalrecall.providers.normalizer import ResponseNormalizer
from totalrecall.testgen.guardrails.input_guardrail import NullInputGuardrail
from totalrecall.testgen.guardrails.output_guardrail import NullOutputGuardrail
from totalrecall.testgen.jira.adapter import StubJiraAdapter
from totalrecall.testgen.jira.models import JiraAcceptanceCriterion, JiraStory
from totalrecall.testgen.models import TestType
from totalrecall.testgen.pack.normalizer import TestCasePackNormalizer
from totalrecall.testgen.prompts.testgen_builder import TestGenPromptBuilder
from totalrecall.testgen.rag.store import StubRagStore
from totalrecall.testgen.reformulator import StubReformulator
from totalrecall.testgen.routing.router import TestTypeRouter
from totalrecall.testgen.tone.checker import NullToneChecker
from totalrecall.validation.coordinator import ValidationCoordinator

from totalrecall.prompts.builder import PromptBuilder
from totalrecall.providers.models import ProviderResponse

from tests.unit.test_context_planner import _make_memory_wrapper, _make_registry

_PACK_JSON = json.dumps(
    {
        "story_summary": "User can log in to the application",
        "test_cases": [
            {
                "id": "TC-001",
                "type": "functional",
                "title": "Login with valid credentials",
                "steps": ["Navigate to /login", "Enter email and password", "Click Login"],
                "expected_result": "User is redirected to the dashboard",
                "tags": ["smoke"],
            },
            {
                "id": "TC-002",
                "type": "negative",
                "title": "Login with wrong password",
                "steps": ["Navigate to /login", "Enter valid email and wrong password", "Click Login"],
                "expected_result": "Error message is displayed",
            },
        ],
        "coverage_summary": "Covers happy path and wrong-password negative case",
        "test_types_covered": ["functional", "negative"],
    }
)


class _StubProvider:
    def generate(self, request):
        return ProviderResponse(
            request_id=request.request_id,
            provider_id="stub",
            model="stub-model",
            raw_text=_PACK_JSON,
        )


def _make_orchestrator(tmp_path: Path) -> GenerationOrchestrator:
    skill_registry = _make_registry(tmp_path)
    memory_wrapper = _make_memory_wrapper()

    story = JiraStory(
        jira_key="AUTH-1",
        summary="User login flow",
        acceptance_criteria=[
            JiraAcceptanceCriterion(index=0, text="Valid creds redirect to dashboard"),
            JiraAcceptanceCriterion(index=1, text="Invalid creds show error"),
        ],
        fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    return GenerationOrchestrator(
        planner=ContextPlanner(skill_registry=skill_registry, memory_wrapper=memory_wrapper),
        prompt_builder=PromptBuilder(skill_registry=skill_registry, memory_wrapper=memory_wrapper),
        gateway=ProviderGateway(providers={"stub": _StubProvider()}),
        normalizer=ResponseNormalizer(),
        validator=ValidationCoordinator(),
        skill_registry=skill_registry,
        reformulator=StubReformulator(),
        input_guardrail=NullInputGuardrail(),
        output_guardrail=NullOutputGuardrail(),
        jira_adapter=StubJiraAdapter(story=story),
        rag_store=StubRagStore(),
        test_type_router=TestTypeRouter(),
        testgen_prompt_builder=TestGenPromptBuilder(),
        tone_checker=NullToneChecker(),
        testgen_normalizer=TestCasePackNormalizer(),
    )


def _make_request() -> GenerationRequest:
    return GenerationRequest(
        tenant_id="t1",
        application_id="app1",
        prompt="Generate tests for the login page",
        target=GenerationTarget(
            language=Language.TYPESCRIPT,
            framework=Framework.PLAYWRIGHT,
            pattern=AutomationPattern.POM,
            locator_strategy=LocatorStrategy.PAGE_FILE,
        ),
        scope=GenerationScope(domain="auth", route="/login"),
        options=GenerationOptions(validate=False, max_input_tokens=12_000),
        jira_key="AUTH-1",
        test_types=[TestType.FUNCTIONAL, TestType.NEGATIVE],
    )


class TestTestgenEndToEnd:
    def test_result_status_is_completed(self, tmp_path: Path) -> None:
        orchestrator = _make_orchestrator(tmp_path)
        result = orchestrator.generate(_make_request())
        assert result.status == GenerationStatus.COMPLETED

    def test_test_case_pack_is_populated(self, tmp_path: Path) -> None:
        orchestrator = _make_orchestrator(tmp_path)
        result = orchestrator.generate(_make_request())
        assert result.test_case_pack is not None

    def test_test_case_pack_has_correct_summary(self, tmp_path: Path) -> None:
        orchestrator = _make_orchestrator(tmp_path)
        result = orchestrator.generate(_make_request())
        assert result.test_case_pack.story_summary == "User can log in to the application"

    def test_test_case_pack_has_expected_test_cases(self, tmp_path: Path) -> None:
        orchestrator = _make_orchestrator(tmp_path)
        result = orchestrator.generate(_make_request())
        ids = [tc.id for tc in result.test_case_pack.test_cases]
        assert "TC-001" in ids
        assert "TC-002" in ids

    def test_result_has_no_errors(self, tmp_path: Path) -> None:
        orchestrator = _make_orchestrator(tmp_path)
        result = orchestrator.generate(_make_request())
        assert result.errors == []

    def test_legacy_path_still_works_without_jira_key(self, tmp_path: Path) -> None:
        orchestrator = _make_orchestrator(tmp_path)
        request = GenerationRequest(
            tenant_id="t1",
            application_id="app1",
            prompt="Generate a page object",
            target=GenerationTarget(
                language=Language.TYPESCRIPT,
                framework=Framework.PLAYWRIGHT,
                pattern=AutomationPattern.POM,
                locator_strategy=LocatorStrategy.PAGE_FILE,
            ),
            scope=GenerationScope(domain="checkout"),
            options=GenerationOptions(validate=False, max_input_tokens=12_000),
        )
        result = orchestrator.generate(request)
        # Legacy path: test_case_pack should be None
        assert result.test_case_pack is None
