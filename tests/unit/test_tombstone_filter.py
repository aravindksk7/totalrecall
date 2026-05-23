from totalrecall.memory.models import MemoryEntry
from totalrecall.memory.tombstone import TombstoneFilter


def _entry(entity_id: str, tenant_id: str = "t1", application_id: str = "app1") -> MemoryEntry:
    return MemoryEntry(
        entity_id=entity_id,
        tenant_id=tenant_id,
        application_id=application_id,
        summary="summary",
        knowledge="knowledge",
    )


def test_new_filter_has_zero_count() -> None:
    f = TombstoneFilter()
    assert f.count == 0


def test_add_marks_entry_as_tombstoned() -> None:
    f = TombstoneFilter()
    f.add("t1", "app1", "mem_001")
    assert f.is_tombstoned("t1", "app1", "mem_001") is True


def test_is_tombstoned_returns_false_for_unknown_entry() -> None:
    f = TombstoneFilter()
    assert f.is_tombstoned("t1", "app1", "mem_999") is False


def test_remove_clears_tombstone() -> None:
    f = TombstoneFilter()
    f.add("t1", "app1", "mem_001")
    f.remove("t1", "app1", "mem_001")
    assert f.is_tombstoned("t1", "app1", "mem_001") is False


def test_remove_is_idempotent_for_unknown_entry() -> None:
    f = TombstoneFilter()
    f.remove("t1", "app1", "mem_missing")  # must not raise
    assert f.count == 0


def test_tombstone_is_scoped_by_tenant() -> None:
    f = TombstoneFilter()
    f.add("t1", "app1", "mem_001")
    assert f.is_tombstoned("t2", "app1", "mem_001") is False


def test_tombstone_is_scoped_by_application() -> None:
    f = TombstoneFilter()
    f.add("t1", "app1", "mem_001")
    assert f.is_tombstoned("t1", "app2", "mem_001") is False


def test_filter_entries_excludes_tombstoned_entries() -> None:
    f = TombstoneFilter()
    f.add("t1", "app1", "mem_bad")

    entries = [_entry("mem_good"), _entry("mem_bad")]
    result = f.filter_entries(entries)

    assert [e.entity_id for e in result] == ["mem_good"]


def test_filter_entries_returns_all_when_none_tombstoned() -> None:
    f = TombstoneFilter()
    entries = [_entry("mem_a"), _entry("mem_b")]
    result = f.filter_entries(entries)
    assert len(result) == 2


def test_filter_entries_returns_empty_list_when_all_tombstoned() -> None:
    f = TombstoneFilter()
    f.add("t1", "app1", "mem_a")
    f.add("t1", "app1", "mem_b")

    result = f.filter_entries([_entry("mem_a"), _entry("mem_b")])
    assert result == []


def test_load_bulk_adds_multiple_tombstones() -> None:
    f = TombstoneFilter()
    f.load_bulk([("t1", "app1", "mem_001"), ("t1", "app1", "mem_002")])

    assert f.is_tombstoned("t1", "app1", "mem_001") is True
    assert f.is_tombstoned("t1", "app1", "mem_002") is True
    assert f.count == 2


def test_load_bulk_is_additive() -> None:
    f = TombstoneFilter()
    f.add("t1", "app1", "mem_pre")
    f.load_bulk([("t1", "app1", "mem_bulk")])

    assert f.is_tombstoned("t1", "app1", "mem_pre") is True
    assert f.is_tombstoned("t1", "app1", "mem_bulk") is True
    assert f.count == 2


def test_count_reflects_unique_entries() -> None:
    f = TombstoneFilter()
    f.add("t1", "app1", "mem_001")
    f.add("t1", "app1", "mem_001")  # duplicate
    f.add("t1", "app1", "mem_002")
    assert f.count == 2
