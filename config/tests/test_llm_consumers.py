"""Consumer fallbacks when a deployment still names the retired AI backend."""
import json
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.achievements.models import SkillCategory
from apps.ingestion.pipeline.base import IngestionItem, StepDraft
from apps.ingestion.pipeline.enrich import EnrichStage
from apps.projects.suggestions import get_project_suggestions
from config.tests.factories import make_family


@override_settings(
    LLM_BACKEND="ollama",
    ANTHROPIC_API_KEY="synthetic-deployment-key",
    OLLAMA_BASE_URL="http://retired-provider.invalid:11434",
)
class RetiredBackendConsumerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        family = make_family(
            parents=[{"username": "llm-consumer-parent"}],
            children=[{"username": "llm-consumer-child"}],
        )
        cls.child = family.children[0]
        SkillCategory.objects.create(name="Woodworking")

    def setUp(self):
        self.unexpected = json.dumps({
            "suggestions": [{"title": "Unexpected AI project", "category": "Woodworking"}],
            "summary": "Unexpected AI enrichment",
        })
        self.response = MagicMock()
        self.response.json.return_value = {"response": self.unexpected}

    def test_project_suggestions_use_curated_fallback_without_contacting_a_provider(self):
        with patch("requests.post", return_value=self.response) as post, patch(
            "config.llm._anthropic_complete", return_value=self.unexpected,
        ) as anthropic:
            suggestions = get_project_suggestions(self.child)

        self.assertEqual(len(suggestions), 1)
        self.assertEqual({suggestion["title"] for suggestion in suggestions}, {"Simple Cutting Board"})
        self.assertEqual({suggestion["category"] for suggestion in suggestions}, {"Woodworking"})
        post.assert_not_called()
        anthropic.assert_not_called()

    def test_ingestion_preserves_parsed_content_without_contacting_a_provider(self):
        item = IngestionItem(
            title="Parsed birdhouse",
            description="Build a small wooden birdhouse.",
            markdown="## Instructions\nMeasure and cut the boards.",
            steps=[StepDraft(title="Measure the boards", description="Mark each length before cutting.")],
        )
        before = item.to_dict()

        with patch("requests.post", return_value=self.response) as post, patch(
            "config.llm._anthropic_complete", return_value=self.unexpected,
        ) as anthropic:
            result = EnrichStage()(item, {})

        self.assertIs(result, item)
        self.assertEqual(result.to_dict(), before)
        self.assertIsNone(result.ai_suggestions)
        self.assertEqual(result.pipeline_warnings, [])
        post.assert_not_called()
        anthropic.assert_not_called()
