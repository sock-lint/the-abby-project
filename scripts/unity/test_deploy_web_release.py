"""Synthetic release/broker checks; no Docker, SSH or production access."""

import hashlib
from contextlib import redirect_stdout
import errno
from email.message import Message
import gzip
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tarfile
import tempfile
import subprocess
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

import deploy_web_release as release


SOURCE = "a" * 40


def manifest_fixture():
    files = {"index.html": b'<canvas id="unity-canvas"></canvas><script>dataUrl: "Build/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.data", frameworkUrl: "Build/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.framework.js", codeUrl: "Build/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.wasm"; loader.src = "Build/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.loader.js";</script>',
             "Build/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.loader.js": b"loader", "Build/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.framework.js": b"framework",
             "Build/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.wasm": b"wasm", "Build/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.data": b"data"}
    manifest = {"schema_version": 1, "repository": release.REPOSITORY,
                "source_commit": SOURCE, "run_id": "123", "run_attempt": "1",
                "release_id": f"{SOURCE}-123-1", "unity_version": "6000.6.5f1",
                "licensed_assets_digest": "b" * 64,
                "scene": {"path": "Assets/AbbyCamp/Licensed/MemoryMeadow.unity", "sha256": "c" * 64},
                "runtime_files": {"data": "Build/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.data", "framework": "Build/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.framework.js",
                                  "wasm": "Build/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.wasm", "loader": "Build/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.loader.js"},
                "files": {name: {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()} for name, data in files.items()}}
    return manifest, json.dumps(manifest).encode(), files


def request_fixture(op="activate"):
    return {"op": op, "source_commit": SOURCE, "run_id": "123", "run_attempt": "1",
            "release_id": f"{SOURCE}-123-1", "manifest_sha256": "d" * 64, "image_id": "sha256:" + "e" * 64}


def add_tar_file(bundle, name, data):
    item = tarfile.TarInfo(name)
    item.size = len(data)
    bundle.addfile(item, io.BytesIO(data))


def image_archive(path, request, *, extra_index=False, duplicate=False, extra_tag=False, unsafe=False,
                  classic=False, nested_index=False, tampered_config=False, tampered_layer=False,
                  bad_descriptor_size=False, bad_descriptor_hash=False, gzip_layer=False,
                  wrong_diff_id=False, unknown_layer_type=False, malformed_rootfs=False, layer_data=None):
    tag = release.request_identity(request)
    decoded_layer = layer_data or b"synthetic uncompressed layer tar"
    diff_id = "sha256:" + hashlib.sha256(decoded_layer).hexdigest()
    layer = gzip.compress(decoded_layer, mtime=0) if gzip_layer else decoded_layer
    layer_id = hashlib.sha256(layer).hexdigest()
    config_raw = json.dumps({"architecture": "amd64", "os": "linux", "config": {"Labels": release.image_labels(request)},
                             "rootfs": [] if malformed_rootfs else {"type": "layers", "diff_ids": ["sha256:" + "f" * 64 if wrong_diff_id else diff_id]}}).encode()
    config_id = hashlib.sha256(config_raw).hexdigest()
    request["image_id"] = "sha256:" + config_id
    config_name = config_id + ".json" if classic else f"blobs/sha256/{config_id}"
    layer_name = layer_id + "/layer.tar" if classic else "blobs/sha256/" + layer_id
    descriptor_raw = json.dumps({"schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json",
                                  "config": {"digest": request["image_id"], "size": len(config_raw)},
                                  "layers": [{"mediaType": "unknown/layer" if unknown_layer_type else "application/vnd.docker.image.rootfs.diff.tar.gzip" if gzip_layer else "application/vnd.oci.image.layer.v1.tar",
                                              "digest": "sha256:" + layer_id, "size": len(layer)}]}).encode()
    descriptor_id = hashlib.sha256(descriptor_raw).hexdigest()
    descriptor = {"mediaType": "application/vnd.oci.image.manifest.v1+json", "digest": "sha256:" + descriptor_id, "size": len(descriptor_raw),
                  "annotations": {"io.containerd.image.name": tag, "org.opencontainers.image.ref.name": tag.split(":")[1]}}
    root_raw = None
    if nested_index:
        runtime = {"mediaType": descriptor["mediaType"], "digest": descriptor["digest"], "size": descriptor["size"],
                   "platform": {"architecture": "amd64", "os": "linux"}}
        root_raw = json.dumps({"schemaVersion": 2, "mediaType": "application/vnd.oci.image.index.v1+json",
                               "manifests": [runtime] * (2 if extra_index else 1)}).encode()
        root_id = hashlib.sha256(root_raw).hexdigest()
        descriptor.update(mediaType="application/vnd.oci.image.index.v1+json", digest="sha256:" + root_id, size=len(root_raw))
    if extra_tag:
        descriptor["annotations"]["io.containerd.image.name"] = "another:tag"
    if bad_descriptor_size:
        descriptor["size"] += 1
    if bad_descriptor_hash:
        descriptor_raw += b" "
    with tarfile.open(path, "w:gz") as bundle:
        add_tar_file(bundle, "manifest.json", json.dumps([{"RepoTags": [tag], "Config": config_name, "Layers": [layer_name]}]).encode())
        add_tar_file(bundle, config_name, config_raw + (b" " if tampered_config else b""))
        add_tar_file(bundle, layer_name, layer + (b"!" if tampered_layer else b""))
        if not classic:
            add_tar_file(bundle, "blobs/sha256/" + descriptor_id, descriptor_raw)
            if root_raw:
                add_tar_file(bundle, "blobs/sha256/" + root_id, root_raw)
            add_tar_file(bundle, "index.json", json.dumps({"manifests": [descriptor] * (2 if extra_index and not nested_index else 1)}).encode())
        if duplicate:
            add_tar_file(bundle, "manifest.json", b"[]")
        if unsafe:
            add_tar_file(bundle, "../outside", b"x")


