"""Tests for the health command."""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tambour.__main__ import (
    cmd_health_check,
    cmd_health_recover,
    cmd_health_status,
    create_parser,
    format_health_results,
    format_task_health,
    task_health_to_dict,
)
from tambour.health import HealthChecker, TaskHealth


class TestHealthParsing:
    """Tests for CLI argument parsing."""

    def test_health_parser_exists(self):
        """Test that health subcommand is registered."""
        parser = create_parser()
        args = parser.parse_args(["health", "status"])
        assert args.command == "health"
        assert args.health_command == "status"

    def test_health_status_json_flag(self):
        parser = create_parser()
        args = parser.parse_args(["health", "status", "--json"])
        assert args.json_output is True

    def test_health_status_default_no_json(self):
        parser = create_parser()
        args = parser.parse_args(["health", "status"])
        assert args.json_output is False

    def test_health_check_requires_issue(self):
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["health", "check"])

    def test_health_check_with_issue(self):
        parser = create_parser()
        args = parser.parse_args(["health", "check", "ta-123"])
        assert args.health_command == "check"
        assert args.issue == "ta-123"

    def test_health_check_json_flag(self):
        parser = create_parser()
        args = parser.parse_args(["health", "check", "ta-123", "--json"])
        assert args.json_output is True

    def test_health_recover_requires_issue(self):
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["health", "recover"])

    def test_health_recover_with_issue(self):
        parser = create_parser()
        args = parser.parse_args(["health", "recover", "ta-123"])
        assert args.health_command == "recover"
        assert args.issue == "ta-123"


class TestFormatTaskHealth:
    """Tests for format_task_health function."""

    def test_zombie_task(self):
        health = TaskHealth(
            issue_id="ta-123",
            status="in_progress",
            assignee="agent-1",
            worktree_path=Path("/tmp/wt"),
            worktree_exists=False,
            is_zombie=True,
        )
        result = format_task_health(health)
        assert "!" in result
        assert "ZOMBIE" in result
        assert "ta-123" in result
        assert "agent-1" in result
        assert "missing" in result

    def test_healthy_task(self):
        health = TaskHealth(
            issue_id="ta-456",
            status="in_progress",
            assignee="agent-2",
            worktree_path=Path("/tmp/wt"),
            worktree_exists=True,
            is_zombie=False,
        )
        result = format_task_health(health)
        assert "*" in result
        assert "healthy" in result
        assert "ta-456" in result
        assert "exists" in result

    def test_no_assignee(self):
        health = TaskHealth(
            issue_id="ta-789",
            status="in_progress",
            assignee=None,
            worktree_path=None,
            worktree_exists=False,
            is_zombie=True,
        )
        result = format_task_health(health)
        assert "(none)" in result

    def test_with_recent_activity(self):
        recent = datetime.now(timezone.utc)
        health = TaskHealth(
            issue_id="ta-111",
            status="in_progress",
            assignee="agent-1",
            worktree_path=Path("/tmp/wt"),
            worktree_exists=True,
            is_zombie=False,
            last_activity=recent,
        )
        result = format_task_health(health)
        assert "last seen" in result
        assert "s ago" in result


