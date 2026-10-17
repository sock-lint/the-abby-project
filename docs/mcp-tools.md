# MCP tool inventory

> **Total: 223 tools across 30 modules.** Checked against the live registry and `tool_policy.py` on October 17, 2026.

Update this inventory and the [README](../README.md#mcp-server) when tools change.
Each name requires an explicit permission policy before registration. See the
[RPG authoring workflow](operations/mcp-authoring.md) for previews, publication,
economy analysis, templates and external asset proposals.

## Authentication and permissions

HTTP MCP at `/mcp` accepts resource-bound OAuth Bearer tokens for active staff
parents. The ordinary web app retains Token authentication. Expired tokens,
missing/wrong resource bindings, broad legacy `mcp` grants, unknown scopes and
lost staff privileges are rejected. Reconnect clients for explicit new grants;
old connections are never upgraded.

| Scope | Permission |
| --- | --- |
| `mcp:catalog` | Global content and anonymous reward analysis; the consent default. No household records. |
| `mcp:author` | Draft and inspect family-owned content packs and asset briefs; save reviewed publication plans. |
| `mcp:publish` | Publish reviewed packs and change global catalog content/prepared artwork. |
| `mcp:read` | Read permitted household records, progress and actual reward evidence. |
| `mcp:write` | Execute permitted household workflows and author family projects/challenges. |

Scopes are independent. Discovery and invocation enforce the same policy;
role, family, ownership and private-journal checks still apply. Read-only,
destructive, idempotency and open-world annotations describe actual operations.
`get_daily_challenge` and `list_cosmetics` can create records and require writes.

## Confirmation contract

Tools marked **Required** require strict boolean `confirmation: true` next to
`params`, after the client obtains confirmation of the operation and targets:

```json
{"name":"delete_project","arguments":{"params":{"project_id":123},"confirmation":true}}
```

The server rejects missing/false confirmation before running the handler.
The flag is a client acknowledgement, not proof of human approval or Google
consent. `delete_content_pack` also requires its existing `params.confirm`.
See the [AI disclosure inventory](operations/google-ai-disclosure.md).

## Module counts

| Module | Tools |
| --- | --- |
| `achievements` | 19 |
| `asset_proposals` | 7 |
| `catalog` | 2 |
| `challenges` | 5 |
| `chores` | 9 |
| `chronicle` | 10 |
| `content_packs` | 13 |
| `creations` | 8 |
| `daily_challenges` | 2 |
| `dashboard` | 1 |
| `economy` | 4 |
| `exchange` | 5 |
| `habits` | 7 |
| `homework` | 17 |
| `ingestion` | 4 |
| `inventory` | 6 |
| `movement` | 6 |
| `notifications` | 4 |
| `payments` | 4 |
| `pets` | 8 |
| `portfolio` | 6 |
| `projects` | 28 |
| `quests` | 9 |
| `rewards` | 9 |
| `savings` | 4 |
| `sprite_assets` | 1 |
| `sprite_authoring` | 6 |
| `templates` | 7 |
| `timecards` | 9 |
| `users` | 3 |

## achievements

| Tool | Scope | Read only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `add_skill_prerequisite` | `mcp:publish` | No | — | Add a prerequisite to a skill (staff-parent-only). |
| `create_badge` | `mcp:publish` | No | — | Create a badge with a criteria rule (staff-parent-only). |
| `create_category` | `mcp:publish` | No | — | Create a new skill category (staff-parent-only). |
| `create_skill` | `mcp:publish` | No | — | Create a skill inside a category/subject (staff-parent-only). |
| `create_subject` | `mcp:publish` | No | — | Create a subject inside a category (staff-parent-only). |
| `delete_badge` | `mcp:publish` | No | Required | Delete a badge definition. UserBadge rows referencing it cascade. Parent-only. |
| `delete_category` | `mcp:publish` | No | Required | Delete a skill category. Cascades to subjects, skills, and dependent rows. |
| `delete_skill` | `mcp:publish` | No | Required | Delete a skill (staff-parent-only). Cascades to SkillPrerequisite + SkillProgress + tags. |
| `delete_subject` | `mcp:publish` | No | Required | Delete a subject. Skills in it keep their category but lose the subject FK (SET_NULL). Parent-only. |
| `get_skill_tree` | `mcp:read` | Yes | — | Full nested skill tree for a category with the target user's progress. |
| `list_badges` | `mcp:catalog` | Yes | — | List all defined badges, optionally filtered by rarity. |
| `list_earned_badges` | `mcp:read` | Yes | — | List badges the target user has earned, newest first. |
| `list_skill_categories` | `mcp:catalog` | Yes | — | List all top-level skill categories. |
| `list_skills` | `mcp:catalog` | Yes | — | Flat list of skills, optionally filtered by category/subject/name. |
| `remove_skill_prerequisite` | `mcp:publish` | No | Required | Remove a prerequisite edge from the skill graph (staff-parent-only). |
| `update_badge` | `mcp:publish` | No | Required | Edit a badge (staff-parent-only). |
| `update_category` | `mcp:publish` | No | Required | Edit a skill category (staff-parent-only). |
| `update_skill` | `mcp:publish` | No | Required | Edit a skill (staff-parent-only). |
| `update_subject` | `mcp:publish` | No | Required | Edit a subject (staff-parent-only). |

## asset_proposals

| Tool | Scope | Read only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `export_asset_proposal` | `mcp:author` | Yes | — | Return a reviewed versioned JSON production brief for an external pipeline. |
| `get_asset_proposal` | `mcp:author` | Yes | — | Inspect a family proposal with paginated history summaries and brief digests. |
| `list_asset_proposals` | `mcp:author` | Yes | — | List the caller family's asset briefs with stable ID pagination. |
| `propose_asset` | `mcp:author` | No | — | Save an asset brief with explicit intended uses and technical acceptance criteria. |
| `record_asset_delivery` | `mcp:author` | No | Required | Record an external artifact claim without downloading, approving or publishing it. |
| `review_asset_proposal` | `mcp:author` | No | Required | Mark a reviewed exact brief ready for external production, or cancel it. |
| `update_asset_proposal` | `mcp:author` | No | Required | Replace a brief at an expected revision; changes reset its ready review. |

## catalog

| Tool | Scope | Read only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `audit_rpg_catalog` | `mcp:catalog` | Yes | — | Inspect one bounded catalog page without modifying rules or player state. |
| `read_rpg_catalog` | `mcp:catalog` | Yes | — | Read one global section in primary-key order with a stable after cursor. |

## challenges

| Tool | Scope | Read only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `create_challenge_goal` | `mcp:write` | No | Required | Create the reviewed same-family parent goal once, using a stable UUID. |
| `list_challenges` | `mcp:read` | Yes | — | Read saved modern goals, legacy history and actual reward receipts. |
| `pin_challenge` | `mcp:write` | No | — | Pin a saved challenge for self or a parent's same-family child. Awards nothing. |
| `preview_challenge_goal` | `mcp:read` | Yes | — | Validate a parent goal without creating records or computing an award. |
| `unpin_challenge` | `mcp:write` | No | — | Clear a matching saved pin; progress, periods and reward promises stay intact. |

## chores

| Tool | Scope | Read only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `approve_chore_completion` | `mcp:write` | No | Required | Approve a pending chore completion (parent-only). Awards money and coins. |
| `complete_chore` | `mcp:write` | No | — | Mark a chore as done (creates a pending completion for parent approval). |
| `create_chore` | `mcp:write` | No | — | Create a new chore (parent-only). |
| `get_chore` | `mcp:read` | Yes | — | Get details for a single chore (family-scoped). |
| `list_chore_completions` | `mcp:read` | Yes | — | List chore completions. Parents see all; children see their own. |
| `list_chores` | `mcp:read` | Yes | — | List chores. Parents see all in their family; children see assigned + unassigned active chores in their family with today's availability. |
| `reject_chore_completion` | `mcp:write` | No | Required | Reject a pending chore completion (parent-only). |
| `set_chore_skill_tags` | `mcp:write` | No | Required | Replace the skill tags on a chore (parent-only). |
| `update_chore` | `mcp:write` | No | Required | Update an existing chore (parent-only, same-family). |

## chronicle

| Tool | Scope | Read only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `create_manual_entry` | `mcp:write` | No | — | Create a parent-authored manual chronicle entry on a child's timeline. |
| `delete_chronicle_entry` | `mcp:write` | No | Required | Delete a manual chronicle entry (parent-only, MANUAL-kind only). |
| `get_chronicle_summary` | `mcp:read` | Yes | — | Group entries by chapter_year with per-chapter stats. |
| `get_pending_celebration` | `mcp:read` | Yes | — | Return today's unviewed BIRTHDAY entry for the caller, or ``null``. |
| `get_today_journal` | `mcp:read` | Yes | — | Return today's journal entry for the caller, or ``null`` if none. |
| `list_chronicle_entries` | `mcp:read` | Yes | — | Read-only timeline of all chronicle entries for a user. |
| `mark_chronicle_viewed` | `mcp:write` | No | — | Set ``viewed_at=now()`` on an entry the caller can see. Idempotent. |
| `update_journal` | `mcp:write` | No | Required | Edit today's journal entry. Locked to owner; 403 after midnight. |
| `update_manual_entry` | `mcp:write` | No | Required | Edit a manual chronicle entry (parent-only, MANUAL-kind only). |
| `write_journal` | `mcp:write` | No | — | Write today's journal entry (caller is always the author). |

## content_packs

| Tool | Scope | Read only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `delete_content_pack` | `mcp:author` | No | Required | Delete an entire pack directory. |
| `delete_pack_file` | `mcp:author` | No | Required | Delete one YAML file from a pack. |
| `draft_pack_entries` | `mcp:author` | No | Required | Merge a batch of YAML entries into a pack file. |
| `get_content_pack` | `mcp:author` | Yes | — | Return a single pack's summary — files present + last-load metadata. |
| `list_content_packs` | `mcp:author` | Yes | — | List all RPG content packs under ``content/rpg/packs/``. |
| `list_rpg_catalog` | `mcp:catalog` | Yes | — | Aggregate read of the live RPG catalog. |
| `load_content_pack` | `mcp:publish` | No | Required | Compatibility publication route: dry_run previews, writes require the reviewed plan. |
| `preview_content_pack` | `mcp:author` | No | — | Review exact field changes, removals, retained definitions and family shop destination. |
| `prune_pack_content` | `mcp:publish` | No | Required | Retired direct pruning. Review removals through the atomic pack publication plan. |
| `publish_content_pack` | `mcp:publish` | No | Required | Atomically apply one reviewed revision and retain its durable audit receipt. |
| `read_pack_file` | `mcp:author` | Yes | — | Read the raw YAML content of a file inside a pack. |
| `validate_content_pack` | `mcp:author` | No | — | Compatibility alias for preview_content_pack; returns an exact expiring plan. |
| `write_pack_file` | `mcp:author` | No | Required | Write YAML content to ``<pack>/<filename>.yaml``. |

## creations

| Tool | Scope | Read only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `approve_creation` | `mcp:write` | No | Required | Approve a Creation's bonus pool (parent-only). |
| `delete_creation` | `mcp:write` | No | Required | Delete a creation (owner or parent). Blob-first; counter NOT decremented. |
| `get_creation` | `mcp:read` | Yes | — | Fetch a single creation. Children may only read their own. |
| `list_creations` | `mcp:read` | Yes | — | List creations. Children see their own; parents see any child. |
| `list_pending_creations` | `mcp:read` | Yes | — | Parent-only queue of submitted-pending Creations awaiting bonus review. |
| `log_creation` | `mcp:write` | No | — | Log a child-authored Creation ("I made a thing") with an image. |
| `reject_creation` | `mcp:write` | No | Required | Reject a Creation's bonus (parent-only). Baseline XP stays intact. |
| `submit_creation` | `mcp:write` | No | — | Submit a Creation for parent bonus approval (owner or parent). |

## daily_challenges

| Tool | Scope | Read only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `claim_daily_challenge` | `mcp:write` | No | — | Claim today's reward (idempotent — second claim returns already_claimed=True). |
| `get_daily_challenge` | `mcp:write` | No | — | Return today's DailyChallenge for the user, creating one if missing. |

## dashboard

| Tool | Scope | Read only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `get_dashboard` | `mcp:read` | Yes | — | Return an aggregated dashboard view. |

## economy

| Tool | Scope | Read only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `get_economy_audit` | `mcp:read` | Yes | — | Audit a bounded family-local period from actual CoinLedger amounts and typed receipts. |
| `get_economy_rules` | `mcp:catalog` | Yes | — | Read authoritative global reward settings, caps, boosts and calculation references; no family records. |
| `list_coin_ledger` | `mcp:read` | Yes | — | Read persisted Coin amounts through a signed cursor, scoped to self or an authorized same-family user. |
| `preview_economy_scenario` | `mcp:catalog` | Yes | — | Compare up to four anonymous 31-day plans using explicit assumptions and current eligible drop pools. |

## exchange

| Tool | Scope | Read only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `approve_exchange` | `mcp:write` | No | Required | Approve a pending exchange (parent-only). |
| `get_exchange_rate` | `mcp:read` | Yes | — | Return the current ``COINS_PER_DOLLAR`` rate. |
| `list_exchange_requests` | `mcp:read` | Yes | — | List exchange requests. Children see their own; parents see any child. |
| `reject_exchange` | `mcp:write` | No | Required | Deny a pending exchange (parent-only). No ledger side-effects. |
| `request_exchange` | `mcp:write` | No | Required | Request a money → coins exchange (child self-scoped). |

## habits

| Tool | Scope | Read only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `create_habit` | `mcp:write` | No | — | Create a new habit. |
| `delete_habit` | `mcp:write` | No | Required | Delete a habit (parent-only, mirrors REST). |
| `get_habit` | `mcp:read` | Yes | — | Get a single habit with its current strength + color. |
| `list_habits` | `mcp:read` | Yes | — | List habits. Parents see their family; children see their own only. |
| `log_habit` | `mcp:write` | No | — | Tap a habit +1 (positive) or -1 (negative). |
| `set_habit_skill_tags` | `mcp:write` | No | Required | Replace the skill tags on a habit (parent-only for other users' |
| `update_habit` | `mcp:write` | No | Required | Edit a habit. Parent-only (mirrors REST). |

## homework

| Tool | Scope | Read only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `approve_homework_submission` | `mcp:write` | No | Required | Approve a pending homework submission (parent-only). Awards XP + fires the RPG loop. |
| `create_homework` | `mcp:write` | No | — | Create a homework assignment. Both parents and children can create. |
| `create_homework_from_template` | `mcp:write` | No | — | Spawn a homework assignment for a child from a template (parent-only). |
| `create_homework_template` | `mcp:write` | No | — | Create a reusable homework template (parent-only). |
| `delete_homework` | `mcp:write` | No | Required | Soft-delete a homework assignment (sets ``is_active=False``). Parent-only. |
| `delete_homework_template` | `mcp:write` | No | Required | Delete a homework template (parent-only). |
| `get_homework` | `mcp:read` | Yes | — | Get details for a single homework assignment. |
| `get_homework_template` | `mcp:read` | Yes | — | Return a single template owned by the calling parent. |
| `list_homework` | `mcp:read` | Yes | — | List homework assignments. Parents see all; children see their own. |
| `list_homework_submissions` | `mcp:read` | Yes | — | List homework submissions. Parents see all; children see their own. |
| `list_homework_templates` | `mcp:read` | Yes | — | List homework templates owned by the calling parent. |
| `plan_homework` | `mcp:write` | No | — | Trigger AI project planning for a homework assignment (parent-only). |
| `reject_homework_submission` | `mcp:write` | No | Required | Reject a pending homework submission (parent-only). Child can re-submit. |
| `set_homework_skill_tags` | `mcp:write` | No | Required | Replace the skill-tag set on an assignment (parent-only). |
| `submit_homework` | `mcp:write` | No | — | Submit homework for review (child-only). Note: images must be uploaded via the REST API. |
| `update_homework` | `mcp:write` | No | Required | Edit fields on a homework assignment (parent-only). |
| `update_homework_template` | `mcp:write` | No | Required | Edit a homework template (parent-only). |

## ingestion

| Tool | Scope | Read only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `commit_ingestion_job` | `mcp:write` | No | — | Materialize a staged ingestion job into a real Project (parent-only). |
| `get_ingestion_job` | `mcp:read` | Yes | — | Fetch a single ingestion job by UUID (parent-only). |
| `list_ingestion_jobs` | `mcp:read` | Yes | — | List the current parent's recent ingestion jobs. |
| `submit_ingestion_job` | `mcp:write` | No | — | Create an ingestion job for an Instructables/URL source and enqueue it. |

## inventory

| Tool | Scope | Read only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `equip_cosmetic` | `mcp:write` | No | — | Equip a cosmetic to its slot. Caller must own one in inventory. |
| `list_cosmetics` | `mcp:write` | No | — | Return owned cosmetics grouped by slot, plus current equipped state. |
| `list_inventory` | `mcp:read` | Yes | — | List a user's inventory entries (children forced to self). |
| `set_trophy_badge` | `mcp:write` | No | — | Set or clear the user's hero ``active_trophy_badge``. |
| `unequip_cosmetic` | `mcp:write` | No | — | Clear a cosmetic slot. |
| `use_consumable` | `mcp:write` | No | Required | Use one of a CONSUMABLE-type item. |

## movement

| Tool | Scope | Read only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `delete_movement_session` | `mcp:write` | No | Required | Remove a session row. Owner or parent only. Counter is NOT decremented. |
| `get_movement_session` | `mcp:read` | Yes | — | Fetch a single session. Children may only read their own. |
| `list_movement_sessions` | `mcp:read` | Yes | — | List logged sessions. Children see their own; parents see any child. |
| `list_movement_types` | `mcp:catalog` | Yes | — | Read-only catalog of MovementType rows. |
| `log_movement_session` | `mcp:write` | No | — | Log a self-reported physical-activity session. |
| `set_movement_type_skill_tags` | `mcp:publish` | No | Required | Replace the skill-tag fan-out on a MovementType (staff-parent-only). |

## notifications

| Tool | Scope | Read only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `get_unread_notification_count` | `mcp:read` | Yes | — | Return the count of unread notifications for the caller. |
| `list_notifications` | `mcp:read` | Yes | — | List notifications for the current user. |
| `mark_all_notifications_read` | `mcp:write` | No | — | Bulk mark every unread notification for the caller as read. |
| `mark_notification_read` | `mcp:write` | No | — | Mark a single notification as read. |

## payments

| Tool | Scope | Read only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `adjust_payment` | `mcp:write` | No | Required | Apply a positive or negative manual adjustment to a child's balance. |
| `get_payment_balance` | `mcp:read` | Yes | — | Return money still owed to a child, breakdown and recent entries. |
| `list_payment_ledger` | `mcp:read` | Yes | — | List PaymentLedger entries, optionally filtered by entry_type/since. |
| `record_payout` | `mcp:write` | No | Required | Confirm a completed Greenlight transfer (parent-only, same-family). |

## pets

| Tool | Scope | Read only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `activate_mount` | `mcp:write` | No | — | Mark a mount as active (deactivates any prior active mount). |
| `activate_pet` | `mcp:write` | No | — | Mark a pet as active (deactivates any prior active pet). |
| `breed_mounts` | `mcp:write` | No | Required | Combine two mounts to yield a hybrid egg + potion pair. |
| `feed_pet` | `mcp:write` | No | Required | Feed a food item to a pet. Auto-evolves at growth >= 100. |
| `get_pet_stable` | `mcp:read` | Yes | — | Aggregate stable view: pets + mounts + collection stats. |
| `hatch_pet` | `mcp:write` | No | Required | Hatch an egg + potion into a new pet (consumes both items). |
| `list_mounts` | `mcp:read` | Yes | — | List a user's evolved mounts. |
| `list_pets` | `mcp:read` | Yes | — | List a user's pets (children forced to self). |

## portfolio

| Tool | Scope | Read only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `delete_homework_proof` | `mcp:write` | No | Required | Delete a single homework-proof image (owner or parent). Blob-first. |
| `delete_project_photo` | `mcp:write` | No | Required | Delete a project photo (owner or parent). Blob-first. |
| `get_portfolio_export_manifest` | `mcp:read` | Yes | — | Manifest of files that would be included in the portfolio ZIP. |
| `get_portfolio_summary` | `mcp:read` | Yes | — | Aggregate counts for a user's portfolio: projects, photos, hours. |
| `list_portfolio_media` | `mcp:read` | Yes | — | Aggregated recent work: project photos + approved homework proofs. |
| `list_project_photos` | `mcp:read` | Yes | — | List ProjectPhoto rows attached to a project (read-only). |

## projects

| Tool | Scope | Read only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `activate_project` | `mcp:write` | No | — | Move a ``draft``/``in_review`` project to ``in_progress`` (parent-only). |
| `add_collaborator` | `mcp:write` | No | — | Add a child as a collaborator on a project (parent-only). |
| `add_material` | `mcp:write` | No | — | Add a material to a project's bill-of-materials (parent-only). |
| `add_milestone` | `mcp:write` | No | — | Add a milestone (chapter) to an existing project. Parent-only. |
| `add_resource` | `mcp:write` | No | — | Add a reference link (video/doc/image/link) to a project or step. Parent-only. |
| `add_step` | `mcp:write` | No | — | Add a walkthrough step to a project, optionally grouped under a milestone. |
| `approve_project` | `mcp:write` | No | Required | Mark a project as ``completed`` (parent-only). |
| `complete_milestone` | `mcp:write` | No | Required | Mark a milestone as complete and award its bonus + skill XP. |
| `complete_step` | `mcp:write` | No | Required | Mark a step complete. Child-safe: assignee or collaborators may toggle. |
| `create_project` | `mcp:write` | No | — | Create a new project with optional inline steps, milestones, resources, |
| `delete_material` | `mcp:write` | No | Required | Delete a material from a project (parent-only). |
| `delete_milestone` | `mcp:write` | No | Required | Delete a milestone. Its steps become ungrouped (milestone=None). |
| `delete_project` | `mcp:write` | No | Required | Delete a project and all its nested milestones/steps/materials/resources. |
| `delete_resource` | `mcp:write` | No | Required | Delete a reference link (parent-only). |
| `delete_step` | `mcp:write` | No | Required | Delete a walkthrough step (parent-only). |
| `get_project` | `mcp:read` | Yes | — | Get a single project's full detail (milestones, materials, skill tags). |
| `list_projects` | `mcp:read` | Yes | — | List projects visible to the current user. |
| `mark_material_purchased` | `mcp:write` | No | Required | Mark a material as purchased; children may only modify their own projects. |
| `remove_collaborator` | `mcp:write` | No | Required | Remove a collaborator from a project (parent-only). |
| `request_project_changes` | `mcp:write` | No | — | Send a project back to ``in_progress`` with parent notes (parent-only). |
| `set_project_skill_tags` | `mcp:write` | No | Required | Replace the full skill-tag set on a project (parent-only). |
| `uncomplete_step` | `mcp:write` | No | Required | Un-mark a step. Child-safe: assignee or collaborators may toggle. |
| `update_material` | `mcp:write` | No | Required | Edit a material (parent-only). To mark purchased, use ``mark_material_purchased``. |
| `update_milestone` | `mcp:write` | No | Required | Edit a milestone. When ``skill_tags`` is provided, replaces the full set. |
| `update_project` | `mcp:write` | No | Required | Edit project fields (parent-only). Only the provided fields are touched. |
| `update_project_status` | `mcp:write` | No | Required | Transition a project's status. |
| `update_resource` | `mcp:write` | No | Required | Edit a reference link (parent-only). |
| `update_step` | `mcp:write` | No | Required | Edit a step. Parent-only. |

## quests

| Tool | Scope | Read only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `assign_co_op_quest` | `mcp:write` | No | — | Start ONE shared Quest with 2+ children as participants. |
| `assign_quest` | `mcp:write` | No | — | Start a live Quest for a specific child from an existing QuestDefinition. |
| `cancel_quest` | `mcp:write` | No | Required | Mark an active quest as ``failed`` (parent-only). |
| `create_quest_definition` | `mcp:write` | No | — | Create a custom QuestDefinition (parent-only). |
| `delete_quest_definition` | `mcp:write` | No | Required | Permanently remove a parent-authored QuestDefinition (parent-only). |
| `get_quest` | `mcp:read` | Yes | — | Get a quest instance with its progress + participants. |
| `list_quest_catalog` | `mcp:read` | Yes | — | Browse every authored QuestDefinition. Parent-only. |
| `list_quests` | `mcp:read` | Yes | — | List quests visible to the current user. |
| `set_quest_definition_skill_tags` | `mcp:write` | No | Required | Replace the skill tags on a QuestDefinition (parent-only). |

## rewards

| Tool | Scope | Read only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `adjust_coins` | `mcp:write` | No | Required | Grant or revoke coins for a child (parent-only, same-family). |
| `approve_redemption` | `mcp:write` | No | Required | Approve a pending redemption (parent-only). |
| `create_reward` | `mcp:write` | No | — | Create a new shop reward (parent-only). Images are not supported via MCP. |
| `delete_reward` | `mcp:write` | No | Required | Delete a reward from the shop (parent-only). |
| `get_coin_balance` | `mcp:read` | Yes | — | Return coin balance, per-reason breakdown, and recent ledger entries. |
| `list_rewards` | `mcp:read` | Yes | — | List rewards in the shop along with the current user's coin balance. |
| `reject_redemption` | `mcp:write` | No | Required | Reject a pending redemption and refund the held coins (parent-only). |
| `request_redemption` | `mcp:write` | No | Required | Request a reward redemption on behalf of the current user. |
| `update_reward` | `mcp:write` | No | Required | Edit an existing reward (parent-only). |

## savings

| Tool | Scope | Read only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `create_savings_goal` | `mcp:write` | No | — | Create a savings goal for the current user. |
| `delete_savings_goal` | `mcp:write` | No | Required | Delete a savings goal (owner or parent only). |
| `list_savings_goals` | `mcp:read` | Yes | — | List a user's savings goals (children forced to self). |
| `update_savings_goal` | `mcp:write` | No | Required | Edit a savings goal's metadata (owner or parent only). |

## sprite_assets

| Tool | Scope | Read only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `register_sprite_assets` | `mcp:publish` | No | Required | Register spritesheets and sprites for a content pack and slice artwork. |

## sprite_authoring

| Tool | Scope | Read only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `delete_sprite` | `mcp:publish` | No | Required | Remove a sprite (DB row + Ceph blob, blob-first). |
| `get_sprite` | `mcp:catalog` | Yes | — | Fetch the full authoring shape for one sprite. |
| `list_sprites` | `mcp:catalog` | Yes | — | Enumerate registered sprites (parent-only, read-only). |
| `register_sprite` | `mcp:publish` | No | Required | Register one sprite (static or animation strip) from bytes or a URL. |
| `register_sprite_batch` | `mcp:publish` | No | Required | Upload one spritesheet and register many named tiles in one call. |
| `update_sprite_metadata` | `mcp:publish` | No | Required | Update metadata (fps, pack) on an existing sprite without |

## templates

| Tool | Scope | Read only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `create_project_from_template` | `mcp:write` | No | — | Instantiate a family template for a child, with skill wiring preserved. |
| `create_template` | `mcp:write` | No | — | Create a family template with skill wiring and linked nested content. |
| `delete_template` | `mcp:write` | No | Required | Delete a family template and its nested rows (parent-only). |
| `get_template` | `mcp:read` | Yes | — | Return one template with its milestones, materials, steps, resources. |
| `list_templates` | `mcp:read` | Yes | — | List project templates visible to the current user. |
| `save_project_as_template` | `mcp:write` | No | — | Save a family project as a reusable template, preserving all skill tags. |
| `update_template` | `mcp:write` | No | Required | Edit template metadata and skill wiring or atomically replace its plan. |

## timecards

| Tool | Scope | Read only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `approve_timecard` | `mcp:write` | No | Required | Approve a weekly timecard (parent-only). |
| `clock_in` | `mcp:write` | No | — | Start a TimeEntry on a project (child self-scoped, parent on-behalf). |
| `clock_out` | `mcp:write` | No | — | End the active TimeEntry. Awards XP + coins via AwardService and |
| `generate_timecard` | `mcp:write` | No | — | Generate (or refresh) the weekly timecard for a child (parent-only). |
| `get_active_entry` | `mcp:read` | Yes | — | Return the user's current active TimeEntry, or null if not clocked in. |
| `list_time_entries` | `mcp:read` | Yes | — | List TimeEntry rows for a user (children forced to self). |
| `list_timecards` | `mcp:read` | Yes | — | List weekly timecards for a user (children forced to self). |
| `mark_timecard_paid` | `mcp:write` | No | Required | Mark a timecard PAID and post a negative PaymentLedger payout (parent-only). |
| `void_time_entry` | `mcp:write` | No | Required | Void a completed TimeEntry (parent-only). Status flips to ``voided``. |

## users

| Tool | Scope | Read only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `get_user` | `mcp:read` | Yes | — | Return a user profile. Children may only look up themselves. |
| `list_children` | `mcp:read` | Yes | — | Return every child user in the family (parent-only). |
| `update_child` | `mcp:write` | No | Required | Update a child's profile fields (parent-only). |
