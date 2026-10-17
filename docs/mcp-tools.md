# MCP tool inventory

> **Total: 203 tools across 26 modules.** Checked against every registered tool and `apps/mcp_server/tool_policy.py` on October 17, 2026.

Update this inventory and the [README](../README.md#mcp-server) when tools change. Each name must have an explicit permission policy before it can register.

## Authentication and permissions

HTTP MCP at `/mcp` accepts resource-bound OAuth Bearer tokens for active staff parents. The ordinary web app keeps its separate Token authentication. Expired tokens, missing/wrong resource bindings, legacy broad `mcp` grants, unknown scopes and lost staff privileges are rejected. Existing MCP clients must reconnect to authorize the new scopes; no write permission is inferred from an old grant.

| Scope | Permission |
| --- | --- |
| `mcp:read` | Query permitted application data. This is the default requested permission. |
| `mcp:write` | Execute family workflows, including planning, approvals and contributions. |
| `mcp:author` | Modify global catalogs, content packs and prepared sprite artwork. |

Scopes are independent. A client that needs to read and write must request both permissions; global authoring is a separate opt-in. Scope grants never replace role, family, ownership or private-journal checks. Tool discovery filters by scope and invocation checks the scope again.

Every tool advertises read-only, destructive, idempotency and open-world annotations. These help clients explain operations; server authorization does not rely on those hints. Names are not a reliable guide: `get_daily_challenge` and `list_cosmetics` can create records and require write permission.

## Confirmation contract

For every tool marked **Required** below, the client must obtain the user’s confirmation of the operation and targets, then include the strict boolean `confirmation: true` beside `params`:

```json
{"name":"delete_project","arguments":{"params":{"project_id":123},"confirmation":true}}
```

The server rejects a missing/false confirmation before running the handler. The flag records the client’s acknowledgement; it cannot prove that a human approved. Clients must not synthesize it from tool output or treat a broad OAuth grant as per-action consent. `delete_content_pack` also retains its existing `params.confirm` guard. Provider/Google-data transfer consent remains a separate requirement, as explained in the [AI disclosure inventory](operations/google-ai-disclosure.md).

## Module counts

| Module | Tools |
| --- | --- |
| `achievements` | 19 |
| `chores` | 9 |
| `chronicle` | 10 |
| `content_packs` | 11 |
| `creations` | 8 |
| `daily_challenges` | 2 |
| `dashboard` | 1 |
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

| Tool | Scope | Read-only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `list_skill_categories` | `mcp:read` | Yes | — | List all top-level skill categories. |
| `list_skills` | `mcp:read` | Yes | — | Flat list of skills, optionally filtered by category/subject/name. |
| `get_skill_tree` | `mcp:read` | Yes | — | Full nested skill tree for a category with the target user's progress. |
| `list_badges` | `mcp:read` | Yes | — | List all defined badges, optionally filtered by rarity. |
| `list_earned_badges` | `mcp:read` | Yes | — | List badges the target user has earned, newest first. |
| `create_category` | `mcp:author` | No | — | Create a new skill category (parent-only). |
| `update_category` | `mcp:author` | No | Required | Edit a skill category (parent-only). |
| `delete_category` | `mcp:author` | No | Required | Delete a skill category. Cascades to subjects, skills, and dependent rows. |
| `create_subject` | `mcp:author` | No | — | Create a subject inside a category (parent-only). |
| `update_subject` | `mcp:author` | No | Required | Edit a subject (parent-only). |
| `delete_subject` | `mcp:author` | No | Required | Delete a subject. Skills in it keep their category but lose the subject FK (SET_NULL). Parent-only. |
| `create_skill` | `mcp:author` | No | — | Create a skill inside a category/subject (parent-only). |
| `update_skill` | `mcp:author` | No | Required | Edit a skill (parent-only). |
| `delete_skill` | `mcp:author` | No | Required | Delete a skill (parent-only). Cascades to SkillPrerequisite + SkillProgress + tags. |
| `add_skill_prerequisite` | `mcp:author` | No | — | Add a prerequisite to a skill (parent-only). |
| `remove_skill_prerequisite` | `mcp:author` | No | Required | Remove a prerequisite edge from the skill graph (parent-only). |
| `create_badge` | `mcp:author` | No | — | Create a badge with a criteria rule (parent-only). |
| `update_badge` | `mcp:author` | No | Required | Edit a badge (parent-only). |
| `delete_badge` | `mcp:author` | No | Required | Delete a badge definition. UserBadge rows referencing it cascade. Parent-only. |

## chores

| Tool | Scope | Read-only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `list_chores` | `mcp:read` | Yes | — | List chores. Parents see all in their family; children see assigned + unassigned active chores in their family with today's availability. |
| `get_chore` | `mcp:read` | Yes | — | Get details for a single chore (family-scoped). |
| `create_chore` | `mcp:write` | No | — | Create a new chore (parent-only). |
| `update_chore` | `mcp:write` | No | Required | Update an existing chore (parent-only, same-family). |
| `complete_chore` | `mcp:write` | No | — | Mark a chore as done (creates a pending completion for parent approval). |
| `list_chore_completions` | `mcp:read` | Yes | — | List chore completions. Parents see all; children see their own. |
| `approve_chore_completion` | `mcp:write` | No | Required | Approve a pending chore completion (parent-only). Awards money and coins. |
| `reject_chore_completion` | `mcp:write` | No | Required | Reject a pending chore completion (parent-only). |
| `set_chore_skill_tags` | `mcp:write` | No | Required | Replace the skill tags on a chore (parent-only). |

## chronicle

| Tool | Scope | Read-only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `list_chronicle_entries` | `mcp:read` | Yes | — | Read-only timeline of all chronicle entries for a user. |
| `get_chronicle_summary` | `mcp:read` | Yes | — | Group entries by chapter_year with per-chapter stats. |
| `mark_chronicle_viewed` | `mcp:write` | No | — | Set ``viewed_at=now()`` on an entry the caller can see. Idempotent. |
| `get_pending_celebration` | `mcp:read` | Yes | — | Return today's unviewed BIRTHDAY entry for the caller, or ``null``. |
| `get_today_journal` | `mcp:read` | Yes | — | Return today's journal entry for the caller, or ``null`` if none. |
| `write_journal` | `mcp:write` | No | — | Write today's journal entry (caller is always the author). |
| `update_journal` | `mcp:write` | No | Required | Edit today's journal entry. Locked to owner; 403 after midnight. |
| `create_manual_entry` | `mcp:write` | No | — | Create a parent-authored manual chronicle entry on a child's timeline. |
| `update_manual_entry` | `mcp:write` | No | Required | Edit a manual chronicle entry (parent-only, MANUAL-kind only). |
| `delete_chronicle_entry` | `mcp:write` | No | Required | Delete a manual chronicle entry (parent-only, MANUAL-kind only). |

## content_packs

| Tool | Scope | Read-only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `list_content_packs` | `mcp:read` | Yes | — | List all RPG content packs under ``content/rpg/packs/``. |
| `get_content_pack` | `mcp:read` | Yes | — | Return a single pack's summary — files present + last-load metadata. |
| `read_pack_file` | `mcp:read` | Yes | — | Read the raw YAML content of a file inside a pack. |
| `write_pack_file` | `mcp:author` | No | Required | Write YAML content to ``<pack>/<filename>.yaml``. |
| `draft_pack_entries` | `mcp:author` | No | Required | Merge a batch of YAML entries into a pack file. |
| `delete_pack_file` | `mcp:author` | No | Required | Delete one YAML file from a pack. |
| `delete_content_pack` | `mcp:author` | No | Required | Delete an entire pack directory. |
| `validate_content_pack` | `mcp:author` | No | — | Dry-run load a pack. Returns what WOULD be created/updated. |
| `load_content_pack` | `mcp:author` | No | Required | Load a content pack into the database. |
| `prune_pack_content` | `mcp:author` | No | Required | Delete pack-scoped DropTable + Reward rows before a re-load. |
| `list_rpg_catalog` | `mcp:read` | Yes | — | Aggregate read of the live RPG catalog. |

## creations

| Tool | Scope | Read-only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `list_creations` | `mcp:read` | Yes | — | List creations. Children see their own; parents see any child. |
| `get_creation` | `mcp:read` | Yes | — | Fetch a single creation. Children may only read their own. |
| `log_creation` | `mcp:write` | No | — | Log a child-authored Creation ("I made a thing") with an image. |
| `delete_creation` | `mcp:write` | No | Required | Delete a creation (owner or parent). Blob-first; counter NOT decremented. |
| `submit_creation` | `mcp:write` | No | — | Submit a Creation for parent bonus approval (owner or parent). |
| `approve_creation` | `mcp:write` | No | Required | Approve a Creation's bonus pool (parent-only). |
| `reject_creation` | `mcp:write` | No | Required | Reject a Creation's bonus (parent-only). Baseline XP stays intact. |
| `list_pending_creations` | `mcp:read` | Yes | — | Parent-only queue of submitted-pending Creations awaiting bonus review. |

## daily_challenges

| Tool | Scope | Read-only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `get_daily_challenge` | `mcp:write` | No | — | Return today's DailyChallenge for the user, creating one if missing. |
| `claim_daily_challenge` | `mcp:write` | No | — | Claim today's reward (idempotent — second claim returns already_claimed=True). |

## dashboard

| Tool | Scope | Read-only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `get_dashboard` | `mcp:read` | Yes | — | Return an aggregated dashboard view. |

## exchange

| Tool | Scope | Read-only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `get_exchange_rate` | `mcp:read` | Yes | — | Return the current ``COINS_PER_DOLLAR`` rate. |
| `list_exchange_requests` | `mcp:read` | Yes | — | List exchange requests. Children see their own; parents see any child. |
| `request_exchange` | `mcp:write` | No | Required | Request a money → coins exchange (child self-scoped). |
| `approve_exchange` | `mcp:write` | No | Required | Approve a pending exchange (parent-only). |
| `reject_exchange` | `mcp:write` | No | Required | Deny a pending exchange (parent-only). No ledger side-effects. |

## habits

| Tool | Scope | Read-only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `list_habits` | `mcp:read` | Yes | — | List habits. Parents see their family; children see their own only. |
| `get_habit` | `mcp:read` | Yes | — | Get a single habit with its current strength + color. |
| `create_habit` | `mcp:write` | No | — | Create a new habit. |
| `update_habit` | `mcp:write` | No | Required | Edit a habit. Parent-only (mirrors REST). |
| `delete_habit` | `mcp:write` | No | Required | Delete a habit (parent-only, mirrors REST). |
| `log_habit` | `mcp:write` | No | — | Tap a habit +1 (positive) or -1 (negative). |
| `set_habit_skill_tags` | `mcp:write` | No | Required | Replace the skill tags on a habit (parent-only for other users' habits; child can tag their own). |

## homework

| Tool | Scope | Read-only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `list_homework` | `mcp:read` | Yes | — | List homework assignments. Parents see all; children see their own. |
| `get_homework` | `mcp:read` | Yes | — | Get details for a single homework assignment. |
| `create_homework` | `mcp:write` | No | — | Create a homework assignment. Both parents and children can create. |
| `submit_homework` | `mcp:write` | No | — | Submit homework for review (child-only). Note: images must be uploaded via the REST API. |
| `list_homework_submissions` | `mcp:read` | Yes | — | List homework submissions. Parents see all; children see their own. |
| `approve_homework_submission` | `mcp:write` | No | Required | Approve a pending homework submission (parent-only). Awards XP + fires the RPG loop. |
| `reject_homework_submission` | `mcp:write` | No | Required | Reject a pending homework submission (parent-only). Child can re-submit. |
| `update_homework` | `mcp:write` | No | Required | Edit fields on a homework assignment (parent-only). |
| `delete_homework` | `mcp:write` | No | Required | Soft-delete a homework assignment (sets ``is_active=False``). Parent-only. |
| `set_homework_skill_tags` | `mcp:write` | No | Required | Replace the skill-tag set on an assignment (parent-only). |
| `plan_homework` | `mcp:write` | No | — | Trigger AI project planning for a homework assignment (parent-only). |
| `list_homework_templates` | `mcp:read` | Yes | — | List homework templates owned by the calling parent. |
| `get_homework_template` | `mcp:read` | Yes | — | Return a single template owned by the calling parent. |
| `create_homework_template` | `mcp:write` | No | — | Create a reusable homework template (parent-only). |
| `update_homework_template` | `mcp:write` | No | Required | Edit a homework template (parent-only). |
| `delete_homework_template` | `mcp:write` | No | Required | Delete a homework template (parent-only). |
| `create_homework_from_template` | `mcp:write` | No | — | Spawn a homework assignment for a child from a template (parent-only). |

## ingestion

| Tool | Scope | Read-only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `submit_ingestion_job` | `mcp:write` | No | — | Create an ingestion job for an Instructables/URL source and enqueue it. |
| `get_ingestion_job` | `mcp:read` | Yes | — | Fetch a single ingestion job by UUID (parent-only). |
| `list_ingestion_jobs` | `mcp:read` | Yes | — | List the current parent's recent ingestion jobs. |
| `commit_ingestion_job` | `mcp:write` | No | — | Materialize a staged ingestion job into a real Project (parent-only). |

## inventory

| Tool | Scope | Read-only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `list_inventory` | `mcp:read` | Yes | — | List a user's inventory entries (children forced to self). |
| `use_consumable` | `mcp:write` | No | Required | Use one of a CONSUMABLE-type item. |
| `list_cosmetics` | `mcp:write` | No | — | Return owned cosmetics grouped by slot, plus current equipped state. |
| `equip_cosmetic` | `mcp:write` | No | — | Equip a cosmetic to its slot. Caller must own one in inventory. |
| `unequip_cosmetic` | `mcp:write` | No | — | Clear a cosmetic slot. |
| `set_trophy_badge` | `mcp:write` | No | — | Set or clear the user's hero ``active_trophy_badge``. |

## movement

| Tool | Scope | Read-only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `list_movement_types` | `mcp:read` | Yes | — | Read-only catalog of MovementType rows. |
| `list_movement_sessions` | `mcp:read` | Yes | — | List logged sessions. Children see their own; parents see any child. |
| `get_movement_session` | `mcp:read` | Yes | — | Fetch a single session. Children may only read their own. |
| `log_movement_session` | `mcp:write` | No | — | Log a self-reported physical-activity session. |
| `delete_movement_session` | `mcp:write` | No | Required | Remove a session row. Owner or parent only. Counter is NOT decremented. |
| `set_movement_type_skill_tags` | `mcp:author` | No | Required | Replace the skill-tag fan-out on a MovementType (parent-only). |

## notifications

| Tool | Scope | Read-only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `list_notifications` | `mcp:read` | Yes | — | List notifications for the current user. |
| `mark_notification_read` | `mcp:write` | No | — | Mark a single notification as read. |
| `mark_all_notifications_read` | `mcp:write` | No | — | Bulk mark every unread notification for the caller as read. |
| `get_unread_notification_count` | `mcp:read` | Yes | — | Return the count of unread notifications for the caller. |

## payments

| Tool | Scope | Read-only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `get_payment_balance` | `mcp:read` | Yes | — | Return money still owed to a child, breakdown and recent entries. |
| `list_payment_ledger` | `mcp:read` | Yes | — | List PaymentLedger entries, optionally filtered by entry_type/since. |
| `record_payout` | `mcp:write` | No | Required | Confirm a completed Greenlight transfer (parent-only, same-family). |
| `adjust_payment` | `mcp:write` | No | Required | Apply a positive or negative manual adjustment to a child's balance. |

## pets

| Tool | Scope | Read-only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `list_pets` | `mcp:read` | Yes | — | List a user's pets (children forced to self). |
| `list_mounts` | `mcp:read` | Yes | — | List a user's evolved mounts. |
| `get_pet_stable` | `mcp:read` | Yes | — | Aggregate stable view: pets + mounts + collection stats. |
| `hatch_pet` | `mcp:write` | No | Required | Hatch an egg + potion into a new pet (consumes both items). |
| `feed_pet` | `mcp:write` | No | Required | Feed a food item to a pet. Auto-evolves at growth >= 100. |
| `activate_pet` | `mcp:write` | No | — | Mark a pet as active (deactivates any prior active pet). |
| `activate_mount` | `mcp:write` | No | — | Mark a mount as active (deactivates any prior active mount). |
| `breed_mounts` | `mcp:write` | No | Required | Combine two mounts to yield a hybrid egg + potion pair. |

## portfolio

| Tool | Scope | Read-only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `list_project_photos` | `mcp:read` | Yes | — | List ProjectPhoto rows attached to a project (read-only). |
| `get_portfolio_summary` | `mcp:read` | Yes | — | Aggregate counts for a user's portfolio: projects, photos, hours. |
| `list_portfolio_media` | `mcp:read` | Yes | — | Aggregated recent work: project photos + approved homework proofs. |
| `delete_project_photo` | `mcp:write` | No | Required | Delete a project photo (owner or parent). Blob-first. |
| `delete_homework_proof` | `mcp:write` | No | Required | Delete a single homework-proof image (owner or parent). Blob-first. |
| `get_portfolio_export_manifest` | `mcp:read` | Yes | — | Manifest of files that would be included in the portfolio ZIP. |

## projects

| Tool | Scope | Read-only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `list_projects` | `mcp:read` | Yes | — | List projects visible to the current user. |
| `get_project` | `mcp:read` | Yes | — | Get a single project's full detail (milestones, materials, skill tags). |
| `create_project` | `mcp:write` | No | — | Create a new project with optional inline steps, milestones, resources, and skill tags. |
| `update_project_status` | `mcp:write` | No | Required | Transition a project's status. |
| `complete_milestone` | `mcp:write` | No | Required | Mark a milestone as complete and award its bonus + skill XP. |
| `set_project_skill_tags` | `mcp:write` | No | Required | Replace the full skill-tag set on a project (parent-only). |
| `mark_material_purchased` | `mcp:write` | No | Required | Mark a material as purchased; children may only modify their own projects. |
| `update_project` | `mcp:write` | No | Required | Edit project fields (parent-only). Only the provided fields are touched. |
| `delete_project` | `mcp:write` | No | Required | Delete a project and all its nested milestones/steps/materials/resources. |
| `activate_project` | `mcp:write` | No | — | Move a ``draft``/``in_review`` project to ``in_progress`` (parent-only). |
| `approve_project` | `mcp:write` | No | Required | Mark a project as ``completed`` (parent-only). |
| `request_project_changes` | `mcp:write` | No | — | Send a project back to ``in_progress`` with parent notes (parent-only). |
| `add_milestone` | `mcp:write` | No | — | Add a milestone (chapter) to an existing project. Parent-only. |
| `update_milestone` | `mcp:write` | No | Required | Edit a milestone. When ``skill_tags`` is provided, replaces the full set. |
| `delete_milestone` | `mcp:write` | No | Required | Delete a milestone. Its steps become ungrouped (milestone=None). |
| `add_step` | `mcp:write` | No | — | Add a walkthrough step to a project, optionally grouped under a milestone. |
| `update_step` | `mcp:write` | No | Required | Edit a step. Parent-only. |
| `delete_step` | `mcp:write` | No | Required | Delete a walkthrough step (parent-only). |
| `complete_step` | `mcp:write` | No | Required | Mark a step complete. Child-safe: assignee or collaborators may toggle. |
| `uncomplete_step` | `mcp:write` | No | Required | Un-mark a step. Child-safe: assignee or collaborators may toggle. |
| `add_material` | `mcp:write` | No | — | Add a material to a project's bill-of-materials (parent-only). |
| `update_material` | `mcp:write` | No | Required | Edit a material (parent-only). To mark purchased, use ``mark_material_purchased``. |
| `delete_material` | `mcp:write` | No | Required | Delete a material from a project (parent-only). |
| `add_resource` | `mcp:write` | No | — | Add a reference link (video/doc/image/link) to a project or step. Parent-only. |
| `update_resource` | `mcp:write` | No | Required | Edit a reference link (parent-only). |
| `delete_resource` | `mcp:write` | No | Required | Delete a reference link (parent-only). |
| `add_collaborator` | `mcp:write` | No | — | Add a child as a collaborator on a project (parent-only). |
| `remove_collaborator` | `mcp:write` | No | Required | Remove a collaborator from a project (parent-only). |

## quests

| Tool | Scope | Read-only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `list_quests` | `mcp:read` | Yes | — | List quests visible to the current user. |
| `get_quest` | `mcp:read` | Yes | — | Get a quest instance with its progress + participants. |
| `list_quest_catalog` | `mcp:read` | Yes | — | Browse every authored QuestDefinition. Parent-only. |
| `create_quest_definition` | `mcp:write` | No | — | Create a custom QuestDefinition (parent-only). |
| `assign_quest` | `mcp:write` | No | — | Start a live Quest for a specific child from an existing QuestDefinition. |
| `assign_co_op_quest` | `mcp:write` | No | — | Start ONE shared Quest with 2+ children as participants. |
| `delete_quest_definition` | `mcp:write` | No | Required | Permanently remove a parent-authored QuestDefinition (parent-only). |
| `cancel_quest` | `mcp:write` | No | Required | Mark an active quest as ``failed`` (parent-only). |
| `set_quest_definition_skill_tags` | `mcp:write` | No | Required | Replace the skill tags on a QuestDefinition (parent-only). |

## rewards

| Tool | Scope | Read-only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `list_rewards` | `mcp:read` | Yes | — | List rewards in the shop along with the current user's coin balance. |
| `get_coin_balance` | `mcp:read` | Yes | — | Return coin balance, per-reason breakdown, and recent ledger entries. |
| `request_redemption` | `mcp:write` | No | Required | Request a reward redemption on behalf of the current user. |
| `approve_redemption` | `mcp:write` | No | Required | Approve a pending redemption (parent-only). |
| `reject_redemption` | `mcp:write` | No | Required | Reject a pending redemption and refund the held coins (parent-only). |
| `create_reward` | `mcp:write` | No | — | Create a new shop reward (parent-only). Images are not supported via MCP. |
| `update_reward` | `mcp:write` | No | Required | Edit an existing reward (parent-only). |
| `delete_reward` | `mcp:write` | No | Required | Delete a reward from the shop (parent-only). |
| `adjust_coins` | `mcp:write` | No | Required | Grant or revoke coins for a child (parent-only, same-family). |

## savings

| Tool | Scope | Read-only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `list_savings_goals` | `mcp:read` | Yes | — | List a user's savings goals (children forced to self). |
| `create_savings_goal` | `mcp:write` | No | — | Create a savings goal for the current user. |
| `update_savings_goal` | `mcp:write` | No | Required | Edit a savings goal's metadata (owner or parent only). |
| `delete_savings_goal` | `mcp:write` | No | Required | Delete a savings goal (owner or parent only). |

## sprite_assets

| Tool | Scope | Read-only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `register_sprite_assets` | `mcp:author` | No | Required | Register spritesheets and sprites for a content pack and slice artwork. |

## sprite_authoring

| Tool | Scope | Read-only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `register_sprite` | `mcp:author` | No | Required | Register one sprite (static or animation strip) from bytes or a URL. |
| `register_sprite_batch` | `mcp:author` | No | Required | Upload one spritesheet and register many named tiles in one call. |
| `list_sprites` | `mcp:read` | Yes | — | Enumerate registered sprites (parent-only, read-only). |
| `get_sprite` | `mcp:read` | Yes | — | Fetch the full authoring shape for one sprite. |
| `update_sprite_metadata` | `mcp:author` | No | Required | Update metadata (fps, pack) on an existing sprite without regenerating the image. |
| `delete_sprite` | `mcp:author` | No | Required | Remove a sprite (DB row + Ceph blob, blob-first). |

## templates

| Tool | Scope | Read-only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `list_templates` | `mcp:read` | Yes | — | List project templates visible to the current user. |
| `get_template` | `mcp:read` | Yes | — | Return one template with its milestones, materials, steps, resources. |
| `create_template` | `mcp:write` | No | — | Create a new project template from scratch (parent-only). |
| `update_template` | `mcp:write` | No | Required | Edit top-level template fields (parent-only). |
| `delete_template` | `mcp:write` | No | Required | Delete a template and all its nested rows (parent-only). |
| `save_project_as_template` | `mcp:write` | No | — | Clone an existing project into a new reusable template (parent-only). |
| `create_project_from_template` | `mcp:write` | No | — | Spawn a new Project for a child from this template (parent-only). |

## timecards

| Tool | Scope | Read-only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `list_time_entries` | `mcp:read` | Yes | — | List TimeEntry rows for a user (children forced to self). |
| `get_active_entry` | `mcp:read` | Yes | — | Return the user's current active TimeEntry, or null if not clocked in. |
| `list_timecards` | `mcp:read` | Yes | — | List weekly timecards for a user (children forced to self). |
| `approve_timecard` | `mcp:write` | No | Required | Approve a weekly timecard (parent-only). |
| `clock_in` | `mcp:write` | No | — | Start a TimeEntry on a project (child self-scoped, parent on-behalf). |
| `clock_out` | `mcp:write` | No | — | End the active TimeEntry. Awards XP + coins via AwardService and fires the RPG game loop (streak, drops, quest progress). |
| `void_time_entry` | `mcp:write` | No | Required | Void a completed TimeEntry (parent-only). Status flips to ``voided``. |
| `generate_timecard` | `mcp:write` | No | — | Generate (or refresh) the weekly timecard for a child (parent-only). |
| `mark_timecard_paid` | `mcp:write` | No | Required | Mark a timecard PAID and post a negative PaymentLedger payout (parent-only). |

## users

| Tool | Scope | Read-only | Confirmation | Description |
| --- | --- | --- | --- | --- |
| `list_children` | `mcp:read` | Yes | — | Return every child user in the family (parent-only). |
| `get_user` | `mcp:read` | Yes | — | Return a user profile. Children may only look up themselves. |
| `update_child` | `mcp:write` | No | Required | Update a child's profile fields (parent-only). |

## Removed image-generation tools

AI sprite/image generation is retired. `generate_sprite_sheet`, `reroll_sprite`, `propose_sprite_reroll` and `get_sprite_prompting_playbook` are no longer registered. Prepared-image registration, catalog reads, metadata edits and deletion remain. Former REST generation/reroll POST URLs return JSON HTTP 410 to authenticated staff parents; they never call a provider.

## Verification and external data handling

Use synthetic local/staging data for tests. Do not use developer smoke scripts as production checks: only the designated trusted observer is authorized for Abby production observations. The application’s scope/permission regressions exercise transport invocation, OAuth issuance/refresh, confirmations and family boundaries. See [PR validation](operations/pr-validation.md) for required hosted checks.

An authorized MCP read transfers its result to the external client. Imported Google-derived text, shared journal/reflection data and media links can be included where the handler permits them. This server does not establish the external provider’s retention/training agreement or prove Google-specific consent. Read the [Google and AI inventory](operations/google-ai-disclosure.md) before making a verification claim.