def proof_fixture(request):
    return {"config_id": request["image_id"], "image_ids": [request["image_id"]]}


class ManifestTests(unittest.TestCase):
    def test_current_licensed_artifact_has_exact_run_identity(self):
        _, raw, _ = manifest_fixture()
        self.assertEqual(release.validate_manifest(raw, SOURCE, "123", "1")["source_commit"], SOURCE)
        with self.assertRaises(release.ReleaseError):
            release.validate_manifest(raw, "f" * 40, "123", "1")
        with self.assertRaises(release.ReleaseError):
            release.validate_manifest(raw, SOURCE, "123", "2")

    def test_public_fallback_and_bad_editor_are_rejected(self):
        data, _, _ = manifest_fixture()
        data["scene"]["path"] = "Assets/AbbyCamp/Scenes/Camp.unity"
        with self.assertRaises(release.ReleaseError):
            release.validate_manifest(json.dumps(data).encode())
        data["scene"]["path"] = "Assets/AbbyCamp/Licensed/MemoryMeadow.unity"
        data["unity_version"] = "6000.3.2f1"
        with self.assertRaises(release.ReleaseError):
            release.validate_manifest(json.dumps(data).encode())

    def test_source_paths_traversal_and_missing_runtime_are_rejected(self):
        data, _, _ = manifest_fixture()
        for name in ("../index.html", "/index.html", "Build/../../secret", "Assets/paid.fbx", "Build/./x"):
            with self.subTest(name=name), self.assertRaises(release.ReleaseError):
                release.safe_web_path(name)
        del data["files"]["Build/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.wasm"]
        with self.assertRaises(release.ReleaseError):
            release.validate_manifest(json.dumps(data).encode())

    def test_exact_export_inventory_and_bytes_are_required(self):
        _, raw, files = manifest_fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "web.tar.gz"
            with tarfile.open(archive, "w:gz") as bundle:
                for name, data in {**files, "release.json": raw}.items():
                    add_tar_file(bundle, "web/" + name, data)
            manifest = release.unpack_artifact(archive, raw, root / "out")
            self.assertEqual(manifest["release_id"], f"{SOURCE}-123-1")
            self.assertEqual((root / "out/release.json").read_bytes(), raw)
            with tarfile.open(archive, "w:gz") as bundle:
                for name, data in {**files, "release.json": raw, "TemplateData/extra.css": b"private"}.items():
                    add_tar_file(bundle, "web/" + name, data)
            with self.assertRaises(release.ReleaseError):
                release.unpack_artifact(archive, raw, root / "bad")

    def test_export_links_are_rejected_without_extracting(self):
        _, raw, _ = manifest_fixture()
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "web.tar.gz"
            with tarfile.open(archive, "w:gz") as bundle:
                member = tarfile.TarInfo("web/index.html")
                member.type, member.linkname = tarfile.SYMTYPE, "/etc/passwd"
                bundle.addfile(member)
            with self.assertRaises(release.ReleaseError):
                release.unpack_artifact(archive, raw, Path(directory) / "out")


