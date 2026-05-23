"""Prompt builder: assembles token-minimized generation payloads from a ContextPlan."""

import json

from totalrecall.context.models import ContextPlan
from totalrecall.generation.models import GenerationRequest
from totalrecall.memory.models import MemoryGetRequest
from totalrecall.memory.wrapper.service import MemoryWrapper
from totalrecall.providers.models import ProviderMessage, ProviderRole
from totalrecall.skills.registry import SkillRegistry

_ARTIFACT_SCHEMA = {
    "type": "object",
    "required": ["artifacts"],
    "properties": {
        "artifacts": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["path", "artifact_type", "language", "content"],
                "properties": {
                    "path": {"type": "string"},
                    "artifact_type": {"type": "string"},
                    "language": {"type": "string"},
                    "content": {"type": "string"},
                },
            },
        }
    },
}

_ROLE_INTRO = (
    "You are TotalRecall, an expert test automation code generator. "
    "Your task is to generate clean, maintainable test automation artifacts "
    "that follow the project's established patterns and conventions."
)

_OUTPUT_INSTRUCTION = (
    "Respond ONLY with a valid JSON object matching this schema:\n"
    f"{json.dumps(_ARTIFACT_SCHEMA, indent=2)}\n\n"
    "Do not include explanations, markdown fences, or any text outside the JSON object."
)


class PromptBuilder:
    """Builds provider messages from a GenerationRequest and its ContextPlan."""

    def __init__(self, skill_registry: SkillRegistry, memory_wrapper: MemoryWrapper) -> None:
        self._skills = skill_registry
        self._memory = memory_wrapper

    def build(self, request: GenerationRequest, plan: ContextPlan) -> list[ProviderMessage]:
        system_content = self._build_system(request, plan)
        user_content = self._build_user(request, plan)
        return [
            ProviderMessage(role=ProviderRole.SYSTEM, content=system_content),
            ProviderMessage(role=ProviderRole.USER, content=user_content),
        ]

    def _build_system(self, request: GenerationRequest, plan: ContextPlan) -> str:
        parts: list[str] = [_ROLE_INTRO, ""]

        # Stack context from selected skills
        for selected in plan.selected_skills:
            try:
                skill = self._skills.get(selected.skill_id)
            except Exception:
                continue
            parts.append(f"## Framework: {skill.framework} / {skill.language}")
            parts.append(f"Pattern: {skill.pattern}")
            if skill.generation_rules:
                parts.append("### Generation Rules")
                for rule in skill.generation_rules:
                    parts.append(f"- {rule}")
            parts.append("")

        # RAG guidance from knowledge base (top chunks)
        if plan.rag_chunks:
            parts.append("## Testing Guidance from Knowledge Base")
            for chunk in plan.rag_chunks[:3]:
                chunk_text = getattr(chunk, "chunk_text", str(chunk))
                parts.append(chunk_text)
                parts.append("")

        # Output format
        parts.append("## Output Format")
        parts.append(_OUTPUT_INSTRUCTION)

        return "\n".join(parts)

    def _build_user(self, request: GenerationRequest, plan: ContextPlan) -> str:
        parts: list[str] = []

        # JIRA story context (prepended when available)
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
                    parts.append(f"- {ac.text}")
            parts.append("")

        # Relevant memories
        memory_texts: list[str] = []
        for selected in plan.selected_memories:
            try:
                entry = self._memory.get(
                    MemoryGetRequest(
                        tenant_id=request.tenant_id,
                        application_id=request.application_id,
                        entity_id=selected.memory_id,
                    )
                )
            except Exception:
                continue
            if entry is not None:
                memory_texts.append(f"- {entry.summary}: {entry.knowledge}")

        if memory_texts:
            parts.append("## Project Context")
            parts.extend(memory_texts)
            parts.append("")

        # Scope
        parts.append("## Scope")
        parts.append(f"Domain: {request.scope.domain}")
        if request.scope.route:
            parts.append(f"Route: {request.scope.route}")
        if request.scope.tags:
            parts.append(f"Tags: {', '.join(request.scope.tags)}")
        parts.append("")

        # User intent
        parts.append("## Request")
        parts.append(request.prompt)

        return "\n".join(parts)

    @staticmethod
    def artifact_schema() -> dict:
        """Return the machine-parseable JSON artifact response schema."""
        return _ARTIFACT_SCHEMA
