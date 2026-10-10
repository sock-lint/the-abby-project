# Pull request validation

[`pr-validation.yml`](../../.github/workflows/pr-validation.yml) runs on every
pull request targeting `main`, merge queue requests, and manual dispatch. It
reports three stable checks:

| Check | What it verifies | Runner |
| --- | --- | --- |
| `Browser bridge` | The same-origin token bridge, account changes, and local sign-out through `scripts/unity/test_browser_session.cjs` | GitHub-hosted Ubuntu, Node 22 |
| `API fixtures` | Real Django endpoint responses match [`shared JSON fixtures`](../../contracts/api/README.md), and React consumes those same responses | GitHub-hosted Ubuntu, Python 3.12 + Node 22, SQLite + test settings |
| `Unity validation` | `CampBuild.ValidateAll` imports/compiles the project and checks the saved scene, assets, and API contracts with Unity 6000.6.5f1 | Dedicated Linux or Windows Unity runner, with a hosted readiness and result check |

There are no workflow path filters, so documentation-only or backend-only PRs
still report the checks expected by branch protection. API checks therefore
catch server changes even when no Unity or fixture file changes. Each test job
uploads its available log for seven days, including failed runs. The existing
push-to-main [`CI/CD Pipeline`](../../.github/workflows/ci-cd.yml) continues to
test, build, scan, and deploy independently.

## Provision the Unity runner once

The workflow source supports Linux and Windows, but source configuration does
not establish that a runner has been provisioned, licensed, or tested in CI.
Use a preinstalled editor and an activated license under the Actions service
account. This validation job does not export a player or require Web Build
Support.