class BrokerTests(unittest.TestCase):
    def test_protocol_cannot_choose_destination_or_command(self):
        request = request_fixture()
        for key, value in (("command", "rm -rf /"), ("container", "120"), ("service_uuid", "another"), ("path", "/etc/passwd")):
            with self.subTest(key=key), self.assertRaises(release.ReleaseError):
                release.request_identity({**request, key: value})
        with self.assertRaises(release.ReleaseError):
            release.request_identity({**request, "op": "shell"})

    def test_inspect_checks_fixed_destination_without_mutation(self):
        request = request_fixture("inspect")
        with patch.object(release, "check_destination") as destination, patch.object(release, "service_action") as action:
            result = release.broker_operation(request, io.BytesIO())
        destination.assert_called_once()
        action.assert_not_called()
        self.assertEqual(result["uuid"], release.SERVICE_UUID)

    def test_wrong_daemon_prevents_service_access(self):
        with patch.object(release, "docker_host", return_value=b"another-daemon\n"), patch.object(release, "service_action") as action:
            with self.assertRaises(release.ReleaseError):
                release.check_destination()
        action.assert_not_called()

    def test_stale_release_never_writes_upload_or_queues_activity(self):
        request = request_fixture("upload")
        request.update(archive_size=1, archive_sha256="a" * 64)
        with patch.object(release, "check_destination"), patch.object(release, "receive_archive") as receive, patch.object(release, "service_action") as action:
            with self.assertRaises(release.ReleaseError):
                release.broker_operation(request, io.BytesIO(), latest=lambda: "f" * 40)
        receive.assert_not_called()
        action.assert_not_called()

    def test_upload_is_bounded_checksum_checked_and_never_overwrites(self):
        checksum = hashlib.sha256(b"abc").hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "release.tar.gz"
            for data, size, digest in ((b"ab", 3, checksum), (b"abcd", 3, checksum), (b"abc", 3, "f" * 64)):
                with self.subTest(data=data), self.assertRaises(release.ReleaseError):
                    release.receive_archive(io.BytesIO(data), target, size, digest)
                self.assertFalse(target.exists())
                self.assertFalse(target.with_suffix(".partial").exists())
            release.receive_archive(io.BytesIO(b"abc"), target, 3, checksum)
            with self.assertRaises(release.ReleaseError):
                release.receive_archive(io.BytesIO(b"abc"), target, 3, checksum)
            self.assertEqual(target.read_bytes(), b"abc")

    def test_image_archive_binds_config_and_oci_index_to_exact_tag(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "image.tar.gz"
            request = request_fixture()
            image_archive(archive, request)
            release.validate_image_archive(archive, request, release.request_identity(request))
            for option in ("extra_index", "extra_tag", "duplicate", "unsafe"):
                with self.subTest(option=option):
                    image_archive(archive, request, **{option: True})
                    with self.assertRaises(release.ReleaseError):
                        release.validate_image_archive(archive, request, release.request_identity(request))

    def test_classic_and_containerd_ids_are_proven_by_one_runtime_content_graph(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "image.tar.gz"
            for options, expected_count in (({"classic": True}, 1), ({}, 2), ({"nested_index": True}, 3)):
                with self.subTest(options=options):
                    request = request_fixture()
                    image_archive(archive, request, **options)
                    proof = release.validate_image_archive(archive, request, release.request_identity(request))
                    self.assertEqual(proof["config_id"], request["image_id"])
                    self.assertEqual(len(proof["image_ids"]), expected_count)
                    self.assertIn(request["image_id"], proof["image_ids"])
                    for store_id in proof["image_ids"]:
                        inspected = {"Id": store_id, "Config": {"Labels": release.image_labels(request)}}
                        with patch.object(release, "docker_host", return_value=json.dumps(inspected).encode()):
                            self.assertEqual(release.exact_image(request, release.request_identity(request), proof["image_ids"]), store_id)
                    inspected["Id"] = "sha256:" + "f" * 64
                    with patch.object(release, "docker_host", return_value=json.dumps(inspected).encode()):
                        with self.assertRaises(release.ReleaseError):
                            release.exact_image(request, release.request_identity(request), proof["image_ids"])

    def test_tampered_config_descriptor_or_layer_and_extra_variant_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "image.tar.gz"
            for options in ({"classic": True, "tampered_layer": True}, {"tampered_layer": True},
                            {"tampered_config": True}, {"bad_descriptor_size": True},
                            {"bad_descriptor_hash": True}, {"nested_index": True, "extra_index": True},
                            {"wrong_diff_id": True}, {"gzip_layer": True, "wrong_diff_id": True},
                            {"unknown_layer_type": True}, {"malformed_rootfs": True}):
                with self.subTest(options=options):
                    request = request_fixture()
                    image_archive(archive, request, **options)
                    with self.assertRaises(release.ReleaseError):
                        release.validate_image_archive(archive, request, release.request_identity(request))

    def test_gzip_layers_are_bound_to_decoded_diff_ids_and_expansion_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "image.tar.gz"
            request = request_fixture()
            image_archive(archive, request, gzip_layer=True, layer_data=b"x" * 8192)
            proof = release.validate_image_archive(archive, request, release.request_identity(request))
            self.assertEqual(proof["config_id"], request["image_id"])
            with patch.object(release, "MAX_ARCHIVE", 1024):
                with self.assertRaisesRegex(release.ReleaseError, "Decoded image layers exceed"):
                    release.validate_image_archive(archive, request, release.request_identity(request))

    def test_oversized_classic_config_or_archive_json_metadata_is_rejected_whole(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original, oversized = root / "image.tar.gz", root / "oversized.tar.gz"
            request = request_fixture()
            image_archive(original, request, classic=True)
            with tarfile.open(original, "r:gz") as bundle:
                members = {item.name: bundle.extractfile(item).read() for item in bundle if item.isfile()}
            config_name = json.loads(members["manifest.json"])[0]["Config"]
            for target in (config_name, "manifest.json", "index.json"):
                with self.subTest(target=target):
                    data = dict(members)
                    data[target] = data.get(target, b"{}") + b" " * release.MAX_MANIFEST
                    with tarfile.open(oversized, "w:gz") as bundle:
                        for name, raw in data.items():
                            add_tar_file(bundle, name, raw)
                    with self.assertRaisesRegex(release.ReleaseError, "metadata exceeds its size limit"):
                        release.validate_image_archive(oversized, request, release.request_identity(request))

    def test_destination_image_record_is_bound_to_archive_and_exact_observed_id(self):
        request = request_fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "image.tar.gz"
            image_archive(archive, request, nested_index=True)
            proof = release.validate_image_archive(archive, request, release.request_identity(request))
            request["archive_sha256"] = release.file_hash(archive)
            observed_id = next(value for value in proof["image_ids"] if value != request["image_id"])
            release.record_image(root, request, proof, observed_id)
            self.assertEqual(release.checked_image_record(root, request, proof, archive), observed_id)
            archive.write_bytes(archive.read_bytes() + b"tampered")
            with self.assertRaises(release.ReleaseError):
                release.checked_image_record(root, request, proof, archive)

    def test_existing_tag_with_different_content_is_not_replaced(self):
        request = request_fixture()
        with patch.object(release, "docker_host", return_value=json.dumps({"Id": "sha256:" + "f" * 64}).encode()):
            with self.assertRaises(release.ReleaseError):
                release.exact_image(request, release.request_identity(request))

    def test_latest_main_is_checked_immediately_before_activate(self):
        request = request_fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / (request["release_id"] + ".tar.gz")).touch()
            heads = iter([SOURCE, "f" * 40])
            with patch.object(release, "check_destination"), patch.object(release, "validate_image_archive", return_value=proof_fixture(request)), patch.object(release, "exact_image", return_value=request["image_id"]), patch.object(release, "checked_image_record", return_value=request["image_id"]), patch.object(release, "service_action") as action:
                with self.assertRaises(release.ReleaseError):
                    release.broker_operation(request, io.BytesIO(), root=root, latest=lambda: next(heads))
            action.assert_not_called()

    def test_activate_waits_for_exact_healthy_image_and_rechecks_source(self):
        request = request_fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / (request["release_id"] + ".tar.gz")).touch()
            with patch.object(release, "check_destination"), patch.object(release, "validate_image_archive", return_value=proof_fixture(request)), patch.object(release, "exact_image", return_value=request["image_id"]), patch.object(release, "checked_image_record", return_value=request["image_id"]), patch.object(release, "service_action", return_value={"activity_id": 123}) as action, patch.object(release, "activity_status", return_value="finished"), patch.object(release, "healthy_image", side_effect=[False, True]) as healthy:
                result = release.broker_operation(request, io.BytesIO(), root=root, latest=lambda: SOURCE, sleep=lambda _: None)
            action.assert_called_once_with("activate", release.request_identity(request))
            self.assertEqual(healthy.call_count, 2)
            self.assertEqual(result["image_id"], request["image_id"])

    def test_superseded_release_keeps_waiting_until_its_activity_drains(self):
        request = request_fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / (request["release_id"] + ".tar.gz")).touch()
            heads = iter([SOURCE, SOURCE, "f" * 40])
            with patch.object(release, "check_destination"), patch.object(release, "validate_image_archive", return_value=proof_fixture(request)), patch.object(release, "exact_image", return_value=request["image_id"]), patch.object(release, "checked_image_record", return_value=request["image_id"]), patch.object(release, "service_action", return_value={"activity_id": 123}), patch.object(release, "activity_status", side_effect=["queued", "in_progress", "finished"]) as status, patch.object(release, "healthy_image") as healthy:
                with self.assertRaises(release.ReleaseError):
                    release.broker_operation(request, io.BytesIO(), root=root, latest=lambda: next(heads), sleep=lambda _: None)
            self.assertEqual(status.call_count, 3)
            healthy.assert_not_called()
            self.assertEqual(json.loads((root / "activity-state.json").read_text())["activity_id"], 123)

    def test_previous_activity_without_proven_completion_blocks_another_release(self):
        request = request_fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / (request["release_id"] + ".tar.gz")).touch()
            (root / "activity-state.json").write_text(json.dumps({"activity_id": 99}))
            with patch.object(release, "check_destination"), patch.object(release, "validate_image_archive", return_value=proof_fixture(request)), patch.object(release, "exact_image", return_value=request["image_id"]), patch.object(release, "checked_image_record", return_value=request["image_id"]), patch.object(release, "activity_status", return_value="cancelled"), patch.object(release, "service_action") as action:
                with self.assertRaises(release.ReleaseError):
                    release.broker_operation(request, io.BytesIO(), root=root, latest=lambda: SOURCE)
            action.assert_not_called()

    def test_public_git_head_check_avoids_anonymous_rest_quota(self):
        with patch.object(release, "command", return_value=(SOURCE + "\trefs/heads/main\n").encode()) as command:
            self.assertEqual(release.current_main(), SOURCE)
        self.assertIn("ls-remote", command.call_args.args[0])
        self.assertIn("credential.helper=", command.call_args.args[0])


class PublicGetTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        requests = self.requests

        class Edge(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append((self.path, dict(self.headers)))
                if self.path.startswith("/redirect") and not self.path.startswith("/redirect-target"):
                    status = 302
                    body = b"synthetic edge diagnostic: fixture-private-detail"
                    location = "/redirect-target?token=fixture-private-detail"
                elif (self.path.startswith("/forbidden")
                      or self.headers.get("User-Agent") != "abby-unity-release-verification/1.0"):
                    status = 403
                    body = b"synthetic edge diagnostic: fixture-private-detail"
                    location = None
                else:
                    status = 200
                    body = b'{"synthetic_release": true}'
                    location = None
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                if location:
                    self.send_header("Location", location)
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_):
                pass

        self.edge = ThreadingHTTPServer(("127.0.0.1", 0), Edge)
        self.thread = threading.Thread(target=self.edge.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f"http://127.0.0.1:{self.edge.server_port}"

    def tearDown(self):
        self.edge.shutdown()
        self.edge.server_close()
        self.thread.join(timeout=5)
        self.assertFalse(self.thread.is_alive())

    def test_descriptive_verifier_identity_passes_an_edge_that_rejects_generic_python(self):
        url = self.origin + "/release.json"
        with self.assertRaises(HTTPError) as generic:
            urlopen(url, timeout=5)
        self.assertEqual(generic.exception.code, 403)
        generic.exception.close()
        self.assertTrue(self.requests[0][1]["User-Agent"].startswith("Python-urllib/"))

        with release.public_get(url) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), b'{"synthetic_release": true}')
        self.assertEqual(len(self.requests), 2)
        headers = self.requests[1][1]
        self.assertEqual(headers["User-Agent"], "abby-unity-release-verification/1.0")
        self.assertEqual(headers["Cache-Control"], "no-cache")
        self.assertEqual(headers["Accept-Encoding"], "identity")
        self.assertNotIn("Authorization", headers)
        self.assertNotIn("Cookie", headers)

    def test_public_get_does_not_follow_an_edge_redirect(self):
        with self.assertRaises(release.ReleaseError) as rejected:
            release.public_get(self.origin + "/redirect?token=fixture-private-detail")
        self.assertEqual([path for path, _ in self.requests], ["/redirect?token=fixture-private-detail"])
        self.assertEqual(str(rejected.exception),
                         "Public Unity release verification request failed; check routing and caches.")
        self.assertNotIn("fixture-private-detail", str(rejected.exception))
        self.assertTrue(rejected.exception.__suppress_context__)
        self.assertIsInstance(rejected.exception.__context__, HTTPError)
        self.assertEqual(rejected.exception.__context__.code, 302)
        rejected.exception.__context__.close()

    def test_public_get_redacts_forbidden_edge_url_and_body(self):
        with self.assertRaises(release.ReleaseError) as rejected:
            release.public_get(self.origin + "/forbidden?token=fixture-private-detail")
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(str(rejected.exception),
                         "Public Unity release verification request failed; check routing and caches.")
        self.assertNotIn(self.origin, str(rejected.exception))
        self.assertNotIn("fixture-private-detail", str(rejected.exception))
        self.assertTrue(rejected.exception.__suppress_context__)
        self.assertIsInstance(rejected.exception.__context__, HTTPError)
        self.assertEqual(rejected.exception.__context__.code, 403)
        rejected.exception.__context__.close()


