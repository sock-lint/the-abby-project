"""Opaque receipt integrity tests using only private temporary regular data.

No native receipt schema, operational gate, runner, process or service is used.
Run this module with Python -B after inspecting the receipt helper functions.
"""

import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import capture_activation_contract as driver


class FreezeReceiptPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="coolify-freeze-policy-", dir=Path.home())
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name).resolve()
        self.state = self.directory / "state"
        self.state.mkdir(mode=0o700)
        self.path = self.state / "receipt.data"
        self.payload = b"\x00synthetic opaque owner receipt\xff\n"
        self.path.write_bytes(self.payload)
        self.path.chmod(0o600)
        self.expected_sha256 = hashlib.sha256(self.payload).hexdigest()

    def capture(self):
        return driver.capture_freeze_receipt(str(self.path), self.state, self.expected_sha256)

    def test_capture_preserves_exact_raw_bytes_without_a_receipt_schema(self):
        captured = self.capture()
        metadata = self.path.stat()
        self.assertEqual(captured["path"], str(self.path))
        self.assertEqual(captured["payload"], self.payload)
        self.assertEqual(captured["sha256"], self.expected_sha256)
        self.assertEqual(captured["metadata"], (
            metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_uid,
            metadata.st_mode, metadata.st_mtime_ns, metadata.st_ctime_ns,
        ))

    def test_exact_one_mib_regular_receipt_is_accepted(self):
        payload = b"r" * (1024 * 1024)
        self.path.write_bytes(payload)
        expected = hashlib.sha256(payload).hexdigest()
        captured = driver.capture_freeze_receipt(str(self.path), self.state, expected)
        self.assertEqual(captured["payload"], payload)

    def test_missing_regular_receipt_is_rejected(self):
        with self.assertRaises(ValueError):
            driver.capture_freeze_receipt(str(self.state / "missing.data"), self.state, self.expected_sha256)

    def test_empty_regular_receipt_is_rejected(self):
        self.path.write_bytes(b"")
        with self.assertRaises(ValueError):
            driver.capture_freeze_receipt(str(self.path), self.state, hashlib.sha256(b"").hexdigest())

    def test_oversized_regular_receipt_is_rejected(self):
        payload = b"r" * (1024 * 1024 + 1)
        self.path.write_bytes(payload)
        with self.assertRaises(ValueError):
            driver.capture_freeze_receipt(str(self.path), self.state, hashlib.sha256(payload).hexdigest())

    def test_group_or_other_permissions_are_rejected(self):
        for mode in (0o640, 0o620, 0o604):
            self.path.chmod(mode)
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.capture()

    def test_receipt_must_be_a_direct_child_of_private_state(self):
        nested = self.state / "nested"
        nested.mkdir(mode=0o700)
        nested_receipt = nested / "receipt.data"
        nested_receipt.write_bytes(self.payload)
        nested_receipt.chmod(0o600)
        with self.assertRaises(ValueError):
            driver.capture_freeze_receipt(str(nested_receipt), self.state, self.expected_sha256)

    def test_relative_receipt_path_is_rejected(self):
        with self.assertRaises(ValueError):
            driver.capture_freeze_receipt("receipt.data", self.state, self.expected_sha256)

    def test_wrong_raw_digest_is_rejected(self):
        with self.assertRaises(ValueError):
            driver.capture_freeze_receipt(str(self.path), self.state, "0" * 64)

    def test_recheck_accepts_unchanged_regular_receipt(self):
        captured = self.capture()
        driver.recheck_freeze_receipt(captured, self.state)
        self.assertEqual(self.path.read_bytes(), self.payload)

    def test_recheck_rejects_each_mocked_metadata_component_change(self):
        captured = self.capture()
        for index in range(len(captured["metadata"])):
            metadata = list(captured["metadata"])
            metadata[index] += 1
            changed = dict(captured, metadata=tuple(metadata))
            with self.subTest(component=index), patch.object(driver, "capture_freeze_receipt", return_value=changed):
                with self.assertRaises(ValueError):
                    driver.recheck_freeze_receipt(captured, self.state)

    def test_recheck_rejects_mocked_payload_change(self):
        captured = self.capture()
        changed = dict(captured, payload=b"synthetic different opaque receipt")
        with patch.object(driver, "capture_freeze_receipt", return_value=changed):
            with self.assertRaises(ValueError):
                driver.recheck_freeze_receipt(captured, self.state)


if __name__ == "__main__":
    unittest.main()
