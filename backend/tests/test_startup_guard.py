# ─── Regression test for issue #26 ───────────────────────────
# The JWT import-order bug escaped several audit rounds because the
# internal test harness always set real process env vars. These tests
# therefore spawn *clean subprocesses* with JWT_SECRET present ONLY in
# a .env file — the documented quick-start configuration:
#
#   (a) the effective signing secret captured at import time must be
#       the .env value, not the public development fallback; and
#   (b) the app must refuse to start (RuntimeError from the lifespan
#       guard) when the secret resolves to the development default —
#       before any database access.
import os
import subprocess
import sys
import textwrap
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEV_DEFAULT = "pmas-dev-secret-change-in-production"


def _run_in_tmp_env(tmp_path, env_file_content, code):
    """Run a Python snippet in a clean subprocess whose cwd holds only .env."""
    (tmp_path / ".env").write_text(env_file_content)
    clean_env = {
        k: v for k, v in os.environ.items()
        if k not in ("JWT_SECRET", "CORS_ORIGINS", "DATABASE_URL")
    }
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=tmp_path,
        env=clean_env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_env_file_secret_is_captured_at_import(tmp_path):
    """(.env-only secret) auth must sign with the .env value, not the fallback (#26)."""
    secret = "env-file-only-secret-0123456789abcdef"
    code = f"""
        import sys
        sys.path.insert(0, r"{BACKEND_DIR}")
        import main, auth
        assert auth.JWT_SECRET == {secret!r}, (
            "auth captured: %r — the .env value was not loaded before the "
            "auth import (regression of #26)" % auth.JWT_SECRET
        )
        print("OK")
    """
    result = _run_in_tmp_env(
        tmp_path,
        f"JWT_SECRET={secret}\nCORS_ORIGINS=http://localhost:5500\n",
        code,
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_refuses_to_start_with_dev_default_secret(tmp_path):
    """(.env containing the public dev default) lifespan must raise before DB access."""
    code = f"""
        import asyncio, sys
        sys.path.insert(0, r"{BACKEND_DIR}")
        import main

        async def enter_lifespan():
            async with main.lifespan(main.app):
                pass

        try:
            asyncio.run(enter_lifespan())
        except RuntimeError as exc:
            if "development default" in str(exc):
                sys.exit(0)
        sys.exit(1)
    """
    result = _run_in_tmp_env(
        tmp_path,
        f"JWT_SECRET={DEV_DEFAULT}\nCORS_ORIGINS=http://localhost:5500\n",
        code,
    )
    assert result.returncode == 0, result.stderr


def test_missing_secret_refuses_to_start(tmp_path):
    """(no secret anywhere) the original guard must still trip."""
    code = f"""
        import asyncio, sys
        sys.path.insert(0, r"{BACKEND_DIR}")
        import main

        async def enter_lifespan():
            async with main.lifespan(main.app):
                pass

        try:
            asyncio.run(enter_lifespan())
        except RuntimeError as exc:
            if "JWT_SECRET is not set" in str(exc):
                sys.exit(0)
        sys.exit(1)
    """
    result = _run_in_tmp_env(tmp_path, "CORS_ORIGINS=http://localhost:5500\n", code)
    assert result.returncode == 0, result.stderr
