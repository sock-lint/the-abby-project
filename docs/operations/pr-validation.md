# Pull request validation

[`pr-validation.yml`](../../.github/workflows/pr-validation.yml) runs on every
pull request targeting `main`, merge queue requests, and manual dispatch. It
reports three stable checks:

| Check | What it verifies | Runner |
| --- | --- | --- |
| `Browser bridge` | The same-origin token bridge, account changes, and local sign-out through `scripts/unity/test_browser_session.cjs` | GitHub-hosted Ubuntu, Node 22 |
| `API fixtures` | Real Django endpoint responses match [`shared JSON fixtures`](../../contracts/api/README.md), and React consumes those same responses | GitHub-hosted Ubuntu, Python 3.12 + Node 22, SQLite + test settings |
| `Unity validation` | `CampBuild.ValidateAll` imports/compiles the project and checks the saved scene, assets, and API contracts with Unity 6000.6.5f1 | Dedicated Windows Unity runner, with a hosted readiness and result check |

There are no workflow path filters, so documentation-only or backend-only PRs
still report the checks expected by branch protection. API checks therefore
catch server changes even when no Unity or fixture file changes. Each test job
uploads its available log for seven days, including failed runs. The existing
push-to-main [`CI/CD Pipeline`](../../.github/workflows/ci-cd.yml) continues to
test, build, scan, and deploy independently.

## Provision the Unity runner once

The workflow source is ready, but the Unity check needs a licensed runner before
it can run. GitHub's [Windows runner inventory](https://github.com/actions/runner-images/blob/main/images/windows/Windows2025-Readme.md)
includes Visual Studio Unity tooling rather than an installed Unity Editor.
A hosted installation also needs license activation, as described in
[GameCI's activation guidance](https://game.ci/docs/github/activation/).
This project uses its existing Windows batch script with a preinstalled editor
and an activated license instead.

1. Provision a dedicated Windows x64 machine or VM for validation, with Git,
   Windows PowerShell, and a current GitHub Actions runner. Keep it separate from
   the `deploy-platform` runner, production credentials, and developer browser
   profiles. Restrict the machine's account and network access to its CI needs,
   following [GitHub's self-hosted runner security guidance](https://docs.github.com/en/actions/reference/security/secure-use#hardening-for-self-hosted-runners).
2. Install Unity **6000.6.5f1** through Unity Hub at
   `C:\Program Files\Unity\Hub\Editor\6000.6.5f1\Editor\Unity.exe`. Activate the
   appropriate Unity license **as the Windows account that runs the Actions
   service**; licensing a different interactive account does not establish that
   the service can use it. This validation job does not export a Web player or
   require Web Build Support.
3. Register the runner for this repository with the labels `self-hosted`,
   `Windows`, `X64`, and `unity-6000.6.5f1`. Only trusted repository contributors
   should be able to send code to it. An organization runner group can restrict
   repository access; see [GitHub's runner routing reference](https://docs.github.com/en/actions/reference/runners/self-hosted-runners).
4. In a fresh checkout under the runner's account, run
   `powershell -NoProfile -File scripts/unity/Build-Camp.ps1 -ValidateOnly`.
   Confirm `unity/AbbyCamp/Logs/validate.log` contains
   `ABBY_CAMP_VALIDATION_PASSED:` and no license/import/compile failure. Keep the
   project closed in the interactive editor during batch validation.
5. Once the runner is online and validated, set repository **Actions variable**
   `UNITY_VALIDATION_RUNNER_ENABLED` to the exact value `true`. Run `PR validation`
   manually to confirm all three checks pass. Then require `Browser bridge`,
   `API fixtures`, and `Unity validation` in the `main` branch rules.

Before the variable is set, the hosted readiness job reports an actionable
failure and the Unity result check fails; the workflow does not queue a job for
a nonexistent runner or claim Unity validation passed. Browser/API checks run
independently and remain useful during provisioning. Setting the variable is an
operator assertion that a matching online runner exists; if that runner later
goes offline, GitHub will queue the editor job until a matching runner returns.
Set the variable back to `false` when decommissioning it.

Fork pull requests still receive hosted browser/API checks, but fail Unity
readiness explicitly. Review those changes and apply them to a trusted branch
in this repository to run the licensed editor. The workflow uses `pull_request`
and never uses `pull_request_target` to execute fork code with elevated access.
The repository flag and job-level guard are also checked before dispatching the
self-hosted job. Repository workflow changes still require review; these guards
are not a security boundary against trusted contributors changing the workflow.

## Diagnose a failed Unity check

`Unity validation` passes only if both `Unity runner readiness` and
`Unity scene and API checks` succeed. A missing license, unavailable editor,
import/compile error, contract failure, or skipped editor job fails the aggregate.
The editor job checks the executable version against the pinned project version,
removes any stale validation log, runs `Build-Camp.ps1 -ValidateOnly` without
rebuilding the saved scene, and requires the explicit completion marker. It also
compares the saved `Camp.unity` SHA-256 before and after validation, including
failed runs; any source-scene mutation fails the check.

Read the failed job and download `unity-validation-log` when present. If the
editor version is deliberately upgraded, update `ProjectVersion.txt`, the build
script's default path, the workflow's version/runner label, and this setup guide
together, then provision and activate that version on the runner.

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
