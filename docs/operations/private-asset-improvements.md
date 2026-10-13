# Private woodland asset checks

The asset lane generates a candidate from a sealed baseline and renders it
through Abby's actual companion components before an asset PR can merge.
Synthetic child901 and Base Chick/Bird fixtures use no account login,
database, real user data or production credentials. Mobile viewport checks
establish browser layout/rendering, not physical phone performance.

The recipe at content/rpg/asset-recipes/woodland.json contains exactly:

~~~json
{"schemaVersion":1,"target":"woodland","operation":"woodland-texture-limit","maxDimension":256}
~~~

The trusted Blender4.1.1 operation permits128/256/384/512 pixel texture limits.
Only embedded PNG payloads change. Nonimage buffer bytes, geometry, UVs,
object transforms, materials and nonlayout JSON semantics must be preserved.
Each run generates its own candidate. Worker-written outputs/pass files and
uncovered exporter or avatar changes are refused. Future PR changes initially
cover only the recipe and companion/component source paths.

Baseline production components are copied from the exact base commit;
candidate components come from the exact PR head. Sources, staged runtime
assets and the trusted fixture are checked against Git blobs/input digests
before and after rendering and again before merge. A reviewed installer smoke
may test its own exact installed commit; the exception never authorizes
uncovered changes in another candidate.

## Installation

Root seals the reviewed source/dependencies under /opt/abby-asset-checks/SHA.
The station manifest at /etc/abby-asset-checks/manifest.json contains
schemaVersion, sourceCommit, installPath, nodePath, browserPath, workbenchFile.
The frontend marker .abby-asset-source.json contains only schemaVersion1 and
the same sourceCommit. Station supervision verifies ownership, immutable
paths, merged-main provenance and the fixed executable.

The root-owned workbench JSON contains exactly schemaVersion1,
baselineDirectory, files, blenderPath, blenderVersion4.1.1. Files maps the
nine GLBs and manifest.json to exact sha256/bytes. Every input byte is checked;
the private manifest remains private_evaluation. sourceInputsSha256 hashes
the files map in the harness's declared filename order; catalogSha256 hashes
the exact workbench file. Raw FBX/PSD packs are unnecessary for this first
operation and remain in separate private storage.

## Checks and receipt

The fixed frontend/scripts/run-asset-checks.mjs CLI accepts:

~~~text
--capabilities --workbench-file FIXED_CONFIG
--worktree PATH --expected-commit HEAD --base-commit BASE --issue N --output FRESH_PRIVATE_DIR --workbench-file FIXED_CONFIG
--verify-receipt RECEIPT --worktree PATH --expected-commit HEAD --base-commit BASE --issue N --workbench-file FIXED_CONFIG
~~~

Capabilities verify baseline hashes and Blender before reporting ready.
The runner executes no candidate package scripts, Vite configuration,
Tailwind executable directives or environment files. All source extensions are
scanned before compilation, guarded pre-transforms reject CSS query aliases,
only the trusted tailwindcss stylesheet import is allowed, and PostCSS uses
inline empty configuration. Browser context routing fences first popup and
WebSocket requests; unexpected popup pages close and fail the run. Blender uses
factory startup, disabled automatic execution and two threads. Browser and
generation are bounded to ten minutes; station supervision drains descendants.

Real GLB loading checks finite animated skinned vertices, grounding, UVs,
textures and double-sided alpha foliage. Production scenes render at375×812
and812×375. Context loss must preserve the synthetic DOM control. Loopback
request fencing prevents external/API requests; no production token exists.

The private receipt binds exact head/base/harness commit, issue, recipe,
catalog, baseline/candidate digests, tool versions and all required checks.
Six PNGs under output/screenshots pair baseline/candidate Chick portrait,
Bird portrait and Chick landscape, each with exact SHA256/path/dimensions.
Independent visual review must inspect these actual images and bind its
decision to the original runner receipt SHA256 and exact head/base, alongside
independent code review and hosted CI. A visible canvas alone is insufficient.

Receipts expire after60minutes. Before merge, verify-receipt checks unchanged
head/base/recipe/config/baseline/candidate/source snapshots/PNG bytes without
another render. The station retains and compares the original receipt SHA256.
Failed runs expose only fixed phase/code categories; missing art never skips.

All artwork, manifests, source snapshots, screenshots and reports stay private
outside Git. This lane does not relabel private_evaluation or publish artwork.
The existing license/public-delivery gates remain in the
[asset boundary](../../content/rpg/react-three-fiber-assets.md).

Public gates: npm run test:asset-config; Python unittest discovery for
scripts/r3f/test_woodland_texture_variant.py. Actual private browser evidence
and independent image review are required before lane activation.
