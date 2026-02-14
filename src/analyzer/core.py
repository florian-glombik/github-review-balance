"""Main GitHub PR review analyzer."""

import logging
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Set, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

from ..models import ReviewStats
from ..api_client import GitHubAPIClient
from ..cache import CacheManager
from ..file_filters import FileFilter


class GitHubReviewAnalyzer:
    """Analyzes GitHub PR reviews for a given user across repositories."""

    def __init__(
        self,
        username: str,
        token: str = None,
        cache_file: str = '.github_review_cache.json',
        use_cache: bool = True,
        excluded_users: Set[str] = None,
        required_pr_label: str = None,
        required_project_state: str = None,
        required_project_number: int = None,
        sort_by: str = 'total_prs',
        exclude_generated_files: bool = False,
        excluded_file_patterns: List[str] = None,
        max_review_count_threshold: int = None
    ):
        """Initialize the analyzer.

        Args:
            username: GitHub username to analyze
            token: GitHub personal access token
            cache_file: Path to cache file
            use_cache: Whether to use caching
            excluded_users: Set of usernames to exclude from analysis
            required_pr_label: Only analyze PRs with this label
            required_project_state: Only analyze PRs with this project state
            required_project_number: Only check project state from this specific project number
            sort_by: Column to sort results by
            exclude_generated_files: Whether to exclude generated files from line counts
            excluded_file_patterns: Custom file patterns to exclude
            max_review_count_threshold: Minimum review count to filter PRs (None = no filtering)
        """
        self.username = username
        self.api_client = GitHubAPIClient(token)
        self.cache_manager = CacheManager(cache_file, use_cache)
        self.excluded_users = excluded_users or set()
        self.required_pr_label = required_pr_label
        self.required_project_state = required_project_state
        self.required_project_number = required_project_number
        self.sort_by = sort_by
        self.exclude_generated_files = exclude_generated_files
        self.file_filter = FileFilter(excluded_file_patterns)
        self.max_review_count_threshold = max_review_count_threshold

        logging.info(f"Initialized analyzer for user '{username}'")

        # Statistics: user -> ReviewStats
        self.reviewed_by_me: Dict[str, ReviewStats] = defaultdict(ReviewStats)
        self.reviewed_by_others: Dict[str, ReviewStats] = defaultdict(ReviewStats)

        # Track all users who have authored PRs (not just those I reviewed)
        self.pr_authors: Set[str] = set()

        # Store repositories for later use
        self.repositories: List[str] = []

        # Thread safety for parallel processing
        self._stats_lock = Lock()

    # Convenience properties for backward compatibility with tests
    @property
    def token(self):
        return self.api_client.token

    @property
    def session(self):
        return self.api_client.session

    @session.setter
    def session(self, value):
        self.api_client.session = value

    @property
    def use_cache(self):
        return self.cache_manager.use_cache

    @property
    def cache(self):
        return self.cache_manager.cache

    @cache.setter
    def cache(self, value):
        self.cache_manager.cache = value

    def _get_cache_key(self, repo: str, endpoint: str, params: Dict = None) -> str:
        """Generate a cache key - convenience wrapper for tests."""
        return self.cache_manager.get_cache_key(repo, endpoint, params)

    def _put_in_cache(self, cache_key: str, data: List[Dict]):
        """Put data in cache - convenience wrapper for tests."""
        self.cache_manager.put(cache_key, data)

    def _get_from_cache(self, cache_key: str) -> Optional[List[Dict]]:
        """Get data from cache - convenience wrapper for tests."""
        return self.cache_manager.get(cache_key)

    def _save_cache(self):
        """Save cache - convenience wrapper for tests."""
        self.cache_manager.save_cache()

    def get_paginated(self, url: str, params: Dict = None, use_cache: bool = True,
                     should_continue=None) -> List[Dict]:
        """Wrapper for API client's get_paginated - convenience for tests."""
        return self._get_paginated(url, params, use_cache, should_continue)

    def print_summary(self):
        """Print summary using the output formatter."""
        open_prs_by_author = self.get_open_prs_needing_review()
        from ..output import OutputFormatter
        output_formatter = OutputFormatter(self.username, self.sort_by)
        output_formatter.print_summary(
            self.reviewed_by_me,
            self.reviewed_by_others,
            open_prs_by_author
        )

    def _get_paginated(self, url: str, params: Dict = None, use_cache: bool = True,
                       should_continue=None) -> List[Dict]:
        """Fetch all pages of a paginated GitHub API endpoint with caching support.

        Args:
            url: The API endpoint URL
            params: Query parameters
            use_cache: Whether to use caching
            should_continue: Optional callback function

        Returns:
            List of all items from all pages
        """
        # Generate cache key
        cache_params = params.copy() if params else {}
        cache_params.pop('page', None)
        cache_params.pop('per_page', None)
        cache_key = self.cache_manager.get_cache_key('', url, cache_params)

        # Try to get from cache
        if use_cache:
            cached_data = self.cache_manager.get(cache_key)
            if cached_data is not None:
                logging.debug(f"Cache hit for {url}")
                return cached_data

        # Fetch from API
        results = self.api_client.get_paginated(url, params, should_continue)

        # Store in cache
        if use_cache:
            self.cache_manager.put(cache_key, results)

        return results

    def analyze_repository(self, repo: str, months: int = 3):
        """Analyze PRs in a repository for the last N months based on merge date.

        Args:
            repo: Repository name in format 'owner/repo'
            months: Number of months to analyze
        """
        logging.info(f"Analyzing repository: {repo}")

        # Store repository for later use
        if repo not in self.repositories:
            self.repositories.append(repo)

        since_date = datetime.now() - timedelta(days=months * 30)
        logging.info(f"Looking for PRs merged since: {since_date.strftime('%Y-%m-%d')}")

        # Fetch PRs
        url = f"https://api.github.com/repos/{repo}/pulls"

        print(f"Fetching pull requests from {repo}...")
        all_prs = []
        total_fetched = 0

        # Fetch both open and closed PRs
        for state in ['open', 'closed']:
            print(f"  Fetching {state} PRs...", end='', flush=True)
            page_count = [0]

            def count_pages(page_data: List[Dict]) -> bool:
                page_count[0] += 1
                return True

            prs = self._get_paginated(url, {
                'state': state,
                'sort': 'updated',
                'direction': 'desc'
            }, should_continue=count_pages)

            all_prs.extend(prs)
            total_fetched += len(prs)
            print(f" fetched {len(prs)} PRs ({page_count[0]} pages)")

        # Fetch project states for filtering (if needed) - only for open PRs
        # Closed/merged PRs don't need project state filtering since they're already done
        project_states = {}
        if self.required_project_state:
            open_prs = [pr for pr in all_prs if pr.get('state') == 'open']
            if open_prs:
                print(f"Fetching project states for {len(open_prs)} open PRs...")
                project_states = self._batch_fetch_project_states(repo, open_prs)
                print(f"  Fetched project states for {len(project_states)} PRs")

        # Filter PRs
        recent_prs = self._filter_prs(all_prs, since_date, project_states)

        filter_msg = f"Found {len(recent_prs)} PRs in the last {months} months (filtered from {total_fetched} fetched)"
        print(filter_msg)

        if not recent_prs:
            logging.info(f"No PRs found for repository: {repo}")
            return

        # Process PRs in parallel
        self._process_prs_parallel(repo, recent_prs)

        print(f"Completed analysis of {repo}")
        logging.info(f"Completed analysis of repository: {repo}")

    def save_cache(self):
        """Save the cache to disk."""
        self.cache_manager.save_cache()


