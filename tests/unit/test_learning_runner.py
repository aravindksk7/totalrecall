"""Unit tests for the learning runner orchestrator."""

import textwrap
from pathlib import Path

from totalrecall.learning.models import (
    LearningDeltaState,
    LearningRunStatus,
    LearningScope,
    LearningTriggerType,
)
from totalrecall.learning.runner import run_learning


def _scope(path: str) -> LearningScope:
    return LearningScope(repository="local", branch="main", path=path)


def test_run_learning_fails_gracefully_for_missing_path() -> None:
    report = run_learning(
        tenant_id="t1",
        application_id="app1",
        scope=_scope("/nonexistent/path/abc123"),
        previous_hashes={},
    )

    assert report.run.status == LearningRunStatus.FAILED
    assert len(report.warnings) > 0
    assert "does not exist" in report.warnings[0]


def test_run_learning_discovers_python_page_objects(tmp_path: Path) -> None:
    src = textwrap.dedent("""\
        class LoginPage:
            def __init__(self, page):
                self.page = page
            def goto(self):
                self.page.goto('/login')
    """)
    (tmp_path / "login.py").write_text(src)

    report = run_learning(
        tenant_id="t1",
        application_id="app1",
        scope=_scope(str(tmp_path)),
        previous_hashes={},
    )

    assert report.run.status == LearningRunStatus.COMPLETED
    assert report.discovered_count >= 1
    assert any("LoginPage" in d.summary for d in report.run.discoveries)


def test_run_learning_marks_unchanged_entries(tmp_path: Path) -> None:
    src = "class CartPage:\n    pass\n"
    (tmp_path / "cart.py").write_text(src)

    first = run_learning("t1", "app1", _scope(str(tmp_path)), previous_hashes={})

    prev_hashes = {
        f"{d.source.file_path}::{d.source.symbol_name}": d.delta.current_hash
        for d in first.run.discoveries
        if d.delta.current_hash
    }
    second = run_learning("t1", "app1", _scope(str(tmp_path)), previous_hashes=prev_hashes)

    assert second.unchanged_count == first.discovered_count
    assert second.discovered_count == 0


def test_run_learning_marks_new_entry_after_file_change(tmp_path: Path) -> None:
    (tmp_path / "page.py").write_text("class LoginPage:\n    pass\n")
    first = run_learning("t1", "app1", _scope(str(tmp_path)), previous_hashes={})

    prev_hashes = {
        f"{d.source.file_path}::{d.source.symbol_name}": d.delta.current_hash
        for d in first.run.discoveries
        if d.delta.current_hash
    }

    # Add a new file
    (tmp_path / "new_page.py").write_text("class CheckoutPage:\n    pass\n")
    second = run_learning("t1", "app1", _scope(str(tmp_path)), previous_hashes=prev_hashes)

    assert second.discovered_count >= 1
    assert any("CheckoutPage" in d.summary for d in second.run.discoveries)


def test_run_learning_assigns_run_id(tmp_path: Path) -> None:
    (tmp_path / "f.py").write_text("x = 1")
    report = run_learning("t1", "app1", _scope(str(tmp_path)), previous_hashes={})

    assert report.run.run_id
    assert len(report.run.run_id) > 0


def test_run_learning_sets_tenant_and_application(tmp_path: Path) -> None:
    (tmp_path / "f.py").write_text("x = 1")
    report = run_learning("tenant_a", "app_b", _scope(str(tmp_path)), previous_hashes={})

    assert report.run.tenant_id == "tenant_a"
    assert report.run.application_id == "app_b"


def test_run_learning_empty_directory_produces_zero_discoveries(tmp_path: Path) -> None:
    report = run_learning("t1", "app1", _scope(str(tmp_path)), previous_hashes={})

    assert report.run.status == LearningRunStatus.COMPLETED
    assert report.discovered_count == 0
    assert report.run.discoveries == []


def test_run_learning_records_completed_at(tmp_path: Path) -> None:
    report = run_learning("t1", "app1", _scope(str(tmp_path)), previous_hashes={})

    assert report.run.completed_at is not None


def test_run_learning_trigger_type_preserved(tmp_path: Path) -> None:
    report = run_learning(
        "t1", "app1", _scope(str(tmp_path)), previous_hashes={},
        trigger_type=LearningTriggerType.SCHEDULED,
    )

    assert report.run.trigger_type == LearningTriggerType.SCHEDULED


def test_run_learning_new_discoveries_have_new_delta_state(tmp_path: Path) -> None:
    (tmp_path / "page.py").write_text("class HomePage:\n    pass\n")
    report = run_learning("t1", "app1", _scope(str(tmp_path)), previous_hashes={})

    new_items = [d for d in report.run.discoveries if d.delta.state == LearningDeltaState.NEW]
    assert len(new_items) >= 1


def test_run_learning_marks_changed_entry_after_content_modification(tmp_path: Path) -> None:
    (tmp_path / "page.py").write_text("class CartPage:\n    pass\n")
    first = run_learning("t1", "app1", _scope(str(tmp_path)), previous_hashes={})

    prev_hashes = {
        f"{d.source.file_path}::{d.source.symbol_name}": d.delta.current_hash
        for d in first.run.discoveries
        if d.delta.current_hash
    }

    # Modify the file content
    (tmp_path / "page.py").write_text("class CartPage:\n    def add_item(self): pass\n")
    second = run_learning("t1", "app1", _scope(str(tmp_path)), previous_hashes=prev_hashes)

    changed_items = [d for d in second.run.discoveries if d.delta.state == LearningDeltaState.CHANGED]
    assert len(changed_items) >= 1
    assert second.changed_count >= 1


def test_run_learning_redacts_secrets_in_source_excerpts(tmp_path: Path) -> None:
    src = 'class AuthPage:\n    API_KEY = "sk-supersecretkey12345"\n    def login(self): pass\n'
    (tmp_path / "auth.py").write_text(src)

    report = run_learning("t1", "app1", _scope(str(tmp_path)), previous_hashes={})

    assert report.run.status == LearningRunStatus.COMPLETED
    # Secrets must not appear in any discovery summary
    for discovery in report.run.discoveries:
        assert "sk-supersecretkey12345" not in discovery.summary


def test_run_learning_emits_redaction_warnings(tmp_path: Path) -> None:
    src = 'class SecretPage:\n    token = "sk-' + "A" * 25 + '"\n    pass\n'
    (tmp_path / "secret.py").write_text(src)

    report = run_learning("t1", "app1", _scope(str(tmp_path)), previous_hashes={})

    assert any("Redacted" in w for w in report.warnings)
