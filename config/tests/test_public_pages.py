"""Public OAuth branding pages must render without sessions, APIs, or JavaScript."""

from django.test import SimpleTestCase
from django.urls import resolve, reverse


class PublicInformationPagesTests(SimpleTestCase):
    # SimpleTestCase forbids database access: these pages never load a family
    # or profile, including while the app's OAuth/Redis setup is unavailable.
    def test_anonymous_get_and_head_render_public_templates(self):
        for name, template, heading in (
            ("public-about", "public/about.html", "Keep your memories."),
            ("public-privacy", "public/privacy.html", "Privacy policy"),
        ):
            with self.subTest(page=name):
                url = reverse(name)
                self.assertEqual(resolve(url).url_name, name)
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/html", response["Content-Type"])
                self.assertTemplateUsed(response, template)
                self.assertContains(response, heading)
                self.assertContains(response, 'href="/privacy/"')
                self.assertContains(response, 'href="/">Sign in')
                self.assertNotContains(response, "<script")
                self.assertNotContains(response, "/api/")
                self.assertNotIn("sessionid", response.cookies)
                head = self.client.head(url)
                self.assertEqual(head.status_code, 200)
                self.assertEqual(head.content, b"")

    def test_homepage_explains_existing_account_link_and_optional_sync(self):
        response = self.client.get(reverse("public-about"))
        self.assertContains(response, "Connect Google account")
        self.assertContains(response, "Sign in with Google")
        self.assertContains(response, "Sync is off by default.")
        self.assertContains(response, "even when sync is off")

    def test_slashless_public_urls_redirect_before_the_spa_catch_all(self):
        for path in ("about", "privacy"):
            with self.subTest(page=path):
                response = self.client.get(f"/{path}?source=sign-in")
                self.assertRedirects(response, f"/{path}/?source=sign-in")

    def test_privacy_discloses_permission_storage_and_disconnect_limits(self):
        response = self.client.get(reverse("public-privacy"))
        for disclosure in (
            "October 17, 2026",
            "https://www.googleapis.com/auth/calendar.events.owned",
            "encrypted credentials",
            "does not revoke Google's authorization grant",
            "Google API Services User Data Policy",
            "Limited Use requirements",
            "https://myaccount.google.com/connections",
            "private by default",
            "copies in deployment backups",
            "scheduled for storage cleanup",
            "Failed cleanup is recorded and retried",
            "not comprehensive anonymization",
            "device drafts may also remain",
        ):
            with self.subTest(disclosure=disclosure):
                self.assertContains(response, disclosure)

    def test_privacy_discloses_ai_recipients_and_google_derived_transfers(self):
        response = self.client.get(reverse("public-privacy"))
        for disclosure in (
            'id="ai"',
            "Anthropic",
            "OpenAI",
            "12,000 characters",
            "before you review",
            "Google-derived text",
            "External assistants through MCP",
            "external speech service",
            "Removing that connection stops new family planning requests",
            "no longer provides AI sprite or image generation",
        ):
            with self.subTest(disclosure=disclosure):
                self.assertContains(response, disclosure)

    def test_public_pages_do_not_echo_credential_or_account_query_parameters(self):
        for name in ("public-about", "public-privacy"):
            with self.subTest(page=name):
                response = self.client.get(
                    reverse(name), {"token": "synthetic-private-token", "email": "synthetic@example.invalid"},
                )
                self.assertNotContains(response, "synthetic-private-token")
                self.assertNotContains(response, "synthetic@example.invalid")

    def test_bundled_font_is_served_without_a_frontend_build(self):
        response = self.client.get(reverse("public-nunito-font"))
        try:
            self.assertEqual(response.status_code, 200)
            font = b"".join(response.streaming_content)
            self.assertEqual(font[:4], b"\x00\x01\x00\x00")
            self.assertNotIn("text/html", response["Content-Type"])
        finally:
            response.close()
