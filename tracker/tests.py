from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Application, PortalCredential
from .utils import decrypt_password, encrypt_password


class TrackerSmokeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='demo', email='demo@example.com', password='SecurePass123')

    def test_profile_created_for_user(self):
        self.assertTrue(hasattr(self.user, 'profile'))

    def test_password_encryption_round_trip(self):
        encrypted = encrypt_password('portal-secret')
        self.assertNotEqual(encrypted, 'portal-secret')
        self.assertEqual(decrypt_password(encrypted), 'portal-secret')

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)

    def test_authenticated_user_can_create_application(self):
        self.client.login(username='demo', password='SecurePass123')
        response = self.client.post(
            reverse('application_create'),
            {
                'company_name': 'Open Horizons',
                'job_title': 'Backend Developer',
                'portal_name': 'LinkedIn',
                'status': Application.STATUS_APPLIED,
                'priority': 'high',
                'tags_input': 'Backend, Python',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Application.objects.count(), 1)

    def test_application_url_without_scheme_is_normalized(self):
        self.client.login(username='demo', password='SecurePass123')
        response = self.client.post(
            reverse('application_create'),
            {
                'company_name': 'Open Horizons',
                'job_title': 'Backend Developer',
                'application_url': 'linkedin.com/jobs/view/123',
                'status': Application.STATUS_APPLIED,
                'priority': 'high',
                'tags_input': 'Backend, Python',
            },
        )
        self.assertEqual(response.status_code, 302)
        application = Application.objects.get()
        self.assertEqual(application.application_url, 'https://linkedin.com/jobs/view/123')

    def test_credential_form_encrypts_password(self):
        application = Application.objects.create(user=self.user, company_name='Acme', job_title='Engineer')
        self.client.login(username='demo', password='SecurePass123')
        response = self.client.post(
            reverse('credential_create'),
            {
                'application': application.pk,
                'portal_name': 'Indeed',
                'portal_email': 'demo@example.com',
                'password': 's3cr3t!',
            },
        )
        self.assertEqual(response.status_code, 302)
        credential = PortalCredential.objects.get()
        self.assertTrue(credential.encrypted_password)
        self.assertEqual(decrypt_password(credential.encrypted_password), 's3cr3t!')
