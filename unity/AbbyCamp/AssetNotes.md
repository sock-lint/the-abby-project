# Prototype asset notes

This selection makes the first scene usable without drawing characters, modeling pets, or authoring movement animations. Keep original source assets under `Assets/ThirdParty`; presentation definitions and generated project materials belong elsewhere. Gameplay identities and saved progression should refer to the project's content IDs, never a Kenney filename.

## Shared meadow presentation

The first meadow slice uses the same temporary dragon expressions, memory-bloom icon, palette and Nunito font as React. Canonical sources are under `shared/storybook`; `scripts/storybook/sync_presentation.py` copies runtime exports into both clients. Temporary dragon and bloom SVGs are project-authored illustrations, with PNG exports, rather than licensed store previews or a substitute for the final purchased models.

Nunito comes from the official Google Fonts repository (`google/fonts`, `ofl/nunito`). The static runtime font is an instance of the variable font at weight 600, with the OFL license also embedded in its metadata. The original variable font and copyright/license text remain in `shared/storybook/fonts`.

The authored presentation and dragon definition live under `Assets/AbbyCamp/Presentation`, outside generated Kenney defaults. A model takes precedence over a portrait. Model controllers map speed and celebration intents; portrait definitions can provide idle, happy and blink sprites with camera-facing rendering and local reactions. Both preserve the stationary root, tap interaction and content identity. Rebuilds validate these references and the canonical palette instead of replacing authored art. The home has no walking avatar, board, movement collider or proximity gate.

## Purchased Cute Series layer

See the [RPG catalog and Unity asset coverage](../../content/rpg/unity-assets.md)
for the exact owned-pack inventory, Chick/egg/Birdseed catalog identities,
legacy species gaps and optional purchases. The Chick catalog is separate
from the fixed scene's artwork preview; an owned-collection-to-3D binding
remains a later presentation slice.

