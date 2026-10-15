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
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as temporary:
            env_file = Path(temporary) / "synthetic.env"
            env_file.write_text("", encoding="utf-8")
            environment = {
                **os.environ,
                "STAGING_DATABASE_PASSWORD": "synthetic-database-password",
                "STAGING_SECRET_KEY": "synthetic-staging-signing-key",
                "STAGING_HOSTNAME": "staging.example.invalid",
                "STAGING_ORIGIN": "https://staging.example.invalid",
                "STAGING_POSTGRES_VOLUME": "synthetic-existing-staging-postgres",
                "SOURCE_COMMIT": "0123456789abcdef0123456789abcdef01234567",
                # These must not enter the service environment through Compose.
                "DATABASE_URL": "postgres://production.invalid/production",
                "AWS_ACCESS_KEY_ID": "synthetic-production-key",
                "ANTHROPIC_API_KEY": "synthetic-production-ai-key",
            }
            def render(recipe, values):
                result = subprocess.run(
                    ["docker", "compose", "--env-file", str(env_file), "-f",
                     str(ROOT / recipe), "config", "--format", "json"],
                    env=values, capture_output=True, text=True, check=True,
                )
                return json.loads(result.stdout)

            cls.recipes = {
                recipe: render(recipe, environment)
                for recipe in ["docker-compose.staging.yml", "docker-compose.staging-cloudflare.yml"]
            }
            build_environment = dict(environment)
            build_environment.pop("SOURCE_COMMIT")
            cls.build_config = render("docker-compose.staging-cloudflare.yml", build_environment)
        cls.config = cls.recipes["docker-compose.staging.yml"]

    def test_effective_recipe_isolated_from_production(self):
        config = self.config
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

    def test_origin_gate_uses_transport_peer_and_canonical_https_headers(self):
        services = self.recipes["docker-compose.staging-cloudflare.yml"]["services"]
        self.assertTrue(all(not service.get("ports") for service in services.values()))
        self.assertFalse(services["db"].get("labels"))
        self.assertFalse(services["redis"].get("labels"))
        labels = services["django"]["labels"]
        self.assertEqual(labels["traefik.http.middlewares.abby-staging-origin.ipallowlist.sourcerange"], "10.0.1.1/32")
        self.assertEqual(labels["traefik.http.middlewares.abby-staging-https.headers.customrequestheaders.X-Forwarded-Proto"], "https")
        self.assertEqual(labels["traefik.http.middlewares.abby-staging-https.headers.customrequestheaders.X-Forwarded-Host"], "staging.example.invalid")
        self.assertEqual(labels["traefik.http.middlewares.abby-staging-https.headers.customrequestheaders.X-Forwarded-Port"], "443")
        self.assertEqual(labels["traefik.http.middlewares.abby-staging-https.headers.customrequestheaders.Forwarded"], "")
        routers = {key for key in labels if key.startswith("traefik.http.routers.")}
        self.assertEqual(routers, {
            "traefik.http.routers.abby-staging.entrypoints",
            "traefik.http.routers.abby-staging.rule",
            "traefik.http.routers.abby-staging.service",
            "traefik.http.routers.abby-staging.middlewares",
        })
        self.assertEqual(labels["traefik.http.routers.abby-staging.rule"], "Host(`staging.example.invalid`)")
        self.assertEqual(labels["traefik.http.routers.abby-staging.entrypoints"], "http")
        self.assertEqual(labels["traefik.http.routers.abby-staging.middlewares"], "abby-staging-origin,abby-staging-https,abby-staging-gzip")
        self.assertEqual(labels["traefik.http.services.abby-staging.loadbalancer.server.port"], "8000")
        self.assertEqual(labels["traefik.docker.network"], "coolify")
        # No ipStrategy.depth/excludedIPs: Traefik must use the real socket peer.
        self.assertFalse(any("ipstrategy" in key.lower() for key in labels))

    def test_raw_cloudflare_recipe_preserves_isolation_and_existing_database(self):
        config = self.recipes["docker-compose.staging-cloudflare.yml"]
        self.assertEqual(set(config["services"]), {"db", "redis", "django"})
        for name, service in config["services"].items():
            with self.subTest(service=name):
                self.assertFalse(service.get("env_file"))
                self.assertFalse(service.get("ports"))
                expected = dict(self.config["services"][name].get("environment", {}))
                if name == "django":
                    expected["SOURCE_COMMIT"] = "0123456789abcdef0123456789abcdef01234567"
                    expected["DATABASE_URL"] = "postgresql://abby_staging:synthetic-database-password@abby-staging-db:5432/abby_staging"
                    expected["REDIS_URL"] = "redis://abby-staging-redis:6379/0"
                    expected["CELERY_BROKER_URL"] = "redis://abby-staging-redis:6379/1"
                self.assertEqual(service.get("environment", {}), expected)
                self.assertEqual(set(service["networks"]), {"default", "coolify"} if name == "django" else {"default"})
                self.assertFalse(service.get("secrets"))
        self.assertEqual(config["volumes"]["staging_postgres"], {
            "name": "synthetic-existing-staging-postgres", "external": True,
        })
        self.assertEqual(config["networks"]["coolify"]["name"], "coolify")
        self.assertTrue(config["networks"]["coolify"]["external"])
        build_secrets = config["services"]["django"]["build"]["secrets"]
        expected_secrets = {
            "ABBY_ASSETS_S3_ENDPOINT", "ABBY_ASSETS_S3_REGION", "ABBY_ASSETS_S3_BUCKET",
            "ABBY_ASSETS_S3_PREFIX", "ABBY_ASSETS_ACCESS_KEY_ID", "ABBY_ASSETS_SECRET_ACCESS_KEY",
            "ABBY_SHARED_ASSETS_REQUIRED", "VITE_ALLOW_SIGNUP",
        }
        self.assertEqual({secret["source"] for secret in build_secrets}, expected_secrets)
        self.assertEqual(set(config["secrets"]), expected_secrets)
        self.assertTrue(all(secret.get("environment") == name and not secret.get("file") for name, secret in config["secrets"].items()))
        self.assertTrue(all(not service.get("labels") for service in self.config["services"].values()))

    def test_private_service_aliases_are_not_shared_with_the_proxy_network(self):
        services = self.recipes["docker-compose.staging-cloudflare.yml"]["services"]
        self.assertEqual(services["db"]["networks"]["default"]["aliases"], ["abby-staging-db"])
        self.assertEqual(services["redis"]["networks"]["default"]["aliases"], ["abby-staging-redis"])
        self.assertEqual(set(services["db"]["networks"]), {"default"})
        self.assertEqual(set(services["redis"]["networks"]), {"default"})

    def test_raw_build_interpolation_can_omit_the_runtime_commit(self):
        self.assertIsNone(self.build_config["services"]["django"]["environment"].get("SOURCE_COMMIT"))


if __name__ == "__main__":
    unittest.main()
