# React Three Fiber owned-asset boundary

Updated October 17, 2026. React owns the complete product UI; R3F presents
server-confirmed companions using the recorded owned art. Django remains the
authority for accounts, permissions, contributions, rewards and progression.
This document defines the baseline art scope and its acceptance gates.

Current code pins six shared runtime families in
[`frontend/assets.lock.json`](../../frontend/assets.lock.json): Archer 1.0.2,
Bird Evolution 1.0.0, catalog icons 1.0.0, pedestal/card UI 1.0.1,
companion roster 1.0.0 and Training Dummy 1.0.0. The
[shared-asset intake](../../docs/operations/shared-avatar-assets.md) and
[companion adoption](../../docs/operations/companion-lifecycle.md) runbooks
describe their verified imports and application bindings. A pin records the
selected runtime artifact; it does not establish production delivery or
physical-device acceptance. Dummy remains unbound future training art.

The [earlier Unity coverage review](unity-assets.md),
[asset notes](../../unity/AbbyCamp/AssetNotes.md) and
[third-party notices](../../unity/AbbyCamp/THIRD_PARTY_NOTICES.md) retain source
provenance and historical validation. Unity is a retained reference, not a
dependency of the new companion renderer.

## Earlier owned-pack baseline

This table retains the original conversion baseline. The current roster and
six shared releases above extend that inventory; use their exact bindings
and current acquisition policy below when implementing app presentation.

| Pack | Baseline capability | Scope limit |
| --- | --- | --- |
| Chick / Fledgling / Bird Evolution | Rigged bird family, supplied diffuse textures and animation takes | Exact Base Chick ownership has server-confirmed Chick/Fledgling/Bird stages; see the Bird adoption runbook |
| Forest Ruins 1.2 | Ground, woodland plants, rocks, mushrooms, steps and ruins | A small fixed setting; props do not imply furnishing ownership or new unlocks |
| Icons for Monsters Ultimate Pack 01 v2 | Matching Chick/Fledgling/Bird portraits | Portraits remain the existing private build overlay; an icon is not proof of an owned 3D model |
| Female Archer Pack 01 | Profile avatar with three costumes, both heads, three faces, four hairstyles, five hair colors and supplied Idle | Owner accepted the exact expanded Profile release on October 13; wardrobe requires its own converted-art review, with no creature fittings |

