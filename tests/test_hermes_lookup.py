"""Tests for jupyter-ai-hermes hermes executable lookup.

The _hermes_path variable is evaluated at import time, so we run each
test in a subprocess to get a fresh module state.
"""

import os
import stat
import subprocess
import sys
import tempfile

import pytest


def _create_executable(parent: str, name: str) -> str:
    """Create a dummy executable script."""
    os.makedirs(parent, exist_ok=True)
    path = os.path.join(parent, name)
    with open(path, "w") as f:
        f.write("#!/bin/sh\nexit 0\n")
    os.chmod(path, stat.S_IRWXU)
    return path


def _run_import(hermes_path: str | None, env_path: str | None) -> tuple[str, str]:
    """Import jupyter_ai_hermes.hermes in a subprocess with controlled PATH.

    Returns (stdout, stderr).
    """
    hermes_dir = os.path.dirname(hermes_path) if hermes_path else None

    env = os.environ.copy()
    if env_path is not None:
        env["HERMES_BIN_PATH"] = env_path
    elif "HERMES_BIN_PATH" in env:
        del env["HERMES_BIN_PATH"]

    if hermes_dir:
        env["PATH"] = hermes_dir + os.pathsep + env.get("PATH", "")

    pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = f"""
import sys
sys.path.insert(0, {pkg_dir!r})
import jupyter_ai_hermes.hermes
print(jupyter_ai_hermes.hermes._hermes_path)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, env=env, timeout=10,
    )
    return result.stdout.strip(), result.stderr


class TestHermesPath:
    """Test _hermes_path resolves the hermes binary correctly."""

    def test_env_var_overrides_path(self, tmp_path):
        """HERMES_BIN_PATH takes precedence over PATH lookup."""
        path_bin = _create_executable(str(tmp_path / "pathdir"), "hermes")
        env_bin = _create_executable(str(tmp_path / "envdir"), "hermes")

        stdout, stderr = _run_import(path_bin, env_bin)
        assert stdout == env_bin, f"HERMES_BIN_PATH should override PATH; got {stdout!r}; stderr: {stderr}"

    def test_hermes_bin_path_fallback(self, tmp_path):
        """HERMES_BIN_PATH is used when hermes is not on PATH."""
        fake_bin = _create_executable(str(tmp_path), "hermes")

        stdout, stderr = _run_import(None, fake_bin)
        assert stdout == fake_bin, f"Expected {fake_bin!r}, got {stdout!r}; stderr: {stderr}"

    def test_raises_when_missing(self, tmp_path):
        """PersonaRequirementsUnmet is raised when neither PATH nor env var works."""
        env_path = str(tmp_path / "nonexistent")

        stdout, stderr = _run_import(None, env_path)
        assert "PersonaRequirementsUnmet" in stderr
        assert "hermes" in stderr.lower()

    def test_path_fallback_when_no_env_var(self, tmp_path):
        """shutil.which is used when HERMES_BIN_PATH is not set."""
        path_bin = _create_executable(str(tmp_path / "pathdir"), "hermes")

        stdout, stderr = _run_import(path_bin, None)
        assert stdout == path_bin, f"Expected {path_bin!r}, got {stdout!r}; stderr: {stderr}"
