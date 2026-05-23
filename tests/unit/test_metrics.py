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
    m.record_generation(completed=True, input_tokens=100, output_tokens=50)
    snap = m.snapshot()
    assert snap["generations_total"] == 1
    assert snap["generations_completed"] == 1
    assert snap["generations_failed"] == 0
    assert snap["input_tokens_total"] == 100
    assert snap["output_tokens_total"] == 50


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
