# Unity Web releases

Unity source must be compiled into a Web player before `/play/` changes. The
[main CI/CD workflow](../../.github/workflows/ci-cd.yml) exports it on the licensed
Unity runner and deploys the existing separate Coolify `abby-unity-web` service
after the React/Django deployment succeeds. PR validation does not deploy.

## Release path

1. The current-main guard rejects superseded commits and non-main deployment
   dispatches. `Build licensed Unity Web player` uses the isolated Linux runner
   with the pinned editor and Web Build Support.
2. `Build-Web.sh` requires an exact clean checkout, fresh output, and a prepared
   private asset root. It preserves all saved scenes and `.meta` GUIDs, requires
   Unity's validation/build markers, and verifies the private asset digest. It
   never regenerates scenes or substitutes prototype art.
3. Only `web.tar.gz` and `release.json` transfer between jobs. The archive contains
   compiled browser files and a matching embedded manifest, with source SHA,
   run/attempt, editor version, scene/asset digests and file sizes/checksums.
   Private source art, caches, licenses and credentials are excluded. Compiled
   artifacts expire after one day; build logs expire after seven days.
4. After platform deployment succeeds, `Deploy and verify Unity Web` validates
   the artifact against the exact Actions identity, builds a versioned nginx
   image, tests its HTTP output, and scans fixable HIGH/CRITICAL vulnerabilities.
5. A forced-command SSH broker checks current main, fixed service/daemon identity,
   and archive/image checksums. It loads the image and changes only
   `UNITY_WEB_IMAGE`, through Coolify's installed `StartService` action.
6. Success requires the exact healthy image, matching public `/play/release.json`,
   non-HTML file hashes, matching HTML runtime URLs and healthy application/database
   state. Cloudflare may modify HTML, so its byte hash is not compared publicly.

Tags are `abby-unity-web:ci-<full-source-sha>-<run-id>-<attempt>` and cannot be
reused for different content. Host archives and previous images remain for
recovery; image pruning is separate from Git branch/worktree cleanup.

## Configured infrastructure

| Role | Configuration |
| --- | --- |
| Unity runner | `unity-ci-01-abby-unity-1`, VM 120, `192.168.4.183`, account `unity-ci` |
| Editor | `/opt/unity/6000.6.5f1/Editor/Unity`, Unity Personal, matching Web Build Support |
| Prepared private art | `/opt/abby-unity/private-assets/20261011`, root owned, read only to `unity-ci` |
| Deployment runner | `gha-runner-01-abby-deploy-1`, VM 110, `192.168.4.150`, label `deploy-platform` |
| Broker host/helper | Proxmox `192.168.4.31`, `/usr/local/libexec/abby-unity-release/deploy_web_release.py`, root owned |
| Broker storage | `/var/lib/abby-unity-release`, root owned mode `0700` on Proxmox and LXC 119 |
| Coolify service | `k137wrcpgc4l0i234jf2adm2`, `abby-unity-web`, server ID `0` |
| Docker daemon | `661d990b-0f03-4758-a11b-09c5c1729230` inside LXC 119 |
| Public player | `https://abby.bos.lol/play/` |

The private root holds `Assets/ThirdParty/Meshtint` and `Assets/AbbyCamp/Licensed`,
both root `.meta` files, and the authored `Licensed/MemoryMeadow.unity`. Keep original
packs and purchase records in private backup storage. For an art update, verify
the prepared scene, provision a new versioned root, and update its variable.
Source merges do not update private art automatically. Routine releases must not
run `PrepareLicensed`.

## Actions configuration

| Repository variable | Value |
| --- | --- |
| `UNITY_WEB_RELEASE_ENABLED` | `true` after runner/broker verification |
| `UNITY_WEB_PRIVATE_ASSET_ROOT` | `/opt/abby-unity/private-assets/20261011` |
| `UNITY_WEB_SSH_TARGET` | `root@192.168.4.31` |
| `UNITY_WEB_SSH_KNOWN_HOSTS` | Verified Proxmox host-key line for `192.168.4.31` |
| `UNITY_EDITOR_PATH` | Optional; defaults to the pinned editor path above |

Store `UNITY_WEB_DEPLOY_SSH_KEY` in the **`unity-production` GitHub environment**,
whose deployment branch policy allows only `main`. Only the deploy job uses that
environment. Install its public key on Proxmox with `restrict`,
`from="192.168.4.150"`, and this forced command:

```text
/usr/bin/python3 /usr/local/libexec/abby-unity-release/deploy_web_release.py --broker
```

The only accepted original SSH command is `abby-unity-release-v1`. The broker
accepts a bounded protocol for this fixed Unity service; it cannot provide a
shell, forwarding, SCP, or arbitrary Coolify access. Pin its host key through a
trusted administrator connection. The client removes the job's temporary key
with `always()` cleanup. Existing platform API/registry credentials are unchanged.
Install broker changes through an administrator connection after review; CI
cannot replace the root-owned helper. Revalidate it after a Coolify upgrade.

## Validation and operation

Hosted PR checks test release guards without Unity or production access:

```bash
python3 -m unittest discover -s scripts/unity -p 'test_*release.py'
```

Use CI/CD manual dispatch **`unity_build_only=true`** to compile and package a
selected repository branch. This skips both deployments, including on main.
Normal main pushes/default dispatches run the guarded production release.
For local reproduction under the licensed account, set `UNITY_WEB_SOURCE_SHA`
to exact HEAD, `UNITY_WEB_PRIVATE_ASSET_ROOT`, a fresh `UNITY_WEB_RELEASE_DIR`,
and the actual `GITHUB_RUN_ID`/`GITHUB_RUN_ATTEMPT`, then run
`bash scripts/unity/Build-Web.sh`. Outputs are under `release-directory/package`
and the editor log is `release-directory/build-web.log`.

Inspect the public manifest's `source_commit` before investigating browser caches.
An older installed React service worker may need to update and reload. CI hosting
checks do not establish actual Android/iPhone performance, keyboard or resume behavior.

## Supersession and recovery

Actions concurrency supersedes older runs. Client and broker recheck current main
before mutations; the broker serializes activation and drains its exact Coolify
activity before allowing another activation. Active older service activities
block new starts. A main change during activation makes the release superseded.

GitHub main checks and asynchronous Coolify starts are not atomic. Manual Coolify
or Windows releases operate outside the broker lock; avoid simultaneous manual
releases. Cancelling Actions does not establish that an in-flight Coolify activity
was cancelled. Timeout or verification failure requires inspecting the specific
service activity/image; no automatic rollback or broad cleanup runs.

For intentional rollback, use the verified saved image/tag with the existing
[Windows administrator release procedure](../unity-web-hosting.md#repeatable-release-from-this-windows-pc).
The CI broker rejects older source SHAs as ordinary deployments.
