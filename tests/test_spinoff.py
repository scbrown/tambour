"""Tests for the spinoff command."""

import argparse
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from tambour.__main__ import create_parser
from tambour.spinoff import SpinoffCommand, SpinoffResult, cmd_spinoff


class TestSpinoffParsing:
    """Tests for CLI argument parsing."""

    def test_spinoff_parser_exists(self):
        parser = create_parser()
        args = parser.parse_args(["spinoff", "Fix the widget"])
        assert args.command == "spinoff"
        assert args.title == "Fix the widget"

    def test_spinoff_with_description(self):
        parser = create_parser()
        args = parser.parse_args(["spinoff", "Fix it", "-d", "Details here"])
        assert args.description == "Details here"

    def test_spinoff_with_type(self):
        parser = create_parser()
        args = parser.parse_args(["spinoff", "Fix it", "-t", "bug"])
        assert args.type == "bug"

    def test_spinoff_type_defaults_to_task(self):
        parser = create_parser()
        args = parser.parse_args(["spinoff", "Fix it"])
        assert args.type == "task"

    def test_spinoff_with_priority(self):
        parser = create_parser()
        args = parser.parse_args(["spinoff", "Fix it", "-p", "1"])
        assert args.priority == "1"

    def test_spinoff_with_labels(self):
        parser = create_parser()
        args = parser.parse_args(["spinoff", "Fix it", "-l", "security", "-l", "urgent"])
        assert args.labels == ["security", "urgent"]

    def test_spinoff_with_parent(self):
        parser = create_parser()
        args = parser.parse_args(["spinoff", "Fix it", "--parent", "ta-abc"])
        assert args.parent == "ta-abc"

    def test_spinoff_blocks_current(self):
        parser = create_parser()
        args = parser.parse_args(["spinoff", "Fix it", "--blocks-current"])
        assert args.blocks_current is True

    def test_spinoff_blocks_current_default_false(self):
        parser = create_parser()
        args = parser.parse_args(["spinoff", "Fix it"])
        assert args.blocks_current is False

    def test_spinoff_with_issue(self):
        parser = create_parser()
        args = parser.parse_args(["spinoff", "Fix it", "--issue", "ta-xyz"])
        assert args.issue == "ta-xyz"

    def test_spinoff_requires_title(self):
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["spinoff"])


