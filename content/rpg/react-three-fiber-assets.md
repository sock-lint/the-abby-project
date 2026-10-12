# React Three Fiber owned-asset boundary

Updated October 12, 2026. React owns the complete product UI; R3F presents
server-confirmed companions using the recorded owned art. Django remains the
authority for accounts, permissions, contributions, rewards and progression.
This document defines the baseline art scope and its acceptance gates.

The [earlier Unity coverage review](unity-assets.md),
[asset notes](../../unity/AbbyCamp/AssetNotes.md) and
[third-party notices](../../unity/AbbyCamp/THIRD_PARTY_NOTICES.md) retain source
provenance and historical validation. Unity is a retained reference, not a
dependency of the new companion renderer.

## Recorded owned packs

| Pack | Baseline capability | Scope limit |
| --- | --- | --- |
| Chick / Fledgling / Bird Evolution | Rigged bird family, supplied diffuse textures and animation takes | Chick and confirmed Bird are the account bindings; Fledgling remains an explicitly labeled asset preview |
| Forest Ruins 1.2 | Ground, woodland plants, rocks, mushrooms, steps and ruins | A small fixed setting; props do not imply furnishing ownership or new unlocks |
| Icons for Monsters Ultimate Pack 01 v2 | Matching Chick/Fledgling/Bird portraits | Portraits remain the existing private build overlay; an icon is not proof of an owned 3D model |
| Female Archer Pack 01 | Recorded modular humanoid and animation sources | Optional future guide/preview only; excluded from the baseline and not fitted creature clothing |

