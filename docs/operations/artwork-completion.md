# Complete artwork adoption

The application appends two immutable releases to `frontend/assets.lock.json`.
All six earlier pins remain unchanged. The complete 2D release supplies 365
transparent 256px PNGs: 182 badge identities, 14 categories, 34 subjects, 96
skills, one birthday candle, 33 item/accessory icons and five challenges.
Existing item, challenge, egg and companion artwork keeps its existing pins.

| Release | Version | Manifest SHA-256 |
| --- | --- | --- |
| `abby-artwork-completion` | `1.0.0` | `1ceb2d42a96c2c8f7c6ec912d8e0901b0d391c4ddbabb4827ed8d3d8ddaf9cde` |
| `abby-bird-accessory-pilot` | `1.0.0` | `432e9298689baf87f059c7c8734bf85aefe395e749149827cb58d0bbe43d9720` |

The handoff catalog was frozen at `ecdc7f3f5646fb8476e790a7c862173df5bd5185`;
integration starts from main `d35847791598501c474b09da0be0fa8518586e6a`.
Private intake independently checked both index digests, both archive digests,
every workspace inventory entry and all runtime file hashes. Each supplied
offline `verify-handoff` command returned `ready` and `verified: true`.
Private payloads, editable masters, archives and visual evidence stay outside Git.

## Identity and presentation

`shared/catalog/artwork-bindings.json` contains code-only semantic rows from
the verified handoff. Django exposes nullable artwork identities alongside
the authored glyphs. Badges require the exact name and final criterion;
subjects require their category; skills also require their authored subject.
Items require exact slug, name and type, and challenge art requires a system
definition with the exact name and type. No database IDs or shared sprite
filenames select artwork.

React resolves only the locked release and each semantic row's PNG digest.
Badge rarity, featured frames, locked state, readable names and all
interactions remain application content. Absent or failed images preserve the
complete authored glyph. Birthday age, rewards and acknowledgement remain
server-owned. The synthetic `/__design` catalog artwork gallery inspects every
new illustration at 24, 32, 40, 64 and 96 CSS pixels under the existing themes.

Artwork import does not load packs, run catalog cleanup, reactivate retired
definitions, change availability, grant ownership or alter rewards. Duplicate
source badge definitions still follow the loader's final update. First Spark
and the Spring Bloom Collector badge have artwork; their historical cleanup
entries do not authorize running cleanup or restoring the retired quest.
The optional Beach Day and Golden Hour theme icons do not supply missing theme
metadata or CSS and do not enable those themes.

## Crown pilot boundary

The separate pilot has 34 GLB payloads and no PNGs. It remains private
evaluation art with no active equipment binding. Its fit covers only
`accessory-crown`, exact Chick/Base, across nine Chick, twelve Fledgling and
ten Bird native takes. Chick/Fledgling require the supplied reversible
96-triangle feather mask. Egg, both evolution transitions, all other species
and potions, and the other 16 accessories remain unsupported.

An equipment integration needs a separate exact positive server policy and
confirmed inventory selection, an explicit renderer lifecycle, checked runtime
and module hashes, removal/restoration and stale-request handling, plus the
required private asset and product checks. This PR does not activate equipment
or adopt the proposed attachment adapter. The current global accessory gate
continues to preserve saved ownership and permit removal of old selections.

## Validation and rollback

Use the existing private reader with `npm run assets:import`, then
`npm run assets:verify`, `npm run test:licensed-art`, the focused artwork/API
checks and both web/native builds. The importer and postbuild verifier check
all eight manifests and 1,519 runtime files plus seven retained supplemental
portraits. Public CI deliberately exercises labelled fallbacks without private
art. The private browser artwork suite additionally checks PNG decoding,
fallbacks and actual badge/skill/birthday presentation. Desktop browser and
native bundle checks do not establish physical-phone performance.

Rollback removes only the two appended pins and this presentation integration;
retain all original pins and catalog enablement. No data migration or content
cleanup is needed. Remove/reimport the ignored staged output through the
existing asset importer so stale files cannot masquerade as a verified install.
