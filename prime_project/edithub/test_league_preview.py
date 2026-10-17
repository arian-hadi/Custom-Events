from datetime import datetime, timezone
from io import StringIO
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.core.management import call_command, CommandError
from django.test import SimpleTestCase, override_settings

from edithub.league.preview import issue_token, sample_league


@override_settings(DEBUG=True, V2_FRONTEND_URL='http://localhost:8082')
class LeaguePreviewTests(SimpleTestCase):
    # SimpleTestCase forbids database queries: previews must not read or write
    # real accounts, competition records, snapshots or point awards.
    def test_command_link_opens_sample_data_without_database_access(self):
        output = StringIO()
        call_command('league_preview', state='live', stdout=output, skip_checks=True)
        url = output.getvalue().splitlines()[-1]
        self.assertTrue(url.startswith('http://localhost:8082/editing-hub/preview?'))
        params = {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}
        response = self.client.get('/api/v2/league/preview/', params)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['preview'])
        self.assertEqual(len(response.json()['weekly']['rows']), 6)
        self.assertIn('no-store', response.headers['Cache-Control'])
        self.assertTrue(all(row['points'] is None for row in response.json()['weekly']['rows']))

    def test_frozen_and_pending_are_distinct_and_sample_winners_are_single(self):
        for state in ('live', 'frozen', 'pending'):
            data = self.client.get('/api/v2/league/preview/', {'token': issue_token(), 'state': state}).json()
            self.assertIsInstance(data['weekly_winner'], dict)
            self.assertIsInstance(data['monthly_winner'], dict)
            self.assertEqual(data['monthly_winner']['points'], 72)
            if state == 'frozen':
                self.assertFalse(data['weekly']['provisional'])
                self.assertEqual(data['weekly']['rows'][0]['points'], 25)
                self.assertEqual(data['monthly']['rows'][0]['points'], 70)
            elif state == 'pending':
                self.assertEqual(data['weekly']['state'], 'finalizing')
                self.assertIsNone(data['weekly']['rows'][-1]['weekly_score'])
                self.assertIsNone(data['weekly']['rows'][-1]['points'])

    def test_preview_disabled_outside_local_debug_settings(self):
        for settings in ({'DEBUG': False}, {'V2_FRONTEND_URL': 'https://example.com'}):
            with self.subTest(settings=settings), override_settings(**settings):
                with self.assertRaises(CommandError):
                    call_command('league_preview', stdout=StringIO(), skip_checks=True)
                self.assertEqual(self.client.get('/api/v2/league/preview/', {'token': issue_token()}).status_code, 404)

    def test_missing_tampered_expired_tokens_and_write_methods_rejected(self):
        with patch('django.core.signing.time.time', return_value=1):
            expired = issue_token()
        for token in ('', issue_token() + 'tampered', expired):
            self.assertEqual(self.client.get('/api/v2/league/preview/', {'token': token}).status_code, 403)
        self.assertEqual(self.client.post('/api/v2/league/preview/').status_code, 405)
        self.assertEqual(self.client.get('/api/v2/league/preview/', {'token': issue_token(), 'state': 'activate'}).status_code, 400)

    def test_preview_clock_uses_next_week_and_friday_month_even_at_new_year(self):
        data = sample_league('live', datetime(2026, 12, 27, tzinfo=timezone.utc))
        self.assertEqual(data['starts_at'], datetime(2026, 12, 28, tzinfo=timezone.utc))
        self.assertEqual(data['month_label'], 'January 2027')
        self.assertEqual(data['monthly_winner']['period_label'], 'December 2026 · sample result')
