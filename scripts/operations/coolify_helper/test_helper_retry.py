"""Execute the actual PHP-generated Bash against synthetic Docker; no live Docker.

PHP_COMMAND_JSON may name an operator-provided pure-PHP stdin runner when PHP
is unavailable locally. It must execute stdin as PHP and return stdout unchanged.
"""

import base64
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
PHP = json.loads(os.environ["PHP_COMMAND_JSON"]) if "PHP_COMMAND_JSON" in os.environ else [shutil.which("php") or "php"]
BASH = os.environ.get("BASH_EXECUTABLE") or shutil.which("bash")
PHP_AVAILABLE = "PHP_COMMAND_JSON" in os.environ or shutil.which("php") is not None


def php(code):
    """Load only these pure functions, without Laravel, configuration, or secrets."""
    files = [HERE / "helper_retry.php", HERE / "apply_patch.php"]
    definitions = "\n".join(path.read_text(encoding="utf-8").removeprefix("<?php\n") for path in files)
    source = (
        "<?php\ndefine('COOLIFY_HELPER_PATCH_LIBRARY_ONLY', true);\n"
        "function escapeShellValue(string $v): string { return chr(39).str_replace(chr(39), chr(39).chr(92).chr(39).chr(39), $v).chr(39); }\n"
        "eval(base64_decode('" + base64.b64encode(definitions.encode()).decode() + "'));\n" + code
    )
    result = subprocess.run(PHP, input=source, text=True, encoding="utf-8", capture_output=True, timeout=15, check=True)
    return result.stdout


def php_value(value):
    return "json_decode(base64_decode('" + base64.b64encode(json.dumps(value).encode()).decode() + "'), true, 512, JSON_THROW_ON_ERROR)"


def generated(command="docker run --name helper-test image", name="helper-test", timeout=1):
    return php(f"$v={php_value([command, name, timeout])}; echo dockerRunWithNameConflictRetryCommand(...$v);")


@unittest.skipUnless(PHP_AVAILABLE and BASH, "PHP and Bash required; see README for an isolated stdin runner")
class HelperCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.command = generated()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="coolify-helper-test-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.count = self.directory / "count"
        self.arguments = self.directory / "arguments"
        self.occupant = self.directory / "original-occupant"
        self.occupant.write_text("original immutable container identity", encoding="utf-8")

    def run_fake(self, behavior, command=None):
        docker = self.directory / "docker"
        docker.write_text(
            "#!/bin/bash\ncase \"$1\" in rm|rename|stop) rm -f \"$OCCUPANT_FILE\"; echo 'forbidden destructive operation' >&2; exit 99 ;; run) ;; *) exit 98 ;; esac\n"
            "count=0\nif [ -f \"$COUNT_FILE\" ]; then count=$(cat \"$COUNT_FILE\"); fi\n"
            "count=$((count + 1))\nprintf '%s' \"$count\" > \"$COUNT_FILE\"\n"
            "printf '%s\\n' \"$@\" > \"$ARGUMENT_FILE\"\n" + behavior + "\n",
            encoding="utf-8", newline="\n",
        )
        docker.chmod(0o755)
        sudo = self.directory / "sudo"
        sudo.write_text('#!/bin/sh\nexec "$@"\n', encoding="utf-8", newline="\n")
        sudo.chmod(0o755)
        env = {**os.environ, "COUNT_FILE": str(self.count), "ARGUMENT_FILE": str(self.arguments), "OCCUPANT_FILE": str(self.occupant), "FAKE_DIRECTORY": str(self.directory)}
        # Git Bash converts Windows paths for its PATH lookup; Linux needs no conversion.
        prefix = 'if command -v cygpath >/dev/null 2>&1; then fake=$(cygpath -u "$FAKE_DIRECTORY"); else fake="$FAKE_DIRECTORY"; fi; export PATH="$fake:$PATH"; '
        return subprocess.run([BASH, "-c", prefix + (command or self.command)], env=env, text=True, capture_output=True, timeout=6)

    @staticmethod
    def conflict(name="helper-test"):
        return f"printf '%s\\n' 'docker: Error response from daemon: Conflict. The container name \"/{name}\" is already in use by container \"original-id\".' >&2; exit 125"

    def test_delayed_name_release_retries_and_preserves_stdout_and_occupant(self):
        before = self.occupant.read_bytes()
        result = self.run_fake('if [ "$count" -lt 3 ]; then ' + self.conflict() + '; fi; printf "replacement-id\\n"', generated(timeout=5))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "replacement-id\n")
        self.assertEqual(self.count.read_text(), "3")
        self.assertEqual(self.occupant.read_bytes(), before)

    def test_persistent_conflict_is_bounded_and_preserves_original(self):
        before = self.occupant.read_bytes()
        result = self.run_fake(self.conflict())
        self.assertEqual(result.returncode, 124)
        self.assertIn("existing container preserved", result.stderr)
        # Coarse integer-second timing may exhaust the deadline on the first conflict.
        self.assertGreaterEqual(int(self.count.read_text()), 1)
        self.assertEqual(self.occupant.read_bytes(), before)

    def test_unrelated_docker_failure_is_not_retried(self):
        result = self.run_fake("echo 'Cannot connect to the Docker daemon' >&2; exit 1")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.count.read_text(), "1")
        self.assertIn("Cannot connect", result.stderr)

    def test_different_container_conflict_is_not_retried(self):
        result = self.run_fake(self.conflict("another-helper"))
        self.assertEqual(result.returncode, 125)
        self.assertEqual(self.count.read_text(), "1")

    def test_conflict_text_with_wrong_exit_code_is_not_retried(self):
        result = self.run_fake(self.conflict().replace("exit 125", "exit 42"))
        self.assertEqual(result.returncode, 42)
        self.assertEqual(self.count.read_text(), "1")

    def test_original_quoted_arguments_survive_retries(self):
        secret = "synthetic a'b $c;d `literal` \"quoted\""
        command = generated("docker run --name helper-test -e " + shlex.quote("SECRET=" + secret) + " image", timeout=5)
        result = self.run_fake('if [ "$count" -lt 2 ]; then ' + self.conflict() + '; fi; echo replacement-id', command)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.arguments.read_text().splitlines(), ["run", "--name", "helper-test", "-e", "SECRET=" + secret, "image"])

    def test_successful_slow_start_is_not_treated_as_conflict_timeout(self):
        result = self.run_fake("sleep 1.2; echo replacement-id")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.count.read_text(), "1")

    def test_non_root_sudo_rewrite_keeps_bash_control_flow_valid(self):
        # These are the exact command rewrites in Coolify v4.1.2 parseLineForSudo.
        # The wrapper receives one sudo; command substitution receives docker's sudo.
        command = "sudo " + generated(timeout=5)
        command = command.replace("$(", "$(sudo ").replace("`", "`sudo ")
        command = command.replace("||", "|| sudo ").replace("&&", "&& sudo ")
        self.assertNotIn("sudo (", command)
        self.assertNotIn("sudo exit", command)
        self.assertIn("$(sudo docker run", command)
        result = self.run_fake('if [ "$count" -lt 2 ]; then ' + self.conflict() + '; fi; echo replacement-id', command)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.count.read_text(), "2")

    def test_invalid_retry_inputs_fail_before_any_command(self):
        value = php("$out=[]; foreach ([['bad;name',1], ['helper-test',0], ['helper-test',61]] as [$n,$t]) { try { dockerRunWithNameConflictRetryCommand('docker run image',$n,$t); $out[]=false; } catch (InvalidArgumentException $e) { $out[]=true; } } echo json_encode($out);")
        self.assertEqual(json.loads(value), [True, True, True])


