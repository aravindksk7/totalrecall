"""Unit tests for MetadataExtractor."""

import pytest

from totalrecall.generation.models import (
    AutomationPattern,
    Framework,
    GenerationOptions,
    GenerationRequest,
    GenerationScope,
    GenerationTarget,
    Language,
    LocatorStrategy,
    ProviderSelection,
)
from totalrecall.metadata.extractor import MetadataExtractor, _normalize_route


def _request(
    prompt: str = "Generate a page object",
    domain: str = "auth",
    route: str | None = None,
    language: Language = Language.TYPESCRIPT,
    framework: Framework = Framework.PLAYWRIGHT,
) -> GenerationRequest:
    return GenerationRequest(
        tenant_id="tenant_test",
        application_id="app_test",
        prompt=prompt,
        target=GenerationTarget(
            language=language,
            framework=framework,
            pattern=AutomationPattern.POM,
            locator_strategy=LocatorStrategy.PAGE_FILE,
        ),
        scope=GenerationScope(domain=domain, route=route),
        provider=ProviderSelection(),
        options=GenerationOptions(validate=True),
    )


@pytest.fixture()
def extractor() -> MetadataExtractor:
    return MetadataExtractor()


# --- domain normalisation ---

def test_domain_is_lowercased(extractor: MetadataExtractor) -> None:
    m = extractor.extract(_request(domain="Auth"))
    assert m.domain == "auth"


def test_domain_strips_whitespace(extractor: MetadataExtractor) -> None:
    m = extractor.extract(_request(domain="  checkout  "))
    assert m.domain == "checkout"


# --- route normalisation ---

def test_route_none_stays_none(extractor: MetadataExtractor) -> None:
    m = extractor.extract(_request(route=None))
    assert m.route is None


def test_route_gets_leading_slash(extractor: MetadataExtractor) -> None:
    m = extractor.extract(_request(route="login"))
    assert m.route == "/login"


def test_route_trailing_slash_stripped(extractor: MetadataExtractor) -> None:
    m = extractor.extract(_request(route="/login/"))
    assert m.route == "/login"


def test_route_root_preserved(extractor: MetadataExtractor) -> None:
    assert _normalize_route("/") == "/"


def test_route_already_correct_unchanged(extractor: MetadataExtractor) -> None:
    m = extractor.extract(_request(route="/auth/login"))
    assert m.route == "/auth/login"


# --- test intent extraction ---

def test_no_keywords_gives_empty_intent(extractor: MetadataExtractor) -> None:
    m = extractor.extract(_request(prompt="Generate a page object for the application"))
    assert m.test_intent == []


def test_login_keyword_detected(extractor: MetadataExtractor) -> None:
    m = extractor.extract(_request(prompt="Create a page object for the login page"))
    assert "login" in m.test_intent


def test_sign_in_maps_to_login(extractor: MetadataExtractor) -> None:
    m = extractor.extract(_request(prompt="Page for signing in to the system"))
    assert "login" in m.test_intent


def test_checkout_keyword_detected(extractor: MetadataExtractor) -> None:
    m = extractor.extract(_request(prompt="Generate checkout payment page object"))
    assert "checkout" in m.test_intent


def test_search_keyword_detected(extractor: MetadataExtractor) -> None:
    m = extractor.extract(_request(prompt="Page object for search and filter results"))
    assert "search" in m.test_intent


def test_multiple_intents_extracted(extractor: MetadataExtractor) -> None:
    m = extractor.extract(
        _request(prompt="Login and then navigate to checkout to submit order")
    )
    intents = m.test_intent
    assert "login" in intents
    assert "checkout" in intents
    assert "navigation" in intents
    assert "order" in intents


def test_intent_list_is_sorted(extractor: MetadataExtractor) -> None:
    m = extractor.extract(_request(prompt="validate and create and update and delete items"))
    assert m.test_intent == sorted(m.test_intent)


def test_validation_keyword_detected(extractor: MetadataExtractor) -> None:
    m = extractor.extract(_request(prompt="Verify and validate the form submission"))
    assert "validation" in m.test_intent


# --- target stack resolution ---

def test_known_combination_has_no_warnings(extractor: MetadataExtractor) -> None:
    m = extractor.extract(_request(language=Language.TYPESCRIPT, framework=Framework.PLAYWRIGHT))
    assert m.target_stack.is_known_combination is True
    assert m.warnings == []


def test_python_pytest_is_known(extractor: MetadataExtractor) -> None:
    m = extractor.extract(_request(language=Language.PYTHON, framework=Framework.PYTEST))
    assert m.target_stack.is_known_combination is True


def test_unknown_combination_emits_warning(extractor: MetadataExtractor) -> None:
    m = extractor.extract(_request(language=Language.TYPESCRIPT, framework=Framework.PYTEST))
    assert m.target_stack.is_known_combination is False
    assert len(m.warnings) == 1
    assert "typescript/pytest" in m.warnings[0]


def test_target_stack_preserves_pattern_and_locator(extractor: MetadataExtractor) -> None:
    m = extractor.extract(_request())
    assert m.target_stack.pattern == AutomationPattern.POM
    assert m.target_stack.locator_strategy == LocatorStrategy.PAGE_FILE
