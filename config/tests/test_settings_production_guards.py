"""Boot-time guards on insecure defaults (audit C4 + H12).

Settings module evaluation has to be done in a clean Python process so the
environment patching takes effect — ``settings.py`` runs once at import,
and Django modules already loaded by the test runner have it cached.

Each test below shells out a one-line ``import config.settings``, with a
controlled environment, and asserts the import either succeeds or raises
``ImproperlyConfigured``.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import unittest


def _import_settings_with_env(env: dict[str, str]) -> subprocess.CompletedProcess:
    """Run ``python -c 'import config.settings'`` with the given env."""
    cwd = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    code = textwrap.dedent(
        """
        import sys
        try:
            import config.settings  # noqa: F401
            sys.exit(0)
        except Exception as exc:
            sys.stderr.write(f"{type(exc).__name__}: {exc}\\n")
            sys.exit(2)
        """,
    )
    # Inherit only the platform-bootstrap vars (PATH on every OS, SystemRoot/
    # WINDIR/LOCALAPPDATA on Windows so Python's networking subsystem loads).
    # We deliberately drop the developer's shell-set SECRET_KEY/DATABASE_URL
    # so the test sees a clean environment.
    _BOOTSTRAP_KEYS = (
        "PATH", "SystemRoot", "WINDIR", "LOCALAPPDATA", "TEMP", "TMP",
        "PYTHONPATH", "HOME", "USERPROFILE",
    )
    clean_env = {k: os.environ[k] for k in _BOOTSTRAP_KEYS if k in os.environ}
    clean_env.update(env)
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=cwd,
        env=clean_env,
        capture_output=True,
        text=True,
        timeout=30,
    )


class ProductionBootGuardTests(unittest.TestCase):
    """Audit C4 + H12: production must refuse to boot on insecure defaults."""

    def test_debug_false_with_no_secret_key_refuses_to_boot(self):
        result = _import_settings_with_env({
            "DEBUG": "False",
            "DATABASE_URL": "postgres://x:y@h/db",
        })
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("ImproperlyConfigured", result.stderr)
        self.assertIn("SECRET_KEY", result.stderr)

    def test_debug_false_with_insecure_secret_key_refuses_to_boot(self):
        result = _import_settings_with_env({
            "DEBUG": "False",
            "SECRET_KEY": "django-insecure-anything",
            "DATABASE_URL": "postgres://x:y@h/db",
        })
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("ImproperlyConfigured", result.stderr)
        self.assertIn("SECRET_KEY", result.stderr)

    def test_debug_false_with_no_database_url_refuses_to_boot(self):
        result = _import_settings_with_env({
            "DEBUG": "False",
            "SECRET_KEY": "a-real-key-32-chars-long-aaaaaaaaaa",
        })
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("ImproperlyConfigured", result.stderr)
        self.assertIn("DATABASE_URL", result.stderr)

    def test_debug_false_with_strong_secret_key_and_database_url_boots(self):
        result = _import_settings_with_env({
            "DEBUG": "False",
            "SECRET_KEY": "a-real-key-32-chars-long-aaaaaaaaaa",
            "DATABASE_URL": "postgres://x:y@h/db",
        })
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_debug_true_falls_back_to_dev_defaults(self):
        # Local dev convenience — no env vars at all should still boot
        # (with explicit "DO-NOT-USE" placeholders).
        result = _import_settings_with_env({"DEBUG": "True"})
        self.assertEqual(result.returncode, 0, result.stderr)


class EmailBackendDefaultTests(unittest.TestCase):
    """Audit H11: production must default to SMTP backend, not console."""

    def _read_email_backend(self, env: dict[str, str]) -> str:
        cwd = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        code = textwrap.dedent(
            """
            from django.conf import settings
            print(settings.EMAIL_BACKEND)
            """,
        )
        full_env = {k: os.environ[k] for k in (
            "PATH", "SystemRoot", "WINDIR", "LOCALAPPDATA", "TEMP", "TMP",
            "PYTHONPATH", "HOME", "USERPROFILE",
        ) if k in os.environ}
        full_env["DJANGO_SETTINGS_MODULE"] = "config.settings"
        full_env.update(env)
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=cwd,
            env=full_env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise AssertionError(result.stderr)
        return result.stdout.strip()

    def test_debug_false_defaults_to_smtp_backend(self):
        backend = self._read_email_backend({
            "DEBUG": "False",
            "SECRET_KEY": "a-real-key-32-chars-long-aaaaaaaaaa",
            "DATABASE_URL": "postgres://x:y@h/db",
        })
        self.assertEqual(backend, "django.core.mail.backends.smtp.EmailBackend")

    def test_debug_true_defaults_to_console_backend(self):
        backend = self._read_email_backend({"DEBUG": "True"})
        self.assertEqual(backend, "django.core.mail.backends.console.EmailBackend")
