# RPG catalog and Unity asset coverage

Reviewed 2026-10-11. The RPG YAML defines saved content identities; purchased
art supplies appearances for those identities. A portrait pack does not supply
the corresponding 3D models, and a model in a preview does not grant a pet.

## Owned Cute Series packs

The four original ZIPs are present in local Downloads and are listed in
[`stage_meshtint.py`](../../scripts/unity/stage_meshtint.py). Their art is private:
the staging script preserves source GUIDs and records archive hashes/counts in
the ignored `Assets/AbbyCamp/Licensed/import-report.json` when run.

| Pack | Available art | Current use |
| --- | --- | --- |
| [Chick / Fledgling / Bird Evolution](https://www.meshtint.com/products/chick-fledgling-bird-evolution-pack-cute-series) | Three rigged models with supplied textures and animations | Selected owned Base Chick uses `cute-chick`; confirmed evolution or its selected mount uses `cute-bird`; Fledgling remains a development preview |
| Forest Ruins 1.2 | Ground, trees, grass, mushrooms, rocks, steps and ruin props | Licensed fixed woodland home; already sufficient for the current setting |
| Icons for Monsters Ultimate Pack 01 v2 | Creature portraits, including matching transparent Bird01/02/03 images | Private `chick.png`, `fledgling.png`, `bird.png` exports shared by the licensed web/Unity pipeline; other icons are not proof of owned models |
| Female Archer Pack 01 | Modular humanoid sources, clothing and animation sources | Staged for later uses; no explorer in the fixed home and no fitted creature accessories |

The public checkout includes Kenney dog/fox, character and nature assets, plus
project-authored temporary dragon/bloom art and Nunito. These remain usable
fallbacks. Exact provenance is in
[`THIRD_PARTY_NOTICES.md`](../../unity/AbbyCamp/THIRD_PARTY_NOTICES.md).
No 100 Eggs pack is owned or required for the current inventory sheets.

## Catalog entries supported by the owned bird family

[`initial/pet_species.yaml`](initial/pet_species.yaml) adds one stable species,
`chick`, rather than three separately hatchable species for the vendor's forms.
It supports only the `base` potion because no separate potion variants are
prepared. Hatching consumes the usual owned egg and potion; it never grants
ingredients or chooses an active companion automatically.

| Catalog identity | Presentation | Progression/acquisition |
| --- | --- | --- |
| Species `chick`, sprite `cute-chick` | Selected Chick model in licensed Unity; Chick portrait in licensed React builds; public web fallback otherwise | Ordinary saved pet, starting at zero growth |
| Egg `chick-egg` | Existing generic `big-egg` sprite/egg icon | Common egg, coin value 3; existing egg-drop macros include it |
| Food `food-birdseed` | Birdseed label and grain icon | Common food, coin value 1; preferred-food FK points to `chick`, giving the existing +15 feed growth |
| Evolved `chick` mount, sprite `cute-chick-mount` | Bird model in licensed Unity and Bird portrait in licensed React builds; normal fallback otherwise | Existing server evolution at 100 growth creates the mount; no new reward or growth rules |
| Prepared Fledgling appearance | Matching model and portrait retained privately | Development appearance only; no intermediate server unlock is authored |

Web portraits resolve only the explicit Chick catalog keys and use the
matching staged manifest. Public builds retain runtime-sprite/emoji fallback.
Unity binds only exact `cute-chick` + `base` server identities to the prepared
Chick/Bird models. An acknowledged selection changes the appearance child,
retaining the stationary actor root and tap target. Confirmed evolution changes
the displayed Chick to Bird without automatically activating its new mount.
The retained active evolved pet keeps that appearance after fresh collection
reads. Explicit pet/mount presentation preference is stored by origin and child,
then checked against that row's saved active state after reload. Account changes
clear the old binding immediately; late replies cannot restore it. Unknown
species, unprepared potion variants and missing models show an explicit preview.
Older prepared licensed profiles receive their existing Chick/Bird references
in the transient build scene, preserving private art and saved-scene bytes.

React's shared `petSpriteKeys` helper uses confirmed `evolved_to_mount` state,
not growth alone, to choose Bird for evolved pets on Today and Companions.
Mounts, species detail, Manage galleries and hatch/evolve/breed/expedition
ceremonies already use the corresponding pet or mount key. Greetings, art
replacement and preference restoration never award XP or consume ingredients.

## Existing species and remaining coverage

All 17 earlier species and their saved pets, mounts, eggs, food, drops and
rewards retain their identities and existing behavior. They are not silently
renamed to match purchased artwork. Together with Chick, the seed catalog has
18 species. This is an additive catalog update, not retirement of acquisition
paths or removal of earned collections.

The compatible collection total is 94 species/potion combinations, including
Base-only Chick, Cosmic-only Archdragon and Base/Golden Companion. Stable totals
count these supported combinations rather than the 108-slot cartesian product.

| Existing species slugs | Current matching 3D coverage | Next action |
| --- | --- | --- |
| `fox` | Kenney public fox fallback; no owned Cute Series fox model | Keep the existing sprite/fallback; review a matching model only when needed |
| `wolf`, `dragon`, `cat` | No owned matching Cute Series models | Best candidates for optional purchases below |
| `owl`, `bear`, `phoenix`, `unicorn`, `stallion` | No owned matching 3D models | Retain existing web art; do not substitute the ordinary bird for Owl/Phoenix |
| `clownling`, `pondshell`, `seafang`, `ripplecoil`, `drift-jelly`, `deepkraken` | No owned matching 3D models | Defer aquatic presentation until the product needs it |
| `archdragon`, `companion` | No owned matching 3D models | Preserve cosmic-only and passive-companion rules; the preview dragon/bird supplies no ownership binding |

Legacy potion color variants and creature accessories remain web presentation.
The Archer's modular clothing cannot be assumed to fit a bird or another
creature. Forest props are presentation assets, not new purchasable furnishings
or progression unlocks.

## Optional purchases

No purchase is necessary to complete the Chick catalog and current fixed home.
The owned family now has an explicit binding to confirmed account state. Prices
below are the publisher's listed USD prices checked on 2026-10-11.

| Priority | Product | Listed price | Reason to add it |
| --- | --- | --- | --- |
| First complete new family | [Dragon Fire Inferno Evolution Pack](https://www.meshtint.com/products/dragon-fire-inferno-evolution-pack-cute-series) | $31.90 | Spark, Fire and Inferno provide related forms for the existing `dragon` identity; this proposed binding needs visual/animation review |
| Smallest companion purchase | [Wolf Pup](https://www.meshtint.com/products/wolf-pup-cute-series) | $9.90 | One 1,338-triangle model with Idle Happy and movement clips for the existing `wolf`; it does not supply an evolved mount model |
| Alternative small purchase | [Cat Meow](https://www.meshtint.com/products/cat-meow-cute-series) | $9.90 | One friendly cat model for `cat`; choose the $31.90 [Cat Lightning Bolt family](https://www.meshtint.com/products/cat-lightning-bolt-evolution-pack-cute-series) instead if all three forms are planned, because it includes Meow |
| Matching UI after choosing models | [Icons for Monsters Ultimate Pack 02](https://www.meshtint.com/products/icons-for-monsters-ultimate-pack-02-cute-series) | $7.99 | 24 portraits, including all dragon and wolf forms, with transparent PNGs in v2; the models are a separate purchase |

The listed dragon/wolf/cat models use Generic Mecanim rigs and Standard
materials. Follow the existing URP material/texture preparation, map each rig's
idle and friendly reaction, disable root motion, and validate on Unity
6000.6.5f1 and real phones. Vendor minimum Unity versions do not establish
compatibility with this project's exact editor or mobile performance.

Avoid buying [Monsters Ultimate Pack 01](https://www.meshtint.com/collections/cute-series/products/monsters-ultimate-pack-01-cute-series)
for this gap: its $139.99 bundle includes the already-owned bird family.
[Ultimate Pack 02](https://www.meshtint.com/collections/ultimate-packs-cute-series/products/monsters-ultimate-pack-02-cute-series)
is $159.90 and includes dragon/wolf families, so choose that bundle or the
individual models before purchasing both. Additional scenery and humanoid
outfits have no immediate use in the fixed home.
The publisher's [Cute Pro Animations Pack](https://www.meshtint.com/collections/cute-series/products/animations-pack-chibi-series)
explicitly discourages use with non-Cute Pro assets; do not buy it as an assumed
animation fix for the owned original Cute Series Archer.

## Loading and future maintenance

Use the existing `loadrpgcontent --dry-run`/`loadrpgcontent` workflow to apply
the YAML to the intended environment. This source update does not load or
deploy a live database. Upserts preserve earlier species and inventory; no
retirement cleanup is needed because no YAML entries are removed. Server
hatching honors authored potion compatibility before consuming ingredients.
Breeding chooses compatible ingredients and grants a Cosmic upgrade only for
species that support it. Both hatch interfaces can still submit any owned
potion; unsupported pairings receive a server rejection without consuming
ingredients. Explaining compatibility before submission remains UI follow-up.

Keep paid FBX/PSD/PNG files, generated licensed references, archive backups and
purchase/license records private. Continue staging the existing bird portraits
instead of publishing the purchased icon pack in Git or a sprite bucket.
After adding an asset, update this coverage table, its exact private import
record and explicit presentation mapping. Retain content slugs and `.meta`
GUIDs across replacements. New API fields require the shared fixture and
backend/React/Unity checks described in
[`contracts/api/README.md`](../../contracts/api/README.md).

## Validation — 2026-10-11

147 Django pet/loader/catalog/Lorebook/shared-response tests passed with Django
5.2.18 and disposable in-memory SQLite. The complete React suite passed 2,847
tests; lint passed with six existing warnings. Public and privately staged
licensed production builds passed, with matching Chick/Bird portraits in the
licensed bundle. Unity 6000.6.5f1 validation passed rendering, saved-scene,
appearance-swap and 308 API/presentation checks, including the restricted
collection fixture. Windows and Web players exported successfully. The
1,300-check Windows harness passed care, evolution, hatching, expeditions,
ambiguous saves and account switching, including an older private profile with
injected build bindings and unchanged private-input/saved-scene hashes.
An isolated same-origin browser check confirmed Chick → Bird through two saved
feeds, matching React art, and Unity mount choice after reload in portrait and
landscape. Browser bridge/template and release packaging guards also passed.
Paid sources and generated import files remain ignored. Physical-phone
testing, live catalog loading and deployment were not performed in this checkout.