The [publisher's bird-family listing](https://www.meshtint.com/products/chick-fledgling-bird-evolution-pack-cute-series)
describes rigged models with FBX sources and supplied takes. Conversion of the
actual owned source determines runtime acceptance; vendor compatibility claims
do not establish this project's WebGL or phone readiness.

No baseline milestone requires purchasing another pack, creating a mesh,
retargeting humanoid clothing, authoring skeletal animation, combat or riding.
Additional species, biomes and gameplay need their own deliberate decisions.
Use existing 2D art for unsupported content; never substitute the bird for an
unrelated earned creature or recolor it into an unprepared potion variant.

## Exact content bindings

The catalog in [initial/pet_species.yaml](initial/pet_species.yaml) continues
to own content identities and compatible acquisition paths.

| Confirmed server identity | R3F appearance |
| --- | --- |
| Species slug `chick`, `species.sprite_key=cute-chick`, potion `base`, unevolved owned pet | Chick |
| The same exact owned pet with confirmed `evolved_to_mount=true` | Bird |
| The same species/potion's confirmed owned mount | Bird |
| Fledgling | Asset test viewer only; no earned intermediate stage |
| Other species, unknown identity, unsupported potion or missing model | Existing portrait/sprite fallback with usable creature controls |

Growth alone never selects Bird. Hatching, feeding, activation, breeding and
expeditions use existing shared services and acknowledged Django responses.
Appearance loading and greetings award nothing. Account changes clear old
bindings, and stale responses cannot restore the prior account's presentation.
Saved ownership is independent of model filenames and availability.

## Private conversion pipeline

The source audit found the recorded staged Meshtint FBX/PSD assets in the local
primary checkout on October 12. They are absent from this isolated worktree;
the original ZIPs were not found in the current Downloads directory. Existing
private sources can be reused without repurchase. Retain the original packs,
import reports and purchase/license records in private backup storage.

Install the separate conversion dependencies and run from the repository root:

```powershell
python -m pip install -r scripts/r3f/requirements.txt
python scripts/r3f/prepare_meshtint.py --source "C:\private\Meshtint" --blender "C:\Program Files\Blender Foundation\Blender 4.1\blender.exe"
& "C:\Program Files\Blender Foundation\Blender 4.1\blender.exe" --background --factory-startup --python-exit-code 1 --python scripts/r3f/verify_exports_blender.py -- --directory frontend/src/companion/licensed --evidence scripts/r3f/private/render
```

`--source` names the privately staged `Assets/ThirdParty/Meshtint` directory,
not a public download. The tool uses Blender 4.1's FBX/glTF import/export and
Pillow/psd-tools for merged PSD pixels, including the supplied 16-bit foliage
texture. Originals remain read-only, and selected input hashes must match
before and after conversion. No publisher scripts or demo scenes execute.

Generated files belong to ignored `frontend/src/companion/licensed/`:
`manifest.json`, `chick.glb`, `bird.glb` and `woodland.glb`. Detailed input
hashes, conversion logs and local render evidence remain in ignored
`scripts/r3f/private/`; they are not runtime payloads. Do not commit either
directory, source archives, FBX/PSD files or license/purchase records.

The manifest records exact identity bindings, file hashes/sizes, embedded
image and skin counts, reviewed clip names and presentation transforms.
Models contain their selected runtime textures, with no external image/file
references. Their supplied UVs and skin weights are retained; textures are
bounded to 512 pixels. A static parent normalizes resting height/grounding
without rewriting source animation keys. Greetings use simple local motion.

The representative woodland uses eight instances from five existing meshes:
soft-edge ground, three trees, two rocks, a mushroom and a pillar. It is not a
conversion of the entire purchased pack. Camera framing must accommodate the
Bird's full animated wingspan, rather than only its resting bounds.

## Export evidence and remaining acceptance

Private representative exports completed on October 12 with Blender 4.1:

| Runtime export | Supplied accepted clip | Export size |
| --- | --- | --- |
| Chick | `Idle` | 64,428 bytes |
| Bird | `Fly Idle` | 167,168 bytes |
| Woodland subset | Static scenery | 205,844 bytes |

The GLB checks verify embedded images, supplied UVs, triangle primitives,
skin joints/weights and positive animation duration. Reimported GLBs were
rendered at the start and middle of their clips; Chick's wings/beak and Bird's
wingbeat visibly animate with intact textures and skinning. Both face the
positive-Z camera in Three.js coordinates. Reimport checks sampled the clip
start/middle/end and verified moving skinned vertices and retained armatures
(16 Chick bones, 37 Bird bones). Selected original inputs stayed unchanged.
The woodland has 2,509 triangles and explicitly retains the supplied
double-sided foliage texture with alpha cutout and the supplied Blue tint;
its ground is normalized to a thin island with its surface at Y=0. Raw FBX defaults
do not carry the authored prefab's texture overrides.
The older static Forest exports retain Y-up when imported by Blender, while
the version 1.1 Ground and creature rigs already import into Z-up. The
converter applies the basis correction only to the older static files before
measuring size/grounding. Reimport validation requires three upright stems
meeting the ground and the supplied green grass surface facing upward. This
prevents sideways trees or a rotated island from passing a geometry-only check.

Separate movement FBX takes remain outside accepted runtime capabilities.
A trial transfer found differing jaw bind/mesh poses; their animation is not
claimed as verified. The runtime manifest deliberately has no movement clip.
The fixed companion home needs no movement take, eating animation, breeding
animation or custom hatch rig. Revisit a clip only for a slice that needs it.

This evidence establishes desktop conversion and render feasibility. Real
iPhone/Android graphics, battery/thermal, lifecycle, keyboard, safe-area,
accessibility and repeated scene-mount measurements remain unverified.
WebGL loss, failed downloads and a disabled scene must leave every ordinary
React control and saved creature usable.

## License and public-delivery gate

The [Meshtint terms](https://www.meshtint.com/pages/terms-of-use-license)
permit website/device use and modification while restricting distribution
outside the compiled-application exception. Verify the purchase channel,
applicable license, entity/seat coverage and retained receipt/license snapshot
before release. This audit confirms staged source availability and the
recorded inventory; it does not claim that purchase records were reviewed.

Every generated manifest starts with `delivery_review=private_evaluation`.
Private conversion may proceed, but approval of public runtime delivery is a
separate recorded gate. A reusable browser-downloadable GLB must not be assumed
equivalent to a compiled Unity player under those terms. Review the specific
web and Capacitor packaging against the applicable license; obtain publisher
clarification if that delivery form remains ambiguous. Conversion, minifying
JavaScript or changing a filename does not itself establish permission.

Keep public Git free of purchased art. Release only the reviewed, bounded
runtime files needed by the application through the private build process;
exclude original archives, editable source files, unused clips, credentials
and private records. Existing portrait staging does not automatically approve
shipping a newly converted mesh. No new purchase is required to investigate
this gate or to continue implementing the functional React fallback.

## Exit gates

- Source provenance/version and applicable license records are verified; the
  chosen public delivery is recorded as accepted before shipping runtime art.
- Actual Chick/Bird textures, skinning, facing, full clip bounds and root-motion
  behavior are accepted in R3F, with exact server identities and 2D fallback.
- The selected woodland fits recorded real-phone startup, frame-time, memory
  and thermal budgets. Desktop renders or viewport screenshots cannot pass
  this device gate.
- Keyboard, overlays, density/resizing, scene entry/exit, loading failures and
  WebGL context loss preserve functional DOM controls and pending-save recovery.
- A confirmed receipt may trigger presentation; greeting, loading, reopening
  and artwork replacement never create XP, Coins, items or ownership.

Each optional activity names its exact existing mesh/clip/texture dependencies,
local versus saved behavior, any explicitly approved server reward rule,
accessible equivalent and device budget. Missing art stays on 2D presentation
or the activity is deferred. The owner is not required to make new models.