The licensed companion and woodland art come from **Meshtint Studio's
[Cute Series collection](https://www.meshtint.com/collections/cute-series)**.
Keep this publisher source with the pack, import and private purchase records
below; the public Kenney prototype is a separate fallback.

The starter selection is Chick / Fledgling / Bird Evolution, Forest Ruins 1.2,
Icons for Monsters Ultimate Pack 01 v2, and Female Archer Pack 01. Bird01/02/03
are the matching transparent portraits for the three model forms. The public
project-authored dragon remains a fallback; all purchased sources and generated
references stay in ignored folders, including their `.meta` files.

From the repository root:

```powershell
python scripts/unity/stage_meshtint.py --downloads "$env:USERPROFILE\Downloads"
./scripts/unity/Build-Camp.ps1 -Target Web -PrepareLicensed
```

The staging script reads the original ZIPs, including the evolution bundle's
nested ZIPs and Unity packages, and retains asset GUIDs. It imports FBX, PNG,
**PSD textures**, materials and prefabs into `Assets/ThirdParty/Meshtint`, skipping
publisher demo scenes/scripts. Originals remain in Downloads. Pack filenames,
SHA-256 hashes and counts are recorded in the ignored
`Assets/AbbyCamp/Licensed/import-report.json`; retain purchase and license records
alongside the original archives in private backup storage.

Unity menu **Abby Camp → Licensed Cute Series → Prepare meadow** creates
`Assets/AbbyCamp/Licensed/MemoryMeadow.unity`. It converts materials to URP,
caps imported textures at 512 pixels, normalizes model bounds and creates
separate animation controllers/definitions for each form. The prepared Archer
sample remains available for later uses but is not instantiated in the home;
the original modular sources are retained.
Chick maps Idle / Jump Forward In Place, Fledgling maps Idle / Walk Forward In
Place, Bird maps Fly Idle / Fly Forward In Place. The humanoid explorer maps
Idle / Walk Forward In Place. Root motion stays disabled. Greetings use the
project's small procedural hop instead of combat animations.

The purchased forms are prepared appearances, **not implemented evolution
unlocks**. The secondary form remains a development appearance-swap check.
The `starter-companion` gameplay identity, controllers, journal receipts and
account boundaries are unchanged. Fitted creature outfits remain additional
art/integration work; modular humanoid clothing does not automatically fit a
creature. The licensed backdrop uses the purchased soft-edge ground, soil
clearing, stone steps, a mixed mint/lavender treeline, grass, mushrooms, rocks,
pillars and broken ruin gateways. The backdrop is brought closer around the
fixed hero. All scenery and actor colliders/rigidbodies are removed; companion
taps use the active appearance's renderer bounds and exclude interface hits.

This first woodland layout has 61 purchased props, 91 renderers and 13,564
scenery triangles. Its distant trees, grass and ground do not cast shadows;
23 small ruin/rock/mushroom renderers do. Preparation marks static geometry
for batching and validation rejects missing geometry, imported physics or a
backdrop exceeding 100 renderers, 150,000 triangles or 25 shadow casters.
These are editor scene budgets, not an Android/iPhone performance benchmark.
Preparing again reconstructs the licensed scene rather than accumulating props.

Only ignored, generated environment material copies receive the softer shared
palette. A private copy of the supplied color atlas preserves its texture detail
and alpha while creating a mint/sand/sky version for the scene; the purchased
source pixels and importer are not edited by that recoloring. Creature/avatar
materials retain their supplied colors. The licensed forms are normalized to
1.8–2 world units and face the fixed, shallow-angle camera. Framing reserves
space for the top account panel and bottom home actions, with the world on the
left in landscape. The public fallback uses the same fixed camera contract.
The scene bird is an artwork preview rather than a fictional owned species;
Bestiary displays actual account ownership and growth independently.

The staging script also writes ignored `shared/storybook/licensed` and
`frontend/src/storybook/licensed` overlays. React bundles their hashed portraits
only when a valid matching manifest and resting image exist; otherwise the
complete public placeholder remains usable. This pack supplies one portrait
per form, so greetings reuse that portrait with the existing local interaction.
The shared palette, font and bloom artwork still come from the canonical public
presentation. `sync_presentation.py` only synchronizes public fallback sources;
rerun licensed staging separately after changing that presentation.

Normal Unity builds select the local licensed scene when present; public
checkouts build `Assets/AbbyCamp/Scenes/Camp.unity`. Licensed production builds
must stage the purchased archives locally or from authenticated private storage
before compiling. A public Git checkout alone cannot reproduce the licensed
art. The [publisher license](https://www.meshtint.com/pages/terms-of-use-license)
permits use and modifications in applications/websites and restricts distributing
source assets. Keep source packs/portraits and their generated Unity assets out
of public Git; deploy compiled runtime exports. Android/iPhone hardware checks
remain necessary before judging phone performance.

## Original harness models

Paths below are relative to `Assets/ThirdParty/Kenney`.

| Role | Model | Appearance | Texture |
| --- | --- | --- | --- |
| Default player | `BlockyCharacters/Models/character-f.fbx` | Green shirt | `BlockyCharacters/Models/Textures/texture-f.png` |
| Alternate player | `BlockyCharacters/Models/character-a.fbx` | Orange outdoor jacket | `BlockyCharacters/Models/Textures/texture-a.png` |
| Default companion | `CubePets/Models/animal-dog.fbx` | Brown dog | `CubePets/Models/Textures/colormap.png` |
| Alternate companion | `CubePets/Models/animal-fox.fbx` | Orange fox | Same shared colormap |

`NatureKit/Models` includes two trees, a rock, a bush, a flower, a small open tent, campfire logs, a fallen log, and a wooden sign. These models use named flat-color materials embedded in the FBX; there are no external texture dependencies. Preserve each renderer's material slots when adjusting shaders so a tree retains separate bark and leaves.

The selected FBX source files import directly in Unity. No Blender installation, `.blend` import, GLTF plugin, or additional asset-store package is required. Original ZIPs also include GLB/OBJ versions, but those redundant formats are excluded from this project.

## Animation mapping

Exact case-sensitive source take names were inspected in the FBX files and checked against the companion GLB versions in the official archives. Use Generic rigs: these models animate a hierarchy of rigid mesh parts rather than a humanoid skinned skeleton.

| Gameplay intent | Blocky character take | Cube pet take |
| --- | --- | --- |
| Rest | `idle` | `idle` |
| Movement | `walk` | `walk` |
| Faster movement | `sprint` | `run` |
| Positive reaction | `emote-yes` | `gesture-positive` |
| Celebration | `emote-yes` | `dance` |
| Object interaction | `interact-right` or `interact-left` | `eat` |

All eight pet takes: `static`, `idle`, `walk`, `run`, `eat`, `dance`, `gesture-positive`, `gesture-negative`.

All 27 character takes: `static`, `idle`, `walk`, `sprint`, `sit`, `drive`, `die`, `pick-up`, `emote-yes`, `emote-no`, `holding-right`, `holding-left`, `holding-both`, `holding-right-shoot`, `holding-left-shoot`, `holding-both-shoot`, `attack-melee-right`, `attack-melee-left`, `attack-kick-right`, `attack-kick-left`, `interact-right`, `interact-left`, `wheelchair-sit`, `wheelchair-move-forward`, `wheelchair-move-back`, `wheelchair-move-left`, `wheelchair-move-right`.

Only the prototype's rest, movement, and positive-reaction clips need controller states. The original takes are retained unmodified; importing the FBX does not require exposing every take as a game action.

## Scale and orientation

All selected sources are Y-up with their resting geometry grounded at Y=0. Animated FBX files specify centimeters; their source translations are about 100 units. Unity's normal file-unit conversion should produce a character about 2.7 units tall. Source OBJ resting bounds are approximately 1.6 × 2.7 × 0.8 for either character, 1.26 × 1.58 × 1.50 for the dog, and 1.25 × 1.69 × 2.31 for the fox including its tail. Animation can extend these bounds.

Nature FBX files specify decimeters and use a different source scale. Normalize actual imported renderer bounds to the desired scene size rather than hard-coding one scale across all packs. Reasonable initial targets are a 1.75-unit player and 0.75-unit companion. Verify facing direction in the scene before adjusting the visual definition's local rotation. Keep collision and interaction dimensions on the gameplay object, separate from the model child.

## Replacing a visual later

1. Import a new model into its own source folder and retain its license.
2. Create or update its visual definition with the prefab, scale, offset, and orientation.
3. Map its animations to the existing gameplay intents. A new rig can have its own controller.
4. Assign that definition to the companion presentation; preserve its gameplay identity and saved progression. Map owned species explicitly before representing an account creature with that artwork.
5. Check fixed camera framing, grounding, visible-bounds taps, modal input exclusion, reward reaction, and lighting in portrait and landscape.

The public companion's appearance swap and licensed bird forms provide concrete checks without changing gameplay code or save data. Character outfits from the earlier walking harness remain unused. Future asset packs may require rig and material setup while preserving the account and reward systems.

Pack provenance and license paths are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Kenney's official import reference is [Importing 3D models into game engines](https://kenney.nl/knowledge-base/game-assets-3d/importing-3d-models-into-game-engines).
