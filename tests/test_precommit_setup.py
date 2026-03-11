"""Tests for repository linting and git hook configuration."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_dev_dependencies_include_ruff_and_pre_commit():
    pyproject = (REPO_ROOT / "pyproject.toml").read_text()

    assert '"ruff>=' in pyproject
    assert '"pre-commit>=' in pyproject


def test_pre_commit_config_runs_ruff():
    config = (REPO_ROOT / ".pre-commit-config.yaml").read_text()

    assert "https://github.com/psf/black" in config
    assert "\n      - id: black\n" in config
    assert "astral-sh/ruff-pre-commit" in config
    assert "ruff-check" in config
    assert "--fix" not in config


def test_ruff_ignores_line_length_to_match_black():
    pyproject = (REPO_ROOT / "pyproject.toml").read_text()

    assert 'ignore = ["E501"]' in pyproject


def test_makefile_has_hook_install_target():
    makefile = (REPO_ROOT / "Makefile").read_text()

    assert ".PHONY: install-git-hooks" in makefile
    assert "uv run pre-commit install" in makefile