class TestFormatHealthResults:
    """Tests for format_health_results function."""

    def test_empty_results(self):
        result = format_health_results([])
        assert result == "No in-progress tasks found."

    def test_all_healthy(self):
        results = [
            TaskHealth(
                issue_id="ta-1",
                status="in_progress",
                assignee="a",
                worktree_path=Path("/tmp/wt"),
                worktree_exists=True,
                is_zombie=False,
            ),
        ]
        result = format_health_results(results)
        assert "Healthy (1):" in result
        assert "Zombies" not in result
        assert "1 task(s)" in result

    def test_all_zombies(self):
        results = [
            TaskHealth(
                issue_id="ta-1",
                status="in_progress",
                assignee="a",
                worktree_path=None,
                worktree_exists=False,
                is_zombie=True,
            ),
        ]
        result = format_health_results(results)
        assert "Zombies (1):" in result
        assert "1 zombie(s)" in result

    def test_mixed(self):
        results = [
            TaskHealth(
                issue_id="ta-1",
                status="in_progress",
                assignee="a",
                worktree_path=Path("/tmp/wt"),
                worktree_exists=True,
                is_zombie=False,
            ),
            TaskHealth(
                issue_id="ta-2",
                status="in_progress",
                assignee="b",
                worktree_path=None,
                worktree_exists=False,
                is_zombie=True,
            ),
        ]
        result = format_health_results(results)
        assert "Zombies (1):" in result
        assert "Healthy (1):" in result
        assert "2 task(s), 1 zombie(s)" in result


class TestTaskHealthToDict:
    """Tests for task_health_to_dict function."""

    def test_basic_conversion(self):
        health = TaskHealth(
            issue_id="ta-123",
            status="in_progress",
            assignee="agent-1",
            worktree_path=Path("/tmp/wt"),
            worktree_exists=True,
            is_zombie=False,
        )
        d = task_health_to_dict(health)
        assert d["issue_id"] == "ta-123"
        assert d["status"] == "in_progress"
        assert d["assignee"] == "agent-1"
        assert d["worktree_path"] == "/tmp/wt"
        assert d["worktree_exists"] is True
        assert d["is_zombie"] is False
        assert d["last_activity"] is None

    def test_with_activity(self):
        dt = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        health = TaskHealth(
            issue_id="ta-123",
            status="in_progress",
            assignee=None,
            worktree_path=None,
            worktree_exists=False,
            is_zombie=True,
            last_activity=dt,
        )
        d = task_health_to_dict(health)
        assert d["assignee"] is None
        assert d["worktree_path"] is None
        assert d["last_activity"] == "2026-01-15T10:30:00+00:00"


