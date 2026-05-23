"""Unit tests for in-process GenerationMetrics counters."""

from totalrecall.observability.metrics import GenerationMetrics


def test_initial_counters_are_zero() -> None:
    m = GenerationMetrics()
    snap = m.snapshot()
    assert snap["generations_total"] == 0
    assert snap["generations_completed"] == 0
    assert snap["generations_failed"] == 0


def test_record_completed_generation() -> None:
    m = GenerationMetrics()
    m.record_generation(
        completed=True,
        input_tokens=100,
        output_tokens=50,
        estimated_tokens_saved=25,
        context_plan_id="plan_1",
        baseline_input_tokens=125,
        selected_skill_count=1,
        selected_memory_count=2,
        excluded_memory_count=3,
        max_input_tokens=1000,
    )
    snap = m.snapshot()
    assert snap["generations_total"] == 1
    assert snap["generations_completed"] == 1
    assert snap["generations_failed"] == 0
    assert snap["input_tokens_total"] == 100
    assert snap["output_tokens_total"] == 50
    assert snap["estimated_tokens_saved_total"] == 25
    assert snap["last_context_plan_id"] == "plan_1"
    assert snap["last_token_savings_percent"] == 20.0
    assert snap["last_selected_skill_count"] == 1
    assert snap["last_selected_memory_count"] == 2
    assert snap["last_excluded_memory_count"] == 3
    assert snap["last_max_input_tokens"] == 1000


def test_record_failed_generation() -> None:
    m = GenerationMetrics()
    m.record_generation(completed=False)
    snap = m.snapshot()
    assert snap["generations_total"] == 1
    assert snap["generations_failed"] == 1
    assert snap["generations_completed"] == 0


def test_record_repaired_generation() -> None:
    m = GenerationMetrics()
    m.record_generation(completed=True, repaired=True)
    snap = m.snapshot()
    assert snap["generations_repaired"] == 1


def test_record_validation_passed() -> None:
    m = GenerationMetrics()
    m.record_validation(status="passed")
    snap = m.snapshot()
    assert snap["validation_passed"] == 1
    assert snap["validation_failed"] == 0


def test_record_validation_failed() -> None:
    m = GenerationMetrics()
    m.record_validation(status="failed")
    snap = m.snapshot()
    assert snap["validation_failed"] == 1
    assert snap["validation_passed"] == 0


def test_record_validation_not_run() -> None:
    m = GenerationMetrics()
    m.record_validation(status="not_run")
    snap = m.snapshot()
    assert snap["validation_not_run"] == 1


def test_multiple_generations_accumulate() -> None:
    m = GenerationMetrics()
    for _ in range(3):
        m.record_generation(completed=True, input_tokens=100)
    m.record_generation(completed=False)
    snap = m.snapshot()
    assert snap["generations_total"] == 4
    assert snap["generations_completed"] == 3
    assert snap["generations_failed"] == 1
    assert snap["input_tokens_total"] == 300


def test_snapshot_returns_copy_not_live_reference() -> None:
    m = GenerationMetrics()
    snap1 = m.snapshot()
    m.record_generation(completed=True)
    snap2 = m.snapshot()
    assert snap1["generations_total"] == 0
    assert snap2["generations_total"] == 1
