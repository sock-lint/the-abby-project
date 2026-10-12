from django.test import TestCase


class DrivePopupPolicyTests(TestCase):
    def test_journal_allows_google_authorization_popup_even_on_revalidation(self):
        response = self.client.get('/quests/ventures/ingest')
        self.assertEqual(response['Cross-Origin-Opener-Policy'], 'same-origin-allow-popups')
        cached = self.client.get('/quests/ventures/ingest', HTTP_IF_NONE_MATCH=response['ETag'])
        self.assertEqual(cached.status_code, 304)
        self.assertEqual(cached['Cross-Origin-Opener-Policy'], 'same-origin-allow-popups')

    def test_api_keeps_its_default_opener_policy(self):
        response = self.client.get('/api/auth/me/')
        self.assertEqual(response['Cross-Origin-Opener-Policy'], 'same-origin')
