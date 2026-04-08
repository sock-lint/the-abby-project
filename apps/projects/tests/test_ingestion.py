"""Tests for the project ingestion pipeline."""
from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.projects.ingestion.category import guess_category
from apps.projects.ingestion.generic_url import GenericUrlIngestor
from apps.projects.ingestion.instructables import InstructablesIngestor
from apps.projects.models import (
    MaterialItem, Project, ProjectIngestionJob, ProjectMilestone, SkillCategory, User,
)


# ---------- ingestor unit tests --------------------------------------------


INSTRUCTABLES_HTML = """
<html>
  <head>
    <meta property="og:image" content="https://example.com/cover.jpg">
    <meta property="og:description" content="Build a simple wooden bird feeder.">
    <meta property="article:section" content="Workshop">
  </head>
  <body>
    <h1>DIY Bird Feeder</h1>
    <section class="step" id="step-1"><h2>Cut the wood</h2><p>Measure and cut the plank to 12 inches.</p></section>
    <section class="step" id="step-2"><h2>Sand edges</h2><p>Use 120 grit sandpaper.</p></section>
    <section class="step" id="step-3"><h2>Assemble</h2><p>Glue the pieces together.</p></section>
    <h2>Supplies</h2>
    <ul>
      <li>Wood plank (12 inches)</li>
      <li>Sandpaper</li>
      <li>Wood glue</li>
    </ul>
  </body>
</html>
"""


JSONLD_HTML = """
<html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "HowTo",
  "name": "No-Sew Felt Bookmark",
  "description": "A quick bookmark craft.",
  "image": "https://example.com/bookmark.jpg",
  "supply": [{"@type":"HowToSupply","name":"Felt sheet"},{"@type":"HowToSupply","name":"Scissors"}],
  "step": [
    {"@type":"HowToStep","name":"Cut the felt","text":"Cut into a 2x6 inch strip"},
    {"@type":"HowToStep","name":"Fold","text":"Fold the top to make a pocket"},
    {"@type":"HowToStep","name":"Decorate","text":"Add stickers or drawings"}
  ]
}
</script>
</head><body></body></html>
"""


HEURISTIC_HTML = """
<html><head><title>Paper Airplane Guide</title>
<meta property="og:image" content="https://example.com/plane.jpg">
</head><body><article>
<h2>You'll need</h2>
<ul><li>1 sheet of paper</li><li>A flat surface</li></ul>
<h2>Instructions</h2>
<ol>
  <li>Fold the paper in half lengthwise. Crease firmly.</li>
  <li>Fold the top corners to the center line.</li>
  <li>Fold the wings down on both sides.</li>
  <li>Throw with a gentle flick.</li>
</ol>
</article></body></html>
"""


class InstructablesIngestorTests(TestCase):
    def test_parses_steps_and_supplies(self):
        ingestor = InstructablesIngestor("https://www.instructables.com/fake/")
        with patch.object(InstructablesIngestor, "fetch_cached", return_value=INSTRUCTABLES_HTML):
            result = ingestor.ingest()
        self.assertEqual(result.title, "DIY Bird Feeder")
        self.assertEqual(result.source_type, "instructables")
        self.assertEqual(result.cover_photo_url, "https://example.com/cover.jpg")
        self.assertEqual(len(result.milestones), 3)
        self.assertEqual(result.milestones[0].title, "Cut the wood")
        self.assertEqual(result.milestones[0].order, 0)
        self.assertEqual(len(result.materials), 3)
        self.assertIn("Wood plank", result.materials[0].name)
        # category hint should match Woodworking keyword map
        self.assertEqual(result.category_hint, "Woodworking")

    def test_rejects_non_instructables_url(self):
        with self.assertRaises(ValueError):
            InstructablesIngestor("https://example.com/foo")


