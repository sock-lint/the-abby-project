#!/usr/bin/env bash
# Validate the saved Unity project on a licensed Linux runner without exporting.
set -euo pipefail

task_repository="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
task_project="$task_repository/unity/AbbyCamp"
task_pinned_version="$(sed -n 's/^m_EditorVersion: //p' "$task_project/ProjectSettings/ProjectVersion.txt" | tr -d '\r')"
if [[ "$task_pinned_version" != '6000.6.5f1' ]]; then
  echo 'Update the Unity runner, workflow labels, and setup guide to match ProjectVersion.txt.' >&2
  exit 1
fi

task_unity_editor="${UNITY_EDITOR_PATH:-/opt/unity/6000.6.5f1/Editor/Unity}"
if [[ ! -x "$task_unity_editor" ]]; then
  echo "Unity executable not found or executable: $task_unity_editor" >&2
  exit 1
fi
task_version_output="$("$task_unity_editor" -version)"
if [[ ! "$task_version_output" =~ (^|[[:space:]])([0-9]+\.[0-9]+\.[0-9]+[a-z][0-9]+)([[:space:]_]|$) ]]; then
  echo 'Unity did not report an Editor version through -version.' >&2
  exit 1
fi
task_installed_version="${BASH_REMATCH[2]}"
if [[ "$task_installed_version" != "$task_pinned_version" ]]; then
  echo "Unity executable version does not match ProjectVersion.txt: $task_installed_version" >&2
  exit 1
fi

task_log="$task_project/Logs/validate.log"
mkdir -p -- "$(dirname -- "$task_log")"
rm -f -- "$task_log"
if [[ ! -f "$task_project/Assets/AbbyCamp/Scenes/Camp.unity" ]]; then
  echo 'The saved Camp.unity scene is missing; validate a complete source checkout.' >&2
  exit 1
fi

# Include optional local licensed scenes when present. Compare bytes on success
# and failure; retain Unity's failure code if it also changed source scenes.
declare -A task_scene_hashes=()
while IFS= read -r -d '' task_scene; do
  task_hash="$(sha256sum -- "$task_scene")"
  task_scene_hashes["$task_scene"]="${task_hash%% *}"
done < <(find "$task_project/Assets" -type f -name '*.unity' -print0)

task_verify_saved_scenes() {
  local task_exit_code=$? task_changed=false task_scene task_hash
  trap - EXIT
  for task_scene in "${!task_scene_hashes[@]}"; do
    if [[ ! -f "$task_scene" ]] || ! task_hash="$(sha256sum -- "$task_scene")"; then
      echo "Unity validation removed or made a saved scene unreadable: $task_scene" >&2
      task_changed=true
    elif [[ "${task_hash%% *}" != "${task_scene_hashes["$task_scene"]}" ]]; then
      echo "Unity validation changed saved scene bytes: $task_scene" >&2
      task_changed=true
    fi
  done
  if [[ "$task_changed" == true && "$task_exit_code" == 0 ]]; then
    task_exit_code=1
  fi
  if [[ "$task_exit_code" == 0 ]]; then
    echo 'Prototype validation passed; saved scene bytes preserved.'
  fi
  exit "$task_exit_code"
}
trap task_verify_saved_scenes EXIT

echo "Unity is validating saved source. Log: $task_log"
if "$task_unity_editor" -batchmode -nographics -quit \
  -projectPath "$task_project" \
  -executeMethod AbbyCamp.Editor.CampBuild.ValidateAll \
  -logFile "$task_log"; then
  :
else
  task_exit_code=$?
  if [[ -f "$task_log" ]]; then tail -n 60 -- "$task_log"; fi
  echo "Unity exited with code $task_exit_code." >&2
  exit "$task_exit_code"
fi
if [[ ! -f "$task_log" ]] || ! grep -Fq 'ABBY_CAMP_VALIDATION_PASSED:' "$task_log"; then
  if [[ -f "$task_log" ]]; then tail -n 60 -- "$task_log"; fi
  echo 'Unity did not report completed scene, asset, and API validation. Check the log for import, compile, or license errors.' >&2
  exit 1
fi
