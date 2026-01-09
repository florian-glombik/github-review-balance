"""GitHub API client for making requests and handling pagination."""

import os
import sys
import logging
from typing import Dict, List, Optional, Callable
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class GitHubAPIClient:
    """Handles GitHub API requests with retry logic and pagination."""

    def __init__(self, token: str = None):
        """Initialize the GitHub API client.

        Args:
            token: GitHub personal access token for authentication
        """
        # Use provided token or fall back to environment variable
        self.token = token or os.environ.get('GITHUB_TOKEN')
        self.session = requests.Session()

        # Configure session with larger connection pool to handle concurrent requests
        # Pool size = 10 (outer workers) * 3 (inner workers per PR) = 30 + buffer
        adapter = HTTPAdapter(
            pool_connections=50,  # Number of connection pools to cache
            pool_maxsize=50,      # Maximum number of connections to save in the pool
            max_retries=Retry(
                total=3,
                backoff_factor=0.3,
                status_forcelist=[500, 502, 503, 504]
            )
        )
        self.session.mount('https://', adapter)
        self.session.mount('http://', adapter)

        if self.token:
            self.session.headers.update({
                'Authorization': f'token {self.token}',
                'Accept': 'application/vnd.github.v3+json'
            })
            logging.info("Initialized GitHub API client with token")
        else:
            logging.warning("No GitHub token provided. Rate limits will be much lower.")
            logging.warning("Set GITHUB_TOKEN environment variable or pass token as argument.")

    def get_paginated(self, url: str, params: Dict = None,
                      should_continue: Optional[Callable[[List[Dict]], bool]] = None) -> List[Dict]:
        """Fetch all pages of a paginated GitHub API endpoint.

        Args:
            url: The API endpoint URL
            params: Query parameters
            should_continue: Optional callback function that takes a page of results and returns
                           False to stop pagination early, True to continue

        Returns:
            List of all items from all pages
        """
        results = []
        page = 1
        per_page = 100

        params = params or {}
        params['per_page'] = per_page

        while True:
            params['page'] = page
            logging.debug(f"Fetching page {page} from {url}")
            response = self.session.get(url, params=params)

            if response.status_code == 403:
                logging.error(f"Rate limit exceeded. Response: {response.json()}")
                sys.exit(1)

            response.raise_for_status()
            data = response.json()

            if not data:
                break

            results.extend(data)

            # Check early termination callback
            if should_continue and not should_continue(data):
                logging.debug(f"Early termination triggered at page {page}")
                break

            # Check if there are more pages
            if len(data) < per_page:
                break

            page += 1

        logging.debug(f"Fetched {len(results)} total items from {url}")
        return results

    def get(self, url: str) -> requests.Response:
        """Make a single GET request to the GitHub API.

        Args:
            url: The API endpoint URL

        Returns:
            Response object
        """
        return self.session.get(url)

    def post_graphql(self, query: str, variables: Dict = None) -> Dict:
        """Make a GraphQL query to the GitHub API.

        Args:
            query: GraphQL query string
            variables: Optional query variables

        Returns:
            JSON response data

        Raises:
            Exception: If the GraphQL query fails
        """
        url = "https://api.github.com/graphql"
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        try:
            response = self.session.post(url, json=payload)

            if response.status_code == 403:
                logging.error(f"Rate limit exceeded. Response: {response.json()}")
                sys.exit(1)

            response.raise_for_status()
            result = response.json()

            # Check for GraphQL errors
            if "errors" in result:
                logging.error(f"GraphQL errors: {result['errors']}")
                raise Exception(f"GraphQL query failed: {result['errors']}")

            return result.get("data", {})

        except Exception as e:
            logging.error(f"GraphQL query failed: {e}")
            raise

    @staticmethod
    def build_pr_project_states_query(repo_owner: str, repo_name: str, pr_numbers: List[int]) -> str:
        """Build a GraphQL query to fetch project states for multiple PRs.

        Args:
            repo_owner: Repository owner
            repo_name: Repository name
            pr_numbers: List of PR numbers to query

        Returns:
            GraphQL query string
        """
        # Build individual PR queries as aliases
        pr_queries = []
        for pr_num in pr_numbers:
            # Use pr_{number} as alias to identify results
            pr_queries.append(f"""
        pr_{pr_num}: pullRequest(number: {pr_num}) {{
          number
          projectItems(first: 10) {{
            nodes {{
              fieldValueByName(name: "Status") {{
                ... on ProjectV2ItemFieldSingleSelectValue {{
                  name
                }}
              }}
            }}
          }}
        }}""")

        query = f"""
    query {{
      repository(owner: "{repo_owner}", name: "{repo_name}") {{
        {chr(10).join(pr_queries)}
      }}
    }}
    """

        return query