"""Metadata extractor: derives structured metadata from a raw GenerationRequest.

Responsibilities:
- Normalise domain (lowercase, strip whitespace)
- Normalise route (ensure leading slash, strip trailing slash)
- Extract test-intent keywords from the free-text prompt using regex patterns
- Resolve and validate the target stack (language/framework/pattern/locator)
- Emit non-fatal warnings for unknown combinations
"""

import re

from totalrecall.generation.models import Framework, GenerationRequest, GenerationTarget, Language
from totalrecall.metadata.models import RequestMetadata, TargetStackResolution

_KNOWN_COMBINATIONS: frozenset[tuple[Language, Framework]] = frozenset(
    {
        (Language.TYPESCRIPT, Framework.PLAYWRIGHT),
        (Language.PYTHON, Framework.PYTEST),
        (Language.JAVA, Framework.JUNIT),
        (Language.JAVA, Framework.TESTNG),
    }
)

# Each entry is a compiled pattern + the canonical keyword to emit when it matches.
_INTENT_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(log(?:ging)?[- ]?in|sign(?:ing)?[ -]?in|authenticate|auth(?:entication)?)\b"), "login"),
    (re.compile(r"\b(log(?:ging)?[- ]?out|sign(?:ing)?[ -]?out)\b"), "logout"),
    (re.compile(r"\b(register|sign(?:ing)?[ -]?up|creat[e]?\s+account)\b"), "registration"),
    (re.compile(r"\b(search|filter|sort|find|lookup)\b"), "search"),
    (re.compile(r"\b(checkout|payment|billing|pay)\b"), "checkout"),
    (re.compile(r"\b(cart|basket|shopping)\b"), "cart"),
    (re.compile(r"\b(order|purchase|buy)\b"), "order"),
    (re.compile(r"\b(upload|download|import|export)\b"), "file_transfer"),
    (re.compile(r"\b(creat[e]?|add|new|submit)\b"), "create"),
    (re.compile(r"\b(edit|updat[e]?|modif[y]?|chang[e]?)\b"), "update"),
    (re.compile(r"\b(delet[e]?|remov[e]?)\b"), "delete"),
    (re.compile(r"\b(navig[a]?t[e]?|redirect|go\s+to)\b"), "navigation"),
    (re.compile(r"\b(verif[y]?|validat[e]?|assert|confirm|check)\b"), "validation"),
    (re.compile(r"\b(profile|account|settings|preferences)\b"), "profile"),
    (re.compile(r"\b(dashboard|overview|home|landing)\b"), "dashboard"),
    (re.compile(r"\b(list|table|grid|paginate?|pagination)\b"), "listing"),
    (re.compile(r"\b(modal|dialog|popup|overlay)\b"), "modal"),
    (re.compile(r"\b(notification|alert|message|toast)\b"), "notification"),
]


class MetadataExtractor:
    """Extracts structured metadata from a GenerationRequest without calling an LLM."""

    def extract(self, request: GenerationRequest) -> RequestMetadata:
        domain = request.scope.domain.strip().lower()
        route = _normalize_route(request.scope.route)
        test_intent = _extract_intent(request.prompt)
        target_stack, warnings = _resolve_target_stack(request.target)

        return RequestMetadata(
            domain=domain,
            route=route,
            test_intent=test_intent,
            target_stack=target_stack,
            warnings=warnings,
        )


def _normalize_route(route: str | None) -> str | None:
    if not route:
        return None
    route = route.strip()
    if not route:
        return None
    if not route.startswith("/"):
        route = "/" + route
    # Preserve root "/" but strip trailing slashes on deeper paths
    if route != "/":
        route = route.rstrip("/")
    return route


def _extract_intent(prompt: str) -> list[str]:
    text = prompt.lower()
    found: set[str] = set()
    for pattern, keyword in _INTENT_RULES:
        if pattern.search(text):
            found.add(keyword)
    return sorted(found)


def _resolve_target_stack(
    target: GenerationTarget,
) -> tuple[TargetStackResolution, list[str]]:
    combo = (target.language, target.framework)
    is_known = combo in _KNOWN_COMBINATIONS
    warnings: list[str] = []
    if not is_known:
        warnings.append(
            f"Unknown language/framework combination: {target.language}/{target.framework}. "
            "No matching skill may be available."
        )
    return TargetStackResolution(
        language=target.language,
        framework=target.framework,
        pattern=target.pattern,
        locator_strategy=target.locator_strategy,
        is_known_combination=is_known,
    ), warnings
