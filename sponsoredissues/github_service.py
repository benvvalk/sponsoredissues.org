import requests
import logging
from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Sum
from typing import Dict, List, Optional
from decimal import Decimal
from .github_auth import GitHubAppAuth

logger = logging.getLogger(__name__)

class GitHubSponsorService:
    """Service for fetching GitHub Sponsors data via GraphQL API using GitHub App installation tokens"""

    GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"

    def __init__(self):
        self.github_app_auth = GitHubAppAuth()

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

    def get_sponsors_received_by_user(self, username: str) -> List[Dict]:
        """
        Get sponsors received by a specific user.
        Returns list of sponsor data with tier information.
        Uses the user's GitHub App installation token.
        """
        # Get installation token for the maintainer (donee)
        access_token = self.github_app_auth.get_installation_token_for_account(username)
        if not access_token:
            logger.debug(f"No GitHub App installation token available for user: {username}")
            return []

        query = """
        query($login: String!) {
            user(login: $login) {
                ... on Sponsorable {
                    sponsorshipsAsMaintainer(first: 100, includePrivate: false) {
                        nodes {
                            tier {
                                monthlyPriceInDollars
                                name
                            }
                            sponsor {
                                ... on User {
                                    login
                                }
                                ... on Organization {
                                    login
                                }
                            }
                            createdAt
                            isActive
                        }
                        totalCount
                    }
                }
            }
        }
        """

        variables = {'login': username}
        data = self._make_graphql_request(query, access_token, variables)

        if not data or not data.get('user'):
            return []

        sponsorships = data['user'].get('sponsorshipsAsMaintainer', {})
        return sponsorships.get('nodes', [])

    def get_sponsorships_by_user(self, sponsor_username: str, maintainer_username: str) -> List[Dict]:
        """
        Get sponsorships made by a specific user (who they sponsor).
        Returns list of sponsorship data.
        Uses the maintainer's GitHub App installation token to query the sponsor's data.

        Args:
            sponsor_username: The username of the sponsor (who makes sponsorships)
            maintainer_username: The username of the maintainer (used to get installation token)
        """
        # Get installation token for the maintainer (donee)
        access_token = self.github_app_auth.get_installation_token_for_account(maintainer_username)
        if not access_token:
            logger.debug(f"No GitHub App installation token available for maintainer: {maintainer_username}")
            return []

        query = """
        query($login: String!) {
            user(login: $login) {
                sponsorshipsAsSponsor(first: 100, includePrivate: false) {
                    nodes {
                        tier {
                            monthlyPriceInDollars
                            name
                        }
                        sponsorable {
                            ... on User {
                                login
                            }
                            ... on Organization {
                                login
                            }
                        }
                        createdAt
                        isActive
                    }
                    totalCount
                }
            }
        }
        """

        variables = {'login': sponsor_username}
        data = self._make_graphql_request(query, access_token, variables)

        if not data or not data.get('user'):
            return []

        sponsorships = data['user'].get('sponsorshipsAsSponsor', {})
        return sponsorships.get('nodes', [])

    def calculate_total_sponsor_dollars_received(self, username: str) -> Decimal:
        """
        Calculate total sponsor dollars received by a user.
        This represents cumulative monthly sponsorships over time.
        """
        sponsorships = self.get_sponsors_received_by_user(username)
        total = Decimal('0')

        for sponsorship in sponsorships:
            if not sponsorship.get('isActive'):
                continue

            tier = sponsorship.get('tier', {})
            monthly_amount = tier.get('monthlyPriceInDollars', 0)

            if monthly_amount:
                # For now, we'll use the monthly amount as a base
                # In a full implementation, we'd calculate based on duration
                # from createdAt to present date
                total += Decimal(str(monthly_amount))

        return total

    def calculate_total_sponsor_dollars_given(self, sponsor_username: str, recipient_username: str) -> Decimal:
        """
        Calculate total sponsor dollars given by sponsor_username to recipient_username.
        This represents the cumulative amount available for allocation.
        """
        sponsorships = self.get_sponsorships_by_user(sponsor_username, recipient_username)
        total = Decimal('0')

        for sponsorship in sponsorships:
            sponsorable = sponsorship.get('sponsorable', {})
            if sponsorable.get('login') != recipient_username:
                continue

            if not sponsorship.get('isActive'):
                continue

            tier = sponsorship.get('tier', {})
            monthly_amount = tier.get('monthlyPriceInDollars', 0)

            if monthly_amount:
                # For now, we'll use the monthly amount as a base
                # In a full implementation, we'd calculate based on duration
                # from createdAt to present date to get total cumulative amount
                total += Decimal(str(monthly_amount))

        return total

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
        # Get GitHub username from social account
        github_username = self._get_github_username(sponsor_user)
        if not github_username:
            return Decimal('0')

        # Get total sponsor dollars given by sponsor to repo_owner
        total_given = self.calculate_total_sponsor_dollars_given(
            github_username, repo_owner
        )

        # Get already allocated amounts
        allocated = self.calculate_allocated_sponsor_dollars(sponsor_user, repo_owner)

        # Return unallocated amount
        return max(total_given - allocated, Decimal('0'))

    def _get_github_username(self, user: User) -> Optional[str]:
        """Get GitHub username from user's social account"""
        from allauth.socialaccount.models import SocialAccount

        try:
            github_account = user.socialaccount_set.get(provider='github')
            return github_account.extra_data.get('login')
        except SocialAccount.DoesNotExist:
            # Fallback to Django username if no GitHub account
            return user.username