"""Check the effective Compose recipe, with synthetic configuration only."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(shutil.which("docker"), "Docker Compose is required")
class StagingRecipeTests(unittest.TestCase):
    def test_effective_recipe_isolated_from_production(self):
        with tempfile.TemporaryDirectory() as temporary:
            env_file = Path(temporary) / "synthetic.env"
            env_file.write_text("", encoding="utf-8")
            environment = {
                **os.environ,
                "STAGING_DATABASE_PASSWORD": "synthetic-database-password",
                "STAGING_SECRET_KEY": "synthetic-staging-signing-key",
                "STAGING_HOSTNAME": "staging.example.invalid",
                "STAGING_ORIGIN": "https://staging.example.invalid",
                # These must not enter the service environment through Compose.
                "DATABASE_URL": "postgres://production.invalid/production",
                "AWS_ACCESS_KEY_ID": "synthetic-production-key",
                "ANTHROPIC_API_KEY": "synthetic-production-ai-key",
            }
            result = subprocess.run(
                ["docker", "compose", "--env-file", str(env_file), "-f",
                 str(ROOT / "docker-compose.staging.yml"), "config", "--format", "json"],
                env=environment, capture_output=True, text=True, check=True,
            )
        config = json.loads(result.stdout)
        self.assertEqual(set(config["services"]), {"db", "redis", "django"})
        app = config["services"]["django"]
        env = app["environment"]
        self.assertEqual(env["DATABASE_URL"], "postgresql://abby_staging:synthetic-database-password@db:5432/abby_staging")
        self.assertEqual(env["ABBY_STAGING"], "true")
        self.assertEqual(env["DEBUG"], "false")
        self.assertEqual(env["ALLOW_PARENT_SIGNUP"], "false")
        self.assertEqual(env["EMAIL_BACKEND"], "django.core.mail.backends.dummy.EmailBackend")
        self.assertEqual(env["USE_S3_STORAGE"], "false")
        self.assertFalse(any("AWS" in key or "ANTHROPIC" in key for key in env))
        self.assertFalse(app.get("volumes"))
        self.assertFalse(app.get("ports"))
        self.assertFalse(app.get("env_file"))
        self.assertFalse(any(volume.get("external") for volume in config["volumes"].values()))
        self.assertTrue(all(not service.get("container_name") for service in config["services"].values()))


if __name__ == "__main__":
    unittest.main()
