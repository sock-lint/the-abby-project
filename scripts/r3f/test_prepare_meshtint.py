"""Synthetic privacy/appearance checks; no purchased files are required."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("prepare_meshtint", Path(__file__).with_name("prepare_meshtint.py"))
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class RuntimeExportSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "model.glb"
        self.document = {
            "asset": {"version": "2.0"}, "buffers": [{"byteLength": 0}],
            "images": [{"bufferView": 0, "mimeType": "image/png"}],
            "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "TEXCOORD_0": 1, "JOINTS_0": 2, "WEIGHTS_0": 3}}]}],
            "skins": [{"joints": [0]}],
            "accessors": [{"count": 31, "min": [0], "max": [1]}],
            "animations": [{"name": "Idle", "channels": [{"sampler": 0}], "samplers": [{"input": 0}]}],
        }

    def tearDown(self):
        self.temporary.cleanup()

    def write(self):
        payload = json.dumps(self.document).encode()
        payload += b" " * (-len(payload) % 4)
        self.path.write_bytes(struct.pack("<4sIII", b"glTF", 2, len(payload) + 20, len(payload)) + struct.pack("<I", 0x4E4F534A) + payload)

    def test_external_source_image_is_rejected(self):
        self.document["images"][0]["uri"] = "file:///private/source.psd"
        self.write()
        with self.assertRaisesRegex(ValueError, "external file"):
            prepare.verify_export(self.path, ["Idle"])

    def test_unreviewed_animation_is_rejected(self):
        self.document["animations"][0]["name"] = "Bite Attack"
        self.write()
        with self.assertRaisesRegex(ValueError, "reviewed clips"):
            prepare.verify_export(self.path, ["Idle"])

    def test_additional_unreviewed_take_cannot_hide_beside_accepted_clip(self):
        self.document["animations"].append({
            "name": "Die", "channels": [{"sampler": 0}], "samplers": [{"input": 0}],
        })
        self.write()
        with self.assertRaisesRegex(ValueError, "reviewed clips"):
            prepare.verify_export(self.path, ["Idle"])

    def test_take_with_empty_animation_channels_is_rejected(self):
        self.document["animations"][0]["channels"] = []
        self.write()
        with self.assertRaisesRegex(ValueError, "Empty animation"):
            prepare.verify_export(self.path, ["Idle"])

    def test_lost_skin_weights_are_rejected(self):
        del self.document["meshes"][0]["primitives"][0]["attributes"]["WEIGHTS_0"]
        self.write()
        with self.assertRaisesRegex(ValueError, "lost skinning"):
            prepare.verify_export(self.path, ["Idle"])

    def test_zero_duration_animation_is_rejected(self):
        self.document["accessors"][0]["max"] = [0]
        self.write()
        with self.assertRaisesRegex(ValueError, "playback duration"):
            prepare.verify_export(self.path, ["Idle"])

    def test_output_cannot_overwrite_original_sources(self):
        source = Path(self.temporary.name) / "owned"
        with self.assertRaisesRegex(ValueError, "overlap"):
            prepare.ensure_private_output(source / "exports", source)

    def test_unignored_repository_output_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "must be ignored"):
            prepare.ensure_private_output(prepare.ROOT / "public-unlicensed-export", Path(self.temporary.name))


if __name__ == "__main__":
    unittest.main()
