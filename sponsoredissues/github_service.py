import requests
import logging
from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Sum
from typing import Dict, List, Optional
from decimal import Decimal

logger = logging.getLogger(__name__)

class GitHubSponsorService:
    """Service for fetching GitHub Sponsors data via GraphQL API using user access tokens"""

    GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"

    def _get_user_access_token(self, user: User) -> Optional[str]:
        """Get GitHub access token from user's social account"""
        from allauth.socialaccount.models import SocialToken, SocialAccount
        github_account = user.socialaccount_set.get(provider='github')
        social_token = SocialToken.objects.get(account=github_account)
        return social_token.token

    def _make_graphql_request(self, query: str, access_token: str, variables: Dict = None) -> Optional[Dict]:
        """Make a GraphQL request to GitHub API"""
        if not access_token:
            return None

        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        }

        payload = {'query': query}
        if variables:
            payload['variables'] = variables

        try:
            response = requests.post(
                self.GITHUB_GRAPHQL_URL,
                json=payload,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()

            data = response.json()
            if 'errors' in data:
                logger.error(f"GitHub GraphQL API errors: {data['errors']}")
                return None

            return data.get('data')
        except requests.exceptions.RequestException as e:
            logger.error(f"GitHub API request failed: {e}")
            return None

    def calculate_total_sponsor_dollars_given(self, sponsor_user: User, recipient_github_username: str) -> Decimal:
        """
        Calculate total sponsor dollars given by sponsor_user to recipient_github_username.
        This represents the cumulative amount available for allocation.
        """
        # Get access token for the logged-in user
        access_token = self._get_user_access_token(sponsor_user)

        query = """
        query($recipient_github_username: String!) {
           viewer {
              totalSponsorshipAmountAsSponsorInCents(sponsorableLogins: [$recipient_github_username])
           }
        }
        """

        variables = {'recipient_github_username': recipient_github_username}
        response = self._make_graphql_request(query, access_token, variables)

        return response['viewer']['totalSponsorshipAmountAsSponsorInCents']

    def calculate_allocated_sponsor_dollars(self, sponsor_user: User, repo_owner: str) -> Decimal:
        """
        Calculate total sponsor dollars already allocated by sponsor_user to repo_owner's issues.
        This looks at the SponsorAmount model to see what has been allocated.
        """
        from .models import SponsorAmount, GitHubIssue

        # Get all sponsor amounts allocated by this sponsor to issues in repos owned by repo_owner
        allocated_amounts = SponsorAmount.objects.filter(
            sponsor_user_id=sponsor_user,
            target_github_issue__url__contains=f"github.com/{repo_owner}/"
        ).aggregate(total=Sum('amount'))

        return allocated_amounts['total'] or Decimal('0')

    def calculate_unallocated_sponsor_dollars(self, sponsor_user: User, repo_owner: str) -> Decimal:
        """
        Calculate unallocated sponsor dollars for a sponsor-repo_owner combination.
        This is: total_sponsor_dollars_given - allocated_sponsor_dollars
        """
        # Get total sponsor dollars given by sponsor to repo_owner
        total_given = self.calculate_total_sponsor_dollars_given(
            sponsor_user, repo_owner
        )

        # Get already allocated amounts
        allocated = self.calculate_allocated_sponsor_dollars(sponsor_user, repo_owner)

        # Return unallocated amount
        return max(total_given - allocated, Decimal('0'))

    def _get_github_username(self, user: User) -> Optional[str]:
        """Get GitHub username from user's social account"""
        from allauth.socialaccount.models import SocialAccount

        github_account = user.socialaccount_set.get(provider='github')
        return github_account.extra_data.get('login')