# Import and attach methods from submodules
from .pr_processing import _process_prs_parallel, _analyze_pr, _fetch_pr_data, _track_reviewer_activity, _update_stats
from .pr_filtering import _filter_prs, _batch_prefetch_filtered_line_counts, _get_filtered_line_counts
from .open_prs import get_open_prs_needing_review, _process_open_prs_parallel, _check_and_create_pr_info, _has_reviewed_pr, _create_pr_info
from .my_prs import get_my_open_prs
from .project_states import _batch_fetch_project_states

# Attach methods to class
GitHubReviewAnalyzer._process_prs_parallel = _process_prs_parallel
GitHubReviewAnalyzer._analyze_pr = _analyze_pr
GitHubReviewAnalyzer._fetch_pr_data = _fetch_pr_data
GitHubReviewAnalyzer._track_reviewer_activity = _track_reviewer_activity
GitHubReviewAnalyzer._update_stats = _update_stats
GitHubReviewAnalyzer._filter_prs = _filter_prs
GitHubReviewAnalyzer._batch_prefetch_filtered_line_counts = _batch_prefetch_filtered_line_counts
GitHubReviewAnalyzer._get_filtered_line_counts = _get_filtered_line_counts
GitHubReviewAnalyzer.get_open_prs_needing_review = get_open_prs_needing_review
GitHubReviewAnalyzer._process_open_prs_parallel = _process_open_prs_parallel
GitHubReviewAnalyzer._check_and_create_pr_info = _check_and_create_pr_info
GitHubReviewAnalyzer._has_reviewed_pr = _has_reviewed_pr
GitHubReviewAnalyzer._create_pr_info = _create_pr_info
GitHubReviewAnalyzer.get_my_open_prs = get_my_open_prs
GitHubReviewAnalyzer._batch_fetch_project_states = _batch_fetch_project_states
