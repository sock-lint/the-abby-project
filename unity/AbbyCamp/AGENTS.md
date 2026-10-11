# Abby Camp instructions

Read [README.md](README.md) before editing this project, and read the root
[../../CLAUDE.md](../../CLAUDE.md) for backend architecture, authentication,
and family boundaries. The README is the canonical product, session,
asset-replacement, build, and runtime-validation guide.

## Editor and assets

- Use **Unity 6000.6.5f1**, as pinned in `ProjectSettings/ProjectVersion.txt`.
  Web builds require its Web Build Support module.
- Retain source `.meta` files and their GUIDs when moving or replacing assets.
  Keep intentional package manifest/lock and project-setting changes together.
  Do not commit `Library`, builds, logs, screenshots, or user settings.
- Gameplay, identity (`CampEntityIdentity`), movement, and colliders belong on
  actor roots. `VisualPresenter` replaces only the appearance child using a
  `VisualDefinition`; art changes must preserve the root and its state.
- The saved `Assets/AbbyCamp/Scenes/Camp.unity` scene is the starting point.
  Normal validation/builds preserve it. `-RebuildScene`, `PrepareAndValidate`,
  and **Create or rebuild camp** replace the scene and generated presentation
  assets; use them only when regeneration is part of the intended change.
- Read [AssetNotes.md](AssetNotes.md) and
  [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) when importing or swapping art.

## API and browser session

Django remains authoritative for saves and progression. Show recognition only
for acknowledged saves; never invent confirmed XP, coins, drops, or ownership.
Demo practice stays local and cannot mutate a real account.

The Web `/play/` client adopts the journal's same-origin `abby_auth_token` and
validates `/api/auth/me/` before enabling child actions. It does not perform
password login. Account changes must abort old requests and clear old
presentation; a late 401 may clear only the credential used by that request.
Camp sign-out is local. Keep tokens out of URLs, logs, and cross-window messages.

Do not automatically replay a mutation after a lost or ambiguous response.
Preserve the refresh/history-acknowledgement flow documented in the README.
Keep `.jslib`/`.jspre` plug-ins compatible with Unity's ES5 requirements.
Read [../../contracts/api/README.md](../../contracts/api/README.md) before
changing shared response parsing or fixtures.

## Validate from the repository root

```powershell
node --test scripts/unity/test_browser_session.cjs
./scripts/unity/Build-Camp.ps1 -ValidateOnly
./scripts/unity/Build-Camp.ps1 -Target Web
```

Close this project in the editor before running batch validation/builds. Pass
`-UnityEditor` for a custom installation path. `-ValidateOnly` invokes
`AbbyCamp.Editor.CampBuild.ValidateAll` for scene, assets, appearance swaps,
and API contracts; it does not export a player. Inspect `Logs/validate.log`.

For affected runtime behavior, use the disposable fixture/browser workflow in
the README or build the Windows harness and run `./scripts/unity/Test-Camp.ps1`.
Web exports must be served over HTTP/HTTPS. Report separately whether source
validation, an exported-player check, and actual phone testing ran. A source
merge does not build or deploy Unity.

Linux CI uses `bash scripts/unity/Validate-Camp.sh` from the repository root.
See [../../docs/operations/pr-validation.md](../../docs/operations/pr-validation.md)
for pull-request checks, runner OS selection, and the dedicated licensed Linux
or Windows Unity runner requirements.
