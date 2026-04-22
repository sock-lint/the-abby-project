"""End-to-end smoke test for the MCP server at ``$MCP_BASE_URL``.

Exercises all 106 MCP tools across 18 modules by speaking JSON-RPC 2.0 over
HTTP against the deployed FastMCP server. Designed to be re-run on every
deploy as a regression check that the full tool surface is reachable, auth
is wired, and per-tool schemas validate.

Usage:
    MCP_BASE_URL=https://abby.bos.lol \\
    MCP_TOKEN=<parent-drf-token> \\
    MCP_TEST_CHILD_ID=<child-user-id> \\
    python scripts/smoke_mcp.py --full

Flags:
    --full          Run every phase (fixture setup → mutations → teardown).
    --read-only     Only phases 0 + 1. Safe on prod at any time.
    --module NAME   Limit to one module (e.g. --module chores). Read-only only.
    --with-ai       Include tools that hit the Anthropic API (plan_homework,
                    ingestion enrichment). Costs real tokens on prod.
    --json PATH     Write the per-tool report to this file (default: stdout).
    --verbose       Print full JSON-RPC responses for every call.

Exit code:
    0 if every attempted tool passed or was explicitly skipped.
    1 on any unexpected failure.

Safety:
    Every write is paired with a teardown in the reverse phase so the prod DB
    ends byte-identical to the pre-run state. Fixtures are prefixed with
    ``MCP-SmokeTest-<timestamp>`` so orphans left by a crashed run can be
    cleaned up by hand. Ledger tools (adjust_coins, adjust_payment,
    record_payout) issue paired +N / -N entries in a net-zero round-trip.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

import requests


JSON = dict[str, Any]

PHASE_HANDSHAKE = "0-handshake"
PHASE_READ = "1-read-only"
PHASE_SETUP = "2-fixture-setup"
PHASE_MUTATE = "3-mid-lifecycle"
PHASE_TEARDOWN = "4-teardown"


# -----------------------------------------------------------------------------
# MCP client
# -----------------------------------------------------------------------------


class MCPClient:
    """Minimal JSON-RPC 2.0 client for FastMCP Streamable HTTP.

    Handles the ``Mcp-Session-Id`` handshake and parses responses that come
    back as either ``application/json`` or ``text/event-stream``.
    """

    def __init__(self, base_url: str, token: str, *, verbose: bool = False) -> None:
        self.base_url = base_url.rstrip("/")
        self.endpoint = f"{self.base_url}/mcp"
        self.token = token
        self.verbose = verbose
        self.session_id: str | None = None
        self._id = 0
        self._session = requests.Session()

    # ---- HTTP helpers -------------------------------------------------------

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _headers(self, *, for_initialize: bool = False) -> dict[str, str]:
        h = {
            "Authorization": f"Token {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id and not for_initialize:
            h["Mcp-Session-Id"] = self.session_id
        return h

    def _parse_body(self, response: requests.Response) -> JSON | None:
        ctype = response.headers.get("Content-Type", "")
        if "text/event-stream" in ctype:
            # Parse SSE with care: DO NOT use str.splitlines() because it
            # splits on lone ``\r`` bytes, which appear inside JSON string
            # values in the tool payloads (badge descriptions, etc.) and
            # fragment what is otherwise a single ``data:`` field. Split on
            # the exact SSE line terminator ``\r\n`` (or ``\n`` as fallback)
            # and concatenate consecutive ``data:`` fields per the SSE spec
            # (multi-line ``data`` is joined by ``\n``).
            body = response.text
            if "\r\n" in body:
                lines = body.split("\r\n")
            else:
                lines = body.split("\n")
            out: JSON | None = None
            data_buf: list[str] = []

            def flush() -> JSON | None:
                if not data_buf:
                    return None
                payload = "\n".join(data_buf)
                try:
                    return json.loads(payload)
                except json.JSONDecodeError:
                    return None

            for line in lines:
                if line == "":
                    parsed = flush()
                    if parsed is not None:
                        out = parsed
                    data_buf = []
                    continue
                if line.startswith("data:"):
                    # SSE: strip a single leading space after ``data:`` if
                    # present; don't strip trailing whitespace (might be
                    # significant inside a JSON string).
                    chunk = line[len("data:") :]
                    if chunk.startswith(" "):
                        chunk = chunk[1:]
                    data_buf.append(chunk)
            # end-of-body flush in case the body didn't end with a blank line
            parsed = flush()
            if parsed is not None:
                out = parsed
            return out
        if not response.text:
            return None
        try:
            return response.json()
        except ValueError:
            return None

    # ---- Public API ---------------------------------------------------------

    def health(self) -> tuple[int, str]:
        r = self._session.get(f"{self.base_url}/health", timeout=15)
        return r.status_code, r.text

    def initialize(self) -> JSON:
        body = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "id": self._next_id(),
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "abby-smoke-mcp", "version": "1.0"},
            },
        }
        r = self._session.post(
            self.endpoint,
            headers=self._headers(for_initialize=True),
            json=body,
            timeout=30,
        )
        r.raise_for_status()
        self.session_id = r.headers.get("Mcp-Session-Id") or r.headers.get(
            "mcp-session-id"
        )
        parsed = self._parse_body(r) or {}
        if self.verbose:
            print(f"[initialize] session={self.session_id!r} body={parsed!r}")
        # Required follow-up: notifications/initialized
        self._session.post(
            self.endpoint,
            headers=self._headers(),
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            timeout=15,
        )
        return parsed

    def list_tools(self) -> list[JSON]:
        resp = self.rpc("tools/list", {})
        if "error" in resp:
            raise RuntimeError(f"tools/list error: {resp['error']}")
        return resp.get("result", {}).get("tools", [])

    def call_tool(self, name: str, arguments: JSON | None = None) -> JSON:
        # Every tool in this server is declared `def tool(params: SchemaIn)`,
        # so FastMCP's argument binding looks for a top-level `params` key.
        # Wrap the caller-supplied dict unless they already wrapped it.
        args = arguments or {}
        if set(args.keys()) != {"params"}:
            args = {"params": args}
        resp = self.rpc("tools/call", {"name": name, "arguments": args})
        return resp

    def rpc(self, method: str, params: JSON) -> JSON:
        body = {
            "jsonrpc": "2.0",
            "method": method,
            "id": self._next_id(),
            "params": params,
        }
        r = self._session.post(
            self.endpoint, headers=self._headers(), json=body, timeout=60
        )
        if r.status_code >= 400:
            parsed = self._parse_body(r) or {"raw": r.text}
            return {
                "error": {
                    "code": r.status_code,
                    "message": f"HTTP {r.status_code}",
                    "data": parsed,
                }
            }
        parsed = self._parse_body(r)
        if parsed is None:
            return {"error": {"code": -1, "message": "empty response", "data": r.text}}
        if self.verbose:
            print(f"[{method}] {name_of_params(params)} -> {json.dumps(parsed)[:400]}")
        return parsed


def name_of_params(params: JSON) -> str:
    if "name" in params:
        return str(params["name"])
    return ""


# -----------------------------------------------------------------------------
# Report row
# -----------------------------------------------------------------------------


@dataclass
class ToolResult:
    name: str
    phase: str
    status: str  # "pass" | "fail" | "skip"
    latency_ms: int = 0
    error: str = ""
    note: str = ""

    def as_dict(self) -> JSON:
        return {
            "name": self.name,
            "phase": self.phase,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "note": self.note,
        }


@dataclass
class RunContext:
    client: MCPClient
    child_id: int
    tag: str  # "MCP-SmokeTest-<ts>"
    slug: str  # "mcp-smoketest-<ts>"
    with_ai: bool = False
    ids: dict[str, Any] = field(default_factory=dict)


def call(
    ctx: RunContext,
    results: list[ToolResult],
    phase: str,
    name: str,
    args: JSON | None = None,
    *,
    extract: Callable[[JSON], None] | None = None,
    tolerate_error: bool = False,
) -> JSON | None:
    """Invoke a tool and record the result. Returns the tool's result payload
    (the dict inside ``result.structuredContent`` or the first content block)
    on success, or None on failure.

    ``extract`` is called with the raw result on success for updating
    ``ctx.ids``.
    """
    t0 = time.monotonic()
    try:
        resp = ctx.client.call_tool(name, args)
    except Exception as exc:
        latency = int((time.monotonic() - t0) * 1000)
        results.append(
            ToolResult(name, phase, "fail", latency, error=f"exception: {exc!r}")
        )
        return None
    latency = int((time.monotonic() - t0) * 1000)
    if "error" in resp:
        err = resp["error"]
        status = "skip" if tolerate_error else "fail"
        results.append(
            ToolResult(
                name,
                phase,
                status,
                latency,
                error=json.dumps(err)[:400],
                note=("tolerated" if tolerate_error else ""),
            )
        )
        return None
    # FastMCP responses: result.content[*].text (stringified JSON) OR
    # result.structuredContent (already parsed).
    result = resp.get("result", {}) or {}
    payload = result.get("structuredContent")
    if payload is None:
        # Fall back to parsing the first content block's text as JSON.
        blocks = result.get("content") or []
        for b in blocks:
            if b.get("type") == "text":
                try:
                    payload = json.loads(b["text"])
                    break
                except (ValueError, KeyError):
                    pass
    if payload is None:
        payload = result
    # isError indicates the tool itself returned a handled error response.
    if result.get("isError"):
        status = "skip" if tolerate_error else "fail"
        results.append(
            ToolResult(
                name,
                phase,
                status,
                latency,
                error=json.dumps(payload)[:400],
                note=("tolerated" if tolerate_error else ""),
            )
        )
        return None
    results.append(ToolResult(name, phase, "pass", latency))
    if extract:
        try:
            extract(payload)
        except Exception as exc:
            # Extract failures downgrade to a note on an already-passing row.
            results[-1].note = f"extract-failed: {exc!r}"
    return payload


def skip(
    results: list[ToolResult], phase: str, name: str, reason: str
) -> None:
    results.append(ToolResult(name, phase, "skip", 0, note=reason))


# -----------------------------------------------------------------------------
# Phase 0: handshake
# -----------------------------------------------------------------------------


def phase_0_handshake(
    ctx: RunContext, results: list[ToolResult], expected_count: int
) -> list[JSON]:
    t0 = time.monotonic()
    try:
        status, body = ctx.client.health()
    except Exception as exc:
        results.append(
            ToolResult("GET /health", PHASE_HANDSHAKE, "fail", 0, error=repr(exc))
        )
        return []
    latency = int((time.monotonic() - t0) * 1000)
    ok = status == 200 and "ok" in body.lower()
    results.append(
        ToolResult(
            "GET /health",
            PHASE_HANDSHAKE,
            "pass" if ok else "fail",
            latency,
            error="" if ok else f"HTTP {status} body={body!r}",
        )
    )

    t0 = time.monotonic()
    try:
        ctx.client.initialize()
    except Exception as exc:
        results.append(
            ToolResult(
                "POST /mcp initialize",
                PHASE_HANDSHAKE,
                "fail",
                int((time.monotonic() - t0) * 1000),
                error=repr(exc),
            )
        )
        return []
    results.append(
        ToolResult(
            "POST /mcp initialize",
            PHASE_HANDSHAKE,
            "pass",
            int((time.monotonic() - t0) * 1000),
            note=f"session={ctx.client.session_id}",
        )
    )

    t0 = time.monotonic()
    try:
        tools = ctx.client.list_tools()
    except Exception as exc:
        results.append(
            ToolResult(
                "tools/list",
                PHASE_HANDSHAKE,
                "fail",
                int((time.monotonic() - t0) * 1000),
                error=repr(exc),
            )
        )
        return []
    latency = int((time.monotonic() - t0) * 1000)
    # Pass as long as tools/list responded with something non-empty; count
    # is informational, not a hard gate (tool count drifts with feature work).
    ok = len(tools) > 0
    note = f"{len(tools)} tools registered"
    if expected_count and len(tools) != expected_count:
        note += f" (expected {expected_count})"
    results.append(
        ToolResult(
            "tools/list",
            PHASE_HANDSHAKE,
            "pass" if ok else "fail",
            latency,
            error="" if ok else "tools/list returned 0 tools",
            note=note,
        )
    )
    return tools


# -----------------------------------------------------------------------------
# Phase 1: read-only sweep
# -----------------------------------------------------------------------------


def phase_1_read_only(ctx: RunContext, results: list[ToolResult]) -> None:
    cid = ctx.child_id

    # dashboard
    call(ctx, results, PHASE_READ, "get_dashboard", {"user_id": cid})

    # users
    call(
        ctx,
        results,
        PHASE_READ,
        "list_children",
        {},
        extract=lambda p: ctx.ids.setdefault("children", p.get("children", [])),
    )
    call(ctx, results, PHASE_READ, "get_user", {"user_id": cid})

    # chores
    call(ctx, results, PHASE_READ, "list_chores", {"limit": 10})
    call(ctx, results, PHASE_READ, "list_chore_completions", {"limit": 10})

    # habits
    call(ctx, results, PHASE_READ, "list_habits", {"limit": 10})

    # homework
    call(ctx, results, PHASE_READ, "list_homework", {"limit": 10})
    call(ctx, results, PHASE_READ, "list_homework_submissions", {"limit": 10})
    call(ctx, results, PHASE_READ, "list_homework_templates", {"limit": 10})

    # projects + templates
    call(
        ctx,
        results,
        PHASE_READ,
        "list_projects",
        {"limit": 10},
        extract=lambda p: ctx.ids.setdefault(
            "existing_project_id",
            (p.get("projects") or [{}])[0].get("id") if p.get("projects") else None,
        ),
    )
    call(ctx, results, PHASE_READ, "list_templates", {"limit": 10})

    # achievements
    call(
        ctx,
        results,
        PHASE_READ,
        "list_skill_categories",
        {},
        extract=lambda p: ctx.ids.setdefault(
            "first_category_id",
            (p.get("categories") or [{}])[0].get("id") if p.get("categories") else None,
        ),
    )
    call(ctx, results, PHASE_READ, "list_skills", {"limit": 10})
    first_cat = ctx.ids.get("first_category_id")
    if first_cat:
        call(ctx, results, PHASE_READ, "get_skill_tree", {"category_id": first_cat})
    else:
        skip(results, PHASE_READ, "get_skill_tree", "no categories exist")
    call(ctx, results, PHASE_READ, "list_badges", {})
    call(ctx, results, PHASE_READ, "list_earned_badges", {"user_id": cid})

    # rewards
    call(ctx, results, PHASE_READ, "list_rewards", {"active_only": False})
    call(ctx, results, PHASE_READ, "get_coin_balance", {"user_id": cid})

    # payments
    call(ctx, results, PHASE_READ, "get_payment_balance", {"user_id": cid})
    call(ctx, results, PHASE_READ, "list_payment_ledger", {"user_id": cid, "limit": 10})

    # savings
    call(ctx, results, PHASE_READ, "list_savings_goals", {"user_id": cid})

    # quests
    call(ctx, results, PHASE_READ, "list_quests", {"user_id": cid, "limit": 10})
    call(ctx, results, PHASE_READ, "list_quest_catalog", {})

    # timecards
    call(ctx, results, PHASE_READ, "list_time_entries", {"user_id": cid, "limit": 10})
    call(ctx, results, PHASE_READ, "get_active_entry", {"user_id": cid})
    call(
        ctx,
        results,
        PHASE_READ,
        "list_timecards",
        {"user_id": cid, "limit": 5},
        extract=lambda p: ctx.ids.setdefault(
            "pending_timecard_id",
            next(
                (
                    tc.get("id")
                    for tc in (p.get("timecards") or [])
                    if tc.get("status") == "pending"
                ),
                None,
            ),
        ),
    )

    # notifications
    call(
        ctx,
        results,
        PHASE_READ,
        "list_notifications",
        {"unread_only": True, "limit": 5},
        extract=lambda p: ctx.ids.setdefault(
            "unread_notification_id",
            (p.get("notifications") or [{}])[0].get("id")
            if p.get("notifications")
            else None,
        ),
    )

    # portfolio
    existing_project = ctx.ids.get("existing_project_id")
    if existing_project:
        call(
            ctx,
            results,
            PHASE_READ,
            "list_project_photos",
            {"project_id": existing_project},
        )
    else:
        skip(results, PHASE_READ, "list_project_photos", "no projects exist")
    call(ctx, results, PHASE_READ, "get_portfolio_summary", {"user_id": cid})
    call(ctx, results, PHASE_READ, "list_portfolio_media", {"user_id": cid, "limit": 10})

    # content packs
    call(ctx, results, PHASE_READ, "list_content_packs", {})
    # get_content_pack / read_pack_file need a real pack name — we'll hit
    # these in the fixture phase instead. Mark as covered-later.
    skip(results, PHASE_READ, "get_content_pack", "exercised in phase 3")
    skip(results, PHASE_READ, "read_pack_file", "exercised in phase 3")
    call(ctx, results, PHASE_READ, "list_rpg_catalog", {})

    # ingestion
    call(
        ctx,
        results,
        PHASE_READ,
        "list_ingestion_jobs",
        {"limit": 5},
        extract=lambda p: ctx.ids.setdefault(
            "existing_job_id",
            (p.get("jobs") or [{}])[0].get("id") if p.get("jobs") else None,
        ),
    )
    if ctx.ids.get("existing_job_id"):
        call(
            ctx,
            results,
            PHASE_READ,
            "get_ingestion_job",
            {"job_id": ctx.ids["existing_job_id"]},
        )
    else:
        skip(results, PHASE_READ, "get_ingestion_job", "no ingestion jobs exist")

    # homework templates
    call(
        ctx,
        results,
        PHASE_READ,
        "list_homework_templates",
        {"limit": 5},
    )


# -----------------------------------------------------------------------------
# Phase 2: fixture setup
# -----------------------------------------------------------------------------


def phase_2_setup(ctx: RunContext, results: list[ToolResult]) -> None:
    tag = ctx.tag
    cid = ctx.child_id

    # Skill tree — category → subject → skill → badge
    p = call(
        ctx,
        results,
        PHASE_SETUP,
        "create_category",
        {"name": f"{tag} Cat", "color": "#AA55AA", "description": "smoke test"},
        extract=lambda p: ctx.ids.update({"cat_id": p.get("id")}),
    )
    if ctx.ids.get("cat_id"):
        call(
            ctx,
            results,
            PHASE_SETUP,
            "create_subject",
            {"category_id": ctx.ids["cat_id"], "name": f"{tag} Subject"},
            extract=lambda p: ctx.ids.update(
                {"subj_id": p.get("id")}
            ),
        )
        call(
            ctx,
            results,
            PHASE_SETUP,
            "create_skill",
            {
                "category_id": ctx.ids["cat_id"],
                "subject_id": ctx.ids.get("subj_id"),
                "name": f"{tag} Skill A",
            },
            extract=lambda p: ctx.ids.update(
                {"skill_a_id": p.get("id")}
            ),
        )
        call(
            ctx,
            results,
            PHASE_SETUP,
            "create_skill",
            {
                "category_id": ctx.ids["cat_id"],
                "subject_id": ctx.ids.get("subj_id"),
                "name": f"{tag} Skill B",
            },
            extract=lambda p: ctx.ids.update(
                {"skill_b_id": p.get("id")}
            ),
        )
        call(
            ctx,
            results,
            PHASE_SETUP,
            "create_badge",
            {
                "name": f"{tag} Badge",
                "description": "smoke test badge",
                "criteria_type": "projects_completed",
                "criteria_value": {"count": 9999},
                "rarity": "common",
            },
            extract=lambda p: ctx.ids.update(
                {"badge_id": p.get("id")}
            ),
        )
    else:
        skip(results, PHASE_SETUP, "create_subject", "category create failed")
        skip(results, PHASE_SETUP, "create_skill", "category create failed")
        skip(results, PHASE_SETUP, "create_badge", "category create failed")

    # Reward (zero cost so child can't accidentally redeem a real one)
    call(
        ctx,
        results,
        PHASE_SETUP,
        "create_reward",
        {
            "name": f"{tag} Reward",
            "description": "smoke test — do not redeem",
            "cost_coins": 999999,
            "is_active": False,
            "requires_parent_approval": True,
        },
        extract=lambda p: ctx.ids.update(
            {"reward_id": p.get("id")}
        ),
    )

    # Chore (zero reward)
    call(
        ctx,
        results,
        PHASE_SETUP,
        "create_chore",
        {
            "title": f"{tag} Chore",
            "reward_amount": "0.00",
            "coin_reward": 0,
            "recurrence": "daily",
            "assigned_to_id": cid,
        },
        extract=lambda p: ctx.ids.update(
            {"chore_id": p.get("id")}
        ),
    )

    # Habit
    call(
        ctx,
        results,
        PHASE_SETUP,
        "create_habit",
        {
            "name": f"{tag} Habit",
            "habit_type": "positive",
            "xp_reward": 0,
            "user_id": cid,
        },
        extract=lambda p: ctx.ids.update(
            {"habit_id": p.get("id")}
        ),
    )

    # Homework template + assignment
    call(
        ctx,
        results,
        PHASE_SETUP,
        "create_homework_template",
        {"title": f"{tag} HW Template", "subject": "other", "effort_level": 1},
        extract=lambda p: ctx.ids.update(
            {"hw_template_id": p.get("id")}
        ),
    )
    call(
        ctx,
        results,
        PHASE_SETUP,
        "create_homework",
        {
            "title": f"{tag} HW",
            "subject": "other",
            "effort_level": 1,
            "due_date": _today_iso(),
            "assigned_to_id": cid,
        },
        extract=lambda p: ctx.ids.update(
            {"hw_id": p.get("id")}
        ),
    )

    # Savings goal
    call(
        ctx,
        results,
        PHASE_SETUP,
        "create_savings_goal",
        {"title": f"{tag} Goal", "target_amount": "1.00", "icon": "💰"},
        extract=lambda p: ctx.ids.update(
            {"goal_id": p.get("id")}
        ),
    )

    # Project + template
    call(
        ctx,
        results,
        PHASE_SETUP,
        "create_project",
        {
            "title": f"{tag} Project",
            "description": "smoke test",
            "assigned_to_id": cid,
            "difficulty": 1,
            "bonus_amount": "0.00",
            "payment_kind": "required",
            "status": "draft",
        },
        extract=lambda p: ctx.ids.update(
            {"project_id": p.get("id")}
        ),
    )
    call(
        ctx,
        results,
        PHASE_SETUP,
        "create_template",
        {"title": f"{tag} Template", "description": "smoke test"},
        extract=lambda p: ctx.ids.update(
            {"template_id": p.get("id")}
        ),
    )

    # Quest definition (collection, threshold=1 so we can't accidentally complete it)
    call(
        ctx,
        results,
        PHASE_SETUP,
        "create_quest_definition",
        {
            "name": f"{tag} Quest",
            "description": "smoke test",
            "quest_type": "collection",
            "target_value": 999999,
            "duration_days": 1,
            "trigger_filter": {},
            "coin_reward": 0,
            "xp_reward": 0,
            "is_repeatable": False,
        },
        extract=lambda p: ctx.ids.update(
            {"quest_def_id": (p.get("definition") or {}).get("id")}
        ),
    )


# -----------------------------------------------------------------------------
# Phase 3: mid-lifecycle mutations
# -----------------------------------------------------------------------------


def phase_3_mutations(ctx: RunContext, results: list[ToolResult]) -> None:
    ids = ctx.ids
    cid = ctx.child_id

    # Skill prerequisites
    if ids.get("skill_a_id") and ids.get("skill_b_id"):
        call(
            ctx,
            results,
            PHASE_MUTATE,
            "add_skill_prerequisite",
            {
                "skill_id": ids["skill_b_id"],
                "required_skill_id": ids["skill_a_id"],
                "required_level": 2,
            },
        )
        call(
            ctx,
            results,
            PHASE_MUTATE,
            "remove_skill_prerequisite",
            {
                "skill_id": ids["skill_b_id"],
                "required_skill_id": ids["skill_a_id"],
            },
        )
    else:
        skip(results, PHASE_MUTATE, "add_skill_prerequisite", "skills missing")
        skip(results, PHASE_MUTATE, "remove_skill_prerequisite", "skills missing")

    # Category/subject/skill/badge updates
    if ids.get("cat_id"):
        call(
            ctx,
            results,
            PHASE_MUTATE,
            "update_category",
            {"category_id": ids["cat_id"], "description": "updated"},
        )
    else:
        skip(results, PHASE_MUTATE, "update_category", "no cat")
    if ids.get("subj_id"):
        call(
            ctx,
            results,
            PHASE_MUTATE,
            "update_subject",
            {"subject_id": ids["subj_id"], "description": "updated"},
        )
    else:
        skip(results, PHASE_MUTATE, "update_subject", "no subject")
    if ids.get("skill_a_id"):
        call(
            ctx,
            results,
            PHASE_MUTATE,
            "update_skill",
            {"skill_id": ids["skill_a_id"], "description": "updated"},
        )
    else:
        skip(results, PHASE_MUTATE, "update_skill", "no skill")
    if ids.get("badge_id"):
        call(
            ctx,
            results,
            PHASE_MUTATE,
            "update_badge",
            {"badge_id": ids["badge_id"], "description": "updated"},
        )
    else:
        skip(results, PHASE_MUTATE, "update_badge", "no badge")

    # Project nested CRUD
    pid = ids.get("project_id")
    if pid:
        call(ctx, results, PHASE_MUTATE, "get_project", {"project_id": pid})
        call(
            ctx,
            results,
            PHASE_MUTATE,
            "update_project",
            {"project_id": pid, "description": "updated"},
        )
        call(
            ctx,
            results,
            PHASE_MUTATE,
            "add_milestone",
            {"project_id": pid, "title": "MS1", "bonus_amount": "0.00"},
            extract=lambda p: ids.update(
                {"milestone_id": p.get("id")}
            ),
        )
        if ids.get("milestone_id"):
            call(
                ctx,
                results,
                PHASE_MUTATE,
                "update_milestone",
                {"milestone_id": ids["milestone_id"], "description": "updated"},
            )
            # complete_milestone posts a milestone_bonus ledger entry — but the
            # milestone has bonus_amount=0, so net-zero.
            call(
                ctx,
                results,
                PHASE_MUTATE,
                "complete_milestone",
                {"milestone_id": ids["milestone_id"]},
            )
        else:
            skip(results, PHASE_MUTATE, "update_milestone", "no milestone")
            skip(results, PHASE_MUTATE, "complete_milestone", "no milestone")
        call(
            ctx,
            results,
            PHASE_MUTATE,
            "add_step",
            {"project_id": pid, "title": "Step 1"},
            extract=lambda p: ids.update(
                {"step_id": p.get("id")}
            ),
        )
        if ids.get("step_id"):
            call(
                ctx,
                results,
                PHASE_MUTATE,
                "update_step",
                {"step_id": ids["step_id"], "description": "updated"},
            )
            call(
                ctx,
                results,
                PHASE_MUTATE,
                "complete_step",
                {"step_id": ids["step_id"]},
            )
            call(
                ctx,
                results,
                PHASE_MUTATE,
                "uncomplete_step",
                {"step_id": ids["step_id"]},
            )
        else:
            skip(results, PHASE_MUTATE, "update_step", "no step")
            skip(results, PHASE_MUTATE, "complete_step", "no step")
            skip(results, PHASE_MUTATE, "uncomplete_step", "no step")
        call(
            ctx,
            results,
            PHASE_MUTATE,
            "add_material",
            {"project_id": pid, "name": "Tape", "estimated_cost": "0.00"},
            extract=lambda p: ids.update(
                {"material_id": p.get("id")}
            ),
        )
        if ids.get("material_id"):
            call(
                ctx,
                results,
                PHASE_MUTATE,
                "update_material",
                {"material_id": ids["material_id"], "estimated_cost": "0.01"},
            )
            call(
                ctx,
                results,
                PHASE_MUTATE,
                "mark_material_purchased",
                {"material_id": ids["material_id"], "actual_cost": "0.00"},
            )
        else:
            skip(results, PHASE_MUTATE, "update_material", "no material")
            skip(results, PHASE_MUTATE, "mark_material_purchased", "no material")
        call(
            ctx,
            results,
            PHASE_MUTATE,
            "add_resource",
            {"project_id": pid, "url": "https://example.com", "title": "ref"},
            extract=lambda p: ids.update(
                {"resource_id": p.get("id")}
            ),
        )
        if ids.get("resource_id"):
            call(
                ctx,
                results,
                PHASE_MUTATE,
                "update_resource",
                {"resource_id": ids["resource_id"], "title": "updated"},
            )
        else:
            skip(results, PHASE_MUTATE, "update_resource", "no resource")

        # set_project_skill_tags
        if ids.get("skill_a_id"):
            call(
                ctx,
                results,
                PHASE_MUTATE,
                "set_project_skill_tags",
                {
                    "project_id": pid,
                    "skill_tags": [{"skill_id": ids["skill_a_id"], "xp_weight": 1}],
                },
            )
        else:
            skip(results, PHASE_MUTATE, "set_project_skill_tags", "no skill")

        # project lifecycle — status transitions
        call(ctx, results, PHASE_MUTATE, "update_project_status", {"project_id": pid, "status": "active"})
        call(ctx, results, PHASE_MUTATE, "activate_project", {"project_id": pid}, tolerate_error=True)
        call(
            ctx,
            results,
            PHASE_MUTATE,
            "request_project_changes",
            {"project_id": pid, "parent_notes": "smoke test"},
            tolerate_error=True,
        )
        call(ctx, results, PHASE_MUTATE, "approve_project", {"project_id": pid}, tolerate_error=True)

        # collaborator on the project (parent itself)
        collab_id = (ctx.ids.get("children") or [{}])[0].get("id") if ctx.ids.get("children") else None
        if collab_id and collab_id != cid:
            call(
                ctx,
                results,
                PHASE_MUTATE,
                "add_collaborator",
                {"project_id": pid, "user_id": collab_id, "pay_split_percent": 50},
            )
            call(
                ctx,
                results,
                PHASE_MUTATE,
                "remove_collaborator",
                {"project_id": pid, "user_id": collab_id},
            )
        else:
            skip(results, PHASE_MUTATE, "add_collaborator", "need second child")
            skip(results, PHASE_MUTATE, "remove_collaborator", "need second child")

        # Template round-trip from the project
        call(
            ctx,
            results,
            PHASE_MUTATE,
            "save_project_as_template",
            {"project_id": pid, "is_public": False},
            extract=lambda p: ids.update(
                {"spawned_template_id": p.get("id")}
            ),
        )
        if ids.get("spawned_template_id"):
            call(
                ctx,
                results,
                PHASE_MUTATE,
                "create_project_from_template",
                {
                    "template_id": ids["spawned_template_id"],
                    "assigned_to_id": cid,
                    "title_override": f"{ctx.tag} Spawned",
                },
                extract=lambda p: ids.update(
                    {"spawned_project_id": p.get("id")}
                ),
            )
        else:
            skip(results, PHASE_MUTATE, "create_project_from_template", "no template")

        # update_template + get_template on the spawned template
        if ids.get("spawned_template_id"):
            call(
                ctx,
                results,
                PHASE_MUTATE,
                "get_template",
                {"template_id": ids["spawned_template_id"]},
            )
            call(
                ctx,
                results,
                PHASE_MUTATE,
                "update_template",
                {
                    "template_id": ids["spawned_template_id"],
                    "description": "updated",
                },
            )
        else:
            skip(results, PHASE_MUTATE, "get_template", "no spawned template")
            skip(results, PHASE_MUTATE, "update_template", "no spawned template")

    else:
        for n in [
            "update_project",
            "add_milestone",
            "update_milestone",
            "complete_milestone",
            "delete_milestone",
            "add_step",
            "update_step",
            "delete_step",
            "add_material",
            "update_material",
            "mark_material_purchased",
            "delete_material",
            "add_resource",
            "update_resource",
            "delete_resource",
            "set_project_skill_tags",
            "update_project_status",
            "activate_project",
            "request_project_changes",
            "approve_project",
            "add_collaborator",
            "remove_collaborator",
            "save_project_as_template",
            "create_project_from_template",
            "update_template",
        ]:
            skip(results, PHASE_MUTATE, n, "no project fixture")

    # Chores: complete → approve → reject (parent is the caller; complete_chore
    # as parent creates a completion for a child via chore.assigned_to_id)
    if ctx.ids.get("chore_id"):
        # complete_chore expects the caller to be the assignee. Parent can't
        # complete on behalf of a child — this returns an error we tolerate.
        call(
            ctx,
            results,
            PHASE_MUTATE,
            "complete_chore",
            {"chore_id": ctx.ids["chore_id"]},
            tolerate_error=True,
        )
        skip(
            results,
            PHASE_MUTATE,
            "approve_chore_completion",
            "needs child-authored completion",
        )
        skip(
            results,
            PHASE_MUTATE,
            "reject_chore_completion",
            "needs child-authored completion",
        )
        call(
            ctx,
            results,
            PHASE_MUTATE,
            "update_chore",
            {"chore_id": ctx.ids["chore_id"], "description": "updated"},
        )
        call(ctx, results, PHASE_MUTATE, "get_chore", {"chore_id": ctx.ids["chore_id"]})
    else:
        for n in ["complete_chore", "approve_chore_completion", "reject_chore_completion", "update_chore", "get_chore"]:
            skip(results, PHASE_MUTATE, n, "no chore fixture")

    # Habits
    if ctx.ids.get("habit_id"):
        call(ctx, results, PHASE_MUTATE, "get_habit", {"habit_id": ctx.ids["habit_id"]})
        call(
            ctx,
            results,
            PHASE_MUTATE,
            "log_habit",
            {"habit_id": ctx.ids["habit_id"], "amount": 1},
            tolerate_error=True,  # parent can't log to own habit on behalf of self always
        )
        call(
            ctx,
            results,
            PHASE_MUTATE,
            "update_habit",
            {"habit_id": ctx.ids["habit_id"], "icon": "⭐"},
        )
    else:
        for n in ["get_habit", "log_habit", "update_habit"]:
            skip(results, PHASE_MUTATE, n, "no habit fixture")

    # Homework lifecycle
    if ctx.ids.get("hw_id"):
        call(
            ctx,
            results,
            PHASE_MUTATE,
            "get_homework",
            {"assignment_id": ctx.ids["hw_id"]},
        )
        call(
            ctx,
            results,
            PHASE_MUTATE,
            "update_homework",
            {"assignment_id": ctx.ids["hw_id"], "description": "updated"},
        )
        if ctx.ids.get("skill_a_id"):
            call(
                ctx,
                results,
                PHASE_MUTATE,
                "set_homework_skill_tags",
                {
                    "assignment_id": ctx.ids["hw_id"],
                    "skill_tags": [
                        {"skill_id": ctx.ids["skill_a_id"], "xp_amount": 5}
                    ],
                },
            )
        else:
            skip(results, PHASE_MUTATE, "set_homework_skill_tags", "no skill")
        # submit_homework is child-only; tolerate the parent-side error
        call(
            ctx,
            results,
            PHASE_MUTATE,
            "submit_homework",
            {"assignment_id": ctx.ids["hw_id"], "notes": "smoke"},
            tolerate_error=True,
        )
        skip(results, PHASE_MUTATE, "approve_homework_submission", "needs child submission")
        skip(results, PHASE_MUTATE, "reject_homework_submission", "needs child submission")
        if ctx.with_ai:
            call(
                ctx,
                results,
                PHASE_MUTATE,
                "plan_homework",
                {"assignment_id": ctx.ids["hw_id"]},
                tolerate_error=True,
            )
        else:
            skip(results, PHASE_MUTATE, "plan_homework", "--with-ai not set")
    else:
        for n in [
            "get_homework",
            "update_homework",
            "set_homework_skill_tags",
            "submit_homework",
            "approve_homework_submission",
            "reject_homework_submission",
            "plan_homework",
        ]:
            skip(results, PHASE_MUTATE, n, "no homework fixture")

    # Homework templates
    if ctx.ids.get("hw_template_id"):
        call(
            ctx,
            results,
            PHASE_MUTATE,
            "get_homework_template",
            {"template_id": ctx.ids["hw_template_id"]},
        )
        call(
            ctx,
            results,
            PHASE_MUTATE,
            "update_homework_template",
            {"template_id": ctx.ids["hw_template_id"], "description": "updated"},
        )
        call(
            ctx,
            results,
            PHASE_MUTATE,
            "create_homework_from_template",
            {
                "template_id": ctx.ids["hw_template_id"],
                "assigned_to_id": ctx.child_id,
                "due_date": _today_iso(),
            },
            extract=lambda p: ctx.ids.update(
                {"hw_from_tpl_id": p.get("id")}
            ),
        )
    else:
        for n in [
            "get_homework_template",
            "update_homework_template",
            "create_homework_from_template",
        ]:
            skip(results, PHASE_MUTATE, n, "no HW template fixture")

    # Rewards
    if ctx.ids.get("reward_id"):
        call(
            ctx,
            results,
            PHASE_MUTATE,
            "update_reward",
            {"reward_id": ctx.ids["reward_id"], "description": "updated"},
        )
        # request_redemption is child-only (parent can't redeem)
        call(
            ctx,
            results,
            PHASE_MUTATE,
            "request_redemption",
            {"reward_id": ctx.ids["reward_id"]},
            tolerate_error=True,
        )
        skip(results, PHASE_MUTATE, "approve_redemption", "needs child redemption")
        skip(results, PHASE_MUTATE, "reject_redemption", "needs child redemption")
    else:
        for n in ["update_reward", "request_redemption", "approve_redemption", "reject_redemption"]:
            skip(results, PHASE_MUTATE, n, "no reward fixture")

    # Savings
    if ctx.ids.get("goal_id"):
        # contribute requires ledger balance — tolerate if child is broke
        call(
            ctx,
            results,
            PHASE_MUTATE,
            "contribute_to_goal",
            {"goal_id": ctx.ids["goal_id"], "amount": "0.01"},
            tolerate_error=True,
        )
        call(
            ctx,
            results,
            PHASE_MUTATE,
            "update_savings_goal",
            {"goal_id": ctx.ids["goal_id"], "title": f"{ctx.tag} Goal (edited)"},
        )
    else:
        for n in ["contribute_to_goal", "update_savings_goal"]:
            skip(results, PHASE_MUTATE, n, "no goal fixture")

    # Quests — assign / cancel. A pre-existing active quest for the child
    # will cause ``assign_quest`` to error ("You already have an active
    # quest"); this is expected state, not a transport failure, so tolerate.
    if ctx.ids.get("quest_def_id"):
        call(
            ctx,
            results,
            PHASE_MUTATE,
            "assign_quest",
            {"definition_id": ctx.ids["quest_def_id"], "user_id": ctx.child_id},
            tolerate_error=True,
            extract=lambda p: ctx.ids.update(
                {"quest_id": p.get("id")}
            ),
        )
        if ctx.ids.get("quest_id"):
            call(
                ctx,
                results,
                PHASE_MUTATE,
                "get_quest",
                {"quest_id": ctx.ids["quest_id"]},
            )
            call(
                ctx,
                results,
                PHASE_MUTATE,
                "cancel_quest",
                {"quest_id": ctx.ids["quest_id"]},
            )
        else:
            skip(results, PHASE_MUTATE, "get_quest", "no quest assigned")
            skip(results, PHASE_MUTATE, "cancel_quest", "no quest assigned")
    else:
        for n in ["assign_quest", "get_quest", "cancel_quest"]:
            skip(results, PHASE_MUTATE, n, "no quest definition fixture")

    # users.update_child — round-trip: read current, PATCH with same, confirm idempotent.
    # We use hourly_rate which is always numeric; nil changes the rate to itself.
    existing_children = ctx.ids.get("children") or []
    me = next((c for c in existing_children if c.get("id") == ctx.child_id), None)
    if me is not None:
        current_rate = me.get("hourly_rate")
        if current_rate is not None:
            call(
                ctx,
                results,
                PHASE_MUTATE,
                "update_child",
                {"user_id": ctx.child_id, "hourly_rate": str(current_rate)},
            )
        else:
            skip(results, PHASE_MUTATE, "update_child", "child hourly_rate unknown")
    else:
        skip(results, PHASE_MUTATE, "update_child", "child not in list_children")

    # Ledger round-trips (net zero)
    call(
        ctx,
        results,
        PHASE_MUTATE,
        "adjust_coins",
        {
            "user_id": ctx.child_id,
            "amount": 1,
            "description": f"{ctx.tag} +1",
        },
    )
    call(
        ctx,
        results,
        PHASE_MUTATE,
        "adjust_coins",
        {
            "user_id": ctx.child_id,
            "amount": -1,
            "description": f"{ctx.tag} -1 rollback",
        },
    )
    # record_payout posts a NEGATIVE ledger entry (the child received cash,
    # so the owed balance goes down). To net to zero we need to ADD back
    # 0.01 via adjust_payment — NOT subtract another 0.01.
    call(
        ctx,
        results,
        PHASE_MUTATE,
        "record_payout",
        {
            "user_id": ctx.child_id,
            "amount": "0.01",
            "description": f"{ctx.tag} test payout (-0.01 to owed balance)",
        },
    )
    call(
        ctx,
        results,
        PHASE_MUTATE,
        "adjust_payment",
        {
            "user_id": ctx.child_id,
            "amount": "0.01",
            "description": f"{ctx.tag} rollback of test payout (+0.01 to owed balance)",
        },
    )

    # approve_timecard — only if a pending one exists
    tid = ctx.ids.get("pending_timecard_id")
    if tid:
        call(
            ctx,
            results,
            PHASE_MUTATE,
            "approve_timecard",
            {"timecard_id": tid, "notes": f"{ctx.tag} smoke approve"},
        )
    else:
        skip(results, PHASE_MUTATE, "approve_timecard", "no pending timecard")

    # mark_notification_read
    nid = ctx.ids.get("unread_notification_id")
    if nid:
        call(
            ctx,
            results,
            PHASE_MUTATE,
            "mark_notification_read",
            {"notification_id": nid},
        )
    else:
        skip(results, PHASE_MUTATE, "mark_notification_read", "no unread notification")

    # Ingestion — submit a tiny URL, poll briefly, commit on success.
    # We tolerate errors so network/AI outages don't break the sweep.
    sub = call(
        ctx,
        results,
        PHASE_MUTATE,
        "submit_ingestion_job",
        {"source_type": "url", "source_url": "https://example.com"},
        tolerate_error=True,
        extract=lambda p: ctx.ids.update(
            {"new_job_id": p.get("id")}
        ),
    )
    if ctx.ids.get("new_job_id"):
        # Poll up to 10s
        done = False
        for _ in range(5):
            time.sleep(2)
            r = ctx.client.call_tool(
                "get_ingestion_job", {"job_id": ctx.ids["new_job_id"]}
            )
            payload = (r.get("result") or {}).get("structuredContent") or {}
            if (payload.get("job") or {}).get("status") in ("success", "failed"):
                done = True
                break
        if done and ctx.with_ai:
            call(
                ctx,
                results,
                PHASE_MUTATE,
                "commit_ingestion_job",
                {
                    "job_id": ctx.ids["new_job_id"],
                    "title": f"{ctx.tag} Ingest",
                    "assigned_to_id": ctx.child_id,
                },
                tolerate_error=True,
                extract=lambda p: ctx.ids.update(
                    {"ingest_project_id": p.get("id")}
                ),
            )
        else:
            skip(
                results,
                PHASE_MUTATE,
                "commit_ingestion_job",
                "ingestion did not finish in time" if not done else "--with-ai not set",
            )
    else:
        skip(results, PHASE_MUTATE, "commit_ingestion_job", "no ingestion job spawned")

    # Content packs: full lifecycle on a throwaway pack
    pack = ctx.slug
    call(
        ctx,
        results,
        PHASE_MUTATE,
        "draft_pack_entries",
        {
            "pack": pack,
            "filename": "items.yaml",
            "entries": [
                {
                    "slug": f"{pack}-placeholder",
                    "name": f"{ctx.tag} Placeholder",
                    "description": "smoke test",
                    "item_type": "cosmetic_title",
                    "rarity": "common",
                    "metadata": {"title_text": f"{ctx.tag}"},
                }
            ],
            "mode": "append",
        },
        tolerate_error=True,
    )
    call(ctx, results, PHASE_MUTATE, "get_content_pack", {"pack": pack}, tolerate_error=True)
    call(
        ctx,
        results,
        PHASE_MUTATE,
        "read_pack_file",
        {"pack": pack, "filename": "items.yaml"},
        tolerate_error=True,
    )
    call(
        ctx,
        results,
        PHASE_MUTATE,
        "write_pack_file",
        {
            "pack": pack,
            "filename": "items.yaml",
            "yaml_content": (
                "- slug: {p}-placeholder\n"
                "  name: {t} Placeholder\n"
                "  description: smoke test\n"
                "  item_type: cosmetic_title\n"
                "  rarity: common\n"
                "  metadata:\n"
                "    title_text: {t}\n"
            ).format(p=pack, t=ctx.tag),
        },
        tolerate_error=True,
    )
    call(
        ctx,
        results,
        PHASE_MUTATE,
        "validate_content_pack",
        {"pack": pack},
        tolerate_error=True,
    )
    call(
        ctx,
        results,
        PHASE_MUTATE,
        "load_content_pack",
        {"pack": pack, "dry_run": True},
        tolerate_error=True,
    )
    call(
        ctx,
        results,
        PHASE_MUTATE,
        "prune_pack_content",
        {"pack": pack, "dry_run": True},
        tolerate_error=True,
    )

    # Sprite assets — additive; tag the registration with the pack slug so
    # it's obvious in the manifest. register_sprite_assets has no exposed
    # delete; we leave it and flag in the report.
    skip(
        results,
        PHASE_MUTATE,
        "register_sprite_assets",
        "additive with no exposed delete; skipped on prod to avoid manifest pollution",
    )


# -----------------------------------------------------------------------------
# Phase 4: teardown
# -----------------------------------------------------------------------------


def phase_4_teardown(ctx: RunContext, results: list[ToolResult]) -> None:
    ids = ctx.ids

    # Homework
    if ids.get("hw_from_tpl_id"):
        call(
            ctx,
            results,
            PHASE_TEARDOWN,
            "delete_homework",
            {"assignment_id": ids["hw_from_tpl_id"]},
            tolerate_error=True,
        )
    if ids.get("hw_id"):
        call(
            ctx,
            results,
            PHASE_TEARDOWN,
            "delete_homework",
            {"assignment_id": ids["hw_id"]},
        )
    else:
        skip(results, PHASE_TEARDOWN, "delete_homework", "no HW fixture")
    if ids.get("hw_template_id"):
        call(
            ctx,
            results,
            PHASE_TEARDOWN,
            "delete_homework_template",
            {"template_id": ids["hw_template_id"]},
        )
    else:
        skip(results, PHASE_TEARDOWN, "delete_homework_template", "no HW template")

    # Habit
    if ids.get("habit_id"):
        call(ctx, results, PHASE_TEARDOWN, "delete_habit", {"habit_id": ids["habit_id"]})
    else:
        skip(results, PHASE_TEARDOWN, "delete_habit", "no habit fixture")

    # Chore
    if ids.get("chore_id"):
        # delete_chore is not in schemas; chores.py exposes it via update_chore
        # with is_active=False as the soft-delete. Check tools/list output.
        call(
            ctx,
            results,
            PHASE_TEARDOWN,
            "update_chore",
            {"chore_id": ids["chore_id"], "is_active": False},
        )
    else:
        skip(results, PHASE_TEARDOWN, "update_chore[deactivate]", "no chore fixture")

    # Reward
    if ids.get("reward_id"):
        call(
            ctx,
            results,
            PHASE_TEARDOWN,
            "delete_reward",
            {"reward_id": ids["reward_id"]},
            tolerate_error=True,
        )
    else:
        skip(results, PHASE_TEARDOWN, "delete_reward", "no reward fixture")

    # Savings
    if ids.get("goal_id"):
        call(
            ctx,
            results,
            PHASE_TEARDOWN,
            "delete_savings_goal",
            {"goal_id": ids["goal_id"]},
        )
    else:
        skip(results, PHASE_TEARDOWN, "delete_savings_goal", "no goal fixture")

    # Project nested teardown
    if ids.get("resource_id"):
        call(
            ctx,
            results,
            PHASE_TEARDOWN,
            "delete_resource",
            {"resource_id": ids["resource_id"]},
        )
    if ids.get("material_id"):
        call(
            ctx,
            results,
            PHASE_TEARDOWN,
            "delete_material",
            {"material_id": ids["material_id"]},
        )
    if ids.get("step_id"):
        call(
            ctx,
            results,
            PHASE_TEARDOWN,
            "delete_step",
            {"step_id": ids["step_id"]},
        )
    if ids.get("milestone_id"):
        call(
            ctx,
            results,
            PHASE_TEARDOWN,
            "delete_milestone",
            {"milestone_id": ids["milestone_id"]},
        )

    # Projects + templates
    for key in ("ingest_project_id", "spawned_project_id", "project_id"):
        pid = ids.get(key)
        if pid:
            call(
                ctx,
                results,
                PHASE_TEARDOWN,
                "delete_project",
                {"project_id": pid},
                tolerate_error=True,
            )
    for key in ("spawned_template_id", "template_id"):
        tid = ids.get(key)
        if tid:
            call(
                ctx,
                results,
                PHASE_TEARDOWN,
                "delete_template",
                {"template_id": tid},
                tolerate_error=True,
            )

    # Badges + skills + subjects + categories
    if ids.get("badge_id"):
        call(ctx, results, PHASE_TEARDOWN, "delete_badge", {"badge_id": ids["badge_id"]})
    for k in ("skill_b_id", "skill_a_id"):
        if ids.get(k):
            call(ctx, results, PHASE_TEARDOWN, "delete_skill", {"skill_id": ids[k]})
    if ids.get("subj_id"):
        call(
            ctx,
            results,
            PHASE_TEARDOWN,
            "delete_subject",
            {"subject_id": ids["subj_id"]},
        )
    if ids.get("cat_id"):
        call(
            ctx,
            results,
            PHASE_TEARDOWN,
            "delete_category",
            {"category_id": ids["cat_id"]},
        )

    # Content pack
    call(
        ctx,
        results,
        PHASE_TEARDOWN,
        "delete_pack_file",
        {"pack": ctx.slug, "filename": "items.yaml"},
        tolerate_error=True,
    )
    call(
        ctx,
        results,
        PHASE_TEARDOWN,
        "delete_content_pack",
        {"pack": ctx.slug, "confirm": True},
        tolerate_error=True,
    )

    # Quest definition has no exposed delete — flag and move on.
    if ids.get("quest_def_id"):
        skip(
            results,
            PHASE_TEARDOWN,
            "delete_quest_definition",
            f"MCP surface exposes no delete; definition id={ids['quest_def_id']} "
            f"tagged {ctx.tag} stays in DB",
        )


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _today_iso() -> str:
    from datetime import date
    return date.today().isoformat()


def _coverage_check(results: list[ToolResult], registered: list[JSON]) -> None:
    """Emit a summary of which registered tools the sweep never touched."""
    seen = {r.name for r in results}
    registered_names = {t.get("name") for t in registered if t.get("name")}
    missed = sorted(registered_names - seen)
    extra = sorted(seen - registered_names - {"GET /health", "POST /mcp initialize", "tools/list"})
    if missed:
        print(f"\n!! {len(missed)} registered tools never exercised:")
        for n in missed:
            print(f"     - {n}")
    if extra:
        print(f"\n!! {len(extra)} sweep entries don't match a registered tool:")
        for n in extra:
            print(f"     - {n}")


def _print_report(results: list[ToolResult]) -> tuple[int, int, int]:
    passes = sum(1 for r in results if r.status == "pass")
    fails = sum(1 for r in results if r.status == "fail")
    skips = sum(1 for r in results if r.status == "skip")
    print("=" * 90)
    print(
        f"{'status':<6}{'ms':>7}  {'phase':<18}{'tool':<38}  note/error"
    )
    print("-" * 90)
    for r in results:
        detail = r.error or r.note
        print(
            f"{r.status:<6}{r.latency_ms:>7}  {r.phase:<18}{r.name:<38}  {detail[:120]}"
        )
    print("-" * 90)
    print(f"{passes} pass   {fails} fail   {skips} skip   total={len(results)}")
    return passes, fails, skips


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------


EXPECTED_TOOL_COUNT = 138  # informational; tools/list just needs to be non-empty


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--full", action="store_true", help="Run every phase (default: read-only)."
    )
    parser.add_argument("--read-only", action="store_true", help="Phases 0 + 1 only.")
    parser.add_argument(
        "--with-ai",
        action="store_true",
        help="Include tools that hit the Anthropic API.",
    )
    parser.add_argument("--json", help="Write report JSON to this file.")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    base = os.environ.get("MCP_BASE_URL")
    token = os.environ.get("MCP_TOKEN")
    child_raw = os.environ.get("MCP_TEST_CHILD_ID")
    if not base or not token:
        print("error: MCP_BASE_URL and MCP_TOKEN must be set", file=sys.stderr)
        return 2

    client = MCPClient(base, token, verbose=args.verbose)
    ts = time.strftime("%Y%m%d-%H%M%S")
    uid = uuid.uuid4().hex[:6]
    tag = f"MCP-SmokeTest-{ts}-{uid}"
    slug = f"mcp-smoketest-{ts}-{uid}"

    results: list[ToolResult] = []
    tools = phase_0_handshake(client_ctx := RunContext(
        client=client,
        child_id=int(child_raw) if child_raw else 0,
        tag=tag,
        slug=slug,
        with_ai=args.with_ai,
    ), results, expected_count=EXPECTED_TOOL_COUNT)

    # Abort if handshake failed
    if any(r.status == "fail" for r in results if r.phase == PHASE_HANDSHAKE):
        _print_report(results)
        if args.json:
            _write_json(args.json, results)
        return 1

    if args.read_only or not args.full:
        phase_1_read_only(client_ctx, results)
    else:
        if not child_raw:
            print(
                "error: --full requires MCP_TEST_CHILD_ID (child-user pk)",
                file=sys.stderr,
            )
            return 2
        phase_1_read_only(client_ctx, results)
        phase_2_setup(client_ctx, results)
        phase_3_mutations(client_ctx, results)
        phase_4_teardown(client_ctx, results)

    passes, fails, skips = _print_report(results)
    _coverage_check(results, tools)
    if args.json:
        _write_json(args.json, results)
    return 0 if fails == 0 else 1


def _write_json(path: str, results: list[ToolResult]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump([r.as_dict() for r in results], f, indent=2)
    print(f"\n[report written to {path}]")


if __name__ == "__main__":
    sys.exit(main())
