"""Release a compiled Unity artifact through a narrowly scoped SSH broker.

Install this file root-owned on Proxmox and force the deploy key to invoke
``python3 /usr/local/libexec/abby-unity-release/deploy_web_release.py --broker``. The broker
accepts only the fixed protocol command, never a shell command from the caller.
No private Unity sources, GitHub token, or Coolify credentials cross SSH.
"""

import argparse
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


REPOSITORY = "sock-lint/the-abby-project"
PUBLIC_ORIGIN = "https://abby.bos.lol"
SSH_COMMAND = "abby-unity-release-v1"
SERVICE_UUID = "k137wrcpgc4l0i234jf2adm2"
DOCKER_HOST_ID = "661d990b-0f03-4758-a11b-09c5c1729230"
LXC = "119"
BROKER_ROOT = Path("/var/lib/abby-unity-release")
SHA = re.compile(r"[a-f0-9]{40}")
HASH = re.compile(r"[a-f0-9]{64}")
NUMBER = re.compile(r"[1-9][0-9]{0,19}")
IMAGE_ID = re.compile(r"sha256:[a-f0-9]{64}")
MAX_ARCHIVE = 2 * 1024**3
MAX_MANIFEST = 1024**2


class ReleaseError(Exception):
    """A safe diagnostic; never includes a remote body or subprocess stderr."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def command(args, *, input_data=None, input_file=None, allow_failure=False, timeout=1800, phase=None):
    result = subprocess.run(args, input=input_data, stdin=input_file, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=timeout, check=False)
    if result.returncode and not allow_failure:
        raise ReleaseError(f"{phase or Path(args[0]).name} failed; inspect the selected release locally.")
    return result.stdout if result.returncode == 0 else None


def read_json(raw):
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=unique_keys)
    except (ValueError, UnicodeError):
        raise ReleaseError("Invalid release JSON.") from None


def identity(source, run_id, attempt):
    if (not isinstance(source, str) or not SHA.fullmatch(source)
            or not isinstance(run_id, str) or not NUMBER.fullmatch(run_id)
            or not isinstance(attempt, str) or not NUMBER.fullmatch(attempt)):
        raise ReleaseError("Invalid source SHA or Actions run identity.")
    return f"{source}-{run_id}-{attempt}"


def safe_web_path(name):
    path = PurePosixPath(name) if isinstance(name, str) else None
    if (path is None or not re.fullmatch(r"[A-Za-z0-9_./-]+", name)
            or path.is_absolute() or str(path) != name or ".." in path.parts
            or any(part.startswith(".") for part in path.parts)):
        raise ReleaseError("Unsafe path in compiled Web artifact.")
    if name not in ("index.html", "release.json") and path.parts[0] not in ("Build", "TemplateData"):
        raise ReleaseError("The release contains files outside the compiled Web export.")
    return path


def validate_manifest(raw, source=None, run_id=None, attempt=None):
    if len(raw) > MAX_MANIFEST:
        raise ReleaseError("Release manifest exceeds the size limit.")
    data = read_json(raw)
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data.get("schema_version") != 1 or data.get("repository") != REPOSITORY:
        raise ReleaseError("Release manifest schema/repository mismatch.")
    release_id = identity(data.get("source_commit"), data.get("run_id"), data.get("run_attempt"))
    if data.get("release_id") != release_id:
        raise ReleaseError("Release manifest identity does not match its source/run.")
    if source is not None and (data["source_commit"], data["run_id"], data["run_attempt"]) != (source, run_id, attempt):
        raise ReleaseError("Compiled artifact belongs to a different source or workflow run.")
    scene = data.get("scene", {})
    if (data.get("unity_version") != "6000.6.5f1" or not isinstance(scene, dict)
            or scene.get("path") != "Assets/AbbyCamp/Licensed/MemoryMeadow.unity"
            or not HASH.fullmatch(str(scene.get("sha256", "")))
            or not HASH.fullmatch(str(data.get("licensed_assets_digest", "")))):
        raise ReleaseError("Release must identify the pinned editor and licensed saved scene/assets.")
    files = data.get("files")
    if not isinstance(files, dict) or not files or len(files) > 1000 or "index.html" not in files:
        raise ReleaseError("Release manifest is missing its compiled file inventory.")
    total = 0
    for name, meta in files.items():
        safe_web_path(name)
        if name == "release.json" or not isinstance(meta, dict) or not HASH.fullmatch(str(meta.get("sha256", ""))):
            raise ReleaseError("Invalid file checksum in release manifest.")
        size = meta.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ReleaseError("Invalid file size in release manifest.")
        total += size
    if total > MAX_ARCHIVE or not all(any(name.endswith(suffix) for name in files)
                                      for suffix in (".wasm", ".data", ".framework.js", ".loader.js")):
        raise ReleaseError("Release is oversized or missing Unity runtime files.")
    runtime = data.get("runtime_files")
    extensions = {"data": ".data", "framework": ".framework.js", "wasm": ".wasm", "loader": ".loader.js"}
    if not isinstance(runtime, dict) or set(runtime) != set(extensions):
        raise ReleaseError("Release must identify every exact runtime component.")
    for key, extension in extensions.items():
        name = runtime[key]
        if (not isinstance(name, str) or not re.fullmatch(r"Build/[a-f0-9]{32}" + re.escape(extension), name)
                or name not in files):
            raise ReleaseError("Release runtime identities must use the compiled hashed files.")
    if {name for name in files if name.startswith("Build/")} != set(runtime.values()):
        raise ReleaseError("Release contains a missing or obsolete runtime file.")
    return data


def file_hash(path):
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024**2), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def unpack_artifact(archive, manifest_raw, destination):
    manifest = validate_manifest(manifest_raw)
    expected = dict(manifest["files"])
    expected["release.json"] = {"size": len(manifest_raw), "sha256": hashlib.sha256(manifest_raw).hexdigest()}
    seen = set()
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle:
            if member.isdir() and member.name in ("web", "web/", "web/Build", "web/TemplateData"):
                continue
            if not member.isfile() or not member.name.startswith("web/"):
                raise ReleaseError("Compiled artifact contains an unexpected member or link.")
            name = member.name.removeprefix("web/")
            safe_web_path(name)
            if name in seen or name not in expected or member.size != expected[name]["size"]:
                raise ReleaseError("Compiled artifact differs from its exact manifest inventory.")
            seen.add(name)
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.extractfile(member) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
            if file_hash(target) != expected[name]["sha256"]:
                raise ReleaseError("Compiled artifact checksum mismatch.")
    if seen != set(expected):
        raise ReleaseError("Compiled artifact is missing a manifest file.")
    return manifest


def current_main(token=None):
    if token is None:
        # Public git transport avoids the shared unauthenticated REST quota.
        raw = command(["git", "-c", "credential.helper=", "-c", "http.followRedirects=false", "ls-remote",
                       f"https://github.com/{REPOSITORY}.git", "refs/heads/main"], timeout=30).decode().splitlines()
        if len(raw) != 1 or not re.fullmatch(r"[a-f0-9]{40}\s+refs/heads/main", raw[0]):
            raise ReleaseError("GitHub did not prove the fixed repository's current main.")
        return raw[0].split()[0]
    # A fixed public repository avoids authenticated redirects/endpoint input.
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "abby-unity-release", "Cache-Control": "no-cache"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(f"https://api.github.com/repos/{REPOSITORY}/git/ref/heads/main", headers=headers)
    try:
        with build_opener(NoRedirect()).open(request, timeout=30) as response:
            result = json.load(response)
            ref = result.get("object") if isinstance(result, dict) else None
            value = ref.get("sha") if isinstance(ref, dict) else None
    except (HTTPError, URLError, TimeoutError, ValueError):
        raise ReleaseError("Cannot verify GitHub current main; no new deployment is authorized.") from None
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise ReleaseError("GitHub returned an invalid main SHA.")
    return value


def require_current(source, latest=current_main):
    if latest() != source:
        raise ReleaseError("Release is superseded on main; a new workflow must build the current source.")


def request_identity(request):
    if not isinstance(request, dict) or request.get("op") not in ("inspect", "upload", "activate"):
        raise ReleaseError("Unsupported broker operation.")
    allowed = {"op", "source_commit", "run_id", "run_attempt", "release_id", "image_id", "manifest_sha256", "archive_size", "archive_sha256"}
    if set(request) - allowed:
        raise ReleaseError("Unsupported broker request fields.")
    release_id = identity(request.get("source_commit"), request.get("run_id"), request.get("run_attempt"))
    if request.get("release_id") != release_id:
        raise ReleaseError("Broker release identity mismatch.")
    if request["op"] != "inspect":
        if not IMAGE_ID.fullmatch(str(request.get("image_id", ""))) or not HASH.fullmatch(str(request.get("manifest_sha256", ""))):
            raise ReleaseError("Broker requires exact image and manifest identities.")
    if request["op"] == "upload":
        size = request.get("archive_size")
        if not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= MAX_ARCHIVE or not HASH.fullmatch(str(request.get("archive_sha256", ""))):
            raise ReleaseError("Broker upload size/checksum is invalid.")
    return f"abby-unity-web:ci-{release_id}"


def docker_host(*args, input_data=None, allow_failure=False, phase="Unity destination Docker operation"):
    return command(["pct", "exec", LXC, "--", "docker", *args], input_data=input_data, allow_failure=allow_failure, phase=phase)


def service_action(operation, image, activity_id=None):
    # This root-owned code is fixed, not supplied by the SSH client. Return only
    # selected identity/activity fields; never expose Compose or environment.
    payload = base64.b64encode(json.dumps({"operation": operation, "image": image, "activity_id": activity_id}).encode()).decode()
    php = r'''<?php
try {
 require '/var/www/html/vendor/autoload.php';
 $app = require '/var/www/html/bootstrap/app.php';
 $app->make(Illuminate\Contracts\Console\Kernel::class)->bootstrap();
 $p = json_decode(base64_decode('__PAYLOAD__'), true, flags: JSON_THROW_ON_ERROR);
 $s = App\Models\Service::where('uuid', 'k137wrcpgc4l0i234jf2adm2')->firstOrFail();
 if ($s->name !== 'abby-unity-web' || (int)$s->server_id !== 0) { throw new RuntimeException(); }
 $c = Symfony\Component\Yaml\Yaml::parse($s->docker_compose_raw);
 $v = $c['services']['unity-web'] ?? [];
 $allowed = ['image','pull_policy','expose','networks','restart','labels','healthcheck'];
 if (array_keys($c['services'] ?? []) !== ['unity-web'] || array_diff(array_keys($v), $allowed)
     || ($v['pull_policy'] ?? '') !== 'never' || !str_contains($v['image'] ?? '', 'UNITY_WEB_IMAGE')
     || ($v['networks'] ?? []) !== ['proxy']) { throw new RuntimeException(); }
 if (isset($v['healthcheck'])) {
   $h = $v['healthcheck'];
   if (!is_array($h) || array_diff(array_keys($h), ['test','interval','timeout','retries','start_period'])
       || ($h['test'] ?? []) !== ['CMD','wget','-q','-O','/dev/null','http://127.0.0.1:8080/health']
       || ($h['interval'] ?? '') !== '30s' || ($h['timeout'] ?? '') !== '5s'
       || ($h['retries'] ?? 0) !== 3 || ($h['start_period'] ?? '') !== '10s') { throw new RuntimeException(); }
 }
 if ($p['operation'] === 'inspect') {
   echo json_encode(['uuid'=>$s->uuid,'name'=>$s->name,'server_id'=>(int)$s->server_id]);
 } elseif ($p['operation'] === 'activate') {
   $active = Spatie\Activitylog\Models\Activity::where('properties->type_uuid', $s->uuid)
     ->whereIn('properties->status', ['queued','in_progress'])->exists();
   if ($active) { throw new RuntimeException(); }
   $s->environment_variables()->updateOrCreate(['key'=>'UNITY_WEB_IMAGE','is_preview'=>false],
     ['value'=>$p['image'],'is_literal'=>true,'is_runtime'=>true,'is_buildtime'=>false]);
   $s->unsetRelation('environment_variables');
   $a = App\Actions\Service\StartService::run(service: $s, pullLatestImages: false);
   echo json_encode(['activity_id'=>$a->id ?? null]);
 } elseif ($p['operation'] === 'status') {
   $a = Spatie\Activitylog\Models\Activity::findOrFail($p['activity_id']);
   if ($a->properties->get('type_uuid') !== $s->uuid || $a->properties->get('server_uuid') !== $s->server->uuid) {
     throw new RuntimeException();
   }
   echo json_encode(['activity_id'=>$a->id,'status'=>$a->properties->get('status')]);
 } else { throw new RuntimeException(); }
} catch (Throwable $e) { fwrite(STDERR,"Unity service operation failed.\n"); exit(1); }
'''
    result = read_json(docker_host("exec", "-i", "coolify", "php", input_data=php.replace("__PAYLOAD__", payload).encode(), phase=f"Coolify scoped Unity service {operation}"))
    if not isinstance(result, dict):
        raise ReleaseError("Broker service operation returned an invalid result.")
    return result


def check_destination():
    daemon = docker_host("info", "--format", "{{.ID}}", phase="Unity destination Docker identity").decode().strip()
    if daemon != DOCKER_HOST_ID:
        raise ReleaseError("Unity destination Docker daemon identity mismatch.")
    result = service_action("inspect", "")
    if result != {"uuid": SERVICE_UUID, "name": "abby-unity-web", "server_id": 0}:
        raise ReleaseError("Unity service identity mismatch.")
    return result


def image_labels(request):
    return {"org.opencontainers.image.revision": request["source_commit"],
            "org.opencontainers.image.source": f"https://github.com/{REPOSITORY}",
            "io.abby.unity.release": request["release_id"],
            "io.abby.unity.manifest.sha256": request["manifest_sha256"]}


def validate_image_archive(path, request, tag):
    with tarfile.open(path, "r:gz") as bundle:
        names, total = set(), 0
        for item in bundle:
            total += item.size
            if (item.name in names or not item.isfile() and not item.isdir()
                    or len(names) >= 5000 or total > 2 * MAX_ARCHIVE):
                raise ReleaseError("Image archive contains duplicate members/links or exceeds its limits.")
            if not re.fullmatch(r"(?:manifest\.json|index\.json|oci-layout|repositories|blobs/?|blobs/sha256/?|blobs/sha256/[a-f0-9]{64}|[a-f0-9]{64}(?:\.json|/|/(?:VERSION|json|layer\.tar))?)", item.name):
                raise ReleaseError("Image archive contains an unsupported or unsafe member path.")
            names.add(item.name)
        manifest = read_json(bundle.extractfile("manifest.json").read(MAX_MANIFEST))
        if not isinstance(manifest, list) or len(manifest) != 1 or not isinstance(manifest[0], dict) or manifest[0].get("RepoTags") != [tag]:
            raise ReleaseError("Image archive must contain only this exact Unity version tag.")
        config_name = manifest[0].get("Config", "")
        if not re.fullmatch(r"(?:blobs/sha256/)?[a-f0-9]{64}(?:\.json)?", config_name):
            raise ReleaseError("Image archive configuration path is invalid.")
        raw = bundle.extractfile(config_name).read(MAX_MANIFEST)
        if "sha256:" + hashlib.sha256(raw).hexdigest() != request["image_id"]:
            raise ReleaseError("Image archive config differs from the expected image ID.")
        config_data = read_json(raw)
        config = config_data.get("config", {}) if isinstance(config_data, dict) else None
        labels = config.get("Labels") if isinstance(config, dict) else None
        if not isinstance(labels, dict) or any(labels.get(key) != value for key, value in image_labels(request).items()):
            raise ReleaseError("Image archive release/source labels mismatch.")
        if "index.json" in names:
            index = read_json(bundle.extractfile("index.json").read(MAX_MANIFEST))
            entries = index.get("manifests") if isinstance(index, dict) else None
            if not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0], dict) or not IMAGE_ID.fullmatch(str(entries[0].get("digest", ""))):
                raise ReleaseError("OCI archive index must identify only one Unity image.")
            annotations = entries[0].get("annotations", {})
            full_tag = "docker.io/library/" + tag
            if (not isinstance(annotations, dict) or annotations.get("io.containerd.image.name", tag) not in (tag, full_tag)
                    or annotations.get("org.opencontainers.image.ref.name", tag.split(":", 1)[1]) not in (tag, tag.split(":", 1)[1])):
                raise ReleaseError("OCI archive index refers to a different image tag.")
            descriptor = entries[0]["digest"].removeprefix("sha256:")
            descriptor_raw = bundle.extractfile("blobs/sha256/" + descriptor).read(MAX_MANIFEST)
            if hashlib.sha256(descriptor_raw).hexdigest() != descriptor:
                raise ReleaseError("OCI archive manifest descriptor checksum mismatch.")
            descriptor_data = read_json(descriptor_raw)
            config_descriptor = descriptor_data.get("config") if isinstance(descriptor_data, dict) else None
            if not isinstance(config_descriptor, dict) or config_descriptor.get("digest") != request["image_id"]:
                raise ReleaseError("OCI archive manifest config refers to a different image.")


def receive_archive(stream, destination, size, checksum):
    if destination.exists():
        # Never overwrite the archive of a previous release attempt.
        raise ReleaseError("Versioned archive already exists; use a new workflow attempt.")
    temporary = destination.with_suffix(".partial")
    hasher = hashlib.sha256()
    remaining = size
    try:
        with temporary.open("xb") as output:
            while remaining:
                chunk = stream.read(min(1024**2, remaining))
                if not chunk:
                    raise ReleaseError("Unity upload was interrupted before the declared size.")
                output.write(chunk)
                hasher.update(chunk)
                remaining -= len(chunk)
        if stream.read(1) or hasher.hexdigest() != checksum:
            raise ReleaseError("Unity upload size/checksum mismatch.")
        temporary.rename(destination)
    finally:
        temporary.unlink(missing_ok=True)


def exact_image(request, tag):
    raw = docker_host("image", "inspect", "--format", "{{json .}}", tag, allow_failure=True)
    if raw is None:
        return False
    data = read_json(raw)
    if data.get("Id") != request["image_id"] or any(data.get("Config", {}).get("Labels", {}).get(k) != v for k, v in image_labels(request).items()):
        raise ReleaseError("Version tag already names different content; refusing to replace it.")
    return True


def healthy_image(image_id):
    containers = docker_host("ps", "-q", "--filter", f"label=com.docker.compose.project={SERVICE_UUID}",
                             "--filter", "label=com.docker.compose.service=unity-web").decode().split()
    if len(containers) != 1 or not re.fullmatch(r"[a-f0-9]{12,64}", containers[0]):
        return False
    raw = docker_host("inspect", "--format", "{{.Image}} {{if .State.Health}}{{.State.Health.Status}}{{end}}", containers[0])
    return raw.decode().strip() == f"{image_id} healthy"


def activity_status(activity_id):
    if type(activity_id) is not int or activity_id <= 0:
        raise ReleaseError("Coolify did not prove a valid scoped activity ID.")
    result = service_action("status", "", activity_id)
    if result.get("activity_id") != activity_id or result.get("status") not in ("queued", "in_progress", "finished", "error", "killed", "cancelled", "closed"):
        raise ReleaseError("Coolify returned an invalid scoped activity status.")
    return result["status"]


def record_activity(root, request, activity_id):
    state = {"activity_id": activity_id, "release_id": request["release_id"], "source_commit": request["source_commit"]}
    temporary = root / "activity-state.tmp"
    temporary.write_text(json.dumps(state), encoding="utf-8")
    temporary.replace(root / "activity-state.json")


def broker_operation(request, stream, root=BROKER_ROOT, latest=current_main, clock=time.monotonic, sleep=time.sleep):
    tag = request_identity(request)
    check_destination()
    if request["op"] == "inspect":
        return {"ok": True, "uuid": SERVICE_UUID, "docker_host_id": DOCKER_HOST_ID}
    require_current(request["source_commit"], latest)
    archive = root / (request["release_id"] + ".tar.gz")
    if request["op"] == "upload":
        receive_archive(stream, archive, request["archive_size"], request["archive_sha256"])
        validate_image_archive(archive, request, tag)
        require_current(request["source_commit"], latest)
        if not exact_image(request, tag):
            command(["pct", "push", LXC, str(archive), str(archive), "--perms", "0600"])
            require_current(request["source_commit"], latest)
            docker_host("image", "load", "--input", str(archive))
        if not exact_image(request, tag):
            raise ReleaseError("Loaded image did not prove the expected identity.")
        return {"ok": True, "image_id": request["image_id"]}
    if not archive.is_file():
        raise ReleaseError("This release has no broker-verified uploaded archive.")
    validate_image_archive(archive, request, tag)
    if not exact_image(request, tag):
        raise ReleaseError("Release image is missing from the selected destination.")
    state_path = root / "activity-state.json"
    if state_path.exists():
        previous = read_json(state_path.read_bytes())
        if not isinstance(previous, dict) or activity_status(previous.get("activity_id")) not in ("finished", "error"):
            raise ReleaseError("Previous Unity activity has not safely drained; inspect it before queuing another release.")
    require_current(request["source_commit"], latest)
    activity = service_action("activate", tag)
    activity_id = activity.get("activity_id")
    if type(activity_id) is not int or activity_id <= 0:
        raise ReleaseError("Coolify did not prove the requested Unity activity; inspect its queue.")
    record_activity(root, request, activity_id)
    deadline = clock() + 600
    superseded = None
    while clock() < deadline:
        # StartService is asynchronous and cancellation does not reliably remove
        # its queued task. Keep the lock until that exact activity drains even
        # when main changes, so an older release cannot overtake a newer one.
        if superseded is None:
            try:
                require_current(request["source_commit"], latest)
            except ReleaseError as error:
                superseded = error
        status = activity_status(activity_id)
        if status in ("finished", "error"):
            if superseded is not None:
                raise superseded
            if status != "finished":
                raise ReleaseError("Unity Coolify activity failed; inspect that exact activity. Archives are retained.")
            break
        sleep(10)
    else:
        raise ReleaseError("Unity activity did not safely drain; further releases will refuse until it finishes. Inspect its recorded activity.")
    deadline = clock() + 120
    while clock() < deadline:
        require_current(request["source_commit"], latest)
        if healthy_image(request["image_id"]):
            return {"ok": True, "image_id": request["image_id"], "activity_id": activity_id}
        sleep(10)
    raise ReleaseError("Exact Unity image did not become healthy; inspect the selected Coolify activity. Archives are retained.")


def broker_main():
    if os.environ.get("SSH_ORIGINAL_COMMAND") != SSH_COMMAND or os.geteuid() != 0:
        raise ReleaseError("Broker requires its root-owned forced SSH command.")
    import fcntl
    os.umask(0o077)
    # Provisioned by the operator in Proxmox and LXC; requests cannot choose paths.
    if not BROKER_ROOT.is_dir() or BROKER_ROOT.is_symlink():
        raise ReleaseError("Provision the fixed broker archive directory first.")
    raw = sys.stdin.buffer.readline(16385)
    if len(raw) > 16384 or not raw.endswith(b"\n"):
        raise ReleaseError("Broker request header exceeds its limit.")
    request = read_json(raw)
    request_identity(request)
    with (BROKER_ROOT / "release.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        result = broker_operation(request, sys.stdin.buffer)
    print(json.dumps(result), flush=True)


class BrokerClient:
    def __init__(self, target, key, known_hosts):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*(?:@[A-Za-z0-9][A-Za-z0-9_.-]*)?", target):
            raise ReleaseError("Invalid Unity SSH target.")
        if not Path(key).is_file() or not Path(known_hosts).is_file():
            raise ReleaseError("Unity deployment requires a scoped SSH key and pinned known-hosts file.")
        self.args = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "IdentitiesOnly=yes",
                     "-o", "ConnectTimeout=15", "-o", f"UserKnownHostsFile={known_hosts}", "-i", key, target, SSH_COMMAND]

    def request(self, request, archive=None):
        request_identity(request)
        with tempfile.TemporaryFile() as payload:
            payload.write(json.dumps(request, separators=(",", ":")).encode() + b"\n")
            if archive:
                with archive.open("rb") as data:
                    shutil.copyfileobj(data, payload)
            payload.seek(0)
            result = read_json(command(self.args, input_file=payload))
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise ReleaseError("Unity broker did not confirm success.")
        return result


def public_get(url):
    try:
        response = build_opener(NoRedirect()).open(Request(url, headers={"Cache-Control": "no-cache", "Accept-Encoding": "identity"}), timeout=120)
        return response
    except (HTTPError, URLError, TimeoutError):
        raise ReleaseError("Public Unity release verification request failed; check routing and caches.") from None


def verify_public(manifest_raw, manifest, origin=PUBLIC_ORIGIN):
    with public_get(origin + "/play/release.json") as response:
        if response.read(MAX_MANIFEST + 1) != manifest_raw:
            raise ReleaseError("Public release manifest does not match this exact source/run.")
    for name, meta in manifest["files"].items():
        if name == "index.html":
            continue  # Cloudflare injects markup into HTML; check its loader below.
        with public_get(origin + "/play/" + name) as response:
            if name.endswith(".wasm") and response.headers.get_content_type() != "application/wasm":
                raise ReleaseError("Public WebAssembly response has an incorrect media type.")
            stream = gzip.GzipFile(fileobj=response) if response.headers.get("Content-Encoding") == "gzip" else response
            hasher, size = hashlib.sha256(), 0
            while chunk := stream.read(1024**2):
                size += len(chunk)
                if size > meta["size"]:
                    raise ReleaseError("Public Unity file exceeds its expected size.")
                hasher.update(chunk)
            if size != meta["size"] or hasher.hexdigest() != meta["sha256"]:
                raise ReleaseError("Public Unity file checksum mismatch; check routing and caches.")
    with public_get(origin + "/play/") as response:
        if response.headers.get_content_type() != "text/html":
            raise ReleaseError("Public Play page is not Unity HTML.")
        html = response.read(4 * 1024**2).decode("utf-8")
        if not re.search(r'<canvas\b[^>]*\bid=["\']unity-canvas["\']', html):
            raise ReleaseError("Public Play HTML is missing its Unity canvas.")
        patterns = {"data": r"\bdataUrl\s*:\s*['\"]([^'\"]+)['\"]",
                    "framework": r"\bframeworkUrl\s*:\s*['\"]([^'\"]+)['\"]",
                    "wasm": r"\bcodeUrl\s*:\s*['\"]([^'\"]+)['\"]",
                    "loader": r"\bloader\.src\s*=\s*['\"]([^'\"]+)['\"]"}
        for key, pattern in patterns.items():
            if re.findall(pattern, html) != [manifest["runtime_files"][key]]:
                raise ReleaseError("Public Play HTML references a different runtime component; check routing and caches.")


def hosting_checks(tag, manifest_raw, manifest):
    """Check the actual packaged image before uploading or changing production."""
    container = command(["docker", "run", "--detach", "--rm", "--publish", "127.0.0.1::8080", tag]).decode().strip()
    if not re.fullmatch(r"[a-f0-9]{64}", container):
        raise ReleaseError("Local Unity hosting container identity is invalid.")
    try:
        port = command(["docker", "port", container, "8080/tcp"]).decode().strip()
        if not re.fullmatch(r"127\.0\.0\.1:[0-9]{1,5}", port):
            raise ReleaseError("Local Unity check must bind only to loopback.")
        origin = "http://" + port
        deadline = time.monotonic() + 30
        while True:
            try:
                with public_get(origin + "/health") as response:
                    if response.read(32) != b"ok\n":
                        raise ReleaseError("Local nginx health response mismatch.")
                break
            except ReleaseError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(1)
        verify_public(manifest_raw, manifest, origin)
        for path, expected in (("/play", 308), ("/play/Build/missing.wasm", 404),
                               ("/play/Build/missing.data", 404), ("/api/auth/me/", 404)):
            request = Request(origin + path, headers={"Accept-Encoding": "identity"})
            try:
                with build_opener(NoRedirect()).open(request, timeout=10) as response:
                    status, headers = response.status, response.headers
            except HTTPError as error:
                status, headers = error.code, error.headers
                error.close()
            if status != expected or path == "/play" and headers.get("Location") != "/play/":
                raise ReleaseError("Local Unity hosting isolation/redirect check failed.")
            if path == "/api/auth/me/" and headers.get("Cache-Control") != "no-store":
                raise ReleaseError("Local Unity host must not cache API paths.")
    finally:
        command(["docker", "rm", "--force", container], allow_failure=True, timeout=30)


def client_main(artifact_dir, verify_only=False):
    identity_names = ["GITHUB_SHA", "GITHUB_REPOSITORY", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"]
    ssh_names = ["UNITY_WEB_SSH_TARGET", "UNITY_WEB_SSH_KEY_PATH", "UNITY_WEB_SSH_KNOWN_HOSTS_PATH"]
    if os.environ.get("GITHUB_REPOSITORY") != REPOSITORY or any(not os.environ.get(name) for name in identity_names):
        raise ReleaseError("Unity artifact verification requires its exact source, repository, and Actions run identity.")
    if not verify_only and (os.environ.get("GITHUB_REF") != "refs/heads/main"
                            or not os.environ.get("GITHUB_TOKEN")
                            or any(not os.environ.get(name) for name in ssh_names)):
        raise ReleaseError("Unity release requires trusted main and the documented Actions/SSH configuration.")
    source, run_id, attempt = (os.environ[name] for name in ("GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"))
    if (artifact_dir / "release.json").stat().st_size > MAX_MANIFEST:
        raise ReleaseError("Compiled manifest exceeds its size limit.")
    raw = (artifact_dir / "release.json").read_bytes()
    manifest = validate_manifest(raw, source, run_id, attempt)
    latest = lambda: current_main(os.environ["GITHUB_TOKEN"])
    request = {"op": "inspect", "source_commit": source, "run_id": run_id, "run_attempt": attempt, "release_id": manifest["release_id"]}
    if not verify_only:
        require_current(source, latest)
        broker = BrokerClient(*(os.environ[name] for name in ssh_names))
        broker.request(request)
    tag = request_identity(request)
    repository_root = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix="abby-unity-release-") as temporary:
        context = Path(temporary)
        export = context / "unity/AbbyCamp/Builds/Web"
        unpack_artifact(artifact_dir / "web.tar.gz", raw, export)
        shutil.copy(repository_root / "Dockerfile.unity-web", context)
        shutil.copy(repository_root / "Dockerfile.unity-web.dockerignore", context)
        hosting = context / "scripts/unity/hosting"
        hosting.mkdir(parents=True)
        shutil.copy(repository_root / "scripts/unity/hosting/nginx.conf", hosting)
        request["manifest_sha256"] = hashlib.sha256(raw).hexdigest()
        build_args = ["docker", "build", "--pull", "--file", str(context / "Dockerfile.unity-web"), "--tag", tag]
        for key, value in image_labels(request).items():
            build_args += ["--label", f"{key}={value}"]
        if command(["docker", "image", "inspect", tag], allow_failure=True) is not None:
            raise ReleaseError("Local immutable version tag already exists; use a new workflow attempt.")
        command([*build_args, str(context)])
        request["image_id"] = command(["docker", "image", "inspect", "--format", "{{.Id}}", tag]).decode().strip()
        if not IMAGE_ID.fullmatch(request["image_id"]):
            raise ReleaseError("Local Docker build did not return a valid image identity.")
        hosting_checks(tag, raw, manifest)
        command(["trivy", "image", "--severity", "HIGH,CRITICAL", "--ignore-unfixed", "--exit-code", "1", tag])
        archive = artifact_dir / (manifest["release_id"] + ".image.tar.gz")
        if archive.exists():
            raise ReleaseError("Local versioned image archive already exists.")
        with archive.open("xb") as output:
            with gzip.GzipFile(fileobj=output, mode="wb", mtime=0) as compressed:
                process = subprocess.Popen(["docker", "image", "save", tag], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                try:
                    shutil.copyfileobj(process.stdout, compressed)
                finally:
                    process.stdout.close()
                if process.wait(timeout=300):
                    raise ReleaseError("Saving the Unity image archive failed.")
        validate_image_archive(archive, request, tag)
        if verify_only:
            print(f"Unity artifact {manifest['release_id']} passed local hosting, vulnerability scanning, and exact image archive checks; no production operation was requested.", flush=True)
            return
        request.update(op="upload", archive_size=archive.stat().st_size, archive_sha256=file_hash(archive))
        require_current(source, latest)
        broker.request(request, archive)
        request["op"] = "activate"
        request.pop("archive_size")
        request.pop("archive_sha256")
        require_current(source, latest)
        broker.request(request)
        require_current(source, latest)
        verify_public(raw, manifest)
        with public_get(PUBLIC_ORIGIN + "/health") as response:
            health = read_json(response.read(MAX_MANIFEST))
            if not isinstance(health, dict) or health.get("status") != "ok" or health.get("db") != "up":
                raise ReleaseError("Existing Abby app/database health did not pass after the Unity release.")
        print(f"Unity release {manifest['release_id']} is healthy; public files match source {source}.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--broker", action="store_true")
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument("--verify-only", action="store_true", help="Build, host-check, scan, and save an artifact locally without SSH or deployment.")
    args = parser.parse_args()
    if args.broker and args.artifact_dir is None and not args.verify_only:
        broker_main()
    elif not args.broker and args.artifact_dir is not None:
        client_main(args.artifact_dir.resolve(), verify_only=args.verify_only)
    else:
        raise ReleaseError("Choose --broker or --artifact-dir.")


if __name__ == "__main__":
    try:
        main()
    except (ReleaseError, OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired, tarfile.TarError, KeyboardInterrupt) as error:
        # Native errors may contain remote/config paths; keep only our diagnostics.
        message = str(error) if isinstance(error, ReleaseError) else "Unity release failed or was interrupted; preserved artifacts remain available."
        print(f"::error::{message}", file=sys.stderr)
        sys.exit(1)