1. Provision a dedicated x64 machine or VM with Git and a current GitHub Actions
   runner. Linux requires Bash and `sha256sum`; Windows requires Windows
   PowerShell. Keep it separate from the `deploy-platform` runner, production
   accounts and credentials, and developer browser profiles. An additional
   runner registration or label on a production host does not provide that
   separation. Restrict its account and network access to CI needs, following
   [GitHub's self-hosted runner security guidance](https://docs.github.com/en/actions/reference/security/secure-use#hardening-for-self-hosted-runners).
2. Install Unity **6000.6.5f1** and activate the appropriate license **as the
   account that runs the Actions service**. Verify batch validation under that
   identity; activation as a different interactive user or Linux `root` does
   not establish that the service can use the license. For Unity Personal,
   [Unity's documented activation method is Hub sign-in](https://docs.unity.com/en-us/engine/6000.5/manual/get-started/install-and-upgrade/licenses-and-activation/license-activation-methods);
   the Editor's serial/password and manual activation procedures do not support
   Personal. Do not put Unity account passwords, tokens, or license files in
   repository variables, source, or logs.
3. Register the runner for this repository with `self-hosted`, its operating
   system label (`Linux` or `Windows`), `X64`, and `unity-6000.6.5f1`.
   GitHub adds the first three labels by default; add the Unity version label.
   Only trusted repository contributors should send code to it. An organization
   runner group can restrict repository access; see
   [GitHub's runner routing reference](https://docs.github.com/en/actions/reference/runners/self-hosted-runners).
4. Choose the routing and installation path below. In a fresh checkout under
   the runner's account, run the applicable local validation command. Confirm
   `unity/AbbyCamp/Logs/validate.log` contains `ABBY_CAMP_VALIDATION_PASSED:`
   and no license/import/compile failure. Keep the project closed in the
   interactive editor during batch validation.
5. Once the matching runner is online and validated, set repository **Actions
   variable** `UNITY_VALIDATION_RUNNER_ENABLED` to the exact value `true`.
   Run `PR validation` manually to confirm all three checks pass. Then require
   `Browser bridge`, `API fixtures`, and `Unity validation` in the `main`
   branch rules, preserving any existing protection requirements.

Repository Actions variables select the runner; they contain configuration,
never credentials:

| Variable | Value |
| --- | --- |
| `UNITY_VALIDATION_RUNNER_OS` | `Linux` selects a Linux runner; `Windows` or an unset value preserves Windows routing |
| `UNITY_EDITOR_PATH` | Optional absolute path to the pinned editor executable on the selected machine; an unset value uses the platform default below |
| `UNITY_VALIDATION_RUNNER_ENABLED` | `true` only after provisioning, activation, and validation succeed |

Before the enabled variable is set, the hosted readiness job reports an
actionable failure and the Unity result check fails; the workflow does not queue
a job for a nonexistent runner or claim Unity validation passed. Browser/API
checks run independently and remain useful during provisioning. Setting the
variable is an operator assertion that a matching online runner exists; if that
runner later goes offline, GitHub will queue the editor job until a matching
runner returns. Set the variable back to `false` when decommissioning it.

Fork pull requests still receive hosted browser/API checks, but fail Unity
readiness explicitly. Review those changes and apply them to a trusted branch
in this repository to run the licensed editor. The workflow uses `pull_request`
and never uses `pull_request_target` to execute fork code with elevated access.
The repository flag and job-level guard are also checked before dispatching the
self-hosted job. Repository workflow changes still require review; these guards
are not a security boundary against trusted contributors changing the workflow.

### Linux

Use Ubuntu 22.04 or 24.04 on x64 with SSE2 support. Unity recommends at least
8 GB RAM; allow additional disk space for project imports and the runner's
checkout. See [Unity 6.6 system requirements](https://docs.unity3d.com/6000.6/Documentation/Manual/system-requirements.html).
The [6000.6.5f1 release page](https://unity.com/releases/editor/whats-new/6000.6.5f1)
provides the Linux editor archive. Install it so the default executable is
`/opt/unity/6000.6.5f1/Editor/Unity`, or set `UNITY_EDITOR_PATH` for a custom
installation. Ensure the service account can execute the editor and write its
own home, cache, and checkout. Check missing libraries with `ldd` and verify
the actual batch invocation before enabling CI.

Set `UNITY_VALIDATION_RUNNER_OS=Linux`. Run from the repository root:

```bash
bash ./scripts/unity/Validate-Camp.sh
# For a custom installation:
UNITY_EDITOR_PATH=/absolute/path/to/Editor/Unity bash ./scripts/unity/Validate-Camp.sh
```

The wrapper uses `-batchmode -nographics` for the scene/API checks. It does
not perform rendering, simulated input, or light baking; those require separate
runtime validation. [Unity's batch arguments](https://docs.unity3d.com/6000.6/Documentation/Manual/EditorCommandLineArguments.html)
document these limitations.

### Windows

Install through Unity Hub at
`C:\Program Files\Unity\Hub\Editor\6000.6.5f1\Editor\Unity.exe`, or set
`UNITY_EDITOR_PATH` for a custom installation. Leave
`UNITY_VALIDATION_RUNNER_OS` unset or set it to `Windows`.

When registering the runner as a Windows service, use an elevated setup shell
and explicitly choose the licensed CI account. The runner
[defaults to Network Service](https://github.com/actions/runner/blob/main/src/Runner.Listener/Configuration/WindowsServiceControlManager.cs),
which is not the interactive user whose Unity license was activated. See
[GitHub's Windows service setup](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/configure-the-application?platform=windows).

Run from the repository root under the service account:

```powershell
powershell -NoProfile -File scripts/unity/Build-Camp.ps1 -ValidateOnly
# For a custom installation:
./scripts/unity/Build-Camp.ps1 -UnityEditor 'C:\path\to\Unity.exe' -ValidateOnly
```

## Diagnose a failed Unity check

`Unity validation` passes only if both `Unity runner readiness` and
`Unity scene and API checks` succeed. A missing license, unavailable editor,
import/compile error, contract failure, or skipped editor job fails the aggregate.
The editor job checks the executable version against the pinned project version,
removes any stale validation log, runs `Validate-Camp.sh` on Linux or
`Build-Camp.ps1 -ValidateOnly` on Windows without rebuilding the saved scene,
and requires the explicit completion marker. It also compares the saved
`Camp.unity` SHA-256 before and after validation, including
failed runs; any source-scene mutation fails the check.

Read the failed job and download `unity-validation-log` when present. If the
editor version is deliberately upgraded, update `ProjectVersion.txt`, both
validation scripts' default paths, the workflow's version/runner label, and this
setup guide together, then provision and activate that version on the runner.

To reproduce the hosted checks locally:

```powershell
node --test scripts/unity/test_browser_session.cjs
$env:SECRET_KEY = 'local-contract-tests'
$env:DATABASE_URL = 'sqlite:///:memory:'
python manage.py test --settings=config.settings_test config.tests.test_api_contract_fixtures
```

From `frontend/`, run:

```powershell
npm ci
npm run test:run -- src/api/sharedContractFixtures.test.js
```

These focused checks supplement the full Django/React suites and affected
Web/native build and runtime checks; scene/API validation does not establish
that the exported player works on a phone.
