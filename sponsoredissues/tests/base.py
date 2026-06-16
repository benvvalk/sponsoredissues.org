from django.test import TestCase
from django.conf import settings


class BaseTestCase(TestCase):
    """
    This custom base class automatically unsets BETA_MAINTAINERS and
    BETA_USERS for all tests.

    Unset values for BETA_MAINTAINERS and BETA_USERS means that all
    GitHub users are allowed to create a sponsored issues page and
    all users are allowed to "Sign in with GitHub", respectively.

    This prevents the tests from failing due to use of
    hypothetical GitHub usernames like "maintainer1".
    """

    def setUp(self):
        """Set up test fixtures and unset beta restrictions."""
        super().setUp()

        # Store original values
        self._original_beta_maintainers = settings.BETA_MAINTAINERS
        self._original_beta_users = settings.BETA_USERS

        # Unset beta restrictions for tests
        settings.BETA_MAINTAINERS = None
        settings.BETA_USERS = None

    def tearDown(self):
        """Restore original settings after test."""
        # Restore original values
        settings.BETA_MAINTAINERS = self._original_beta_maintainers
        settings.BETA_USERS = self._original_beta_users

        super().tearDown()
