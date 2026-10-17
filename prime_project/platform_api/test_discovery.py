"""Read-only discovery contracts for the V2 standings and retail interfaces."""
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from edithub.league import services
from edithub.league_models import CompetitionEntry, CompetitionWeek, LeaguePointsAward, LeagueSeason, MonthlyAward, ScoringVersion, WeeklyResult
from edithub.models import EditorApplication
from shop.models import AmazonSource, Product, ProductPayment
from .test_member_dashboard import NOW, pilot_config


class ShopDiscoveryTests(TestCase):
    def product(self, name, price='25.00', **values):
        product = Product(name=name, original_price=price, description='Public details', thumbnail='shop/test.png',
                          main_image='shop/test.png', redirect_url='https://example.test/buy', **values)
        Product.objects.bulk_create([product])
        return product

    def checkout(self, product, amount, currency='usd'):
        ProductPayment.objects.bulk_create([ProductPayment(product=product, enabled=True, amount_minor=amount, currency=currency)])

    def get(self, **params):
        response = self.client.get('/api/v2/products/', params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_price_sort_and_bounds_use_checkout_amount_not_legacy_display_price(self):
        expensive = self.product('Checkout 10.99', '1.00')
        cheap = self.product('Checkout 10.01', '900.00')
        self.checkout(expensive, 1099)
        self.checkout(cheap, 1001)
        eur = self.product('Euro', '2.00')
        self.checkout(eur, 100, 'eur')
        data = self.get(sort='price_asc', currency='USD')
        self.assertEqual([item['id'] for item in data['results']], [cheap.pk, expensive.pk])
        self.assertEqual(self.get(currency='USD', min_price='10.50')['results'][0]['id'], expensive.pk)
        self.assertEqual(self.get(currency='USD', max_price='10.50')['results'][0]['id'], cheap.pk)
        self.assertEqual(data['count'], 2)
        self.assertEqual(data['total_count'], 3)
        self.assertEqual({row['value'] for row in data['facets']['currencies']}, {'USD', 'EUR'})
        # Configured checkout still has authoritative pricing when payment service is off.
        self.assertFalse(data['results'][0]['checkout']['enabled'])

    def test_zero_and_three_decimal_currency_ranges(self):
        jpy = self.product('Yen')
        self.checkout(jpy, 1099, 'jpy')
        kwd = self.product('Dinar')
        self.checkout(kwd, 1001, 'kwd')
        self.assertEqual(self.get(currency='JPY', min_price='1098', max_price='1100')['count'], 1)
        self.assertEqual(self.get(currency='KWD', min_price='1.000', max_price='1.002')['count'], 1)

    def test_free_and_sale_facets_follow_effective_offer_and_scope(self):
        sale = self.product('Figure sale', '50', discount_active=True, discounted_price='20', category='merges_1_0', ecommerce_platform='ebay')
        free = self.product('Free creator edit', free_deadline_active=True, free_deadline=timezone.now() + timedelta(hours=1))
        paid = self.product('Checkout overrides sale', discount_active=True, discounted_price='2')
        self.checkout(paid, 5000)
        self.product('Hidden sale', is_active=False, discount_active=True, discounted_price='1')
        self.assertEqual([row['id'] for row in self.get(offer='sale')['results']], [sale.pk])
        self.assertEqual([row['id'] for row in self.get(offer='free')['results']], [free.pk])
        data = self.get(search='Figure', platform='ebay', category='merges_1_0')
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['facets']['offers'][0]['count'], 1)
        self.assertEqual(sum(item['count'] for item in data['categories']), 1)

    @override_settings(AMAZON_AUTOMATION_ENABLED=True)
    def test_amazon_freshness_filters_and_unpublished_records_do_not_leak(self):
        now = timezone.now()
        fresh = self.product('Provider placeholder', '0', is_active=False, category='merges_1_0', ecommerce_platform='amazon')
        stale = self.product('Stale provider placeholder', '0', is_active=False, category='merges_1_0', ecommerce_platform='amazon')
        hidden = self.product('Hidden provider placeholder', '0', is_active=False, category='merges_1_0', ecommerce_platform='amazon')
        sources = [AmazonSource(product=product, asin=f'B00000000{index}', publish=product != hidden, title='Public Amazon item',
            price='12.50', currency='USD', image_url='https://m.media-amazon.com/image.jpg',
            content_expires_at=now + timedelta(hours=2), offer_expires_at=now + timedelta(hours=1) if product == fresh else now - timedelta(hours=1))
            for index, product in enumerate([fresh, stale, hidden])]
        AmazonSource.objects.bulk_create(sources)
        all_data = self.get(platform='amazon')
        self.assertEqual(all_data['count'], 2)
        self.assertEqual([row['id'] for row in self.get(currency='USD', min_price='1')['results']], [fresh.pk])
        self.assertFalse(next(row for row in all_data['results'] if row['id'] == stale.pk)['price_available'])
        self.assertEqual(self.get(search='placeholder')['count'], 0)
        AmazonSource.objects.filter(product=fresh).update(content_expires_at=now - timedelta(seconds=1))
        self.assertEqual(self.get(currency='USD', sort='price_asc')['count'], 0)

    def test_invalid_price_comparisons_and_unsupported_filters_are_rejected(self):
        for query in ({'sort': 'price_asc'}, {'min_price': '1'}, {'sort': 'popular'}, {'offer': 'in_stock'},
                      {'currency': 'US'}, {'currency': 'USD', 'min_price': 'nan'}, {'currency': 'USD', 'max_price': '-1'},
                      {'currency': 'USD', 'min_price': '3', 'max_price': '2'}):
            self.assertEqual(self.client.get('/api/v2/products/', query).status_code, 400, query)

    def test_favorites_pagination_and_query_count_stay_scoped_and_bounded(self):
        products = [self.product(f'Figure {index}') for index in range(28)]
        self.product('Inactive favorite', is_active=False)
        user = get_user_model().objects.create_user(email='favorites@example.test', username='favorites', password='password', is_verified=True)
        user.favorite_products.add(*products[:2])
        self.assertEqual(self.client.get('/api/v2/favorites/').status_code, 401)
        self.client.force_login(user)
        favorites = self.client.get('/api/v2/favorites/', {'sort': 'oldest'}).json()
        self.assertEqual(favorites['total_count'], 2)
        self.assertEqual(sum(item['count'] for item in favorites['categories']), 2)
        self.client.logout()
        with CaptureQueriesContext(connection) as queries:
            page = self.get(page=2)
        self.assertEqual(len(page['results']), 4)
        self.assertEqual(page['pages'], 2)
        self.assertLessEqual(len(queries), 10)


class LeagueDiscoveryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(email='league@example.test', username='League editor', password='password', is_verified=True)
        cls.season = LeagueSeason.objects.create(year=2026)
        cls.version = ScoringVersion.objects.create(name='discovery-test', config=pilot_config(), rules_confirmed=True, calibrated=True, calibration_notes='Test fixture')
        cls.application = EditorApplication(user=cls.user, channel_type='youtube', channel_link='https://example.test/channel',
            channel_name='Verified channel', status='accepted', channel_verified=True, editing_area='transformers', follower_count=999999, rank_position=1)
        EditorApplication.objects.bulk_create([cls.application])

    def week(self, offset=0, **values):
        start = NOW.replace(hour=0) - timedelta(days=4 + offset)
        return CompetitionWeek.objects.create(season=self.season, scoring_version=self.version, start_at=start,
            cutoff_at=start + timedelta(days=5), scoring_date=(start + timedelta(days=4)).date(), **values)

    def entry(self, week, state='active', user=None):
        index = CompetitionEntry.objects.count()
        return CompetitionEntry.objects.create(week=week, editor=user or self.user, approved_application=None if user else self.application, platform='youtube',
            video_id=f'video{index}', channel_id='channel', video_format='short', published_at=week.start_at - timedelta(days=1),
            canonical_url=f'https://youtube.com/watch?v=video{index}', title='Creative edit', state=state)

    def result(self, entry, revision=1, points=25, snapshot=None):
        WeeklyResult.objects.create(week=entry.week, entry=entry, revision=revision, placement=1, league_points=points, snapshot=snapshot, baseline=None)
        LeaguePointsAward.objects.create(week=entry.week, entry=entry, editor=self.user, revision=revision, points=points)

    def test_calendar_supports_history_without_exposing_queued_entries(self):
        finished = self.week(state='finalized', current_revision=1)
        self.result(self.entry(finished))
        scheduled = self.week(offset=-7, state='scheduled')
        self.entry(scheduled, 'queued')
        LeagueSeason.objects.create(year=2025)
        with patch('platform_api.league_views.timezone.now', return_value=NOW), CaptureQueriesContext(connection) as queries:
            response = self.client.get('/api/v2/league/rounds/', {'year': 2026})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual([item['year'] for item in data['years']], [2026, 2025])
        self.assertEqual(data['rounds'][0]['entry_count'], 0)
        self.assertFalse(data['rounds'][0]['official_results'])
        self.assertTrue(data['rounds'][1]['official_results'])
        self.assertEqual(data['rounds'][1]['entry_count'], 1)
        self.assertNotIn('email', response.content.decode())
        self.assertNotIn('video_id', response.content.decode())
        self.assertLessEqual(len(queries), 4)
        self.assertEqual(self.client.get('/api/v2/league/rounds/', {'year': 2025}).json()['rounds'], [])
        self.assertEqual(self.client.get('/api/v2/league/rounds/', {'year': 'bad'}).status_code, 400)
        self.assertEqual(self.client.post('/api/v2/league/rounds/', {}).status_code, 405)

    def test_public_standings_use_verified_identity_and_current_official_revision_only(self):
        finished = self.week(state='finalized', current_revision=2)
        entry = self.entry(finished)
        WeeklyResult.objects.create(week=finished, entry=entry, revision=1, placement=1, league_points=900, snapshot=None, baseline=None)
        self.result(entry, revision=2, points=18)
        data = self.client.get('/api/v2/league/standings/', {'period': 'month', 'year': 2026, 'month': finished.scoring_date.month}).json()
        row = data['rows'][0]
        self.assertEqual(row['points'], 18)
        self.assertEqual(row['latest_result']['points'], 18)
        self.assertEqual(row['channel_name'], 'Verified channel')
        self.assertTrue(row['channel_verified'])
        self.assertEqual(row['scored_rounds'], 1)
        self.assertIsNone(row['rank_change'])
        self.assertNotIn('follower', str(data))
        self.assertNotIn(self.user.email, str(data))
        weekly = self.client.get('/api/v2/league/standings/', {'period': 'week', 'week': finished.pk}).json()
        self.assertEqual(weekly['rows'][0]['points'], 18)
        self.client.force_login(self.user)
        own = self.client.get('/api/v2/league/entries/me/').json()['entries'][0]
        self.assertEqual(own['state'], 'finalized')
        self.assertEqual(own['points'], 18)
        ScoringVersion.objects.filter(pk=self.version.pk).update(rules_confirmed=False)
        self.assertEqual(self.client.get('/api/v2/league/standings/', {'week': finished.pk}).json()['rows'], [])
        self.assertFalse(self.client.get('/api/v2/league/rounds/', {'year': 2026}).json()['rounds'][0]['official_results'])

    def test_exhibition_and_canceled_remain_neutral_not_ranked_results(self):
        for offset, state in [(0, 'exhibition'), (7, 'canceled')]:
            week = self.week(offset=offset, state=state, current_revision=1)
            self.result(self.entry(week))
            data = self.client.get('/api/v2/league/standings/', {'week': week.pk}).json()
            self.assertEqual(data['state'], state)
            self.assertEqual(data['rows'], [])

    def test_winner_highlights_obey_the_same_official_scoring_gate(self):
        week = self.week(state='finalized', current_revision=1)
        entry = self.entry(week)
        self.result(entry)
        WeeklyResult.objects.filter(entry=entry).update(is_winner=True)
        MonthlyAward.objects.create(year=2026, month=10, revision=1, editor=self.user, entry=entry, points=25)
        data = self.client.get('/api/v2/league/winners/').json()
        self.assertEqual(data['weekly_winner']['points'], 25)
        self.assertEqual(data['monthly_winner']['points'], 25)
        ScoringVersion.objects.filter(pk=self.version.pk).update(calibrated=False)
        self.assertIsNone(self.client.get('/api/v2/league/winners/').json()['weekly_winner'])
        self.assertIsNone(self.client.get('/api/v2/league/winners/').json()['monthly_winner'])

    def test_live_standings_serialize_real_scores_and_leave_missing_data_unranked(self):
        week = self.week(state='scheduled')
        entry = self.entry(week, 'queued')
        other = get_user_model().objects.create_user(email='pending@example.test', username='Pending editor')
        pending = self.entry(week, 'queued', user=other)
        with patch('platform_api.league_views.timezone.now', return_value=NOW):
            services.activate_week(week, now=week.start_at + timedelta(minutes=1))
            services.record_snapshot(entry, {'completed_at': NOW, 'likes': 120, 'views': 1000, 'provider': 'test-fixture'})
            response = self.client.get('/api/v2/league/standings/', {'week': week.pk})
            self.client.force_login(self.user)
            own = self.client.get('/api/v2/league/entries/me/').json()['entries'][0]
        self.assertEqual(response.status_code, 200, response.content)
        self.assertGreater(float(own['weekly_score']), 0)
        self.assertIsNotNone(own['response_score'])
        self.assertIsNotNone(own['improvement_score'])
        self.assertIsNotNone(own['popularity_score'])
        self.assertIsNone(own['points'])
        for private_field in ('tie_draw', 'baseline_id', 'snapshot_id', 'reference_key'):
            self.assertNotIn(private_field, own)
        data = response.json()
        self.assertTrue(data['provisional'])
        self.assertEqual(data['state'], 'live')
        self.assertEqual(data['last_refresh'], NOW.isoformat().replace('+00:00', 'Z'))
        self.assertEqual([row['entry_id'] for row in data['rows']], [entry.pk, pending.pk])
        scored, unscored = data['rows']
        self.assertEqual(scored['rank'], 1)
        self.assertGreater(float(scored['weekly_score']), 0)
        self.assertIsNone(scored['points'])
        self.assertTrue(scored['neutral_baseline'])
        self.assertIsNotNone(scored['last_refresh'])
        self.assertIsNone(unscored['rank'])
        self.assertIsNone(unscored['weekly_score'])
        self.assertTrue(unscored['data_pending'])
        self.assertEqual(unscored['state'], 'data_pending')
        for private_field in ('entry', 'tie_draw', 'baseline_id', 'snapshot_id', 'reference_key', 'reason'):
            self.assertNotIn(private_field, scored)

    def test_scheduled_and_unactivated_rounds_do_not_publish_submissions(self):
        week = self.week(offset=-7, state='scheduled')
        entry = self.entry(week, 'queued')
        with patch('platform_api.league_views.timezone.now', return_value=NOW), patch('platform_api.league_views.services.provisional_standings') as score:
            for values in ({}, {'state': 'live', 'activated_at': NOW},
                           {'start_at': NOW - timedelta(hours=1), 'activated_at': None},
                           {'state': 'scheduled', 'activated_at': NOW}):
                if values:
                    CompetitionWeek.objects.filter(pk=week.pk).update(**values)
                response = self.client.get('/api/v2/league/standings/', {'week': week.pk})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['rows'], [])
                self.assertNotIn(entry.canonical_url, response.content.decode())
            score.assert_not_called()

    def test_cutoff_status_does_not_wait_for_worker_to_show_finalizing(self):
        week = self.week(state='live', activated_at=NOW - timedelta(days=1))
        with patch('platform_api.league_views.timezone.now', return_value=week.cutoff_at):
            status = self.client.get('/api/v2/league/status/').json()
            standings = self.client.get('/api/v2/league/standings/', {'week': week.pk}).json()
        self.assertEqual(status['current_week']['state'], 'finalizing')
        self.assertEqual(standings['state'], 'finalizing')
        week.refresh_from_db()
        self.assertEqual(week.state, 'live')  # A read does not finalize or mutate a round.

    def test_live_standings_exclude_queued_withdrawn_and_disqualified_entries(self):
        week = self.week(state='live', activated_at=NOW - timedelta(days=1))
        public = self.entry(week)
        private = []
        for state in ('queued', 'withdrawn', 'disqualified'):
            user = get_user_model().objects.create_user(email=f'{state}@example.test', username=f'{state} editor')
            private.append(self.entry(week, state, user=user))
        with patch('platform_api.league_views.timezone.now', return_value=NOW):
            response = self.client.get('/api/v2/league/standings/', {'week': week.pk})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual([row['entry_id'] for row in response.json()['rows']], [public.pk])
        for entry in private:
            self.assertNotIn(entry.canonical_url, response.content.decode())

    def test_live_rank_comes_from_scoring_placement_and_audit_fields_stay_private(self):
        week = self.week(state='finalizing', activated_at=NOW - timedelta(days=1))
        entry = self.entry(week)
        service_row = {'entry_id': entry.pk, 'editor_id': self.user.pk, 'entry': entry,
                       'placement': 7, 'weekly_score': '55', 'details': {'internal': 'audit'},
                       'tie_draw': 'private draw', 'data_pending': False}
        with patch('platform_api.league_views.timezone.now', return_value=NOW), patch('platform_api.league_views.services.provisional_standings', return_value=[service_row]):
            response = self.client.get('/api/v2/league/standings/', {'week': week.pk})
            self.assertEqual(response.status_code, 200, response.content)
            row = response.json()['rows'][0]
            self.assertEqual(row['rank'], 7)
            self.assertIsNone(row['points'])
            self.assertNotIn('details', row)
            self.assertNotIn('tie_draw', row)
            service_row['placement'] = None
            self.assertIsNone(self.client.get('/api/v2/league/standings/', {'week': week.pk}).json()['rows'][0]['rank'])
            service_row['disqualified'] = True
            self.assertEqual(self.client.get('/api/v2/league/standings/', {'week': week.pk}).json()['rows'], [])

    def test_archived_standings_preserve_result_snapshot_and_round_refresh_timestamps(self):
        week = self.week(offset=7, state='finalized', current_revision=1)
        entry = self.entry(week)
        closing_time = week.cutoff_at - timedelta(minutes=5)
        later_time = week.cutoff_at + timedelta(hours=1)
        with patch('platform_api.league_views.timezone.now', return_value=NOW):
            closing = services.record_snapshot(entry, {'completed_at': closing_time, 'likes': 120, 'views': 1000, 'provider': 'test-fixture'})
            services.record_snapshot(entry, {'completed_at': later_time, 'likes': 140, 'views': 1200, 'provider': 'test-fixture'})
            self.result(entry, snapshot=closing)
            response = self.client.get('/api/v2/league/standings/', {'week': week.pk})
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data['last_refresh'], later_time.isoformat().replace('+00:00', 'Z'))
        self.assertEqual(data['rows'][0]['last_refresh'], closing_time.isoformat().replace('+00:00', 'Z'))

    def test_standings_without_snapshots_do_not_invent_refresh_timestamps(self):
        week = self.week(offset=7, state='finalized', current_revision=1)
        self.result(self.entry(week))
        data = self.client.get('/api/v2/league/standings/', {'week': week.pk}).json()
        self.assertIsNone(data['last_refresh'])
        self.assertIsNone(data['rows'][0]['last_refresh'])
        with patch('platform_api.league_views.timezone.now', return_value=NOW):
            upcoming = self.client.get('/api/v2/league/standings/').json()
        self.assertIsNone(upcoming['last_refresh'])