class TestCmdHealthStatus:
    """Tests for cmd_health_status handler."""

    @patch("tambour.health.HealthChecker.check_all")
    @patch("tambour.config.Config.load_or_default")
    def test_no_tasks(self, mock_config, mock_check_all, capsys):
        mock_config.return_value = MagicMock()
        mock_check_all.return_value = []

        parser = create_parser()
        args = parser.parse_args(["health", "status"])
        result = cmd_health_status(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "No in-progress tasks found." in captured.out

    @patch("tambour.health.HealthChecker.check_all")
    @patch("tambour.config.Config.load_or_default")
    def test_returns_1_with_zombies(self, mock_config, mock_check_all, capsys):
        mock_config.return_value = MagicMock()
        mock_check_all.return_value = [
            TaskHealth(
                issue_id="ta-1",
                status="in_progress",
                assignee="a",
                worktree_path=None,
                worktree_exists=False,
                is_zombie=True,
            ),
        ]

        parser = create_parser()
        args = parser.parse_args(["health", "status"])
        result = cmd_health_status(args)

        assert result == 1

    @patch("tambour.health.HealthChecker.check_all")
    @patch("tambour.config.Config.load_or_default")
    def test_returns_0_all_healthy(self, mock_config, mock_check_all, capsys):
        mock_config.return_value = MagicMock()
        mock_check_all.return_value = [
            TaskHealth(
                issue_id="ta-1",
                status="in_progress",
                assignee="a",
                worktree_path=Path("/tmp/wt"),
                worktree_exists=True,
                is_zombie=False,
            ),
        ]

        parser = create_parser()
        args = parser.parse_args(["health", "status"])
        result = cmd_health_status(args)

        assert result == 0

    @patch("tambour.health.HealthChecker.check_all")
    @patch("tambour.config.Config.load_or_default")
    def test_json_output(self, mock_config, mock_check_all, capsys):
        mock_config.return_value = MagicMock()
        mock_check_all.return_value = [
            TaskHealth(
                issue_id="ta-1",
                status="in_progress",
                assignee="a",
                worktree_path=Path("/tmp/wt"),
                worktree_exists=True,
                is_zombie=False,
            ),
        ]

        parser = create_parser()
        args = parser.parse_args(["health", "status", "--json"])
        result = cmd_health_status(args)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert len(data) == 1
        assert data[0]["issue_id"] == "ta-1"
        assert data[0]["is_zombie"] is False


class TestCmdHealthCheck:
    """Tests for cmd_health_check handler."""

    @patch("tambour.health.HealthChecker.check_task")
    @patch("tambour.config.Config.load_or_default")
    def test_task_not_found(self, mock_config, mock_check, capsys):
        mock_config.return_value = MagicMock()
        mock_check.return_value = None

        parser = create_parser()
        args = parser.parse_args(["health", "check", "ta-missing"])
        result = cmd_health_check(args)

        assert result == 1
        captured = capsys.readouterr()
        assert "Task not found" in captured.err

    @patch("tambour.health.HealthChecker.check_task")
    @patch("tambour.config.Config.load_or_default")
    def test_healthy_task(self, mock_config, mock_check, capsys):
        mock_config.return_value = MagicMock()
        mock_check.return_value = TaskHealth(
            issue_id="ta-1",
            status="in_progress",
            assignee="a",
            worktree_path=Path("/tmp/wt"),
            worktree_exists=True,
            is_zombie=False,
        )

        parser = create_parser()
        args = parser.parse_args(["health", "check", "ta-1"])
        result = cmd_health_check(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "healthy" in captured.out

    @patch("tambour.health.HealthChecker.check_task")
    @patch("tambour.config.Config.load_or_default")
    def test_zombie_task_returns_1(self, mock_config, mock_check, capsys):
        mock_config.return_value = MagicMock()
        mock_check.return_value = TaskHealth(
            issue_id="ta-1",
            status="in_progress",
            assignee="a",
            worktree_path=None,
            worktree_exists=False,
            is_zombie=True,
        )

        parser = create_parser()
        args = parser.parse_args(["health", "check", "ta-1"])
        result = cmd_health_check(args)

        assert result == 1

    @patch("tambour.health.HealthChecker.check_task")
    @patch("tambour.config.Config.load_or_default")
    def test_json_output(self, mock_config, mock_check, capsys):
        mock_config.return_value = MagicMock()
        mock_check.return_value = TaskHealth(
            issue_id="ta-1",
            status="in_progress",
            assignee="a",
            worktree_path=Path("/tmp/wt"),
            worktree_exists=True,
            is_zombie=False,
        )

        parser = create_parser()
        args = parser.parse_args(["health", "check", "ta-1", "--json"])
        result = cmd_health_check(args)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["issue_id"] == "ta-1"


class TestCmdHealthRecover:
    """Tests for cmd_health_recover handler."""

    @patch("tambour.health.HealthChecker.check_task")
    @patch("tambour.config.Config.load_or_default")
    def test_task_not_found(self, mock_config, mock_check, capsys):
        mock_config.return_value = MagicMock()
        mock_check.return_value = None

        parser = create_parser()
        args = parser.parse_args(["health", "recover", "ta-missing"])
        result = cmd_health_recover(args)

        assert result == 1
        captured = capsys.readouterr()
        assert "Task not found" in captured.err

    @patch("tambour.health.HealthChecker.check_task")
    @patch("tambour.config.Config.load_or_default")
    def test_not_a_zombie(self, mock_config, mock_check, capsys):
        mock_config.return_value = MagicMock()
        mock_check.return_value = TaskHealth(
            issue_id="ta-1",
            status="in_progress",
            assignee="a",
            worktree_path=Path("/tmp/wt"),
            worktree_exists=True,
            is_zombie=False,
        )

        parser = create_parser()
        args = parser.parse_args(["health", "recover", "ta-1"])
        result = cmd_health_recover(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "not a zombie" in captured.out

    @patch("tambour.health.HealthChecker._recover_zombie")
    @patch("tambour.health.HealthChecker.check_task")
    @patch("tambour.config.Config.load_or_default")
    def test_successful_recovery(self, mock_config, mock_check, mock_recover, capsys):
        mock_config.return_value = MagicMock()
        mock_check.return_value = TaskHealth(
            issue_id="ta-1",
            status="in_progress",
            assignee="a",
            worktree_path=None,
            worktree_exists=False,
            is_zombie=True,
        )
        mock_recover.return_value = True

        parser = create_parser()
        args = parser.parse_args(["health", "recover", "ta-1"])
        result = cmd_health_recover(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "Recovered" in captured.out

    @patch("tambour.health.HealthChecker._recover_zombie")
    @patch("tambour.health.HealthChecker.check_task")
    @patch("tambour.config.Config.load_or_default")
    def test_failed_recovery(self, mock_config, mock_check, mock_recover, capsys):
        mock_config.return_value = MagicMock()
        mock_check.return_value = TaskHealth(
            issue_id="ta-1",
            status="in_progress",
            assignee="a",
            worktree_path=None,
            worktree_exists=False,
            is_zombie=True,
        )
        mock_recover.return_value = False

        parser = create_parser()
        args = parser.parse_args(["health", "recover", "ta-1"])
        result = cmd_health_recover(args)

        assert result == 1
        captured = capsys.readouterr()
        assert "Failed to recover" in captured.err


class TestHealthChecker:
    """Tests for HealthChecker business logic."""

    @pytest.fixture
    def config(self):
        config = MagicMock()
        config.daemon.zombie_threshold = 300
        config.daemon.auto_recover = False
        config.worktree.base_path = "../{repo}-worktrees"
        return config

    def test_check_all_empty(self, config):
        checker = HealthChecker(config)
        with patch.object(checker, "_get_in_progress_tasks", return_value=[]):
            results = checker.check_all()
            assert results == []

    def test_check_all_with_tasks(self, config):
        checker = HealthChecker(config)
        tasks = [
            {"id": "ta-1", "status": "in_progress", "assignee": "a"},
        ]
        with patch.object(checker, "_get_in_progress_tasks", return_value=tasks), \
             patch.object(checker, "_find_worktree", return_value=None):
            results = checker.check_all()
            assert len(results) == 1
            assert results[0].is_zombie

    def test_check_task_not_found(self, config):
        checker = HealthChecker(config)
        with patch.object(checker, "_get_task", return_value=None):
            result = checker.check_task("ta-missing")
            assert result is None

    def test_check_task_found(self, config):
        checker = HealthChecker(config)
        task = {"id": "ta-1", "status": "in_progress", "assignee": "a"}
        with patch.object(checker, "_get_task", return_value=task), \
             patch.object(checker, "_find_worktree", return_value=None):
            result = checker.check_task("ta-1")
            assert result is not None
            assert result.issue_id == "ta-1"
            assert result.is_zombie

    @patch("subprocess.run")
    def test_recover_zombie_success(self, mock_run, config):
        mock_run.return_value = MagicMock(returncode=0)
        checker = HealthChecker(config)
        health = TaskHealth(
            issue_id="ta-1",
            status="in_progress",
            assignee="a",
            worktree_path=None,
            worktree_exists=False,
            is_zombie=True,
        )
        assert checker._recover_zombie(health) is True
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_recover_zombie_failure(self, mock_run, config):
        mock_run.return_value = MagicMock(returncode=1)
        checker = HealthChecker(config)
        health = TaskHealth(
            issue_id="ta-1",
            status="in_progress",
            assignee="a",
            worktree_path=None,
            worktree_exists=False,
            is_zombie=True,
        )
        assert checker._recover_zombie(health) is False
