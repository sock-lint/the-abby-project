# RPG content workbench

Staff parents open **Manage → Admin → RPG content** to manage global challenge
and item definitions. This combines the catalog and publication services from
the MCP authoring work with Progression Lab's anonymous new-child simulator.
Ordinary parents and children cannot edit the global catalog. MCP exposes the same revisioned draft, preview, simulation and publication services; its catalog references omit family shop usage.

Milestone fields select exact prerequisite challenge and skill IDs plus a
minimum unlocked skill level. They currently support only one-time daily
Reading Adventure collection challenges, whose source service captures the
new acceptance boundary. See [Reading Voyager milestones](reading-voyager-milestones.md)
for the inactive candidate preparation command, preservation rules and separate
publication workflow.

## Edit, evaluate and publish

1. Browse challenges or items. Inspect reward quantities, XP destinations,
   acquisition availability, prerequisites and references before editing.
2. Create or reopen a saved draft. Edit an existing definition or add an item
   or challenge, then save. Saving does not alter the published catalog.
3. Preview the draft to validate its fields and inspect the exact before/after
   changes and catalog findings. Fix missing references and unsupported reward
   items before evaluating a proposed acquisition path.
4. Compare the published catalog with the proposed catalog using the same
   anonymous routine and random seed. The reports identify their catalog and
   rules fingerprints, assumptions, coverage and exclusions.
5. Review the changes and explicitly confirm publication. Editing the draft or
   changing the catalog invalidates the previous review. A successful publication
   records a receipt; retrying it does not publish a second time.

The simulator captures a fully detached proposed catalog during validation and
then calculates journeys in memory. It creates no child accounts, inventory,
ledger credits, progress, notifications or actual reward receipts. The baseline
and candidate share a routine and seed, but changed content may change the
sequence of random draws. A difference between two reports is conditional on
the modeled mechanics; it is not a retention prediction or a complete economy
audit. Read [Progression Lab's model boundary](progression-lab.md#model-boundary).

Challenge activity choices follow the current factual Challenges engine. Boss
challenges require activities that actually deal boss damage. Older unsupported
filters remain visible for correction; a valid historical RPG event name alone
does not make it a supported automatic challenge source.

## YAML and durable editing

Bundled YAML in `content/rpg/initial/` remains the initial catalog. It is editable
source data, and forms do not require storing every resource in a different
format. Browser edits instead need durable storage: a container's application
source directory is not a safe database for user-created drafts.

The workbench therefore saves drafts and explicit published overrides in
PostgreSQL. Publishing preserves the existing definition's identity. Once a
definition has a published override, later YAML loading preserves that managed
definition instead of silently replacing it. A renamed challenge also retains
its original source identity so a subsequent seed load cannot recreate it under
the former name. Other bundled definitions continue to load normally.

Changing database drafts or publishing content does not rewrite tracked YAML,
register artwork, modify the supported-art registry or publish private assets.
Existing item rarity, Coin value and effect metadata are versioned: create a
new item version and explicitly select it for future challenge rewards to
change those behaviors. This keeps already-owned and promised items consistent
with their saved explanations. Names, descriptions and presentation references
can be edited on the existing definition.
Generated eggs and potions retain their species/type bindings; adding a new
creature family still follows the reviewed asset/catalog integration process.

## Ownership and existing promises

Drafts are private to their family and bound to the acting staff parent for
preview and publication. Global definitions from another family's owned pack
remain visible as catalog references and cannot be overwritten through this
workspace. Private household goals and shop offers never become global catalog
entries or anonymous simulation inputs.

Existing inventory, accepted challenge windows and pending shop redemptions
retain their saved identities and promises. Legacy active quests still use
their definition's scalar rules, so changing those rules requires a new version
while an active legacy run exists. Use the same preservation rules described in
[MCP authoring](mcp-authoring.md#reviewed-content-pack-publishing).

The workbench manages definitions, rather than saved household progress. A
catalog edit does not rewrite a child's already-enrolled goal. Removed offers
and retained definitions have separate meanings; deleting a draft is not
permission to cascade-delete owned content or earned state.

## Validation

Backend checks cover role and family boundaries, revision conflicts, validation,
exact publication, anonymous comparison, preservation of accepted promises and
YAML reload behavior. Frontend checks cover request payloads, draft editing,
stale reviews, failures and explicit publication. Shared synthetic wire fixtures
connect the actual endpoints to the React client. Required hosted checks remain
the [normal PR validation gates](pr-validation.md).