class PublicTests(unittest.TestCase):
    def test_all_public_runtime_components_must_match_even_with_same_loader(self):
        manifest, raw, files = manifest_fixture()

        class Response(io.BytesIO):
            def __init__(self, body, media_type):
                super().__init__(body)
                self.headers = Message()
                self.headers["Content-Type"] = media_type

        def public_response(url, stale_html=False):
            if url.endswith("/release.json"):
                return Response(raw, "application/json")
            if url.endswith("/play/"):
                html = files["index.html"]
                if stale_html:
                    html = html.replace(b"Build/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.wasm", b"Build/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.wasm")
                return Response(html, "text/html")
            name = url.removeprefix(release.PUBLIC_ORIGIN + "/play/")
            return Response(files[name], "application/wasm" if name.endswith(".wasm") else "application/octet-stream")

        with patch.object(release, "public_get", side_effect=public_response):
            release.verify_public(raw, manifest)
        with patch.object(release, "public_get", side_effect=lambda url: public_response(url, True)):
            with self.assertRaises(release.ReleaseError):
                release.verify_public(raw, manifest)

    def test_manifest_mismatch_fails_before_fetching_runtime(self):
        data, raw, _ = manifest_fixture()
        response = io.BytesIO(b"another release")
        with patch.object(release, "public_get", return_value=response) as get:
            with self.assertRaises(release.ReleaseError):
                release.verify_public(raw, data)
        get.assert_called_once_with(release.PUBLIC_ORIGIN + "/play/release.json")

    def test_ssh_key_uses_only_forced_protocol_and_pinned_host(self):
        with tempfile.TemporaryDirectory() as directory:
            key, hosts = Path(directory) / "key", Path(directory) / "known_hosts"
            key.touch(); hosts.touch()
            broker = release.BrokerClient("root@proxmox-1", str(key), str(hosts))
            self.assertEqual(broker.args[-1], release.SSH_COMMAND)
            self.assertIn("StrictHostKeyChecking=yes", broker.args)
            self.assertIn("IdentitiesOnly=yes", broker.args)


