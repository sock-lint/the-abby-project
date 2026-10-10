"""Safety checks for licensed staging using synthetic archives only."""
from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile


spec = importlib.util.spec_from_file_location(
    "stage_meshtint", Path(__file__).with_name("stage_meshtint.py")
)
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)


def unity_package(assets: dict[str, tuple[bytes, bytes]]) -> bytes:
    """Create the pathname/asset/meta records used by a Unity package."""
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for index, (pathname, (data, metadata)) in enumerate(assets.items()):
            guid_folder = f"{index:032x}"
            for name, content in (
                ("pathname", pathname.encode("utf-8")),
                ("asset", data),
                ("asset.meta", metadata),
            ):
                member = tarfile.TarInfo(f"{guid_folder}/{name}")
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
    return output.getvalue()


def zip_archive(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


class StageMeshtintTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="abby-staging-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "unity/AbbyCamp/Assets/ThirdParty/Meshtint"
        self.licensed = self.root / "unity/AbbyCamp/Assets/AbbyCamp/Licensed"
        locations = patch.multiple(
            stage, ROOT=self.root, SOURCE=self.source, LICENSED=self.licensed
        )
        locations.start()
        self.addCleanup(locations.stop)

    def test_rejects_absolute_parent_and_windows_drive_paths(self) -> None:
        for pathname in (
            "/Assets/escaped.png",
            "Assets/../escaped.png",
            "Assets\\..\\escaped.png",
            "C:/Assets/escaped.png",
            "C:\\Assets\\escaped.png",
            "\\\\server\\share\\escaped.png",
        ):
            with self.subTest(pathname=pathname), self.assertRaises(ValueError):
                stage.safe_path(pathname)

    def test_unity_package_cannot_write_outside_asset_destination(self) -> None:
        archive = unity_package({
            "Assets/../../escaped.png": (b"synthetic art", b"synthetic meta")
        })
        with self.assertRaises(ValueError):
            stage.stage_package(archive)
        self.assertFalse(self.source.exists())
        self.assertFalse((self.root / "escaped.png").exists())

    def test_preserves_art_and_guid_metadata_while_excluding_demo_and_code(self) -> None:
        metadata = (
            b"fileFormatVersion: 2\n"
            b"guid: 0123456789abcdef0123456789abcdef\n"
            b"ModelImporter:\n  serializedVersion: 22200\n"
        )
        texture_metadata = (
            b"fileFormatVersion: 2\n"
            b"guid: abcdef0123456789abcdef0123456789\n"
            b"TextureImporter:\n  serializedVersion: 13\n"
        )
        archive = unity_package({
            "Assets/Chick Cute Series/FBX/Chick.FBX": (b"synthetic mesh", metadata),
            "Assets/Chick Cute Series/Prefabs/Chick.prefab": (b"synthetic prefab", metadata),
            "Assets/Chick Cute Series/Textures/Chick.PSD": (b"synthetic layered texture", texture_metadata),
            "Assets/Chick Cute Series/Scripts/Publisher.cs": (b"publisher code", metadata),
            "Assets/Chick Cute Series/Demo/Showcase.prefab": (b"demo prefab", metadata),
            "Assets/Chick Cute Series/Scenes/Showcase.unity": (b"demo scene", metadata),
        })
        self.assertEqual(stage.stage_package(archive), 3)
        model = self.source / "Chick Cute Series/FBX/Chick.FBX"
        self.assertEqual(model.read_bytes(), b"synthetic mesh")
        self.assertEqual(Path(str(model) + ".meta").read_bytes(), metadata)
        texture = self.source / "Chick Cute Series/Textures/Chick.PSD"
        self.assertEqual(texture.read_bytes(), b"synthetic layered texture")
        self.assertEqual(Path(str(texture) + ".meta").read_bytes(), texture_metadata)
        self.assertEqual(
            sorted(path.relative_to(self.source).as_posix() for path in self.source.rglob("*") if path.is_file()),
            [
                "Chick Cute Series/FBX/Chick.FBX",
                "Chick Cute Series/FBX/Chick.FBX.meta",
                "Chick Cute Series/Prefabs/Chick.prefab",
                "Chick Cute Series/Prefabs/Chick.prefab.meta",
                "Chick Cute Series/Textures/Chick.PSD",
                "Chick Cute Series/Textures/Chick.PSD.meta",
            ],
        )

    def prepare_downloads(self, *, include_bird: bool, include_avatar: bool) -> Path:
        downloads = self.root / "Downloads"
        downloads.mkdir()
        metadata = b"fileFormatVersion: 2\nguid: abcdef0123456789abcdef0123456789\n"
        art = unity_package({"Assets/Synthetic/mesh.fbx": (b"mesh", metadata)})
        if include_bird:
            (downloads / stage.PACKS[0]).write_bytes(zip_archive({"bird.unitypackage": art}))
        (downloads / stage.PACKS[1]).write_bytes(zip_archive({"forest.unitypackage": art}))
        (downloads / stage.PACKS[2]).write_bytes(zip_archive({
            "Icons/Transparent BG/Bird01.png": b"synthetic chick portrait",
            "Icons/Transparent BG/Bird02.png": b"synthetic fledgling portrait",
            "Icons/Transparent BG/Bird03.png": b"synthetic bird portrait",
        }))
        if include_avatar:
            (downloads / stage.PACKS[3]).write_bytes(zip_archive({"avatar.unitypackage": art}))
        presentation = self.root / "shared/storybook/presentation.json"
        presentation.parent.mkdir(parents=True)
        presentation.write_text(json.dumps({"schema_version": 1, "companion": {"id": "starter-companion"}}))
        return downloads

    def run_main(self, downloads: Path) -> int:
        with patch.object(sys, "argv", ["stage_meshtint.py", "--downloads", str(downloads)]):
            with redirect_stdout(io.StringIO()):
                return stage.main()

    def test_avatar_cannot_substitute_for_missing_required_companion(self) -> None:
        downloads = self.prepare_downloads(include_bird=False, include_avatar=True)
        with self.assertRaisesRegex(FileNotFoundError, "bird, forest and icon"):
            self.run_main(downloads)
        self.assertFalse((self.root / "shared/storybook/licensed/presentation.json").exists())
        self.assertFalse((self.root / "frontend/src/storybook/licensed/presentation.json").exists())
        self.assertFalse((self.licensed / "import-report.json").exists())

    def test_required_packs_stage_without_optional_avatar_and_repeat_safely(self) -> None:
        downloads = self.prepare_downloads(include_bird=True, include_avatar=False)
        self.assertEqual(self.run_main(downloads), 0)
        first_files = {
            path.relative_to(self.root): path.read_bytes()
            for path in self.root.rglob("*") if path.is_file()
        }
        self.assertEqual(self.run_main(downloads), 0)
        second_files = {
            path.relative_to(self.root): path.read_bytes()
            for path in self.root.rglob("*") if path.is_file()
        }
        self.assertEqual(first_files, second_files)
        for folder in ("shared/storybook/licensed", "frontend/src/storybook/licensed"):
            overlay = self.root / folder
            manifest = json.loads((overlay / "presentation.json").read_text())
            self.assertEqual(manifest["companion"]["id"], "starter-companion")
            self.assertFalse(manifest["companion"]["temporary"])
            self.assertEqual((overlay / "chick.png").read_bytes(), b"synthetic chick portrait")
            self.assertEqual((overlay / "fledgling.png").read_bytes(), b"synthetic fledgling portrait")
            self.assertEqual((overlay / "bird.png").read_bytes(), b"synthetic bird portrait")


if __name__ == "__main__":
    unittest.main()