class GenericUrlIngestorTests(TestCase):
    def test_prefers_jsonld_howto(self):
        ingestor = GenericUrlIngestor("https://example.com/howto")
        with patch.object(GenericUrlIngestor, "fetch_cached", return_value=JSONLD_HTML):
            result = ingestor.ingest()
        self.assertEqual(result.title, "No-Sew Felt Bookmark")
        self.assertEqual(len(result.milestones), 3)
        self.assertEqual(result.milestones[0].title, "Cut the felt")
        self.assertEqual(result.milestones[1].order, 1)
        self.assertEqual(len(result.materials), 2)
        self.assertEqual(result.materials[0].name, "Felt sheet")
        self.assertEqual(result.cover_photo_url, "https://example.com/bookmark.jpg")

    def test_heuristic_fallback_parses_ordered_list(self):
        ingestor = GenericUrlIngestor("https://example.com/plane")
        with patch.object(GenericUrlIngestor, "fetch_cached", return_value=HEURISTIC_HTML):
            result = ingestor.ingest()
        self.assertEqual(len(result.milestones), 4)
        self.assertTrue(any("best-effort heuristics" in w for w in result.warnings))
        self.assertEqual(len(result.materials), 2)
        self.assertEqual(result.cover_photo_url, "https://example.com/plane.jpg")


class CategoryMapperTests(TestCase):
    def test_matches_known_keywords(self):
        self.assertEqual(guess_category("Knit a scarf", "yarn project"), "Knitting")
        self.assertEqual(guess_category("Build a breadboard blinky", "LED arduino"), "Electronics")
        self.assertIsNone(guess_category("asdf qwer"))


# ---------- commit flow integration test -----------------------------------


class IngestCommitFlowTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(
            username="parent1", password="pw", role="parent"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.parent)
        self.category = SkillCategory.objects.create(name="Woodworking")

    def _make_ready_job(self, result_json):
        return ProjectIngestionJob.objects.create(
            created_by=self.parent,
            source_type="instructables",
            source_url="https://www.instructables.com/fake/",
            status=ProjectIngestionJob.Status.READY,
            result_json=result_json,
        )

    def test_commit_creates_project_with_milestones_and_materials(self):
        job = self._make_ready_job({
            "title": "Birdhouse",
            "description": "Build a simple birdhouse.",
            "cover_photo_url": None,
            "source_url": "https://www.instructables.com/fake/",
            "source_type": "instructables",
            "category_hint": "Woodworking",
            "difficulty_hint": 3,
            "milestones": [
                {"title": "Cut", "description": "Cut wood", "order": 0},
                {"title": "Sand", "description": "Smooth edges", "order": 1},
                {"title": "Assemble", "description": "Glue pieces", "order": 2},
            ],
            "materials": [
                {"name": "Wood", "description": "", "estimated_cost": "5.00"},
                {"name": "Glue", "description": "", "estimated_cost": None},
            ],
            "warnings": [],
        })

        resp = self.client.post(
            f"/api/projects/ingest/{job.id}/commit/", {}, format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        project_id = resp.json()["id"]
        project = Project.objects.get(pk=project_id)

        self.assertEqual(project.title, "Birdhouse")
        self.assertEqual(project.created_by, self.parent)
        self.assertEqual(project.category_id, self.category.id)
        self.assertEqual(project.difficulty, 3)
        self.assertEqual(ProjectMilestone.objects.filter(project=project).count(), 3)
        self.assertEqual(MaterialItem.objects.filter(project=project).count(), 2)

        job.refresh_from_db()
        self.assertEqual(job.status, ProjectIngestionJob.Status.COMMITTED)
        self.assertEqual(job.project_id, project.id)

    def test_commit_rejects_non_ready_job(self):
        job = ProjectIngestionJob.objects.create(
            created_by=self.parent,
            source_type="url",
            source_url="https://example.com",
            status=ProjectIngestionJob.Status.PENDING,
        )
        resp = self.client.post(
            f"/api/projects/ingest/{job.id}/commit/", {}, format="json",
        )
        self.assertEqual(resp.status_code, 400)
