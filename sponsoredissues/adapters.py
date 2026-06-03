"""
Custom django-allauth adapters for GitHub authentication.
"""

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from django.contrib import messages
from django.shortcuts import redirect
from django.conf import settings

from .beta import user_allowed_to_sign_in_with_github

class GitHubAccountAdapter(DefaultSocialAccountAdapter):
    """
    Custom adapter to restrict GitHub logins to a whitelist of users.

    This is useful during development to prevent unauthorized access while
    still allowing specific test accounts to log in.
    """

    def pre_social_login(self, request, sociallogin):
        """
        Called after a user successfully authenticates with GitHub but before
        they are logged into Django.

        If BETA_USERS is configured and the user is not in the list,
        we reject the login and show a custom message.
        """
        # Get the GitHub username from the social login data
        github_username = sociallogin.account.extra_data.get('login')

        # Check if user is allowed to "Sign in with GitHub",
        # based on current values of `BETA_USERS` and `BETA_MAINTAINERS`. 
        if not user_allowed_to_sign_in_with_github(github_username):
            # Get the custom message
            message = getattr(
                settings,
                'GITHUB_LOGIN_DISABLED_MESSAGE',
                'Sorry, logins are currently disabled.'
            )

            # Show the message to the user
            messages.error(request, message)

            # Redirect back to the page they came from (or home page)
            next_url = request.GET.get('next', '/')
            raise ImmediateHttpResponse(redirect(next_url))
