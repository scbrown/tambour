"""Tests for the init command."""

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tambour.__main__ import cmd_init, create_parser
from tambour.init import DEFAULT_CONFIG, _get_git_root, _is_git_repo, init_tambour


class TestInitParsing:
    """Tests for CLI argument parsing."""

    def test_init_parser_exists(self):
        """Test that init subcommand is registered."""
        parser = create_parser()
        args = parser.parse_args(["init"])
        assert args.command == "init"

    def test_init_force_flag(self):
        parser = create_parser()
        args = parser.parse_args(["init", "--force"])
        assert args.force is True

    def test_init_force_flag_default(self):
        parser = create_parser()
        args = parser.parse_args(["init"])
        assert args.force is False

    def test_init_directory_flag(self):
        parser = create_parser()
        args = parser.parse_args(["init", "--directory", "/tmp/foo"])
        assert args.directory == "/tmp/foo"


class TestIsGitRepo:
    """Tests for _is_git_repo."""

    @patch("subprocess.run")
    def test_returns_true_for_git_repo(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="true\n")
        assert _is_git_repo(Path("/some/repo")) is True

    @patch("subprocess.run")
    def test_returns_false_for_non_git_dir(self, mock_run):
        mock_run.return_value = MagicMock(returncode=128, stdout="")
        assert _is_git_repo(Path("/some/dir")) is False

    @patch("subprocess.run")
    def test_passes_directory_as_cwd(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="true\n")
        _is_git_repo(Path("/my/dir"))
        mock_run.assert_called_once_with(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            cwd=Path("/my/dir"),
        )


class TestGetGitRoot:
    """Tests for _get_git_root."""

    @patch("subprocess.run")
    def test_returns_git_root_path(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="/my/repo\n")
        assert _get_git_root(Path("/my/repo/sub")) == Path("/my/repo")

    @patch("subprocess.run")
    def test_returns_none_on_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=128, stdout="")
        assert _get_git_root(Path("/not/a/repo")) is None


class TestInitTambour:
    """Tests for init_tambour."""

    @patch("tambour.init._get_git_root")
    @patch("tambour.init._is_git_repo")
    def test_creates_config_in_git_root(self, mock_is_git, mock_git_root, tmp_path):
        mock_is_git.return_value = True
        mock_git_root.return_value = tmp_path

        success, message = init_tambour(directory=tmp_path)

        assert success is True
        assert "Initialized" in message
        config_path = tmp_path / ".tambour" / "config.toml"
        assert config_path.exists()
        assert config_path.read_text() == DEFAULT_CONFIG

    @patch("tambour.init._get_git_root")
    @patch("tambour.init._is_git_repo")
    def test_fails_if_not_git_repo(self, mock_is_git, mock_git_root, tmp_path):
        mock_is_git.return_value = False

        success, message = init_tambour(directory=tmp_path)

        assert success is False
        assert "Not a git repository" in message

    @patch("tambour.init._get_git_root")
    @patch("tambour.init._is_git_repo")
    def test_fails_if_already_initialized(self, mock_is_git, mock_git_root, tmp_path):
        mock_is_git.return_value = True
        mock_git_root.return_value = tmp_path
        tambour_dir = tmp_path / ".tambour"
        tambour_dir.mkdir()
        (tambour_dir / "config.toml").write_text("existing")

        success, message = init_tambour(directory=tmp_path)

        assert success is False
        assert "Already initialized" in message
        assert "--force" in message

    @patch("tambour.init._get_git_root")
    @patch("tambour.init._is_git_repo")
    def test_force_overwrites_existing(self, mock_is_git, mock_git_root, tmp_path):
        mock_is_git.return_value = True
        mock_git_root.return_value = tmp_path
        tambour_dir = tmp_path / ".tambour"
        tambour_dir.mkdir()
        (tambour_dir / "config.toml").write_text("old config")

        success, message = init_tambour(directory=tmp_path, force=True)

        assert success is True
        assert (tambour_dir / "config.toml").read_text() == DEFAULT_CONFIG

    @patch("tambour.init._get_git_root")
    @patch("tambour.init._is_git_repo")
    def test_creates_tambour_directory(self, mock_is_git, mock_git_root, tmp_path):
        mock_is_git.return_value = True
        mock_git_root.return_value = tmp_path

        success, _ = init_tambour(directory=tmp_path)

        assert success is True
        assert (tmp_path / ".tambour").is_dir()

    def test_fails_if_not_a_directory(self, tmp_path):
        fake_file = tmp_path / "not_a_dir"
        fake_file.write_text("hello")

        success, message = init_tambour(directory=fake_file)

        assert success is False
        assert "Not a directory" in message

    @patch("tambour.init._get_git_root")
    @patch("tambour.init._is_git_repo")
    def test_git_root_none_returns_error(self, mock_is_git, mock_git_root, tmp_path):
        mock_is_git.return_value = True
        mock_git_root.return_value = None

        success, message = init_tambour(directory=tmp_path)

        assert success is False
        assert "Could not determine git root" in message


class TestDefaultConfig:
    """Tests for the default config content."""

    def test_default_config_is_valid_toml(self):
        import tomllib

        data = tomllib.loads(DEFAULT_CONFIG)
        assert data["tambour"]["version"] == "1"
        assert data["agent"]["default_cli"] == "claude"
        assert data["daemon"]["health_interval"] == 60
        assert data["daemon"]["zombie_threshold"] == 300
        assert data["daemon"]["auto_recover"] is False
        assert data["worktree"]["base_path"] == "../{repo}-worktrees"

    def test_default_config_loadable_by_config_class(self, tmp_path):
        from tambour.config import Config

        config_dir = tmp_path / ".tambour"
        config_dir.mkdir()
        config_path = config_dir / "config.toml"
        config_path.write_text(DEFAULT_CONFIG)

        config = Config.load(config_path)
        assert config.version == "1"
        assert config.agent.default_cli == "claude"
        assert config.daemon.health_interval == 60


class TestCmdInit:
    """Tests for the cmd_init CLI handler."""

    @patch("tambour.init.init_tambour")
    def test_returns_zero_on_success(self, mock_init):
        mock_init.return_value = (True, "Initialized tambour")
        args = argparse.Namespace(directory=None, force=False)
        assert cmd_init(args) == 0

    @patch("tambour.init.init_tambour")
    def test_returns_one_on_failure(self, mock_init):
        mock_init.return_value = (False, "Already initialized")
        args = argparse.Namespace(directory=None, force=False)
        assert cmd_init(args) == 1

    @patch("tambour.init.init_tambour")
    def test_passes_force_flag(self, mock_init):
        mock_init.return_value = (True, "Initialized")
        args = argparse.Namespace(directory=None, force=True)
        cmd_init(args)
        mock_init.assert_called_once_with(directory=None, force=True)

    @patch("tambour.init.init_tambour")
    def test_passes_directory(self, mock_init):
        mock_init.return_value = (True, "Initialized")
        args = argparse.Namespace(directory="/tmp/foo", force=False)
        cmd_init(args)
        mock_init.assert_called_once_with(directory=Path("/tmp/foo"), force=False)

    @patch("tambour.init.init_tambour", return_value=(True, "ok"))
    def test_prints_message(self, mock_init, capsys):
        args = argparse.Namespace(directory=None, force=False)
        cmd_init(args)
        captured = capsys.readouterr()
        assert "ok" in captured.out
