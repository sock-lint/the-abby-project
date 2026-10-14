"""Synthetic buffer tests require no licensed art or Blender."""
import ast
import json
from pathlib import Path
import struct
import unittest

SOURCE = Path(__file__).with_name("woodland_texture_variant.py")
NAMES = {"require", "digest", "view_payloads", "require_repack_identity", "repack_images"}
tree = ast.parse(SOURCE.read_text())
nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in NAMES]
namespace = {}
exec("import copy, hashlib, json, struct\nMAX_FILE = 64 * 1024 * 1024", namespace)
exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), namespace)


class BufferRepackTests(unittest.TestCase):
    def fixture(self):
        binary = b"mesh" + b"old-image-payload".ljust(24, b"\0")
        doc = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": len(binary)}],
               "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 4},
                               {"buffer": 0, "byteOffset": 4, "byteLength": 24}],
               "accessors": [{"bufferView": 0}], "images": [{"bufferView": 1}],
               "materials": [{"alphaMode": "MASK", "doubleSided": True}],
               "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}]}
        return doc, binary

    def test_only_image_payloads_and_layout_change(self):
        doc, binary = self.fixture()
        candidate = namespace["repack_images"](doc, binary, {1: b"new-image-payload".ljust(32, b"\0")})
        length = struct.unpack_from("<I", candidate, 12)[0]
        after = json.loads(candidate[20:20 + length])
        binary_after = candidate[28 + length:]
        evidence = namespace["require_repack_identity"](doc, after, binary, binary_after)
        self.assertEqual(evidence[0]["bytes"], 4)
        self.assertEqual(binary_after[:4], b"mesh")
        self.assertEqual(after["materials"], doc["materials"])
        self.assertEqual(doc["buffers"][0]["byteLength"], len(binary))

    def test_geometry_overlap_or_missing_replacements_are_refused(self):
        doc, binary = self.fixture()
        with self.assertRaises(ValueError):
            namespace["repack_images"](doc, binary, {})
        doc["accessors"][0]["bufferView"] = 1
        with self.assertRaises(ValueError):
            namespace["repack_images"](doc, binary, {1: b"x" * 24})

    def test_nonlayout_semantic_change_is_refused(self):
        doc, binary = self.fixture()
        changed = json.loads(json.dumps(doc))
        changed["materials"][0]["doubleSided"] = False
        with self.assertRaises(ValueError):
            namespace["require_repack_identity"](doc, changed, binary, binary)


if __name__ == "__main__":
    unittest.main()
