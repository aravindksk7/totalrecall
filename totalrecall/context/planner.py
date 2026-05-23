import uuid
from dataclasses import dataclass, field
from typing import Any

from totalrecall.context.models import (
    ContextExclusion,
    ContextExclusionReason,
    ContextPlan,
    SelectedMemory,
    SelectedSkill,
    TokenBudget,
)
from totalrecall.generation.models import GenerationRequest
from totalrecall.memory.models import MemorySearchRequest
from totalrecall.memory.wrapper.service import MemoryWrapper
from totalrecall.metadata.extractor import MetadataExtractor
from totalrecall.metadata.models import RequestMetadata
from totalrecall.skills.registry import SkillRegistry


@dataclass
class ExternalPlanInputs:
    """Optional external data (JIRA story, RAG chunks) to inject into a ContextPlan."""

    jira_story: Any = None
    rag_chunks: list[Any] = field(default_factory=list)


_TOKENS_PER_RULE = 20
_TOKENS_PER_MEMORY = 60
_SYSTEM_OVERHEAD_TOKENS = 300


class ContextPlanner:
    """Assembles a ContextPlan from skill selection and memory search without calling an LLM."""

    def __init__(
        self,
        skill_registry: SkillRegistry,
        memory_wrapper: MemoryWrapper,
        metadata_extractor: MetadataExtractor | None = None,
    ) -> None:
        self._skills = skill_registry
        self._memory = memory_wrapper
        self._extractor = metadata_extractor or MetadataExtractor()

    def plan(
        self,
        request: GenerationRequest,
        request_id: str,
        plan_inputs: ExternalPlanInputs | None = None,
    ) -> ContextPlan:
        budget = TokenBudget(
            max_input_tokens=request.options.max_input_tokens,
            estimated_input_tokens=0,
            baseline_estimate=0,
            estimated_tokens_saved=0,
        )

        metadata = self._extractor.extract(request)
        selected_skills, skill_exclusions, skill_tokens = self._select_skills(request)
        remaining = request.options.max_input_tokens - _SYSTEM_OVERHEAD_TOKENS - skill_tokens

        selected_memories, memory_exclusions, memory_tokens = self._select_memories(
            request, metadata, remaining
        )

        prompt_tokens = len(request.prompt.split())
        optimized = _SYSTEM_OVERHEAD_TOKENS + prompt_tokens + skill_tokens + memory_tokens
        candidate_memory_tokens = memory_tokens + (len(memory_exclusions) * _TOKENS_PER_MEMORY)
        baseline = _SYSTEM_OVERHEAD_TOKENS + prompt_tokens + skill_tokens + candidate_memory_tokens
        saved = max(0, baseline - optimized)

        budget = TokenBudget(
            max_input_tokens=request.options.max_input_tokens,
            estimated_input_tokens=optimized,
            baseline_estimate=baseline,
            estimated_tokens_saved=saved,
        )

        return ContextPlan(
            context_plan_id=str(uuid.uuid4()),
            tenant_id=request.tenant_id,
            application_id=request.application_id,
            request_id=request_id,
            selected_skills=selected_skills,
            selected_memories=selected_memories,
            skill_ids=[s.skill_id for s in selected_skills],
            memory_ids=[m.memory_id for m in selected_memories],
            excluded=skill_exclusions + memory_exclusions,
            token_budget=budget,
            jira_story=plan_inputs.jira_story if plan_inputs else None,
            rag_chunks=plan_inputs.rag_chunks if plan_inputs else [],
        )

    def _select_skills(
        self, request: GenerationRequest
    ) -> tuple[list[SelectedSkill], list[ContextExclusion], int]:
        skill = self._skills.select(request.target.language, request.target.framework)
        if skill is None:
            exclusion = ContextExclusion(
                entity_id=f"{request.target.framework}:{request.target.language}",
                reason=ContextExclusionReason.FRAMEWORK_MISMATCH,
                details={
                    "language": request.target.language,
                    "framework": request.target.framework,
                },
            )
            return [], [exclusion], 0

        token_cost = len(skill.generation_rules) * _TOKENS_PER_RULE
        selected = SelectedSkill(
            skill_id=skill.skill_id,
            version=skill.version,
            reason=f"Matched {skill.framework}/{skill.language}",
        )
        return [selected], [], token_cost

    def _select_memories(
        self,
        request: GenerationRequest,
        metadata: RequestMetadata,
        token_budget: int,
    ) -> tuple[list[SelectedMemory], list[ContextExclusion], int]:
        filters: dict[str, str] = {"domain": metadata.domain}
        if metadata.route:
            filters["route"] = metadata.route

        # Enrich search query with extracted intent keywords for better relevance
        query_parts = [request.prompt] + metadata.test_intent
        enriched_query = " ".join(query_parts)

        try:
            result = self._memory.search(
                MemorySearchRequest(
                    tenant_id=request.tenant_id,
                    application_id=request.application_id,
                    query=enriched_query,
                    filters=filters,
                )
            )
        except Exception:
            return [], [], 0

        selected: list[SelectedMemory] = []
        exclusions: list[ContextExclusion] = []
        tokens_used = 0

        for entry in result.items:
            cost = _TOKENS_PER_MEMORY
            if tokens_used + cost > token_budget:
                exclusions.append(
                    ContextExclusion(
                        entity_id=entry.entity_id,
                        reason=ContextExclusionReason.TOKEN_BUDGET,
                        details={"tokens_used": tokens_used, "cost": cost, "budget": token_budget},
                    )
                )
                continue
            selected.append(
                SelectedMemory(
                    memory_id=entry.entity_id,
                    confidence=1.0,
                    reason="domain/route match",
                )
            )
            tokens_used += cost

        return selected, exclusions, tokens_used
