"""Successful pack edits survive other workers and interrupted replacements."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Barrier, BrokenBarrierError
from unittest.mock import patch

from asgiref.sync import async_to_sync, sync_to_async
from django.db import connections
from django.test import SimpleTestCase, TransactionTestCase, override_settings
import yaml

from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPValidationError
from apps.mcp_server.pack_files import pack_file_lock
from apps.mcp_server.server import mcp
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PackFileConcurrencyTests(TransactionTestCase):
    def setUp(self):
        family = make_family("Pack workers", parents=[
            {"username": "pack-worker-a", "is_staff": True},
            {"username": "pack-worker-b", "is_staff": True},
        ])
        self.actors = family.parents
        folder = TemporaryDirectory(prefix="abby-pack-workers-")
        self.addCleanup(folder.cleanup)
        settings = override_settings(BASE_DIR=Path(folder.name))
        settings.enable()
        self.addCleanup(settings.disable)
        self.path = Path(folder.name) / "content/rpg/packs/safe/items.yaml"
        self.invoke("write_pack_file", {"pack": "safe", "filename": "items.yaml",
            "yaml_content": "items:\n- slug: baseline\n  name: Baseline\n  item_type: food\n"})

    def invoke(self, name, params, *, actor=None):
        async def run():
            with override_user(actor or self.actors[0], scopes=frozenset({"mcp:author"})):
                try:
                    result = await mcp.call_tool(name, {"params": params, "confirmation": True})
                    return result[1] if isinstance(result, tuple) else result.structuredContent
                finally:
                    await sync_to_async(connections.close_all, thread_sensitive=True)()
        return async_to_sync(run)()

    def test_concurrent_disjoint_appends_keep_both_successful_changes(self):
        actual_read = Path.read_text
        barrier = Barrier(2)

        def read_then_pause(path, *args, **kwargs):
            saved = actual_read(path, *args, **kwargs)
            if path == self.path:
                try:
                    # Without serialization both workers read the old file.
                    # With serialization the first worker times out here,
                    # commits, then the second reads the updated file.
                    barrier.wait(timeout=1)
                except BrokenBarrierError:
                    pass
            return saved

        def append(index):
            return self.invoke("draft_pack_entries", {"pack": "safe", "filename": "items.yaml",
                "entries": [{"slug": f"added-{index}", "name": f"Added {index}", "item_type": "food"}]},
                actor=self.actors[index])

        with patch.object(Path, "read_text", read_then_pause):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(append, range(2)))
        self.assertTrue(all("error" not in result for result in results), results)
        saved = yaml.safe_load(self.path.read_text())["items"]
        self.assertEqual({row["slug"] for row in saved}, {"baseline", "added-0", "added-1"})

    def test_stale_replacement_and_delete_cannot_discard_another_edit(self):
        before = self.invoke("read_pack_file", {"pack": "safe", "filename": "items.yaml"})
        digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.assertEqual(before.get("content_digest"), digest)
        self.invoke("draft_pack_entries", {"pack": "safe", "filename": "items.yaml",
            "entries": [{"slug": "kept", "name": "Kept", "item_type": "food"}]})
        accepted = self.path.read_bytes()
        for name, changes in (("write_pack_file", {"yaml_content": "items: []\n"}),
                              ("delete_pack_file", {})):
            with self.subTest(name=name):
                result = self.invoke(name, {"pack": "safe", "filename": "items.yaml",
                    "expected_digest": digest, **changes})
                self.assertEqual(result["error"]["code"], "pack_source_conflict", result)
                self.assertEqual(self.path.read_bytes(), accepted)

    def test_interrupted_replace_preserves_original_bytes_and_cleans_temporary_file(self):
        original = self.path.read_bytes()
        with patch("os.replace", side_effect=OSError("Synthetic replacement interruption")):
            result = self.invoke("write_pack_file", {"pack": "safe", "filename": "items.yaml",
                "yaml_content": "items: []\n"})
        self.assertIn("error", result)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual({path.name for path in self.path.parent.iterdir()}, {".manifest.json", "items.yaml"})

    def test_exact_digest_is_bytes_based_and_missing_precondition_cannot_replace(self):
        content = "items:\r\n- slug: café\r\n"
        saved = self.invoke("write_pack_file", {"pack": "safe", "filename": "items.yaml",
            "yaml_content": content})
        self.assertEqual(self.path.read_bytes(), content.encode())
        read = self.invoke("read_pack_file", {"pack": "safe", "filename": "items.yaml"})
        self.assertEqual(read["yaml_content"], content)
        self.assertEqual(read["content_digest"], saved["content_digest"])
        failed = self.invoke("write_pack_file", {"pack": "safe", "filename": "items.yaml",
            "yaml_content": "items: []\n", "expected_digest": "missing"})
        self.assertEqual(failed["error"]["code"], "pack_source_conflict")
        success = self.invoke("write_pack_file", {"pack": "safe", "filename": "items.yaml",
            "yaml_content": "items: []\n", "expected_digest": read["content_digest"]})
        self.assertNotIn("error", success)

    def test_failed_initial_manifest_does_not_strand_an_unowned_empty_pack(self):
        from apps.mcp_server.tools import content_packs
        params = {"pack": "interrupted", "filename": "items.yaml", "yaml_content": "items: []\n"}
        with patch.object(content_packs, "_write_manifest", side_effect=OSError("Synthetic manifest failure")):
            failed = self.invoke("write_pack_file", params)
        self.assertIn("error", failed)
        self.assertFalse((self.path.parent.parent / "interrupted").exists())
        self.assertNotIn("error", self.invoke("write_pack_file", params))

    def test_rejected_digest_does_not_create_a_new_pack(self):
        for name, content in (("write_pack_file", {"yaml_content": "items: []\n"}),
                              ("draft_pack_entries", {"entries": [{"slug": "new", "name": "New"}]})):
            with self.subTest(tool=name):
                pack = "rejected-" + name.replace("_", "-")
                params = {"pack": pack, "filename": "items.yaml", "expected_digest": "a" * 64, **content}
                failed = self.invoke(name, params)
                self.assertEqual(failed["error"]["code"], "pack_source_conflict", failed)
                self.assertFalse((self.path.parent.parent / pack).exists())
                params["expected_digest"] = "missing"
                self.assertNotIn("error", self.invoke(name, params))

    def test_manifest_failure_preserves_unknown_files_and_committed_ownership(self):
        from apps.mcp_server.tools import content_packs
        original = content_packs._write_manifest

        def interrupted(path, metadata):
            if path.name == "unowned":
                (path / "unknown.txt").write_text("Preserve unknown work")
            else:
                original(path, metadata)
            raise OSError("Synthetic failure after partial setup")

        for pack in ("unowned", "owned"):
            with self.subTest(pack=pack):
                params = {"pack": pack, "filename": "items.yaml", "yaml_content": "items: []\n"}
                with patch.object(content_packs, "_write_manifest", side_effect=interrupted):
                    self.assertIn("error", self.invoke("write_pack_file", params))
                path = self.path.parent.parent / pack
                if pack == "unowned":
                    self.assertEqual((path / "unknown.txt").read_text(), "Preserve unknown work")
                    self.assertEqual(self.invoke("write_pack_file", params)["error"]["code"], "not_found")
                else:
                    manifest = (path / ".manifest.json").read_bytes()
                    self.assertNotIn("error", self.invoke("write_pack_file", params))
                    self.assertEqual((path / ".manifest.json").read_bytes(), manifest)


class PackProcessLockTests(SimpleTestCase):
    def test_independent_python_process_waits_for_same_pack(self):
        script = """\
