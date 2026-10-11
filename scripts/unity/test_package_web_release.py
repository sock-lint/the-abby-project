"""Release tests use synthetic exports and private art, never purchased files."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("package_web_release", Path(__file__).with_name("package_web_release.py"))
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class WebReleaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="abby-release-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.project = self.repo / "unity/AbbyCamp"
        self.write(self.repo / ".gitignore", "unity/AbbyCamp/Assets/ThirdParty/Meshtint*\nunity/AbbyCamp/Assets/AbbyCamp/Licensed*\n")
        self.write(self.project / "ProjectSettings/ProjectVersion.txt", "m_EditorVersion: 6000.6.5f1\n")
        self.write(self.project / "Assets/AbbyCamp/Scenes/Camp.unity", "synthetic public scene")
        self.git("init", "-q")
        self.git("config", "user.name", "Synthetic release test")
        self.git("config", "user.email", "synthetic@example.invalid")
        self.git("remote", "add", "origin", "https://github.com/sock-lint/the-abby-project.git")
        self.git("add", ".")
        self.git("commit", "-qm", "synthetic source")
        self.commit = self.git("rev-parse", "HEAD").strip()
        self.write(self.project / release.LICENSED_SCENE, "synthetic licensed scene")
        self.write(self.project / (release.LICENSED_SCENE + ".meta"), "guid: synthetic-scene")
        self.write(self.project / "Assets/ThirdParty/Meshtint/bird.fbx", "synthetic model")
        self.write(self.project / "Assets/ThirdParty/Meshtint/bird.fbx.meta", "guid: synthetic-model")
        for relative in release.PRIVATE_PATHS:
            if relative.endswith(".meta"):
                self.write(self.project / relative, "guid: synthetic-folder")
        self.export = self.root / "export"
        self.runtime = {
            "data": "Build/" + "1" * 32 + ".data",
            "framework": "Build/" + "2" * 32 + ".framework.js",
            "wasm": "Build/" + "3" * 32 + ".wasm",
            "loader": "Build/" + "4" * 32 + ".loader.js",
        }
        for path in self.runtime.values():
            self.write(self.export / path, "compiled synthetic bytes: " + path)
        self.write(self.export / "TemplateData/phone.css", "body { color: blue }")
        self.write(self.export / "index.html", self.html())
        self.output = self.root / "package"
        self.digest = release.private_assets_digest(self.project)

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], text=True, stderr=subprocess.DEVNULL)

    def html(self):
        return ('<html><link href="TemplateData/phone.css"><canvas id="unity-canvas"></canvas><script>'
                f"const config = {{ dataUrl: '{self.runtime['data']}', frameworkUrl: '{self.runtime['framework']}', codeUrl: '{self.runtime['wasm']}' }};"
                f"loader.src = '{self.runtime['loader']}';</script></html>")

    def package(self, **overrides):
        options = dict(repository=self.repo, export=self.export, output=self.output, source_commit=self.commit,
                       run_id="12345", run_attempt="2", licensed_assets_digest=self.digest)
        options.update(overrides)
        return release.package_release(**options)

    def test_packages_only_compiled_files_and_identical_manifest(self):
        manifest = self.package()
        self.assertEqual(manifest["source_commit"], self.commit)
        self.assertEqual(manifest["release_id"], f"{self.commit}-12345-2")
        self.assertEqual(manifest["repository"], "sock-lint/the-abby-project")
        self.assertEqual(manifest["scene"]["sha256"], release.sha256(self.project / release.LICENSED_SCENE))
        self.assertEqual(manifest["runtime_files"], self.runtime)
        self.assertNotIn("release.json", manifest["files"])
        with tarfile.open(self.output / "web.tar.gz", "r:gz") as archive:
            self.assertEqual(set(archive.getnames()), {"web/" + path for path in manifest["files"]} | {"web/release.json"})
            self.assertEqual(archive.extractfile("web/release.json").read(), (self.output / "release.json").read_bytes())
            for path, record in manifest["files"].items():
                data = archive.extractfile("web/" + path).read()
                self.assertEqual(len(data), record["size"])
                self.assertEqual(hashlib.sha256(data).hexdigest(), record["sha256"])
                self.assertTrue(archive.getmember("web/" + path).isfile())

    def test_rejects_wrong_source_and_dirty_checkout(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.package(source_commit="f" * 40)
        self.write(self.project / "Assets/AbbyCamp/Scenes/Camp.unity", "changed source")
        with self.assertRaisesRegex(ValueError, "clean checkout"):
            self.package()
        self.assertFalse(self.output.exists())

    def test_rejects_a_checkout_from_another_repository(self):
        self.git("remote", "set-url", "origin", "https://github.com/example/unrelated.git")
        with self.assertRaisesRegex(ValueError, "expected GitHub repository"):
            self.package()

    def test_rejects_untracked_source_and_wrong_editor_pin(self):
        self.write(self.repo / "unexpected.cs", "source")
        with self.assertRaisesRegex(ValueError, "clean checkout"):
            self.package()
        (self.repo / "unexpected.cs").unlink()
        self.write(self.project / "ProjectSettings/ProjectVersion.txt", "m_EditorVersion: 6000.6.4f1\n")
        self.git("add", ".")
        self.git("commit", "-qm", "wrong version")
        with self.assertRaisesRegex(ValueError, "supported release editor"):
            self.package(source_commit=self.git("rev-parse", "HEAD").strip())

    def test_rejects_missing_licensed_scene(self):
        (self.project / release.LICENSED_SCENE).unlink()
        with self.assertRaisesRegex(ValueError, "preserved licensed scene"):
            self.package()

    def test_rejects_unhashed_or_missing_runtime_and_stale_extra_file(self):
        path = self.export / self.runtime["loader"]
        path.rename(path.with_name("Web.loader.js"))
        with self.assertRaises(ValueError):
            self.package()
        path.with_name("Web.loader.js").rename(path)
        path.unlink()
        with self.assertRaisesRegex(ValueError, "missing or stale"):
            self.package()
        self.write(path, "loader")
        self.write(self.export / ("Build/" + "5" * 32 + ".wasm"), "stale")
        with self.assertRaisesRegex(ValueError, "missing or stale"):
            self.package()

    def test_rejects_source_art_and_compressed_runtime_in_export(self):
        for relative in ("Assets/paid.prefab", "TemplateData/paid.psd", ".env", self.runtime["wasm"] + ".gz"):
            with self.subTest(relative=relative):
                path = self.export / relative
                self.write(path, "not a public compiled artifact")
                with self.assertRaisesRegex(ValueError, "source asset"):
                    self.package()
                path.unlink()

    def test_rejects_external_traversing_and_duplicate_loader_references(self):
        for replacement in ("https://example.invalid/game.loader.js", "../loader.js"):
            with self.subTest(reference=replacement):
                self.write(self.export / "index.html", self.html().replace(self.runtime["loader"], replacement))
                with self.assertRaisesRegex(ValueError, "hashed file"):
                    self.package()
        self.write(self.export / "index.html", self.html() + f"loader.src = '{self.runtime['loader']}';")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.package()

    def test_rejects_missing_css_dependency_and_reused_output(self):
        self.write(self.export / "TemplateData/phone.css", "@font-face { src:url(missing.ttf) }")
        with self.assertRaisesRegex(ValueError, "stylesheet resource"):
            self.package()
        self.write(self.export / "TemplateData/phone.css", "body { color: blue }")
        self.package()
        with self.assertRaisesRegex(ValueError, "already exist"):
            self.package()

    def test_rejects_bad_run_identity_and_digest(self):
        for options in ({"run_id": "../1"}, {"run_attempt": "0"}, {"licensed_assets_digest": "missing"}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.package(**options)

    def test_rejects_changed_private_metadata_even_when_source_is_clean(self):
        self.write(self.project / "Assets/ThirdParty/Meshtint/bird.fbx.meta", "guid: unexpected-replacement")
        release.validate_source(self.repo, self.commit)
        with self.assertRaisesRegex(ValueError, "changed after staging"):
            self.package()

    def private_inputs(self):
        private = self.root / "private"
        for relative in release.PRIVATE_PATHS:
            if relative.endswith(".meta"):
                self.write(private / relative, "guid: synthetic-folder")
        self.write(private / release.LICENSED_SCENE, "authored synthetic licensed scene")
        self.write(private / (release.LICENSED_SCENE + ".meta"), "guid: synthetic-scene")
        self.write(private / "Assets/ThirdParty/Meshtint/bird.fbx", "synthetic model")
        self.write(private / "Assets/ThirdParty/Meshtint/bird.fbx.meta", "guid: synthetic-model")
        for relative in release.PRIVATE_PATHS:
            target = self.project / relative
            if target.is_dir():
                self.assertTrue(target.resolve().is_relative_to(self.root.resolve()))
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
        return private

    def test_private_staging_preserves_scene_and_guids_and_hashes_all_inputs(self):
        private = self.private_inputs()
        digest = release.stage_private_assets(self.repo, private)
        self.assertRegex(digest, r"^[a-f0-9]{64}$")
        for source in private.rglob("*"):
            if source.is_file():
                self.assertEqual(source.read_bytes(), (self.project / source.relative_to(private)).read_bytes())
        release.validate_source(self.repo, self.commit)
        with self.assertRaisesRegex(ValueError, "fresh"):
            release.stage_private_assets(self.repo, private)

    def test_private_staging_rejects_missing_metadata_or_code_before_copying(self):
        private = self.private_inputs()
        meta = private / "Assets/ThirdParty/Meshtint/bird.fbx.meta"
        meta.unlink()
        with self.assertRaisesRegex(ValueError, "metadata GUID"):
            release.stage_private_assets(self.repo, private)
        self.assertFalse((self.project / "Assets/ThirdParty/Meshtint").exists())
        self.write(meta, "guid: synthetic-model")
        self.write(private / "Assets/ThirdParty/Meshtint/publisher.cs", "never execute imported code")
        with self.assertRaisesRegex(ValueError, "executable code"):
            release.stage_private_assets(self.repo, private)
        self.assertFalse((self.project / "Assets/ThirdParty/Meshtint").exists())

    def test_rejects_symlink_export_or_private_input(self):
        private = self.private_inputs()
        for link, target in ((self.export / "TemplateData/link.css", self.export / "TemplateData/phone.css"),
                             (private / "Assets/ThirdParty/Meshtint/link.fbx", private / "Assets/ThirdParty/Meshtint/bird.fbx")):
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest("This environment does not permit creating test symlinks")
        with self.assertRaisesRegex(ValueError, "Links"):
            release.validate_export(self.export)
        with self.assertRaisesRegex(ValueError, "Links"):
            release.stage_private_assets(self.repo, private)


if __name__ == "__main__":
    unittest.main()