The [publisher's bird-family listing](https://www.meshtint.com/products/chick-fledgling-bird-evolution-pack-cute-series)
describes rigged models with FBX sources and supplied takes. Conversion of the
actual owned source determines runtime acceptance; vendor compatibility claims
do not establish this project's WebGL or phone readiness.

No baseline milestone requires purchasing another pack, creating a mesh,
retargeting humanoid clothing, authoring skeletal animation, combat or riding.
Additional species, biomes and gameplay need their own deliberate decisions.
Use existing 2D art for unsupported content; never substitute the bird for an
unrelated earned creature or recolor it into an unprepared potion variant.

## Four-stage families

All species have the shared Egg → Baby → Middle → Grown lifecycle described in
[companion lifecycle](../../docs/operations/companion-lifecycle.md). Egg is the
existing species-linked inventory ingredient, not a new owned pet or model.
The prepared roster adds 14 exact namespaced Meshtint families alongside
retained Chick, each with a supplied egg and three post-hatch forms. Exact
bindings, intake receipts, native motion limits, preservation and rollback are
in the [adoption runbook](../../docs/operations/companion-lifecycle.md).
Missing stage art retains the same family's sprite/icon fallback. Dummy is
separate future training art without any companion/acquisition binding.

## Exact content bindings

The catalog in [initial/pet_species.yaml](initial/pet_species.yaml) continues
to own content identities and compatible acquisition paths.

| Confirmed server identity | R3F appearance |
| --- | --- |
| Species slug `chick`, `species.sprite_key=cute-chick`, potion `base`, unevolved owned pet | Chick |
| The same exact owned pet with confirmed `evolved_to_mount=true` | Bird |
| The same species/potion's confirmed owned mount | Bird |
| The same exact owned pet with server `evolution_stage=fledgling` (50–99 growth) | Fledgling from the pinned shared Bird family |
| One of 14 exact `meshtint-*` slug/sprite identities, global Base potion, server-confirmed lifecycle stage | Its exact pinned native family-stage take and portrait |
| Unknown identity, unsupported potion or missing model | Existing portrait/sprite fallback with usable creature controls |

The owner approved Fledgling at 50 server-confirmed growth; growth alone never selects Bird. See [Bird Evolution adoption](../../docs/operations/bird-evolution.md) for the new shared release, motions, lifecycle and rollback. The private conversion details below retain the prior export baseline. Hatching, feeding, activation and
expeditions use existing shared services and acknowledged Django responses.
Appearance loading and greetings award nothing. Account changes clear old
bindings, and stale responses cannot restore the prior account's presentation.
Saved ownership is independent of model filenames and availability.

## Active acquisition policy

[`shared/catalog/asset-support.json`](../../shared/catalog/asset-support.json)
is the positive registry for new offers and acquisition. Its production pet
allowlist contains retained `chick` / `cute-chick` and the 14 exact namespaced
identities in `shared/catalog/companion-roster.json`, with Base for all fifteen.
The five Fire/Ice releases enable twenty additional pairs for exact `chick`,
`meshtint-wolf`, `meshtint-dragon`, `meshtint-mushroom`, `meshtint-bee`,
`meshtint-bat`, `meshtint-snake`, `meshtint-hermit-crab`, `meshtint-ghost` and
`meshtint-potted-plant` identities: 35 pairs in total. The other five families remain
Base only. Dragon/Mushroom adoption is recorded in
[its runbook](../../docs/operations/elemental-dragon-mushroom.md); Bee/Bat's
exact receiving pins, canonical readback, four new guarantees and rollback are
recorded in [its runbook](../../docs/operations/elemental-bee-bat.md).
Snake/Hermit Crab's exact bindings, four Coil/Shore guarantees and rollback are
recorded in [its runbook](../../docs/operations/elemental-snake-hermit-crab.md).
Ghost/Potted Plant's exact native bindings, Wisp/Sprout guarantees, canonical
receipt and rollback belong in
[its runbook](../../docs/operations/elemental-ghost-potted-plant.md).
The owner accepted the actual app previews for all five batches. Chick/Wolf was
canonically published and verified on October 20, 2026; Dragon/Mushroom on
October 21; Bee/Bat on October 23. Bee/Bat retains the accepted manifest
`7cce23a080a2a018fd5e4f55041c8f861df383ac857b94c543b3f331b13699e5`
and all 146 runtime files unchanged. Snake/Hermit Crab was canonically published
and independently read back on October 26, retaining manifest
`2c14765c0fd379f4f06b76a8b38cb6be7a04f7e618d6eaff89c7cac84d1e80b3`
and all 234 runtime files unchanged. Application rollout uses the normal MAIN gates;
see [Fire and Ice companions](../../docs/operations/fire-ice-companions.md).
Exact egg slug, typed species FK and canonical metadata must agree. Native take
order does not set gameplay thresholds; explicit server rules select stages.
Shadow, Golden and Cosmic remain outside new acquisition. Archer outfit
palettes are separate avatar choices; they
do not establish a potion variant or fitted creature outfit.

`apps/rpg/catalog_support.py` applies this art gate without deleting saved
catalog, inventory or collection rows. The separate owner-approved one-time
prelaunch retirement removes only its exact obsolete identities after settling
accepted supported resources; see the [retirement contract](../../docs/operations/companion-lifecycle.md#unused-first-party-content-retirement).
That transition preserves current families, Base/Fire/Ice, unrelated custom
content, SpriteAsset registration/rows and stored artwork. Existing service rules
still decide
permissions, authored potion compatibility, consumption and rewards. Generic
domain tests can declare an explicit scoped synthetic policy; production
defaults stay strict. Collection badge availability is checked against actual
achievable capacity, including remaining ownership outside the retirement list.
Impossible goals remain unavailable without lowering their criteria or
payouts; independent badge and consumable collections remain valid.

DOM titles, initial frames, app-color covers, badges, food, coins and utility
items do not need a new 3D model. Keep their actual DOM behavior. Forest props
are scenery rather than new inventory furnishings. Capture, tasks, family
workflows and administration remain ordinary React screens.

### Owned sources versus accepted runtime capabilities

The following retains earlier source inventory and conversion notes, including
later Bird adoption references. Its statuses describe those earlier sources;
they do not define current app availability. The prepared 14-family roster
supersedes the unprepared-creature rows for its exact namespaced identities,
while the separate prelaunch retirement removes its explicitly listed old
species and ownership after accepted-resource settlement. That content cleanup
does not change the Archer, Bird, pedestal/UI or catalog pins. Exact current intake and
application validation are recorded separately in the adoption runbook:

| Art | Earlier source evidence | Earlier conversion status |
| --- | --- | --- |
| Chick / Bird | Prepared private models and matching Bird01/Bird03 portraits | Exact Base Chick pet and confirmed evolved/mount forms |
| Fledgling | Published Bird Evolution 1.0.0 private runtime and retained Bird02 portrait | Intermediate stage from 50 server-confirmed growth; all native motions in the shared release |
| Bat, Bee, Flower, Ghost, Mushroom, Spider | Owned icon pack 01 contains forms 01–03 for each | Unprepared 2D portraits; no matching owned 3D models or current species bindings |
| Egg00–Egg03 | Four owned generic egg portraits | Unprepared inventory presentation, not distinct creature ownership |
| Archer bodies, both heads and three faces | Owned FBX modules/face palettes in Female Archer Pack 01 | Prepared private three-costume Profile release; 2,880 saved identity choices with supplied Idle |
| Archer hat hair, crown, hood, mask, bows and quivers | Owned FBX modules and authored prefab sockets in Female Archer Pack 01 | Schema-v3 Profile wardrobe support; new converted artwork remains private pending exact owner acceptance |
| Archer arrow | Owned FBX module in Female Archer Pack 01 | Unprepared; no shooting or weapon behavior |
| Archer Brown/Orange/Grey hair materials | Owned source material choices | Prepared private palettes with matching eyebrows; five saved hair colors |
| Kenney Fox/Dog | Retained CC0 models with original licenses | Available reference sources, not accepted R3F catalog or evolution bindings |
| Other seeded species and potion variants | Legacy catalog/sprites are not matching Meshtint model ownership | Outside new acquisition offers; never inherit the ordinary Chick/Bird model |

The private icon pack contains 28 distinct portraits, each with transparent
and background versions. Portrait ownership does not supply a creature model.
The older Shikashi 2D sheet is also present in private sources; its inventory
icons do not supply attachable geometry. Runtime-generated sprite records are
not evidence that a matching model is owned or prepared.

No fitted accessories for the current bird are prepared or recorded. All
15 initial `cosmetic_pet_accessory` entries, plus the school backpack charm
and birthday party horn, remain outside active offers/equipping. Ring,
necklace and bead icons are inventory images, and the Archer's Crown Eve
is a human module, not a fitted bird crown. Their saved rows can be retained
with an unavailable explanation without promising that equip changes the
3D companion. Extra models, species bindings or fittings need deliberate
acceptance before expanding this registry.

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

The representative woodland export uses eight instances from five existing
meshes: soft-edge ground, three trees, two rocks, a mushroom and a pillar.
Runtime presentation reuses those meshes in an asymmetric grove with a larger
muted ground, small edge details, warm lighting, mist and a lightweight contact
shadow. It is not a conversion of the entire purchased pack or furnishing
ownership. Camera framing accommodates the Bird's full animated wingspan,
rather than only its resting bounds.

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

Six additional friendly takes passed desktop conversion/reimport/render checks:
Chick's `Jump Forward In Place`, Bird's `Fly Forward In Place`, and each
creature's `Turn Left` / `Turn Right`. Each interaction export retains its
complete supplied rig and keys. Transferring tracks onto the idle rig distorted
Chick's jaw and Bird's leg platforms, so runtime playback swaps the complete
matched take with the exact idle-derived normalization. Bird turns preserve
the animated object root as well as skeletal tracks. Turns play forward and
reverse to face front again; jump/flight use four bounded supplied loops and
return to idle. The private manifest's `interaction_clips` records each file,
clip, hash and return behavior; the private conversion report retains source
provenance.

Pet tapping and play remain local presentation with no growth, XP, Coins or
items. Existing confirmed feed/claim receipts may trigger a small visual
acknowledgement. No eating, sleeping, combat or custom hatch clip is
claimed. Motion pauses outside the viewport, in background/hidden tabs, when
disabled, and for reduced-motion preferences. Failed models retain purchased
portraits and usable DOM care/expedition controls.

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

## Accepted Profile avatar

The owner chose the owned Archer as the current Profile avatar on October 12,
with Pets remaining the place for pet interaction. `prepare_archer.py` exports
the supplied body, head, face and four hair modules to private
`frontend/src/avatar/licensed/`; runtime choices use the supplied Fair/Tan skin,
Aqua/Nature/Fire/Dark outfit, Light/Dark hair and matching eyebrow textures.
The original static GLB retains supplied UVs and the 40-bone body rig. All four hairstyles
and eight outfit/skin combinations passed GLB reimport/render checks. Original
source hashes remained unchanged. The supplied Idle bind matrices differ from
this body rig and were unaccepted in that initial static release.
Saved appearance is separate from inventory, rewards, pet ownership and earned
cosmetics. The same private-license/public-delivery and real-phone gates apply.

That October 12 static release remains supported. The owner's October 13
original-pack upload enabled a private expanded release with three supplied
costume rigs, rounded/pointed ears, three face expressions, four hairstyles,
five matching hair/eyebrow colors, two skins and four outfit palettes. Saved
preferences remain free identity choices rather than inventory rewards.

The supplied Idle has different anatomical proportions despite matching all
40 bone identities and their hierarchy. `prepare_archer.py --source-map`
retargets its rotations through each costume's own rest hierarchy, preserving
the target's offsets, original UVs and weights. Each complete GLB retains
eight modules and only the supplied 1.333-second Idle. Reimported geometry,
joints, rotations and head attachment pass measured checks; original source
hashes stay unchanged. Archer 03's original fifth influence is exported and
rendered through the bounded extra-weight helper rather than truncated.
Detailed evidence and recovery are in
[the implementation record](../../docs/operations/r3f-profile-pets.md).

The owner accepted the exact expanded schema-v2 visuals, supplied Idle and
public browser delivery for PR #210 on October 13. That release was published
through the existing private avatar build settings. This acceptance is specific
to its recorded artifact; it does not accept newly converted wardrobe artwork
or establish physical-phone graphics readiness.

Schema-v3 adds independent headwear, mask, bow and quiver preferences with
`None` choices and coordinated Aqua/Nature/Fire/Dark presets. The source-map
converter uses the publisher's actual head, left-palm and back socket transforms,
preserving supplied geometry, materials and complete costume rigs. Hood choices
use the supplied hat hair, while the selected ordinary hairstyle remains saved.
The new wardrobe outputs retain `private_evaluation` until exact visual and
delivery acceptance. New runtime art needs the separately recorded owner review in
[private avatar builds](../../docs/operations/licensed-avatar-art.md).
Source archives, conversion evidence and review records remain outside public
Git. Physical-phone graphics acceptance is still separate.

Profile taps retain bounded local hop, twirl and bow movements of the entire
character. Camera orbit, keyboard controls, reset and Idle are local
presentation and award nothing. Hidden/offscreen/reduced-motion views pause
animation, and failures retain the functional DOM customization fallback.

## Ghost and Potted Plant activation

The owner accepted all twelve Fire/Ice appearances for
`abby-elemental-ghost-potted-plant` 1.0.0, manifest
`6e1f2cb2f67503c63e3ab8a27135b6f7579f894e0d62b814bfa89df3a45ae9e9`.
It is the fifteenth runtime pin alongside all fourteen existing releases;
canonical application readback passed. The policy contains
35 supported pairs and twenty elemental guarantees. Natural eggs, Baby-only
challenge handles, native stage names and all 138 exact v1 bindings stay intact.
Runtime inventory is 154 files / 51,889,149 bytes (138 GLBs and 16 PNGs).
The separate evaluation lock preserves the earlier private receiving evidence;
normal runtime uses the active lock without staged input. Keep actual app test
revision/source drift, the original 16-pass/1-failure private browser run and its
unchanged isolated pass distinct from later canonical checks. Formal durable
backup/restoration and physical-phone/native-shell acceptance remain separately
pending. Existing package versions and integrity pins are unchanged. See
[the receiving and rollback runbook](../../docs/operations/elemental-ghost-potted-plant.md).
