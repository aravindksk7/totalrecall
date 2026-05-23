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

    def record_generation(
        self,
        *,
        completed: bool,
        repaired: bool = False,
        input_tokens: int = 0,
        output_tokens: int = 0,
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
            }
