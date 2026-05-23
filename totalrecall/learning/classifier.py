"""Classify extracted patterns into LearningDiscoveryType."""

from totalrecall.learning.models import LearningDiscoveryType
from totalrecall.learning.parser import ExtractedPattern

_TYPE_MAP: dict[str, LearningDiscoveryType] = {
    "page_object_class": LearningDiscoveryType.STATIC_SKILL_CANDIDATE,
    "fixture_function": LearningDiscoveryType.DYNAMIC_MEMORY,
    "test_function": LearningDiscoveryType.CATALOGUE_REFERENCE,
    "utility_class": LearningDiscoveryType.CATALOGUE_REFERENCE,
}


def classify(pattern: ExtractedPattern) -> LearningDiscoveryType:
    return _TYPE_MAP.get(pattern.pattern_type, LearningDiscoveryType.CATALOGUE_REFERENCE)