@unittest.skipUnless(PHP_AVAILABLE, "PHP required")
class PatchGuardTests(unittest.TestCase):
    def fixture(self):
        job = """<?php
    private function prepare_builder_image(bool $firstTry = true)
    {
        $this->graceful_shutdown_container($this->deployment_uuid, skipRemove: true);
        $this->execute_remote_command(
            [
                $runCommand,
                'hidden' => true,
            ],
        );
    }
    private function restart_builder_container_with_actual_commit()
    {
        // Stop the current helper container (no need for rm -f as it was started with --rm)
        $this->graceful_shutdown_container($this->deployment_uuid, skipRemove: true);

        $this->env_args = null;
        $this->prepare_builder_image(firstTry: false);
    }
"""
        return {"app/Jobs/ApplicationDeploymentJob.php": job, "bootstrap/helpers/docker.php": "<?php\nfunction syntheticOriginalHelper() {}\n"}

    def invoke_patch(self, alteration=""):
        sources = self.fixture()
        fragment = (HERE / "helper_retry.php").read_text(encoding="utf-8")
        code = f"$sources={php_value(sources)}; $retry={php_value(fragment)}; $expected=[]; foreach($sources as $p=>$s) $expected[$p]=hash('sha256',$s); "
        code += alteration + " try { $patched=patchCoolifyHelperSources($sources,$retry,$expected); echo json_encode(['patched'=>$patched]); } catch (RuntimeException $e) { echo json_encode(['error'=>$e->getMessage()]); }"
        return json.loads(php(code))

    def test_exact_inputs_transform_once_and_remove_duplicate_stop(self):
        patched = self.invoke_patch()["patched"]
        job = patched["app/Jobs/ApplicationDeploymentJob.php"]
        self.assertEqual(job.count("dockerRunWithNameConflictRetryCommand($runCommand, $this->deployment_uuid)"), 1)
        self.assertEqual(job.count("graceful_shutdown_container($this->deployment_uuid, skipRemove: true)"), 1)
        self.assertEqual(patched["bootstrap/helpers/docker.php"].count("function dockerRunWithNameConflictRetryCommand("), 1)

    def test_either_source_drift_rejects_every_output(self):
        for path in self.fixture():
            with self.subTest(path=path):
                result = self.invoke_patch(f"$sources[{php_value(path)}].='drift';")
                self.assertNotIn("patched", result)
                self.assertIn("source hash mismatch", result["error"])

    def test_already_patched_sources_reject_original_hashes(self):
        result = self.invoke_patch("$sources=patchCoolifyHelperSources($sources,$retry,$expected);")
        self.assertNotIn("patched", result)
        self.assertIn("source hash mismatch", result["error"])

    def test_duplicate_anchor_rejects_even_with_matching_fixture_hashes(self):
        path = "app/Jobs/ApplicationDeploymentJob.php"
        result = self.invoke_patch(f"$sources[{php_value(path)}].=$sources[{php_value(path)}]; $expected[{php_value(path)}]=hash('sha256',$sources[{php_value(path)}]);")
        self.assertNotIn("patched", result)
        self.assertIn("anchor mismatch", result["error"])


if __name__ == "__main__":
    unittest.main()