class TestSpinoffCommand:
    """Tests for SpinoffCommand."""

    @patch("subprocess.run")
    def test_basic_spinoff(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ta-new\n", stderr="")

        cmd = SpinoffCommand(title="Fix the widget")
        result = cmd.run()

        assert result.success is True
        assert result.issue_id == "ta-new"
        assert result.title == "Fix the widget"

    @patch("subprocess.run")
    def test_passes_title_and_type(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ta-new\n", stderr="")

        cmd = SpinoffCommand(title="Fix it", issue_type="bug")
        cmd.run()

        call_args = mock_run.call_args[0][0]
        assert "Fix it" in call_args
        assert "--type" in call_args
        idx = call_args.index("--type")
        assert call_args[idx + 1] == "bug"

    @patch("subprocess.run")
    def test_passes_description(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ta-new\n", stderr="")

        cmd = SpinoffCommand(title="Fix it", description="More details")
        cmd.run()

        call_args = mock_run.call_args[0][0]
        assert "--description" in call_args
        idx = call_args.index("--description")
        assert call_args[idx + 1] == "More details"

    @patch("subprocess.run")
    def test_passes_priority(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ta-new\n", stderr="")

        cmd = SpinoffCommand(title="Fix it", priority="1")
        cmd.run()

        call_args = mock_run.call_args[0][0]
        assert "--priority" in call_args
        idx = call_args.index("--priority")
        assert call_args[idx + 1] == "1"

    @patch("subprocess.run")
    def test_passes_labels(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ta-new\n", stderr="")

        cmd = SpinoffCommand(title="Fix it", labels=["security", "urgent"])
        cmd.run()

        call_args = mock_run.call_args[0][0]
        # Each label gets its own --labels flag
        label_indices = [i for i, x in enumerate(call_args) if x == "--labels"]
        assert len(label_indices) == 2
        assert call_args[label_indices[0] + 1] == "security"
        assert call_args[label_indices[1] + 1] == "urgent"

    @patch("subprocess.run")
    def test_passes_parent(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ta-new\n", stderr="")

        cmd = SpinoffCommand(title="Fix it", parent_issue="ta-parent")
        cmd.run()

        call_args = mock_run.call_args[0][0]
        assert "--parent" in call_args
        idx = call_args.index("--parent")
        assert call_args[idx + 1] == "ta-parent"

    @patch("subprocess.run")
    def test_links_to_current_issue(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ta-new\n", stderr="")

        cmd = SpinoffCommand(title="Fix it", current_issue="ta-current")
        cmd.run()

        call_args = mock_run.call_args[0][0]
        assert "--deps" in call_args
        idx = call_args.index("--deps")
        assert "discovered-from:ta-current" in call_args[idx + 1]

    @patch("subprocess.run")
    def test_blocks_current_adds_dep(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ta-new\n", stderr="")

        cmd = SpinoffCommand(
            title="Fix it",
            current_issue="ta-current",
            blocks_current=True,
        )
        cmd.run()

        call_args = mock_run.call_args[0][0]
        idx = call_args.index("--deps")
        deps_val = call_args[idx + 1]
        assert "discovered-from:ta-current" in deps_val
        assert "blocks:ta-current" in deps_val

    @patch("subprocess.run")
    def test_resolves_issue_from_env(self, mock_run, monkeypatch):
        mock_run.return_value = MagicMock(returncode=0, stdout="ta-new\n", stderr="")
        monkeypatch.setenv("TAMBOUR_ISSUE_ID", "ta-env")

        cmd = SpinoffCommand(title="Fix it")
        cmd.run()

        call_args = mock_run.call_args[0][0]
        assert "--deps" in call_args
        idx = call_args.index("--deps")
        assert "discovered-from:ta-env" in call_args[idx + 1]

    @patch("subprocess.run")
    def test_explicit_issue_overrides_env(self, mock_run, monkeypatch):
        mock_run.return_value = MagicMock(returncode=0, stdout="ta-new\n", stderr="")
        monkeypatch.setenv("TAMBOUR_ISSUE_ID", "ta-env")

        cmd = SpinoffCommand(title="Fix it", current_issue="ta-explicit")
        cmd.run()

        call_args = mock_run.call_args[0][0]
        idx = call_args.index("--deps")
        assert "discovered-from:ta-explicit" in call_args[idx + 1]

    @patch("subprocess.run")
    def test_no_deps_without_current_issue(self, mock_run, monkeypatch):
        mock_run.return_value = MagicMock(returncode=0, stdout="ta-new\n", stderr="")
        monkeypatch.delenv("TAMBOUR_ISSUE_ID", raising=False)

        cmd = SpinoffCommand(title="Fix it")
        cmd.run()

        call_args = mock_run.call_args[0][0]
        assert "--deps" not in call_args

    @patch("subprocess.run")
    def test_uses_silent_flag(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ta-new\n", stderr="")

        cmd = SpinoffCommand(title="Fix it")
        cmd.run()

        call_args = mock_run.call_args[0][0]
        assert "--silent" in call_args

    def test_empty_title_fails(self):
        cmd = SpinoffCommand(title="")
        result = cmd.run()
        assert result.success is False
        assert "Title is required" in result.error

    @patch("subprocess.run")
    def test_bd_failure_returns_error(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="something went wrong"
        )

        cmd = SpinoffCommand(title="Fix it")
        result = cmd.run()

        assert result.success is False
        assert "something went wrong" in result.error

    @patch("subprocess.run")
    def test_bd_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError("No such file: 'bd'")

        cmd = SpinoffCommand(title="Fix it")
        result = cmd.run()

        assert result.success is False
        assert "'bd' command not found" in result.error

    @patch("subprocess.run")
    def test_empty_stdout_on_success_fails(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        cmd = SpinoffCommand(title="Fix it")
        result = cmd.run()

        assert result.success is False
        assert "returned no issue ID" in result.error

    @patch("subprocess.run")
    def test_no_description_omits_flag(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ta-new\n", stderr="")

        cmd = SpinoffCommand(title="Fix it")
        cmd.run()

        call_args = mock_run.call_args[0][0]
        assert "--description" not in call_args

    @patch("subprocess.run")
    def test_no_priority_omits_flag(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ta-new\n", stderr="")

        cmd = SpinoffCommand(title="Fix it")
        cmd.run()

        call_args = mock_run.call_args[0][0]
        assert "--priority" not in call_args


class TestCmdSpinoff:
    """Tests for the cmd_spinoff CLI handler."""

    @patch("tambour.spinoff.SpinoffCommand.run")
    def test_returns_zero_on_success(self, mock_run):
        mock_run.return_value = SpinoffResult(
            success=True, issue_id="ta-new", title="Fix it"
        )
        args = argparse.Namespace(
            title="Fix it",
            description=None,
            type="task",
            priority=None,
            labels=None,
            parent=None,
            blocks_current=False,
            issue=None,
        )
        assert cmd_spinoff(args) == 0

    @patch("tambour.spinoff.SpinoffCommand.run")
    def test_returns_one_on_failure(self, mock_run):
        mock_run.return_value = SpinoffResult(
            success=False, error="Something failed"
        )
        args = argparse.Namespace(
            title="Fix it",
            description=None,
            type="task",
            priority=None,
            labels=None,
            parent=None,
            blocks_current=False,
            issue=None,
        )
        assert cmd_spinoff(args) == 1

    @patch("tambour.spinoff.SpinoffCommand.run")
    def test_prints_created_issue(self, mock_run, capsys):
        mock_run.return_value = SpinoffResult(
            success=True, issue_id="ta-new", title="Fix widget"
        )
        args = argparse.Namespace(
            title="Fix widget",
            description=None,
            type="task",
            priority=None,
            labels=None,
            parent=None,
            blocks_current=False,
            issue=None,
        )
        cmd_spinoff(args)
        captured = capsys.readouterr()
        assert "ta-new" in captured.out
        assert "Fix widget" in captured.out

    @patch("tambour.spinoff.SpinoffCommand.run")
    def test_prints_link_info(self, mock_run, capsys):
        mock_run.return_value = SpinoffResult(
            success=True, issue_id="ta-new", title="Fix it"
        )
        args = argparse.Namespace(
            title="Fix it",
            description=None,
            type="task",
            priority=None,
            labels=None,
            parent=None,
            blocks_current=False,
            issue="ta-current",
        )
        cmd_spinoff(args)
        captured = capsys.readouterr()
        assert "ta-current" in captured.out
        assert "discovered-from" in captured.out

    @patch("tambour.spinoff.SpinoffCommand.run")
    def test_prints_blocks_link(self, mock_run, capsys):
        mock_run.return_value = SpinoffResult(
            success=True, issue_id="ta-new", title="Fix it"
        )
        args = argparse.Namespace(
            title="Fix it",
            description=None,
            type="task",
            priority=None,
            labels=None,
            parent=None,
            blocks_current=True,
            issue="ta-current",
        )
        cmd_spinoff(args)
        captured = capsys.readouterr()
        assert "blocks" in captured.out

    @patch("tambour.spinoff.SpinoffCommand.run")
    def test_prints_error_on_failure(self, mock_run, capsys):
        mock_run.return_value = SpinoffResult(
            success=False, error="bd not found"
        )
        args = argparse.Namespace(
            title="Fix it",
            description=None,
            type="task",
            priority=None,
            labels=None,
            parent=None,
            blocks_current=False,
            issue=None,
        )
        cmd_spinoff(args)
        captured = capsys.readouterr()
        assert "bd not found" in captured.err

    @patch("tambour.spinoff.SpinoffCommand.run")
    def test_passes_labels_list(self, mock_run):
        mock_run.return_value = SpinoffResult(
            success=True, issue_id="ta-new", title="Fix it"
        )
        args = argparse.Namespace(
            title="Fix it",
            description=None,
            type="task",
            priority=None,
            labels=["security", "urgent"],
            parent=None,
            blocks_current=False,
            issue=None,
        )
        cmd_spinoff(args)

        # Verify SpinoffCommand was constructed correctly by checking
        # that run was called (constructor args are tested via SpinoffCommand tests)
        mock_run.assert_called_once()

    @patch("tambour.spinoff.SpinoffCommand.run")
    def test_none_labels_becomes_empty_list(self, mock_run):
        mock_run.return_value = SpinoffResult(
            success=True, issue_id="ta-new", title="Fix it"
        )
        args = argparse.Namespace(
            title="Fix it",
            description=None,
            type="task",
            priority=None,
            labels=None,
            parent=None,
            blocks_current=False,
            issue=None,
        )
        # Should not crash when labels is None
        result = cmd_spinoff(args)
        assert result == 0
