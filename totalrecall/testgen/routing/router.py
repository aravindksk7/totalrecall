"""TestTypeRouter: determines which test types to generate."""

from totalrecall.testgen.models import TestType

_DEFAULT_TEST_TYPES = [TestType.FUNCTIONAL, TestType.NEGATIVE, TestType.EDGE_CASE]


class TestTypeRouter:
    """Routes a generation request to the appropriate test types.

    Priority: request.test_types (explicit) > intent.test_types (reformulated) > defaults.
    """

    def route(self, intent, request) -> list[TestType]:
        if request.test_types:
            return list(request.test_types)
        if intent is not None and intent.test_types:
            return list(intent.test_types)
        return list(_DEFAULT_TEST_TYPES)
