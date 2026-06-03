import logging

from django.conf import settings
from sponsoredissues.models import GitHubIssue

logger = logging.getLogger(__name__)

def maintainer_allowed_to_install_github_app(github_username):
    """
    Return true if the given GitHub username is allowed to
    install the `sponsoredissues-maintainer` GitHub App,
    in order to create a sponsored issues page.
    """
    beta_maintainers = getattr(settings, 'BETA_MAINTAINERS', [])

    # If `BETA_MAINTAINERS` env var is not set, it means all maintainers
    # are allowed (i.e. the website is out of beta and open to all users).
    if not beta_maintainers:
        return True

    # If maintainer has been approved to participate in website beta.
    if github_username in beta_maintainers:
        return True

    # If maintainer somehow has funded issues, despite not being
    # in the allowlist. It could be that I accidentally removed them
    # from `BETA_MAINTAINERS` when I shouldn't have.
    has_funded_issues = GitHubIssue.objects.filter(
        url__startswith = f'https://github.com/{github_username}/',
        sponsor_amounts__isnull = False
    ).exists()

    return has_funded_issues

def user_allowed_to_sign_in_with_github(github_username):
    """
    Return true if the given GitHub username is allowed to
    "Sign in with GitHub".
    """
    # Check if allowlist is configured
    beta_users = getattr(settings, 'BETA_USERS', [])

    # If no allowlist is configured, allow all users
    if not beta_users:
        return True

    # If user is listed in BETA_USERS, allow them to sign in
    if github_username in beta_users:
        return True

    # Automatically allow all GitHub usernames listed in
    # `BETA_MAINTAINERS` to "Sign in with GitHub", even if they aren't
    # explicitly listed in `BETA_USERS`. It doesn't make sense to
    # allow a user to install the `sponsoredissues-maintainer` GitHub
    # App in order to create a sponsored issues page, but not allow
    # them to "Sign in with GitHub".
    return maintainer_allowed_to_install_github_app(github_username)