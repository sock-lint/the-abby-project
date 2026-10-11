#!/usr/bin/env bash
# Export a pinned, licensed Unity Web player and produce a source-bound artifact.
set -euo pipefail

task_repository="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
task_project="$task_repository/unity/AbbyCamp"
task_python="${PYTHON:-python3}"
task_packager="$task_repository/scripts/unity/package_web_release.py"
task_source="${UNITY_WEB_SOURCE_SHA:?Set UNITY_WEB_SOURCE_SHA to the exact full source commit.}"
task_private_root="${UNITY_WEB_PRIVATE_ASSET_ROOT:?Configure a prepared private art root outside the checkout.}"
task_release="${UNITY_WEB_RELEASE_DIR:?Configure a fresh release output directory.}"
task_run="${GITHUB_RUN_ID:?Set GITHUB_RUN_ID for the release identity.}"
task_attempt="${GITHUB_RUN_ATTEMPT:?Set GITHUB_RUN_ATTEMPT for the release identity.}"
task_editor="${UNITY_EDITOR_PATH:-/opt/unity/6000.6.5f1/Editor/Unity}"
task_release="$("$task_python" -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).absolute())' "$task_release")"
task_pinned="$(sed -n 's/^m_EditorVersion: //p' "$task_project/ProjectSettings/ProjectVersion.txt" | tr -d '\r')"
if [[ "$task_pinned" != '6000.6.5f1' || ! -x "$task_editor" ]]; then
  echo 'A licensed Unity 6000.6.5f1 editor is required.' >&2
  exit 1
fi
task_version="$("$task_editor" -version)"
if [[ ! "$task_version" =~ (^|[[:space:]])6000\.6\.5f1([[:space:]_]|$) ]]; then
  echo 'Installed Unity does not match the pinned editor.' >&2
  exit 1
fi
"$task_python" - "$task_repository" "$task_source" "$task_release" "$task_packager" <<'PY'
import importlib.util, pathlib, sys
repository, source, release, helper = sys.argv[1:]
spec = importlib.util.spec_from_file_location("package_web_release", helper)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.validate_source(pathlib.Path(repository), source)
output = pathlib.Path(release).absolute()
if output.exists() or output.is_symlink():
    raise SystemExit("Release output must not already exist.")
project = pathlib.Path(repository).resolve() / "unity/AbbyCamp"
if output.resolve() == project or project.is_relative_to(output.resolve()):
    raise SystemExit("Release output cannot contain the source project.")
if output.resolve().is_relative_to(pathlib.Path(repository).resolve()) and not output.resolve().is_relative_to(project / "Builds"):
    raise SystemExit("Inside the checkout, release output must be under ignored Unity Builds.")
if not (project / "Assets/AbbyCamp/Scenes/Camp.unity").is_file():
    raise SystemExit("The saved public source scene is missing; regeneration is forbidden.")
output.mkdir(parents=True)
PY
task_digest="$("$task_python" "$task_packager" stage-assets --repository "$task_repository" --private-root "$task_private_root")"
task_scene_record="$task_release/saved-scenes.json"
"$task_python" - "$task_project" "$task_scene_record" <<'PY'
import hashlib, json, pathlib, sys
project = pathlib.Path(sys.argv[1])
scenes = {p.relative_to(project).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
          for p in (project / "Assets").rglob("*.unity")}
pathlib.Path(sys.argv[2]).write_text(json.dumps(scenes), encoding="utf-8")
PY
task_check_scenes() {
  "$task_python" - "$task_project" "$task_scene_record" <<'PY'
import hashlib, json, pathlib, sys
project = pathlib.Path(sys.argv[1])
before = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
after = {p.relative_to(project).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
         for p in (project / "Assets").rglob("*.unity")}
if before != after:
    raise SystemExit("Unity release changed saved scenes; release rejected without regeneration.")
PY
}
task_verify_scenes() {
  local task_exit=$?
  trap - EXIT
  if ! task_check_scenes; then
    task_exit=1
  fi
  exit "$task_exit"
}
trap task_verify_scenes EXIT

task_export="$task_release/export"
task_log="$task_release/build-web.log"
echo "Building the preserved licensed scene with Unity $task_pinned."
# BuildWeb checks Web Build Support and validates both scenes/API contracts.
"$task_editor" -batchmode -nographics -quit -buildTarget WebGL \
  -projectPath "$task_project" -executeMethod AbbyCamp.Editor.CampBuild.BuildWeb \
  -abbyWebOutput "$task_export" -logFile "$task_log"
if ! grep -Fq 'ABBY_CAMP_WEB_BUILD_PASSED:' "$task_log" || \
   ! grep -Fq 'ABBY_CAMP_VALIDATION_PASSED:' "$task_log"; then
  echo 'Unity did not confirm a completed Web export and validation.' >&2
  exit 1
fi
# Only compiled static files and release provenance enter the transferable tar.
task_check_scenes
"$task_python" "$task_packager" package --repository "$task_repository" \
  --export "$task_export" --output "$task_release/package" --source-commit "$task_source" \
  --run-id "$task_run" --run-attempt "$task_attempt" --licensed-assets-digest "$task_digest"
echo "Unity release ready: $task_release/package/web.tar.gz"
