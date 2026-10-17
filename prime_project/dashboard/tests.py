from django.contrib.auth import get_user_model
from django.test import TestCase


class DashboardEntryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.member = User.objects.create_user(email='dashboard-member@example.test', username='dashboard-member', password='Test-passphrase-927')
        cls.organizer = User.objects.create_user(email='dashboard-organizer@example.test', username='dashboard-organizer', password='Test-passphrase-927', role='admin')
        cls.staff_member = User.objects.create_user(email='dashboard-staff@example.test', username='dashboard-staff', password='Test-passphrase-927', is_staff=True)

    def test_anonymous_dashboard_entry_requires_login(self):
        self.assertRedirects(self.client.get('/dashboard/'), '/accounts/login/?next=/dashboard/', fetch_redirect_response=False)

    def test_member_dashboard_entry_redirects_without_rendering_missing_template(self):
        self.client.force_login(self.member)
        self.assertRedirects(self.client.get('/dashboard/'), '/dashboard/user/', fetch_redirect_response=False)

    def test_organizer_role_uses_existing_admin_dashboard(self):
        self.client.force_login(self.organizer)
        self.assertRedirects(self.client.get('/dashboard/'), '/dashboard/admin/', fetch_redirect_response=False)

    def test_staff_status_does_not_grant_organizer_role(self):
        self.client.force_login(self.staff_member)
        self.assertRedirects(self.client.get('/dashboard/'), '/dashboard/user/', fetch_redirect_response=False)
