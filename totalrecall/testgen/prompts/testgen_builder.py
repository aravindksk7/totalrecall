"""TestGenPromptBuilder: assembles test case generation prompts."""

import json

from totalrecall.context.models import ContextPlan
from totalrecall.generation.models import GenerationRequest
from totalrecall.providers.models import ProviderMessage, ProviderRole
from totalrecall.testgen.models import TestType
from totalrecall.testgen.prompts.templates import _SECTION_BUILDERS, _TEST_CASE_PACK_SCHEMA

_ROLE_INTRO = (
    "You are TotalRecall, an expert QA engineer specializing in test case design. "
    "Your task is to produce comprehensive, structured test cases from the provided story and requirements."
)

_OUTPUT_INSTRUCTION = (
    "Respond ONLY with a valid JSON object matching this schema:\n"
    f"{json.dumps(_TEST_CASE_PACK_SCHEMA, indent=2)}\n\n"
    "Do not include explanations, markdown fences, or any text outside the JSON object."
)


class TestGenPromptBuilder:
    """Builds provider messages for the testgen path (JIRA story → test case pack)."""

    def build(
        self,
        request: GenerationRequest,
        plan: ContextPlan,
        intent,
        active_test_types: list[TestType],
    ) -> list[ProviderMessage]:
        system_content = self._build_system(active_test_types)
        user_content = self._build_user(request, plan, intent, active_test_types)
        return [
            ProviderMessage(role=ProviderRole.SYSTEM, content=system_content),
            ProviderMessage(role=ProviderRole.USER, content=user_content),
        ]

    def _build_system(self, active_test_types: list[TestType]) -> str:
        parts: list[str] = [_ROLE_INTRO, ""]
        parts.append(f"## Requested Test Types: {', '.join(t.value for t in active_test_types)}")
        parts.append("")
        parts.append("## Output Format")
        parts.append(_OUTPUT_INSTRUCTION)
        return "\n".join(parts)

    def _build_user(
        self,
        request: GenerationRequest,
        plan: ContextPlan,
        intent,
        active_test_types: list[TestType],
    ) -> str:
        parts: list[str] = []

        # JIRA story context
        if plan.jira_story is not None:
            story = plan.jira_story
            parts.append("## JIRA Story")
            parts.append(f"Key: {story.jira_key}")
            parts.append(f"Summary: {story.summary}")
            if story.description:
                parts.append(f"Description: {story.description}")
            if story.acceptance_criteria:
                parts.append("### Acceptance Criteria")
                for ac in story.acceptance_criteria:
                    parts.append(f"- [{ac.index}] {ac.text}")
            parts.append("")

        # RAG guidance (top-3 chunks)
        if plan.rag_chunks:
            parts.append("## Testing Guidance from Knowledge Base")
            for chunk in plan.rag_chunks[:3]:
                chunk_text = getattr(chunk, "chunk_text", str(chunk))
                parts.append(chunk_text)
                parts.append("")

        # Reformulated intent summary
        if intent is not None and intent.intent_summary:
            parts.append("## Test Intent")
            parts.append(intent.intent_summary)
            parts.append("")

        # Per-type sections
        for test_type in active_test_types:
            builder_fn = _SECTION_BUILDERS.get(test_type)
            if builder_fn:
                parts.append(builder_fn(plan.jira_story, plan.rag_chunks))
                parts.append("")

        # User's original prompt
        parts.append("## Additional Requirements")
        parts.append(request.prompt)

        return "\n".join(parts)
