"""Main GitHub PR review analyzer."""

import logging
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Set, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

from .models import ReviewStats
from .api_client import GitHubAPIClient
from .cache import CacheManager
from .file_filters import FileFilter


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
        from .output import OutputFormatter
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

    def _get_filtered_line_counts(self, repo: str, pr_number: int, should_cache: bool) -> Dict[str, int]:
        """Fetch PR files and calculate filtered line counts excluding generated files.

        Args:
            repo: Repository name
            pr_number: PR number
            should_cache: Whether to cache the results

        Returns:
            Dictionary with 'additions' and 'deletions' counts, or None if filtering is disabled
        """
        if not self.exclude_generated_files:
            return None

        # Create cache key for this PR's filtered line counts
        cache_key = f"filtered_lines:{repo}:{pr_number}"

        # Try to get from cache
        if should_cache and cache_key in self.cache_manager:
            cached_data = self.cache_manager.cache[cache_key]
            logging.debug(f"Using cached filtered line counts for PR #{pr_number}")
            return cached_data['data']

        # Fetch files from API
        files_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/files"

        try:
            files = self._get_paginated(files_url, use_cache=False)
            result = self.file_filter.calculate_filtered_line_counts(files)

            # Log the PR number with the result
            logging.info(f"PR #{pr_number}: Filtered line counts: +{result['additions']:,}/-{result['deletions']:,}")

            # Cache only the filtered counts
            if should_cache:
                self.cache_manager.cache[cache_key] = {
                    'timestamp': datetime.now().isoformat(),
                    'data': result
                }

            return result

        except Exception as e:
            logging.warning(f"Error fetching files for PR #{pr_number}: {e}")
            return None

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

        # Filter PRs
        recent_prs = self._filter_prs(all_prs, since_date)

        filter_msg = f"Found {len(recent_prs)} PRs in the last {months} months (filtered from {total_fetched} fetched)"
        print(filter_msg)

        if not recent_prs:
            logging.info(f"No PRs found for repository: {repo}")
            return

        # Process PRs in parallel
        self._process_prs_parallel(repo, recent_prs)

        print(f"Completed analysis of {repo}")
        logging.info(f"Completed analysis of repository: {repo}")

    def _filter_prs(self, all_prs: List[Dict], since_date: datetime) -> List[Dict]:
        """Filter PRs by date, draft status, and labels.

        Args:
            all_prs: List of all PRs
            since_date: Only include PRs merged after this date

        Returns:
            Filtered list of PRs
        """
        # Deduplicate PRs by number
        seen_pr_numbers = set()
        deduplicated_prs = []
        for pr in all_prs:
            if pr['number'] not in seen_pr_numbers:
                seen_pr_numbers.add(pr['number'])
                deduplicated_prs.append(pr)

        recent_prs = []
        for pr in deduplicated_prs:
            # Check date range
            if pr['state'] == 'open':
                pass  # Include all open PRs
            elif pr.get('merged_at'):
                merged_date = datetime.strptime(pr['merged_at'], '%Y-%m-%dT%H:%M:%SZ')
                if merged_date < since_date:
                    continue
            else:
                continue  # Skip closed but not merged

            # Skip draft PRs
            if pr.get('draft', False):
                logging.debug(f"Skipping draft PR #{pr['number']}")
                continue

            # Check for required label
            if self.required_pr_label:
                pr_labels = [label['name'] for label in pr.get('labels', [])]
                if self.required_pr_label not in pr_labels:
                    logging.debug(f"Skipping PR #{pr['number']} - missing required label '{self.required_pr_label}'")
                    continue

            recent_prs.append(pr)

        return recent_prs

    def _batch_prefetch_filtered_line_counts(self, repo: str, prs: List[Dict]):
        """Batch-prefetch filtered line counts for all closed PRs in parallel.

        Args:
            repo: Repository name
            prs: List of PRs to prefetch file data for
        """
        if not self.exclude_generated_files:
            return

        # Only prefetch for closed PRs (which will be cached)
        closed_prs = [pr for pr in prs if pr.get('state') == 'closed']

        if not closed_prs:
            return

        print(f"Pre-fetching file data for {len(closed_prs)} closed PRs...")
        prefetched = 0
        max_workers = min(10, len(closed_prs))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_pr = {
                executor.submit(self._get_filtered_line_counts, repo, pr['number'], should_cache=True): pr
                for pr in closed_prs
            }

            for future in as_completed(future_to_pr):
                pr = future_to_pr[future]
                try:
                    future.result()
                    prefetched += 1

                    if prefetched % 20 == 0 or prefetched == len(closed_prs):
                        print(f"  Prefetch progress: {prefetched}/{len(closed_prs)} PRs", flush=True)

                except Exception as e:
                    logging.warning(f"Error prefetching PR #{pr['number']}: {e}")
                    prefetched += 1

        print(f"Pre-fetching complete. Proceeding with PR analysis...")

    def _process_prs_parallel(self, repo: str, prs: List[Dict]):
        """Process PRs in parallel.

        Args:
            repo: Repository name
            prs: List of PRs to process
        """
        # Batch-prefetch filtered line counts before processing
        self._batch_prefetch_filtered_line_counts(repo, prs)

        print(f"Analyzing {len(prs)} PRs...")
        completed = 0
        max_workers = min(10, len(prs))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_pr = {
                executor.submit(self._analyze_pr, repo, pr): pr
                for pr in prs
            }

            for future in as_completed(future_to_pr):
                pr = future_to_pr[future]
                try:
                    future.result()
                    completed += 1

                    if completed % 10 == 0 or completed == len(prs):
                        print(f"  Progress: {completed}/{len(prs)} PRs analyzed", flush=True)

                except Exception as e:
                    logging.error(f"Error analyzing PR #{pr['number']}: {e}", exc_info=True)
                    completed += 1

    def _analyze_pr(self, repo: str, pr: Dict):
        """Analyze a single PR for review activity.

        Args:
            repo: Repository name
            pr: PR data from GitHub API
        """
        pr_number = pr['number']
        pr_author = pr['user']['login']
        pr_title = pr['title']
        pr_url = pr['html_url']
        pr_state = pr.get('state', 'open')

        # Skip excluded users
        if pr_author in self.excluded_users:
            logging.debug(f"Skipping PR #{pr_number} by excluded user {pr_author}")
            return

        # Fetch PR details, reviews, and comments in parallel
        pr_details_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
        reviews_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/reviews"
        comments_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/comments"

        # Only cache closed PRs
        should_cache = (pr_state == 'closed')

        additions, deletions, reviews, review_comments = self._fetch_pr_data(
            pr, pr_details_url, reviews_url, comments_url, should_cache
        )

        # Apply file filtering if enabled
        if self.exclude_generated_files:
            filtered_counts = self._get_filtered_line_counts(repo, pr_number, should_cache)
            if filtered_counts:
                additions = filtered_counts['additions']
                deletions = filtered_counts['deletions']

        total_lines = additions + deletions

        logging.debug(f"Analyzing PR #{pr_number}: {pr_title} (by {pr_author}, +{additions}/-{deletions} lines, state: {pr_state})")

        # Track reviewer activity
        reviewer_activity = self._track_reviewer_activity(reviews, review_comments, pr_author)

        # Update stats
        self._update_stats(pr_author, pr_number, pr_title, pr_url, total_lines,
                          additions, deletions, reviews, review_comments, reviewer_activity)

    def _fetch_pr_data(self, pr: Dict, pr_details_url: str, reviews_url: str,
                       comments_url: str, should_cache: bool) -> tuple:
        """Fetch PR details, reviews, and comments in parallel.

        Returns:
            Tuple of (additions, deletions, reviews, review_comments)
        """
        additions = pr.get('additions', 0)
        deletions = pr.get('deletions', 0)
        reviews = []
        review_comments = []

        with ThreadPoolExecutor(max_workers=3) as executor:
            future_details = executor.submit(self.api_client.get, pr_details_url)
            future_reviews = executor.submit(self._get_paginated, reviews_url, use_cache=should_cache)
            future_comments = executor.submit(self._get_paginated, comments_url, use_cache=should_cache)

            # Get PR details
            try:
                pr_details_response = future_details.result()
                if pr_details_response.status_code == 200:
                    pr_details = pr_details_response.json()
                    additions = pr_details.get('additions', 0)
                    deletions = pr_details.get('deletions', 0)
            except Exception as e:
                logging.warning(f"Error fetching PR details: {e}")

            # Get reviews and comments
            try:
                reviews = future_reviews.result()
            except Exception as e:
                logging.warning(f"Error fetching reviews: {e}")

            try:
                review_comments = future_comments.result()
            except Exception as e:
                logging.warning(f"Error fetching comments: {e}")

        return additions, deletions, reviews, review_comments

    def _track_reviewer_activity(self, reviews: List[Dict], review_comments: List[Dict],
                                 pr_author: str) -> Dict:
        """Track unique reviewers and their activity.

        Returns:
            Dictionary mapping reviewer names to their activity
        """
        reviewer_activity = defaultdict(lambda: {
            'review_events': 0,
            'comments': 0,
            'reviews': set()
        })

        # Process reviews
        for review in reviews:
            reviewer = review['user']['login']
            review_id = review['id']

            if reviewer == self.username or reviewer == pr_author or reviewer in self.excluded_users:
                continue

            reviewer_activity[reviewer]['reviews'].add(review_id)
            reviewer_activity[reviewer]['review_events'] += 1

        # Process review comments
        for comment in review_comments:
            commenter = comment['user']['login']

            if commenter == self.username or commenter == pr_author or commenter in self.excluded_users:
                continue

            reviewer_activity[commenter]['comments'] += 1

        return reviewer_activity

    def _update_stats(self, pr_author: str, pr_number: int, pr_title: str, pr_url: str,
                     total_lines: int, additions: int, deletions: int,
                     reviews: List[Dict], review_comments: List[Dict],
                     reviewer_activity: Dict):
        """Update statistics with thread safety.

        Args:
            pr_author: PR author username
            pr_number: PR number
            pr_title: PR title
            pr_url: PR URL
            total_lines: Total lines changed
            additions: Lines added
            deletions: Lines deleted
            reviews: List of reviews
            review_comments: List of review comments
            reviewer_activity: Dictionary of reviewer activity
        """
        pr_info = {
            'title': pr_title,
            'url': pr_url,
            'number': pr_number,
            'lines': total_lines,
            'additions': additions,
            'deletions': deletions
        }

        with self._stats_lock:
            # Track PR author (unless it's me)
            if pr_author != self.username:
                self.pr_authors.add(pr_author)

            if pr_author == self.username:
                # Others reviewed my PR
                for reviewer, activity in reviewer_activity.items():
                    stats = self.reviewed_by_others[reviewer]
                    stats.prs_reviewed += 1
                    stats.lines_reviewed += total_lines
                    stats.additions_reviewed += additions
                    stats.deletions_reviewed += deletions
                    stats.review_events += activity['review_events']
                    stats.comments += activity['comments']
                    stats.prs.append(pr_info)
            else:
                # I reviewed someone else's PR
                my_reviews = [r for r in reviews if r['user']['login'] == self.username]
                my_comments = [c for c in review_comments if c['user']['login'] == self.username]

                if my_reviews or my_comments:
                    stats = self.reviewed_by_me[pr_author]
                    stats.prs_reviewed += 1
                    stats.lines_reviewed += total_lines
                    stats.additions_reviewed += additions
                    stats.deletions_reviewed += deletions
                    stats.review_events += len(my_reviews)
                    stats.comments += len(my_comments)
                    stats.prs.append(pr_info)

    def get_open_prs_needing_review(self) -> Dict[str, List[Dict]]:
        """Fetch open PRs from analyzed repositories that need review from the user.

        Returns:
            Dictionary mapping author names to lists of their open PRs
        """
        prs_by_author = defaultdict(list)

        print("\nFetching currently open PRs...")
        for repo in self.repositories:
            url = f"https://api.github.com/repos/{repo}/pulls"

            try:
                open_prs = self._get_paginated(url, {
                    'state': 'open',
                    'sort': 'updated',
                    'direction': 'desc'
                }, use_cache=False)

                # Filter PRs first
                candidate_prs = []
                for pr in open_prs:
                    pr_author = pr['user']['login']

                    # Skip my own PRs and excluded users
                    if pr_author == self.username or pr_author in self.excluded_users:
                        continue

                    # Skip draft PRs
                    if pr.get('draft', False):
                        continue

                    # Check for required label
                    if self.required_pr_label:
                        pr_labels = [label['name'] for label in pr.get('labels', [])]
                        if self.required_pr_label not in pr_labels:
                            continue

                    candidate_prs.append(pr)

                # Process PRs in parallel
                if candidate_prs:
                    self._process_open_prs_parallel(repo, candidate_prs, prs_by_author)

            except Exception as e:
                logging.error(f"Error fetching open PRs from {repo}: {e}")

        return prs_by_author

    def _process_open_prs_parallel(self, repo: str, prs: List[Dict], prs_by_author: Dict):
        """Process open PRs in parallel to check if they need review.

        Args:
            repo: Repository name
            prs: List of candidate PRs
            prs_by_author: Dictionary to populate with results
        """
        max_workers = min(10, len(prs))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_pr = {
                executor.submit(self._check_and_create_pr_info, repo, pr): pr
                for pr in prs
            }

            for future in as_completed(future_to_pr):
                pr = future_to_pr[future]
                try:
                    result = future.result()
                    if result is not None:
                        pr_author = pr['user']['login']
                        prs_by_author[pr_author].append(result)
                except Exception as e:
                    logging.warning(f"Error processing open PR #{pr['number']}: {e}")

    def _check_and_create_pr_info(self, repo: str, pr: Dict) -> Optional[Dict]:
        """Check if a PR needs review and create PR info if so.

        Args:
            repo: Repository name
            pr: PR data

        Returns:
            PR info dictionary if PR needs review, None otherwise
        """
        pr_number = pr['number']
        pr_details_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
        reviews_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/reviews"
        comments_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/comments"

        try:
            # Fetch PR details first, then reviews and comments sequentially to ensure deterministic ordering
            pr_details_response = self.api_client.get(pr_details_url)
            reviews = self._get_paginated(reviews_url, use_cache=False)
            comments = self._get_paginated(comments_url, use_cache=False)

            # Check if I've already reviewed
            my_reviews = [r for r in reviews if r['user']['login'] == self.username]
            my_comments = [c for c in comments if c['user']['login'] == self.username]

            # Track if my review was dismissed
            my_review_dismissed = False
            my_previous_review_count = 0

            if my_reviews or my_comments:
                my_previous_review_count = len(my_reviews)

                # Check if my LATEST review was dismissed
                if my_reviews:
                    # Sort by submitted_at to get the latest review
                    sorted_my_reviews = sorted(
                        my_reviews,
                        key=lambda r: r.get('submitted_at', ''),
                        reverse=True
                    )
                    latest_review = sorted_my_reviews[0]

                    if latest_review.get('state') == 'DISMISSED':
                        my_review_dismissed = True
                    else:
                        # Latest review is not dismissed, so I've already reviewed
                        return None
                elif my_comments:
                    # Only have comments, no reviews - I've already reviewed
                    return None

            # Create PR info
            additions = 0
            deletions = 0
            review_count = 0
            requested_my_review = False
            changes_requested = False

            requested_reviewer_logins = set()
            if pr_details_response.status_code == 200:
                pr_details = pr_details_response.json()
                additions = pr_details.get('additions', 0)
                deletions = pr_details.get('deletions', 0)

                # Check if I was requested to review
                requested_reviewers = pr_details.get('requested_reviewers', [])
                requested_reviewer_logins = {r['login'] for r in requested_reviewers}
                requested_my_review = self.username in requested_reviewer_logins

                # Apply file filtering if enabled - check cache first
                if self.exclude_generated_files:
                    filtered_counts = self._get_filtered_line_counts(repo, pr_number, should_cache=True)
                    if filtered_counts:
                        additions = filtered_counts['additions']
                        deletions = filtered_counts['deletions']

            # Count unique reviewers and check for active changes requested
            unique_reviewers = set()
            pr_author = pr['user']['login']

            # Track all reviews (including dismissed ones - we need them to find latest state)
            valid_reviews = []
            for review in reviews:
                reviewer = review['user']['login']
                submitted_at = review.get('submitted_at')

                # Skip reviews without timestamps
                if not submitted_at:
                    continue

                # Exclude PR author, myself, and excluded users from review tracking
                if reviewer != pr_author and reviewer != self.username and reviewer not in self.excluded_users:
                    unique_reviewers.add(reviewer)
                    valid_reviews.append(review)

            # Group reviews by reviewer
            reviews_by_reviewer = defaultdict(list)
            for review in valid_reviews:
                reviewer = review['user']['login']
                reviews_by_reviewer[reviewer].append(review)

            # Check if any reviewer has an active change request
            # A change request is ACTIVE if:
            #   - The reviewer has at least one CHANGES_REQUESTED review
            #   - AND has NOT submitted an APPROVED review after the last CHANGES_REQUESTED
            #   - AND the review has NOT been DISMISSED
            #   - AND the reviewer is NOT in requested_reviewers (which means their review is outdated)
            # Note: COMMENTED reviews do NOT clear a change request!
            # Note: Being re-requested (in requested_reviewers) means previous reviews are outdated
            changes_requested = False

            for reviewer, reviewer_reviews in reviews_by_reviewer.items():
                # Skip reviewers who are in requested_reviewers - their previous reviews are outdated
                # When new commits are pushed that address concerns, reviewers are re-requested
                # and their old CHANGES_REQUESTED reviews are no longer considered active
                if reviewer in requested_reviewer_logins:
                    continue

                # Sort by submitted_at (chronological order)
                sorted_reviews = sorted(
                    reviewer_reviews,
                    key=lambda r: r.get('submitted_at', ''),
                    reverse=False  # oldest first
                )

                # Check if there's an active change request
                has_change_request = False
                last_changes_requested_time = None

                for review in sorted_reviews:
                    state = review.get('state')
                    submitted_at = review.get('submitted_at', '')

                    if state == 'CHANGES_REQUESTED':
                        has_change_request = True
                        last_changes_requested_time = submitted_at
                    elif state == 'APPROVED' and last_changes_requested_time:
                        # APPROVED after CHANGES_REQUESTED clears the change request
                        if submitted_at > last_changes_requested_time:
                            has_change_request = False
                    elif state == 'DISMISSED':
                        # DISMISSED clears any change request
                        has_change_request = False

                if has_change_request:
                    changes_requested = True
                    break

            review_count = len(unique_reviewers)

            # Extract label names
            labels = []
            if pr_details_response.status_code == 200:
                pr_details = pr_details_response.json()
                labels = [label['name'] for label in pr_details.get('labels', [])]

            return {
                'number': pr_number,
                'title': pr['title'],
                'url': pr['html_url'],
                'repo': repo,
                'additions': additions,
                'deletions': deletions,
                'created_at': pr['created_at'],
                'updated_at': pr['updated_at'],
                'review_count': review_count,
                'requested_my_review': requested_my_review,
                'changes_requested': changes_requested,
                'labels': labels,
                'my_review_dismissed': my_review_dismissed,
                'my_previous_review_count': my_previous_review_count
            }

        except Exception as e:
            logging.warning(f"Error checking PR #{pr_number}: {e}")
            return None

    def _has_reviewed_pr(self, repo: str, pr: Dict) -> bool:
        """Check if the user has already reviewed a PR.

        Args:
            repo: Repository name
            pr: PR data

        Returns:
            True if the user has reviewed the PR, False otherwise
        """
        pr_number = pr['number']
        reviews_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/reviews"
        comments_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/comments"

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                future_reviews = executor.submit(self._get_paginated, reviews_url, use_cache=False)
                future_comments = executor.submit(self._get_paginated, comments_url, use_cache=False)

                reviews = future_reviews.result()
                review_comments = future_comments.result()

                my_reviews = [r for r in reviews if r['user']['login'] == self.username]
                my_comments = [c for c in review_comments if c['user']['login'] == self.username]

                return bool(my_reviews or my_comments)

        except Exception as e:
            logging.warning(f"Error checking reviews for PR #{pr_number}: {e}")
            return False

    def _create_pr_info(self, repo: str, pr: Dict) -> Dict:
        """Create a PR info dictionary with line counts.

        Args:
            repo: Repository name
            pr: PR data

        Returns:
            Dictionary with PR information
        """
        pr_number = pr['number']
        pr_details_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
        reviews_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/reviews"

        additions = 0
        deletions = 0
        review_count = 0
        requested_my_review = False
        requested_reviewer_logins = set()

        try:
            # Fetch PR details and reviews in parallel
            with ThreadPoolExecutor(max_workers=2) as executor:
                future_details = executor.submit(self.api_client.get, pr_details_url)
                future_reviews = executor.submit(self._get_paginated, reviews_url, use_cache=False)

                pr_details_response = future_details.result()
                if pr_details_response.status_code == 200:
                    pr_details = pr_details_response.json()
                    additions = pr_details.get('additions', 0)
                    deletions = pr_details.get('deletions', 0)

                    # Check if I was requested to review this PR
                    requested_reviewers = pr_details.get('requested_reviewers', [])
                    requested_reviewer_logins = {r['login'] for r in requested_reviewers}
                    requested_my_review = self.username in requested_reviewer_logins

                    # Apply file filtering if enabled
                    if self.exclude_generated_files:
                        filtered_counts = self._get_filtered_line_counts(repo, pr_number, should_cache=False)
                        if filtered_counts:
                            additions = filtered_counts['additions']
                            deletions = filtered_counts['deletions']

                # Count unique reviewers (excluding PR author and excluded users)
                reviews = future_reviews.result()
                unique_reviewers = set()
                pr_author = pr['user']['login']

                # Track all reviews (including dismissed ones - we need them to find latest state)
                valid_reviews = []
                for review in reviews:
                    reviewer = review['user']['login']
                    submitted_at = review.get('submitted_at')

                    # Skip reviews without timestamps
                    if not submitted_at:
                        continue

                    if reviewer != pr_author and reviewer not in self.excluded_users:
                        unique_reviewers.add(reviewer)
                        valid_reviews.append(review)

                # Group reviews by reviewer
                reviews_by_reviewer = defaultdict(list)
                for review in valid_reviews:
                    reviewer = review['user']['login']
                    reviews_by_reviewer[reviewer].append(review)

                # Check if any reviewer's latest review is CHANGES_REQUESTED
                # A reviewer's change request is cleared if they submit ANY new review
                # (APPROVED, COMMENTED, DISMISSED, etc. - anything other than CHANGES_REQUESTED)
                # Also skip if the reviewer is in requested_reviewers (review was re-requested)
                changes_requested = False

                for reviewer, reviewer_reviews in reviews_by_reviewer.items():
                    # Skip reviewers who are still in the requested_reviewers list
                    # (their review was re-requested, clearing the previous state)
                    if reviewer in requested_reviewer_logins:
                        continue

                    # Sort by submitted_at to get the most recent
                    sorted_reviews = sorted(
                        reviewer_reviews,
                        key=lambda r: r.get('submitted_at', ''),
                        reverse=True
                    )
                    if sorted_reviews:
                        latest_review = sorted_reviews[0]
                        review_state = latest_review.get('state')

                        # Only count as active change request if their LATEST review is CHANGES_REQUESTED
                        # (DISMISSED, APPROVED, COMMENTED all clear the change request)
                        if review_state == 'CHANGES_REQUESTED':
                            changes_requested = True
                            break

                review_count = len(unique_reviewers)

        except Exception as e:
            logging.warning(f"Error fetching PR details for #{pr_number}: {e}")

        return {
            'number': pr_number,
            'title': pr['title'],
            'url': pr['html_url'],
            'repo': repo,
            'additions': additions,
            'deletions': deletions,
            'created_at': pr['created_at'],
            'updated_at': pr['updated_at'],
            'review_count': review_count,
            'requested_my_review': requested_my_review,
            'changes_requested': changes_requested
        }

    def get_my_open_prs(self) -> List[Dict]:
        """Fetch my open PRs from analyzed repositories that are ready for review.

        Returns:
            List of my open PRs with details
        """
        my_prs = []

        print("\nFetching my open PRs...")
        for repo in self.repositories:
            url = f"https://api.github.com/repos/{repo}/pulls"

            try:
                open_prs = self._get_paginated(url, {
                    'state': 'open',
                    'sort': 'updated',
                    'direction': 'desc'
                }, use_cache=False)

                for pr in open_prs:
                    pr_author = pr['user']['login']

                    # Only include my PRs
                    if pr_author != self.username:
                        continue

                    # Skip draft PRs
                    if pr.get('draft', False):
                        continue

                    # Check for required label (if specified)
                    if self.required_pr_label:
                        pr_labels = [label['name'] for label in pr.get('labels', [])]
                        if self.required_pr_label not in pr_labels:
                            continue

                    # Get PR details
                    pr_number = pr['number']
                    pr_details_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
                    reviews_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/reviews"

                    try:
                        # Fetch PR details and reviews in parallel
                        with ThreadPoolExecutor(max_workers=2) as executor:
                            future_details = executor.submit(self.api_client.get, pr_details_url)
                            future_reviews = executor.submit(self._get_paginated, reviews_url, use_cache=False)

                            pr_details_response = future_details.result()
                            reviews = future_reviews.result()

                        additions = 0
                        deletions = 0
                        requested_reviewers = []
                        review_count = 0
                        labels = []

                        if pr_details_response.status_code == 200:
                            pr_details = pr_details_response.json()
                            additions = pr_details.get('additions', 0)
                            deletions = pr_details.get('deletions', 0)

                            # Get requested reviewers
                            requested_reviewers_list = pr_details.get('requested_reviewers', [])
                            requested_reviewers = [r['login'] for r in requested_reviewers_list]

                            # Get labels
                            labels = [label['name'] for label in pr_details.get('labels', [])]

                            # Apply file filtering if enabled
                            if self.exclude_generated_files:
                                filtered_counts = self._get_filtered_line_counts(repo, pr_number, should_cache=True)
                                if filtered_counts:
                                    additions = filtered_counts['additions']
                                    deletions = filtered_counts['deletions']

                        # Count unique reviewers and check for active change requests (excluding me and excluded users)
                        unique_reviewers = set()
                        requested_reviewer_logins = set(requested_reviewers)
                        reviews_by_reviewer = defaultdict(list)

                        for review in reviews:
                            reviewer = review['user']['login']
                            if reviewer != self.username and reviewer not in self.excluded_users:
                                unique_reviewers.add(reviewer)
                                reviews_by_reviewer[reviewer].append(review)

                        review_count = len(unique_reviewers)

                        # Check for active change requests
                        # A change request is ACTIVE if:
                        #   - The reviewer has at least one CHANGES_REQUESTED review
                        #   - AND has NOT submitted an APPROVED review after the last CHANGES_REQUESTED
                        #   - AND the review has NOT been DISMISSED
                        #   - AND the reviewer is NOT in requested_reviewers (which means their review is outdated)
                        # Note: COMMENTED reviews do NOT clear a change request!
                        # Note: Being re-requested (in requested_reviewers) means previous reviews are outdated
                        has_change_requests = False
                        for reviewer, reviewer_reviews in reviews_by_reviewer.items():
                            # Skip reviewers who are in requested_reviewers - their previous reviews are outdated
                            # When new commits are pushed that address concerns, reviewers are re-requested
                            # and their old CHANGES_REQUESTED reviews are no longer considered active
                            if reviewer in requested_reviewer_logins:
                                continue

                            # Sort by submitted_at (chronological order)
                            sorted_reviews = sorted(
                                reviewer_reviews,
                                key=lambda r: r.get('submitted_at', ''),
                                reverse=False  # oldest first
                            )

                            # Check if there's an active change request
                            has_change_request = False
                            last_changes_requested_time = None

                            for review in sorted_reviews:
                                state = review.get('state')
                                submitted_at = review.get('submitted_at', '')

                                if state == 'CHANGES_REQUESTED':
                                    has_change_request = True
                                    last_changes_requested_time = submitted_at
                                elif state == 'APPROVED' and last_changes_requested_time:
                                    # APPROVED after CHANGES_REQUESTED clears the change request
                                    if submitted_at > last_changes_requested_time:
                                        has_change_request = False
                                elif state == 'DISMISSED':
                                    # DISMISSED clears any change request
                                    has_change_request = False

                            if has_change_request:
                                has_change_requests = True
                                break

                        my_prs.append({
                            'number': pr_number,
                            'title': pr['title'],
                            'url': pr['html_url'],
                            'repo': repo,
                            'additions': additions,
                            'deletions': deletions,
                            'created_at': pr['created_at'],
                            'updated_at': pr['updated_at'],
                            'review_count': review_count,
                            'requested_reviewers': requested_reviewers,
                            'labels': labels,
                            'has_change_requests': has_change_requests
                        })
                    except Exception as e:
                        logging.warning(f"Error fetching PR details for #{pr_number}: {e}")

            except Exception as e:
                logging.error(f"Error fetching my open PRs from {repo}: {e}")

        return my_prs

    def save_cache(self):
        """Save the cache to disk."""
        self.cache_manager.save_cache()