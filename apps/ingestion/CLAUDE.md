# apps/ingestion/

Scrapy-style pipeline for ingesting Instructables / generic-URL / PDF project sources into staged drafts. AI enrichment is opt-in and never mutates source fields automatically.

## Models
- `ProjectIngestionJob` — UUID pk, db_table preserved as `projects_projectingestionjob`. Tracks status + result JSON.

## Pipeline (`apps/ingestion/pipeline/`)

Stages assembled by `default_pipeline()` in `pipeline.py` and executed from `runner.py` (which `apps.ingestion.tasks.run_ingestion_job` calls).

Default stages: `ParseStage → NormalizeStage → MarkdownStage → EnrichStage`.

`detect.route_source` picks the per-source ingestor (`instructables.py`, `pdf.py`, `generic_url.py`) which becomes the `ParseStage`.

`IngestionItem` (alias of `IngestionResult`) carries additive `raw_html`, `markdown`, `ai_suggestions`, `pipeline_warnings` fields — `result_json` shape is additive-only so the frontend poller is unchanged.

Instructables scrapes cached in Redis 24h via `fetch_cached()`.

## Endpoints
- `ProjectIngestViewSet` at `/api/projects/ingest/` — async job kickoff + status polling.
- Commit endpoint resolves `ResourceDraft.step_index` (0-based) to real `ProjectStep` FKs after creating the steps.

## Frontend preview

`frontend/src/pages/ProjectIngest.jsx` lets parents author **Milestones** (chapters) above **Steps** (tasks) before commit. Each step row carries a milestone dropdown that writes `milestone_index` (0-based) into the staged payload; deleting a milestone shifts every step's `milestone_index` down so post-commit FKs don't dangle. The commit endpoint silently falls back to `milestone=None` when an index is out of range — never 500.

## Gotchas

- **Ingestion pipeline** (`apps/ingestion/pipeline/`): Scrapy-style `Pipeline` of ordered `Stage`s assembled by `default_pipeline()` in `pipeline.py` and executed from `runner.py` (which `apps.ingestion.tasks.run_ingestion_job` calls). `detect.route_source` picks the per-source ingestor (`instructables.py`, `pdf.py`, `generic_url.py`) which becomes the `ParseStage`. Default stages: `ParseStage → NormalizeStage → MarkdownStage → EnrichStage`. `IngestionItem` (alias of `IngestionResult`) carries additive `raw_html`, `markdown`, `ai_suggestions`, `pipeline_warnings` fields — `result_json` shape is additive-only so the frontend poller is unchanged. Instructables scrapes cached in Redis 24h via `fetch_cached()`. Async job tracked in `apps.ingestion.models.ProjectIngestionJob` (UUID pk, db_table preserved as `projects_projectingestionjob`). Tests live in `tests/test_pipeline.py` (pipeline stages) and `tests/test_tasks.py` (Celery task path).

- **AI enrichment** (`ingestion/enrich.py`): `EnrichStage` is a no-op when no LLM backend is configured (see "LLM backend" gotcha in root CLAUDE.md). When configured, sends the item's markdown to whichever backend is active and writes `{category, difficulty, skill_tags, extra_materials, summary, steps, resources}` to `item.ai_suggestions`. Rendered as opt-in chips on the `ProjectIngest` preview — never mutates title/description/milestones/materials automatically. Markdown conversion (`ingestion/markdown.py`) prefers `crawl4ai`, falls back to `markdownify`, then synthesizes from title+description.

## Key entry points
- `pipeline/pipeline.py` — `default_pipeline()`.
- `pipeline/runner.py` — pipeline execution.
- `pipeline/{detect,instructables,pdf,generic_url}.py` — per-source ingestors.
- `pipeline/enrich.py` — AI enrichment stage (calls `config.llm.complete_json`).
- `pipeline/markdown.py` — markdown conversion fallback chain.
- `tasks.py` — `run_ingestion_job` Celery task.
- `tests/test_pipeline.py`, `tests/test_tasks.py`.