class ClientPhaseTests(unittest.TestCase):
    def test_native_failure_identifies_phase_without_native_arguments(self):
        secret = "fixture-private-detail"
        errors = [OSError(errno.EIO, secret, secret), ValueError(secret), KeyError(secret),
                  TypeError(secret), subprocess.TimeoutExpired([secret], 15, output=secret, stderr=secret),
                  tarfile.TarError(secret), KeyboardInterrupt(secret)]
        for error in errors:
            with self.subTest(kind=type(error).__name__), redirect_stdout(io.StringIO()) as output:
                with self.assertRaises(release.ReleaseError) as rejected:
                    with release.client_phase("image archive creation"):
                        raise error
                message = str(rejected.exception)
                self.assertIn("image archive creation", message)
                self.assertIn(type(error).__name__, message)
                if isinstance(error, OSError):
                    self.assertIn(f"errno {errno.EIO}", message)
                self.assertNotIn(secret, message + output.getvalue())
                self.assertTrue(rejected.exception.__suppress_context__)

    def test_existing_release_diagnostic_is_preserved(self):
        error = release.ReleaseError("Release is superseded on main.")
        with redirect_stdout(io.StringIO()), self.assertRaises(release.ReleaseError) as rejected:
            with release.client_phase("current-main check and archive upload"):
                raise error
        self.assertIs(rejected.exception, error)

    def test_native_hosting_and_upload_failures_abort_without_retry_or_activation(self):
        manifest, raw, files = manifest_fixture()
        for phase in ("hosting", "upload"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "release.json").write_bytes(raw)
                with tarfile.open(root / "web.tar.gz", "w:gz") as bundle:
                    for name, data in {**files, "release.json": raw}.items():
                        add_tar_file(bundle, "web/" + name, data)
                request = request_fixture()
                request["manifest_sha256"] = hashlib.sha256(raw).hexdigest()
                image_archive(root / "fixture.tar.gz", request)
                saved_image = gzip.decompress((root / "fixture.tar.gz").read_bytes())

                def local_command(args, **kwargs):
                    if args[:3] == ["docker", "image", "inspect"]:
                        return (request["image_id"] + "\n").encode() if "--format" in args else None
                    return b""

                operations = []

                def broker_request(payload, archive=None):
                    operations.append(payload["op"])
                    if payload["op"] == "upload":
                        raise PermissionError(errno.EACCES, "fixture-private-detail", "/fixture-private-detail")
                    return {"ok": True}

                env = {"GITHUB_SHA": SOURCE, "GITHUB_REPOSITORY": release.REPOSITORY,
                       "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_REF": "refs/heads/main",
                       "GITHUB_TOKEN": "fixture-token", "UNITY_WEB_SSH_TARGET": "fixture-host",
                       "UNITY_WEB_SSH_KEY_PATH": "fixture-key", "UNITY_WEB_SSH_KNOWN_HOSTS_PATH": "fixture-hosts"}
                process = SimpleNamespace(stdout=io.BytesIO(saved_image), wait=lambda timeout: 0)
                hosting_error = OSError(errno.EIO, "fixture-private-detail") if phase == "hosting" else None
                with patch.dict(release.os.environ, env, clear=True), patch.object(release, "command", side_effect=local_command) as commands, patch.object(release, "hosting_checks", side_effect=hosting_error), patch.object(release.subprocess, "Popen", return_value=process) as save, patch.object(release, "current_main", return_value=SOURCE) as main, patch.object(release, "BrokerClient") as broker, patch.object(release, "verify_public") as public, redirect_stdout(io.StringIO()):
                    broker.return_value.request.side_effect = broker_request
                    with self.assertRaises(release.ReleaseError) as rejected:
                        release.client_main(root)
                self.assertNotIn("fixture-private-detail", str(rejected.exception))
                public.assert_not_called()
                archive = root / (manifest["release_id"] + ".image.tar.gz")
                scans = [call for call in commands.call_args_list if call.args[0][0] == "trivy"]
                if phase == "hosting":
                    self.assertIn("local HTTP hosting verification", str(rejected.exception))
                    self.assertEqual(operations, ["inspect"])
                    self.assertEqual(main.call_count, 1)
                    self.assertEqual(scans, [])
                    save.assert_not_called()
                    self.assertFalse(archive.exists())
                else:
                    self.assertIn("current-main check and archive upload", str(rejected.exception))
                    self.assertEqual(operations, ["inspect", "upload"])
                    self.assertEqual(main.call_count, 2)
                    self.assertEqual(len(scans), 1)
                    save.assert_called_once()
                    self.assertTrue(archive.is_file())
                    release.validate_image_archive(archive, request, release.request_identity(request))


