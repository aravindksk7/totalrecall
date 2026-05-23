"""Resolved metadata derived from a GenerationRequest."""

from pydantic import Field

from totalrecall.contracts import ContractModel
from totalrecall.generation.models import AutomationPattern, Framework, Language, LocatorStrategy


class TargetStackResolution(ContractModel):
    language: Language
    framework: Framework
    pattern: AutomationPattern
    locator_strategy: LocatorStrategy
    is_known_combination: bool


class RequestMetadata(ContractModel):
    """Structured metadata extracted from a GenerationRequest."""

    domain: str = Field(min_length=1)
    route: str | None = None
    test_intent: list[str] = Field(default_factory=list)
    target_stack: TargetStackResolution
    warnings: list[str] = Field(default_factory=list)
