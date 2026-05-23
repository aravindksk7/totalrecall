"""In-process generation metrics counters.

Tracks counts and cumulative totals across the lifetime of the process.
Exposed via GET /v1/metrics for health dashboards and alerting.
"""

import threading
from dataclasses import dataclass, field


@dataclass
class GenerationMetrics:
    """Thread-safe counters for generation pipeline activity."""

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    generations_total: int = 0
    generations_completed: int = 0
    generations_failed: int = 0
    generations_repaired: int = 0

    validation_passed: int = 0
    validation_failed: int = 0
    validation_not_run: int = 0

    input_tokens_total: int = 0
    output_tokens_total: int = 0
    estimated_tokens_saved_total: int = 0

    last_context_plan_id: str | None = None
    last_estimated_input_tokens: int = 0
    last_baseline_input_tokens: int = 0
    last_estimated_tokens_saved: int = 0
    last_token_savings_percent: float = 0.0
    last_selected_skill_count: int = 0
    last_selected_memory_count: int = 0
    last_excluded_memory_count: int = 0
    last_max_input_tokens: int = 0

    def record_generation(
        self,
        *,
        completed: bool,
        repaired: bool = False,
        input_tokens: int = 0,
        output_tokens: int = 0,
        estimated_tokens_saved: int = 0,
        context_plan_id: str | None = None,
        baseline_input_tokens: int = 0,
        selected_skill_count: int = 0,
        selected_memory_count: int = 0,
        excluded_memory_count: int = 0,
        max_input_tokens: int = 0,
    ) -> None:
        with self._lock:
            self.generations_total += 1
            if completed:
                self.generations_completed += 1
            else:
                self.generations_failed += 1
            if repaired:
                self.generations_repaired += 1
            self.input_tokens_total += input_tokens
            self.output_tokens_total += output_tokens
            self.estimated_tokens_saved_total += estimated_tokens_saved

            self.last_context_plan_id = context_plan_id
            self.last_estimated_input_tokens = input_tokens
            self.last_baseline_input_tokens = baseline_input_tokens
            self.last_estimated_tokens_saved = estimated_tokens_saved
            self.last_token_savings_percent = (
                round((estimated_tokens_saved / baseline_input_tokens) * 100, 2)
                if baseline_input_tokens
                else 0.0
            )
            self.last_selected_skill_count = selected_skill_count
            self.last_selected_memory_count = selected_memory_count
            self.last_excluded_memory_count = excluded_memory_count
            self.last_max_input_tokens = max_input_tokens

    def record_validation(self, *, status: str) -> None:
        with self._lock:
            if status == "passed":
                self.validation_passed += 1
            elif status == "failed":
                self.validation_failed += 1
            else:
                self.validation_not_run += 1

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "generations_total": self.generations_total,
                "generations_completed": self.generations_completed,
                "generations_failed": self.generations_failed,
                "generations_repaired": self.generations_repaired,
                "validation_passed": self.validation_passed,
                "validation_failed": self.validation_failed,
                "validation_not_run": self.validation_not_run,
                "input_tokens_total": self.input_tokens_total,
                "output_tokens_total": self.output_tokens_total,
                "estimated_tokens_saved_total": self.estimated_tokens_saved_total,
                "last_context_plan_id": self.last_context_plan_id,
                "last_estimated_input_tokens": self.last_estimated_input_tokens,
                "last_baseline_input_tokens": self.last_baseline_input_tokens,
                "last_estimated_tokens_saved": self.last_estimated_tokens_saved,
                "last_token_savings_percent": self.last_token_savings_percent,
                "last_selected_skill_count": self.last_selected_skill_count,
                "last_selected_memory_count": self.last_selected_memory_count,
                "last_excluded_memory_count": self.last_excluded_memory_count,
                "last_max_input_tokens": self.last_max_input_tokens,
            }
