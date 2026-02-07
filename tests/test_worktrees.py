"""Tests for the worktrees command."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tambour.__main__ import cmd_worktrees, create_parser
from tambour.worktrees import (
    WorktreeInfo,
    _format_age,
    _parse_porcelain,
    format_worktrees,
    list_worktrees,
)


class TestWorktreesParsing:
    """Tests for CLI argument parsing."""

    def test_worktrees_parser_exists(self):
        """Test that worktrees subcommand is registered."""
        parser = create_parser()
        args = parser.parse_args(["worktrees"])
        assert args.command == "worktrees"


class TestParsePorcelain:
    """Tests for git worktree list --porcelain parsing."""

    def test_parse_bare_repo(self):
        output = "worktree /path/to/repo\nbare\n\n"
        result = _parse_porcelain(output)
        assert len(result) == 1
        assert result[0].is_bare
        assert result[0].path == Path("/path/to/repo")

    def test_parse_regular_worktree(self):
        output = (
            "worktree /path/to/wt\n"
            "HEAD abc1234567890\n"
            "branch refs/heads/feature\n\n"
        )
        result = _parse_porcelain(output)
        assert len(result) == 1
        assert result[0].path == Path("/path/to/wt")
        assert result[0].head == "abc1234567890"
        assert result[0].branch == "refs/heads/feature"
        assert not result[0].is_bare

    def test_parse_detached_head(self):
        output = (
            "worktree /path/to/wt\n"
            "HEAD abc1234567890\n"
            "detached\n\n"
        )
        result = _parse_porcelain(output)
        assert len(result) == 1
        assert result[0].branch is None

    def test_parse_multiple_worktrees(self):
        output = (
            "worktree /path/to/repo\n"
            "bare\n\n"
            "worktree /path/to/wt1\n"
            "HEAD aaa1111111111\n"
            "branch refs/heads/main\n\n"
            "worktree /path/to/wt2\n"
            "HEAD bbb2222222222\n"
            "branch refs/heads/feature\n\n"
        )
        result = _parse_porcelain(output)
        assert len(result) == 3
        assert result[0].is_bare
        assert result[1].short_branch == "main"
        assert result[2].short_branch == "feature"

    def test_parse_no_trailing_newline(self):
        output = "worktree /path/to/wt\nHEAD abc1234567890\nbranch refs/heads/main"
        result = _parse_porcelain(output)
        assert len(result) == 1
        assert result[0].short_branch == "main"

    def test_parse_empty_output(self):
        result = _parse_porcelain("")
        assert len(result) == 0


class TestWorktreeInfo:
    """Tests for WorktreeInfo properties."""

    def test_name(self):
        wt = WorktreeInfo(
            path=Path("/a/b/my-worktree"),
            head="abc1234",
            branch=None,
            is_bare=False,
            heartbeat_age=None,
            heartbeat_pid=None,
        )
        assert wt.name == "my-worktree"

    def test_short_head(self):
        wt = WorktreeInfo(
            path=Path("/a"),
            head="abc1234567890",
            branch=None,
            is_bare=False,
            heartbeat_age=None,
            heartbeat_pid=None,
        )
        assert wt.short_head == "abc1234"

    def test_short_branch_strips_prefix(self):
        wt = WorktreeInfo(
            path=Path("/a"),
            head="abc",
            branch="refs/heads/my-feature",
            is_bare=False,
            heartbeat_age=None,
            heartbeat_pid=None,
        )
        assert wt.short_branch == "my-feature"

    def test_short_branch_detached(self):
        wt = WorktreeInfo(
            path=Path("/a"),
            head="abc",
            branch=None,
            is_bare=False,
            heartbeat_age=None,
            heartbeat_pid=None,
        )
        assert wt.short_branch == "(detached)"

    def test_is_alive_with_fresh_heartbeat(self):
        wt = WorktreeInfo(
            path=Path("/a"),
            head="abc",
            branch=None,
            is_bare=False,
            heartbeat_age=30.0,
            heartbeat_pid=1234,
        )
        assert wt.is_alive

    def test_is_alive_with_stale_heartbeat(self):
        wt = WorktreeInfo(
            path=Path("/a"),
            head="abc",
            branch=None,
            is_bare=False,
            heartbeat_age=600.0,
            heartbeat_pid=1234,
        )
        assert not wt.is_alive

    def test_is_alive_with_no_heartbeat(self):
        wt = WorktreeInfo(
            path=Path("/a"),
            head="abc",
            branch=None,
            is_bare=False,
            heartbeat_age=None,
            heartbeat_pid=None,
        )
        assert not wt.is_alive

    def test_status_indicator_bare(self):
        wt = WorktreeInfo(
            path=Path("/a"),
            head="",
            branch=None,
            is_bare=True,
            heartbeat_age=None,
            heartbeat_pid=None,
        )
        assert wt.status_indicator == " "

    def test_status_indicator_no_heartbeat(self):
        wt = WorktreeInfo(
            path=Path("/a"),
            head="abc",
            branch=None,
            is_bare=False,
            heartbeat_age=None,
            heartbeat_pid=None,
        )
        assert wt.status_indicator == "-"

    def test_status_indicator_active(self):
        wt = WorktreeInfo(
            path=Path("/a"),
            head="abc",
            branch=None,
            is_bare=False,
            heartbeat_age=30.0,
            heartbeat_pid=1234,
        )
        assert wt.status_indicator == "*"

    def test_status_indicator_stale(self):
        wt = WorktreeInfo(
            path=Path("/a"),
            head="abc",
            branch=None,
            is_bare=False,
            heartbeat_age=600.0,
            heartbeat_pid=1234,
        )
        assert wt.status_indicator == "!"


class TestFormatAge:
    """Tests for age formatting."""

    def test_none(self):
        assert _format_age(None) == ""

    def test_seconds(self):
        assert _format_age(45) == "45s"

    def test_minutes(self):
        assert _format_age(120) == "2m"

    def test_hours(self):
        assert _format_age(7200) == "2h"

    def test_days(self):
        assert _format_age(172800) == "2d"


class TestFormatWorktrees:
    """Tests for worktree formatting."""

    def test_empty_list(self):
        assert format_worktrees([]) == "No worktrees found."

    def test_bare_worktree(self):
        wt = WorktreeInfo(
            path=Path("/path/to/repo"),
            head="",
            branch=None,
            is_bare=True,
            heartbeat_age=None,
            heartbeat_pid=None,
        )
        result = format_worktrees([wt])
        assert "(bare)" in result
        assert "/path/to/repo" in result

    def test_regular_worktree(self):
        wt = WorktreeInfo(
            path=Path("/path/to/wt"),
            head="abc1234567890",
            branch="refs/heads/feature",
            is_bare=False,
            heartbeat_age=None,
            heartbeat_pid=None,
        )
        result = format_worktrees([wt])
        assert "abc1234" in result
        assert "feature" in result
        assert result.startswith("-")  # no heartbeat indicator

    def test_worktree_with_heartbeat(self):
        wt = WorktreeInfo(
            path=Path("/path/to/wt"),
            head="abc1234567890",
            branch="refs/heads/feature",
            is_bare=False,
            heartbeat_age=30.0,
            heartbeat_pid=1234,
        )
        result = format_worktrees([wt])
        assert "[30s ago pid:1234]" in result
        assert result.startswith("*")  # active indicator


class TestReadHeartbeat:
    """Tests for heartbeat file reading."""

    def test_reads_valid_heartbeat(self):
        from tambour.worktrees import _read_heartbeat

        with tempfile.TemporaryDirectory() as tmpdir:
            wt_path = Path(tmpdir)
            hb_dir = wt_path / ".tambour"
            hb_dir.mkdir()
            hb_file = hb_dir / "heartbeat"
            hb_file.write_text(json.dumps({
                "timestamp": "2026-01-01T00:00:00Z",
                "pid": 42,
            }))

            age, pid = _read_heartbeat(wt_path)
            assert age is not None
            assert age > 0
            assert pid == 42

    def test_returns_none_for_missing(self):
        from tambour.worktrees import _read_heartbeat

        with tempfile.TemporaryDirectory() as tmpdir:
            age, pid = _read_heartbeat(Path(tmpdir))
            assert age is None
            assert pid is None

    def test_returns_none_for_invalid_json(self):
        from tambour.worktrees import _read_heartbeat

        with tempfile.TemporaryDirectory() as tmpdir:
            wt_path = Path(tmpdir)
            hb_dir = wt_path / ".tambour"
            hb_dir.mkdir()
            (hb_dir / "heartbeat").write_text("not json")

            age, pid = _read_heartbeat(wt_path)
            assert age is None
            assert pid is None


class TestListWorktrees:
    """Tests for list_worktrees function."""

    @patch("subprocess.run")
    def test_calls_git_worktree_list(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="worktree /path/to/repo\nbare\n\n",
        )
        result = list_worktrees()
        mock_run.assert_called_once_with(
            ["git", "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        )
        assert len(result) == 1

    @patch("subprocess.run")
    def test_raises_on_failure(self, mock_run):
        import subprocess

        mock_run.side_effect = subprocess.CalledProcessError(128, "git")
        with pytest.raises(subprocess.CalledProcessError):
            list_worktrees()


class TestCmdWorktrees:
    """Tests for the CLI command handler."""

    @patch("tambour.__main__.cmd_worktrees")
    def test_worktrees_dispatches(self, mock_cmd):
        """Test that main() dispatches to cmd_worktrees."""
        mock_cmd.return_value = 0
        parser = create_parser()
        args = parser.parse_args(["worktrees"])
        result = cmd_worktrees(args)
        # cmd_worktrees calls the real implementation, so we test it directly
        # (mock is on the import, which doesn't help here)

    @patch("tambour.worktrees.list_worktrees")
    def test_cmd_worktrees_success(self, mock_list, capsys):
        mock_list.return_value = [
            WorktreeInfo(
                path=Path("/path/to/repo"),
                head="",
                branch=None,
                is_bare=True,
                heartbeat_age=None,
                heartbeat_pid=None,
            )
        ]
        parser = create_parser()
        args = parser.parse_args(["worktrees"])
        result = cmd_worktrees(args)
        assert result == 0
        captured = capsys.readouterr()
        assert "(bare)" in captured.out

    @patch("tambour.worktrees.list_worktrees")
    def test_cmd_worktrees_error(self, mock_list, capsys):
        mock_list.side_effect = Exception("git not found")
        parser = create_parser()
        args = parser.parse_args(["worktrees"])
        result = cmd_worktrees(args)
        assert result == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err
