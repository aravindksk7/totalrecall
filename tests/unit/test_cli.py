"""Unit tests for the CLI commands using Click's test runner."""

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from totalrecall.cli.client import ApiError, TotalRecallClient
from totalrecall.cli.main import cli


def _runner() -> CliRunner:
    return CliRunner()


def _invoke(args: list[str], client: TotalRecallClient | None = None) -> object:
    runner = _runner()
    mock = client or MagicMock(spec=TotalRecallClient)
    with patch("totalrecall.cli.main.TotalRecallClient", return_value=mock):
        return runner.invoke(cli, args, catch_exceptions=False)


def test_cli_help_exits_zero() -> None:
    result = _runner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "TotalRecall" in result.output


def test_generate_cmd_outputs_status_text() -> None:
    mock_client = MagicMock(spec=TotalRecallClient)
    mock_client.generate.return_value = {
        "status": "completed",
        "artifacts": [{"path": "pages/login.page.ts", "language": "typescript"}],
        "validation": {"status": "passed", "diagnostics": []},
    }

    result = _invoke(
        [
            "generate",
            "--tenant-id", "t1",
            "--application-id", "app1",
            "--prompt", "Generate a login page object",
        ],
        client=mock_client,
    )

    assert result.exit_code == 0
    assert "Status: completed" in result.output
    assert "Artifacts: 1" in result.output
    assert "pages/login.page.ts" in result.output


def test_generate_cmd_json_output() -> None:
    payload = {"status": "completed", "artifacts": [], "validation": {}}
    mock_client = MagicMock(spec=TotalRecallClient)
    mock_client.generate.return_value = payload

    result = _invoke(
        [
            "generate",
            "--tenant-id", "t1",
            "--application-id", "app1",
            "--prompt", "Generate",
            "--output", "json",
        ],
        client=mock_client,
    )

    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["status"] == "completed"


def test_generate_cmd_exits_2_on_failed_status() -> None:
    mock_client = MagicMock(spec=TotalRecallClient)
    mock_client.generate.return_value = {"status": "failed", "artifacts": [], "validation": {}}

    result = _invoke(
        ["generate", "--tenant-id", "t1", "--application-id", "app1", "--prompt", "x"],
        client=mock_client,
    )

    assert result.exit_code == 2


def test_generate_cmd_exits_1_on_api_error() -> None:
    mock_client = MagicMock(spec=TotalRecallClient)
    mock_client.generate.side_effect = ApiError(403, "Forbidden")

    result = _invoke(
        ["generate", "--tenant-id", "t1", "--application-id", "app1", "--prompt", "x"],
        client=mock_client,
    )

    assert result.exit_code == 1


def test_catalogue_search_outputs_table() -> None:
    mock_client = MagicMock(spec=TotalRecallClient)
    mock_client.search_catalogue.return_value = {
        "items": [
            {
                "entity_id": "ent_001",
                "category": "static_skill",
                "status": "active",
                "summary": "Login page object",
            }
        ],
        "total": 1,
    }

    result = _invoke(["catalogue", "search"], client=mock_client)

    assert result.exit_code == 0
    assert "Found 1" in result.output
    assert "ent_001" in result.output


def test_catalogue_search_json_output() -> None:
    mock_client = MagicMock(spec=TotalRecallClient)
    mock_client.search_catalogue.return_value = {"items": [], "total": 0}

    result = _invoke(["catalogue", "search", "--output", "json"], client=mock_client)

    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "items" in parsed


def test_catalogue_get_outputs_entry() -> None:
    mock_client = MagicMock(spec=TotalRecallClient)
    mock_client.get_catalogue_entry.return_value = {
        "entity_id": "ent_001",
        "category": "static_skill",
        "status": "active",
        "summary": "Login page",
        "tags": {},
    }

    result = _invoke(["catalogue", "get", "ent_001"], client=mock_client)

    assert result.exit_code == 0
    assert "ent_001" in result.output
    assert "Login page" in result.output


def test_catalogue_delete_memory_requires_confirmation() -> None:
    mock_client = MagicMock(spec=TotalRecallClient)

    with patch("totalrecall.cli.main.TotalRecallClient", return_value=mock_client):
        result = _runner().invoke(
            cli,
            ["catalogue", "delete-memory", "mem_001", "--application-id", "app1"],
            input="n\n",
        )

    assert result.exit_code != 0
    mock_client.delete_memory.assert_not_called()


def test_catalogue_delete_memory_yes_flag_skips_confirmation() -> None:
    mock_client = MagicMock(spec=TotalRecallClient)
    mock_client.delete_memory.return_value = {"deleted": True, "tombstoned": True}

    result = _invoke(
        ["catalogue", "delete-memory", "mem_001", "--application-id", "app1", "--yes"],
        client=mock_client,
    )

    assert result.exit_code == 0
    assert "Deleted: True" in result.output


def test_learn_run_outputs_run_summary() -> None:
    mock_client = MagicMock(spec=TotalRecallClient)
    mock_client.trigger_learning_run.return_value = {
        "run": {"run_id": "run_abc", "status": "completed", "discoveries": []},
        "discovered_count": 3,
        "changed_count": 1,
        "unchanged_count": 2,
        "warnings": [],
    }

    result = _invoke(
        ["learn", "run", "--application-id", "app1", "--path", "/tmp"],
        client=mock_client,
    )

    assert result.exit_code == 0
    assert "run_abc" in result.output
    assert "Discovered: 3" in result.output


def test_learn_list_outputs_table() -> None:
    mock_client = MagicMock(spec=TotalRecallClient)
    mock_client.list_learning_runs.return_value = [
        {
            "run": {"run_id": "run_001", "status": "completed"},
            "discovered_count": 5,
            "changed_count": 0,
        }
    ]

    result = _invoke(["learn", "list"], client=mock_client)

    assert result.exit_code == 0
    assert "run_001" in result.output
    assert "completed" in result.output


def test_learn_show_outputs_run_details() -> None:
    mock_client = MagicMock(spec=TotalRecallClient)
    mock_client.get_learning_run.return_value = {
        "run": {
            "run_id": "run_xyz",
            "status": "completed",
            "scope": {"path": "/tmp/tests"},
            "started_at": "2026-05-21T10:00:00",
            "completed_at": "2026-05-21T10:00:05",
            "discoveries": [],
        },
        "discovered_count": 2,
        "changed_count": 0,
        "unchanged_count": 1,
    }

    result = _invoke(["learn", "show", "run_xyz"], client=mock_client)

    assert result.exit_code == 0
    assert "run_xyz" in result.output
    assert "/tmp/tests" in result.output