class VerificationOnlyTests(unittest.TestCase):
    def test_local_mode_builds_hosts_scans_and_saves_without_any_production_access(self):
        manifest, raw, files = manifest_fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "release.json").write_bytes(raw)
            with tarfile.open(root / "web.tar.gz", "w:gz") as bundle:
                for name, data in {**files, "release.json": raw}.items():
                    add_tar_file(bundle, "web/" + name, data)
            request = request_fixture()
            request["manifest_sha256"] = hashlib.sha256(raw).hexdigest()
            image_archive(root / "fixture.tar.gz", request)
            docker_save = gzip.decompress((root / "fixture.tar.gz").read_bytes())

            def local_command(args, **kwargs):
                if args[:3] == ["docker", "image", "inspect"]:
                    return (request["image_id"] + "\n").encode() if "--format" in args else None
                return b""

            env = {"GITHUB_SHA": SOURCE, "GITHUB_REPOSITORY": release.REPOSITORY,
                   "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1"}
            process = SimpleNamespace(stdout=io.BytesIO(docker_save), wait=lambda timeout: 0)
            with patch.dict(release.os.environ, env, clear=True), patch.object(release, "command", side_effect=local_command) as commands, patch.object(release, "hosting_checks") as hosting, patch.object(release.subprocess, "Popen", return_value=process), patch.object(release, "current_main") as main, patch.object(release, "BrokerClient") as broker:
                release.client_main(root, verify_only=True)
            main.assert_not_called()
            broker.assert_not_called()
            hosting.assert_called_once()
            args = [call.args[0] for call in commands.call_args_list]
            self.assertTrue(any(call[:2] == ["docker", "build"] for call in args))
            self.assertIn(["trivy", "image", "--severity", "HIGH,CRITICAL", "--ignore-unfixed", "--exit-code", "1", release.request_identity(request)], args)
            archive = root / (manifest["release_id"] + ".image.tar.gz")
            self.assertTrue(archive.is_file())
            release.validate_image_archive(archive, request, release.request_identity(request))

    def test_local_mode_still_requires_exact_identity_and_deploy_still_requires_main(self):
        _, raw, _ = manifest_fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "release.json").write_bytes(raw)
            env = {"GITHUB_SHA": "f" * 40, "GITHUB_REPOSITORY": release.REPOSITORY,
                   "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1"}
            with patch.dict(release.os.environ, env, clear=True), patch.object(release, "current_main") as main, patch.object(release, "BrokerClient") as broker:
                with self.assertRaises(release.ReleaseError):
                    release.client_main(root, verify_only=True)
                with self.assertRaises(release.ReleaseError):
                    release.client_main(root)
            main.assert_not_called()
            broker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