from pathlib import Path
import sys
from apps.mcp_server.pack_files import pack_file_lock
print('waiting', flush=True)
with pack_file_lock(Path(sys.argv[1]), 'shared'):
    print('acquired', flush=True)
"""
        with TemporaryDirectory(prefix="abby-pack-lock-") as folder:
            child = None
            try:
                with pack_file_lock(Path(folder), "shared"):
                    child = subprocess.Popen([sys.executable, "-c", script, folder],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    self.assertEqual(child.stdout.readline().strip(), "waiting")
                    with self.assertRaises(subprocess.TimeoutExpired):
                        child.wait(timeout=0.15)
                stdout, stderr = child.communicate(timeout=5)
                self.assertEqual(child.returncode, 0, stderr)
                self.assertEqual(stdout.strip(), "acquired")
            finally:
                if child is not None and child.poll() is None:
                    child.kill()
                    child.communicate()

    def test_lock_is_reentrant_but_other_thread_gets_bounded_busy_result(self):
        with TemporaryDirectory(prefix="abby-pack-lock-") as folder:
            with pack_file_lock(Path(folder), "shared"), pack_file_lock(Path(folder), "shared"):
                def attempt():
                    with pack_file_lock(Path(folder), "shared"):
                        return "unexpectedly acquired"

                with patch("apps.mcp_server.pack_files.PACK_LOCK_TIMEOUT", 0.05):
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        with self.assertRaises(MCPValidationError) as error:
                            pool.submit(attempt).result(timeout=2)
                self.assertEqual(error.exception.code, "pack_busy")
                self.assertTrue(error.exception.retryable)
            with pack_file_lock(Path(folder), "shared"):
                pass
