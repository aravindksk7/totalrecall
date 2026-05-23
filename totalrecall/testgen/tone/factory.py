"""Factory for building the tone checker from feature flags."""

from totalrecall.testgen.tone.checker import NullToneChecker, ToneCheckAdapter


def build_tone_checker(feature_flags, gateway=None) -> ToneCheckAdapter:
    """Return the appropriate tone checker based on feature flags.

    Flag: tone_check.enabled (bool) — when False, returns NullToneChecker.
    """
    if not feature_flags.get("tone_check.enabled", False):
        return NullToneChecker()

    if gateway is None:
        return NullToneChecker()

    from totalrecall.testgen.tone.checker import LLMToneChecker

    return LLMToneChecker(gateway=gateway)
