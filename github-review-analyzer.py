#!/usr/bin/env python3
"""
GitHub PR Review Analyzer
Analyzes PR review activity between users in specified repositories.
"""

import os
import sys
import logging
import json
import hashlib
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Set, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Configure logging (can be overridden by LOG_LEVEL environment variable)
log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%m/%d/%Y %I:%M:%S %p'
)


@dataclass
class ReviewStats:
    """Statistics for reviews between two users."""
    prs_reviewed: int = 0
    lines_reviewed: int = 0
    additions_reviewed: int = 0  # Total +lines reviewed
    deletions_reviewed: int = 0  # Total -lines reviewed
    review_events: int = 0  # approvals, change requests, etc.
    comments: int = 0
    prs: List[Dict] = field(default_factory=list)


class GitHubReviewAnalyzer:
    """Analyzes GitHub PR reviews for a given user across repositories."""

    def __init__(self, username: str, token: str = None, cache_file: str = '.github_review_cache.json', use_cache: bool = True, excluded_users: Set[str] = None, required_pr_label: str = None, sort_by: str = 'total_prs'):
        self.username = username
        self.token = token or os.environ.get('GITHUB_TOKEN')
        self.session = requests.Session()
        self.cache_file = cache_file
        self.use_cache = use_cache
        self.cache = self._load_cache()
        self.excluded_users = excluded_users or set()
        self.required_pr_label = required_pr_label
        self.sort_by = sort_by

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
            logging.info(f"Initialized analyzer for user '{username}' with GitHub token")
        else:
            logging.warning("No GitHub token provided. Rate limits will be much lower.")
            logging.warning("Set GITHUB_TOKEN environment variable or pass token as argument.")

        # Statistics: user -> ReviewStats
        self.reviewed_by_me: Dict[str, ReviewStats] = defaultdict(ReviewStats)
        self.reviewed_by_others: Dict[str, ReviewStats] = defaultdict(ReviewStats)

        # Store repositories for later use
        self.repositories: List[str] = []

        # Thread safety for parallel processing
        self._stats_lock = Lock()

    def _get_cache_key(self, repo: str, endpoint: str, params: Dict = None) -> str:
        """Generate a cache key for an API call."""
        key_data = f"{repo}:{endpoint}:{json.dumps(params, sort_keys=True) if params else ''}"
        return hashlib.md5(key_data.encode()).hexdigest()

    def _load_cache(self) -> Dict:
        """Load cache from file."""
        if not self.use_cache or not os.path.exists(self.cache_file):
            return {}

        try:
            with open(self.cache_file, 'r') as f:
                cache = json.load(f)
                logging.info(f"Loaded cache from {self.cache_file} with {len(cache)} entries")
                return cache
        except Exception as e:
            logging.warning(f"Failed to load cache: {e}")
            return {}

    def _save_cache(self):
        """Save cache to file."""
        if not self.use_cache:
            return

        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f, indent=2)
                logging.info(f"Saved cache to {self.cache_file} with {len(self.cache)} entries")
        except Exception as e:
            logging.warning(f"Failed to save cache: {e}")

    def _get_from_cache(self, cache_key: str) -> Optional[List[Dict]]:
        """Get data from cache if it exists."""
        if not self.use_cache or cache_key not in self.cache:
            return None

        cached_entry = self.cache[cache_key]
        cached_time = datetime.fromisoformat(cached_entry['timestamp'])
        age_hours = (datetime.now() - cached_time).total_seconds() / 3600

        logging.debug(f"Using cached data (age: {age_hours:.1f} hours)")
        return cached_entry['data']

    def _put_in_cache(self, cache_key: str, data: List[Dict]):
        """Store data in cache."""
        if not self.use_cache:
            return

        self.cache[cache_key] = {
            'timestamp': datetime.now().isoformat(),
            'data': data
        }

    def get_paginated(self, url: str, params: Dict = None, use_cache: bool = True,
                      should_continue: Optional[Callable[[List[Dict]], bool]] = None) -> List[Dict]:
        """Fetch all pages of a paginated GitHub API endpoint with caching support.

        Args:
            url: The API endpoint URL
            params: Query parameters
            use_cache: Whether to use caching
            should_continue: Optional callback function that takes a page of results and returns
                           False to stop pagination early, True to continue
        """
        # Generate cache key
        cache_params = params.copy() if params else {}
        cache_params.pop('page', None)  # Don't include page in cache key
        cache_params.pop('per_page', None)  # Don't include per_page in cache key
        cache_key = self._get_cache_key('', url, cache_params)

        # Try to get from cache
        if use_cache:
            cached_data = self._get_from_cache(cache_key)
            if cached_data is not None:
                logging.debug(f"Cache hit for {url}")
                return cached_data

        # Fetch from API
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

        # Store in cache
        if use_cache:
            self._put_in_cache(cache_key, results)

        return results

    def analyze_repository(self, repo: str, months: int = 3):
        """Analyze PRs in a repository for the last N months based on merge date."""
        logging.info(f"Analyzing repository: {repo}")

        # Store repository for later use
        if repo not in self.repositories:
            self.repositories.append(repo)

        since_date = datetime.now() - timedelta(days=months * 30)
        logging.info(f"Looking for PRs merged since: {since_date.strftime('%Y-%m-%d')}")

        # Fetch PRs with early termination
        url = f"https://api.github.com/repos/{repo}/pulls"

        print(f"Fetching pull requests from {repo}...")
        all_prs = []
        total_fetched = 0

        # Fetch both open and closed PRs
        # For open PRs, we'll include them as they might be under review
        # For closed PRs, we'll filter by merged_at date
        for state in ['open', 'closed']:
            print(f"  Fetching {state} PRs...", end='', flush=True)
            page_count = [0]  # Use list to allow modification in nested function

            def count_pages(page_data: List[Dict]) -> bool:
                """Count pages as we fetch them."""
                page_count[0] += 1
                return True

            # Sort by updated - we fetch all PRs and filter by merged_at date later
            # Note: We don't use early termination because PRs are sorted by 'updated' time,
            # not 'merged_at' time. Early termination could cause us to miss PRs that were
            # merged recently but haven't been updated recently.
            prs = self.get_paginated(url, {
                'state': state,
                'sort': 'updated',
                'direction': 'desc'
            }, should_continue=count_pages)

            all_prs.extend(prs)
            total_fetched += len(prs)
            print(f" fetched {len(prs)} PRs ({page_count[0]} pages)")

        # Filter PRs by merge date (or include open PRs), draft status, and labels
        recent_prs = []
        filtered_draft = 0
        filtered_label = 0

        for pr in all_prs:
            # First check if PR is in our date range
            if pr['state'] == 'open':
                # Include all open PRs as they're currently under review
                pass  # Continue to other checks
            elif pr.get('merged_at'):
                # For merged PRs, check merge date
                merged_date = datetime.strptime(pr['merged_at'], '%Y-%m-%dT%H:%M:%SZ')
                if merged_date < since_date:
                    continue  # Skip PRs outside date range
            else:
                continue  # Skip PRs that are closed but not merged

            # Skip draft PRs
            if pr.get('draft', False):
                logging.debug(f"Skipping draft PR #{pr['number']}")
                filtered_draft += 1
                continue

            # Check for required label if specified
            if self.required_pr_label:
                pr_labels = [label['name'] for label in pr.get('labels', [])]
                if self.required_pr_label not in pr_labels:
                    logging.debug(f"Skipping PR #{pr['number']} - missing required label '{self.required_pr_label}'")
                    filtered_label += 1
                    continue

            recent_prs.append(pr)

        filter_msg = f"Found {len(recent_prs)} PRs in the last {months} months (filtered from {total_fetched} fetched)"
        if filtered_draft > 0:
            filter_msg += f", {filtered_draft} draft PRs filtered"
        if filtered_label > 0:
            filter_msg += f", {filtered_label} PRs without required label filtered"
        print(filter_msg)

        if not recent_prs:
            logging.info(f"No PRs found for repository: {repo}")
            return

        # Process PRs in parallel
        print(f"Analyzing {len(recent_prs)} PRs...")
        completed = 0
        max_workers = min(10, len(recent_prs))  # Limit concurrent requests

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all PR analysis tasks
            future_to_pr = {
                executor.submit(self._analyze_pr, repo, pr): pr
                for pr in recent_prs
            }

            # Process completed tasks as they finish
            for future in as_completed(future_to_pr):
                pr = future_to_pr[future]
                try:
                    future.result()
                    completed += 1

                    # Show progress every 10 PRs or at completion
                    if completed % 10 == 0 or completed == len(recent_prs):
                        print(f"  Progress: {completed}/{len(recent_prs)} PRs analyzed", flush=True)

                except Exception as e:
                    logging.error(f"Error analyzing PR #{pr['number']}: {e}", exc_info=True)
                    completed += 1

        print(f"Completed analysis of {repo}")
        logging.info(f"Completed analysis of repository: {repo}")

    def _analyze_pr(self, repo: str, pr: Dict):
        """Analyze a single PR for review activity."""
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

        # Only cache closed PRs since open PRs can still change
        should_cache = (pr_state == 'closed')

        # Fetch all data in parallel
        additions = pr.get('additions', 0)
        deletions = pr.get('deletions', 0)
        reviews = []
        review_comments = []

        with ThreadPoolExecutor(max_workers=3) as executor:
            # Submit all requests in parallel
            future_details = executor.submit(self.session.get, pr_details_url)
            future_reviews = executor.submit(self.get_paginated, reviews_url, use_cache=should_cache)
            future_comments = executor.submit(self.get_paginated, comments_url, use_cache=should_cache)

            # Get PR details
            try:
                pr_details_response = future_details.result()
                if pr_details_response.status_code == 200:
                    pr_details = pr_details_response.json()
                    additions = pr_details.get('additions', 0)
                    deletions = pr_details.get('deletions', 0)
                    pr_state = pr_details.get('state', pr_state)
                else:
                    logging.warning(f"Failed to fetch PR details for #{pr_number}, using list data")
            except Exception as e:
                logging.warning(f"Error fetching PR details for #{pr_number}: {e}")

            # Get reviews and comments
            try:
                reviews = future_reviews.result()
            except Exception as e:
                logging.warning(f"Error fetching reviews for #{pr_number}: {e}")

            try:
                review_comments = future_comments.result()
            except Exception as e:
                logging.warning(f"Error fetching comments for #{pr_number}: {e}")

        total_lines = additions + deletions

        logging.debug(f"Analyzing PR #{pr_number}: {pr_title} (by {pr_author}, +{additions}/-{deletions} lines, state: {pr_state})")

        # Track unique reviewers and their activity
        reviewer_activity = defaultdict(lambda: {
            'review_events': 0,
            'comments': 0,
            'reviews': set()  # Track unique review IDs to avoid double counting
        })

        # Process reviews
        for review in reviews:
            reviewer = review['user']['login']
            review_id = review['id']

            if reviewer == self.username or reviewer == pr_author or reviewer in self.excluded_users:
                continue  # Skip self-reviews and excluded users

            reviewer_activity[reviewer]['reviews'].add(review_id)
            reviewer_activity[reviewer]['review_events'] += 1

        # Process review comments
        for comment in review_comments:
            commenter = comment['user']['login']

            if commenter == self.username or commenter == pr_author or commenter in self.excluded_users:
                continue

            reviewer_activity[commenter]['comments'] += 1

        # Determine if I reviewed this PR or if others reviewed my PR
        pr_info = {
            'title': pr_title,
            'url': pr_url,
            'number': pr_number,
            'lines': total_lines,
            'additions': additions,
            'deletions': deletions
        }

        # Update stats with thread safety
        with self._stats_lock:
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
                # I reviewed someone else's PR - check if I actually reviewed it
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
        """Fetch open PRs from analyzed repositories that need review from the user."""
        prs_by_author = defaultdict(list)

        print("\nFetching currently open PRs...")
        for repo in self.repositories:
            url = f"https://api.github.com/repos/{repo}/pulls"

            try:
                # Fetch open PRs (don't use cache for open PRs as they change frequently)
                open_prs = self.get_paginated(url, {
                    'state': 'open',
                    'sort': 'updated',
                    'direction': 'desc'
                }, use_cache=False)

                for pr in open_prs:
                    pr_author = pr['user']['login']

                    # Skip my own PRs
                    if pr_author == self.username:
                        continue

                    # Skip excluded users
                    if pr_author in self.excluded_users:
                        continue

                    # Skip draft PRs
                    if pr.get('draft', False):
                        continue

                    # Check for required label if specified
                    if self.required_pr_label:
                        pr_labels = [label['name'] for label in pr.get('labels', [])]
                        if self.required_pr_label not in pr_labels:
                            continue

                    # Check if I've already reviewed this PR
                    pr_number = pr['number']
                    pr_details_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
                    reviews_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/reviews"
                    comments_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/comments"

                    try:
                        # Fetch PR details, reviews, and comments in parallel
                        with ThreadPoolExecutor(max_workers=3) as executor:
                            future_details = executor.submit(self.session.get, pr_details_url)
                            future_reviews = executor.submit(self.get_paginated, reviews_url, use_cache=False)
                            future_comments = executor.submit(self.get_paginated, comments_url, use_cache=False)

                            # Get PR details to fetch accurate line counts
                            additions = 0
                            deletions = 0
                            try:
                                pr_details_response = future_details.result()
                                if pr_details_response.status_code == 200:
                                    pr_details = pr_details_response.json()
                                    additions = pr_details.get('additions', 0)
                                    deletions = pr_details.get('deletions', 0)
                                else:
                                    logging.warning(f"Failed to fetch PR details for #{pr_number}")
                            except Exception as e:
                                logging.warning(f"Error fetching PR details for #{pr_number}: {e}")

                            # Get reviews and comments
                            reviews = future_reviews.result()
                            review_comments = future_comments.result()

                            my_reviews = [r for r in reviews if r['user']['login'] == self.username]
                            my_comments = [c for c in review_comments if c['user']['login'] == self.username]

                            # If I haven't reviewed this PR yet, add it to the list
                            if not my_reviews and not my_comments:
                                prs_by_author[pr_author].append({
                                    'number': pr_number,
                                    'title': pr['title'],
                                    'url': pr['html_url'],
                                    'repo': repo,
                                    'additions': additions,
                                    'deletions': deletions,
                                    'created_at': pr['created_at'],
                                    'updated_at': pr['updated_at']
                                })
                    except Exception as e:
                        logging.warning(f"Error checking reviews for PR #{pr_number}: {e}")

            except Exception as e:
                logging.error(f"Error fetching open PRs from {repo}: {e}")

        return prs_by_author

    def print_summary(self):
        """Print a comprehensive summary of review statistics."""
        print("\n" + "="*80)
        print(f"REVIEW SUMMARY FOR {self.username}")
        print("="*80)

        # Get all users involved
        all_users = set(self.reviewed_by_me.keys()) | set(self.reviewed_by_others.keys())

        if not all_users:
            print("\nNo review activity found.")
            return

        # ACTIONABLE SUMMARY: Who should review next PRs
        print("\n" + "="*80)
        print("REVIEW BALANCE & NEXT ACTIONS")
        print("="*80)

        # Calculate review balance for each user
        review_balance = []
        for user in all_users:
            my_reviews = self.reviewed_by_me[user]
            their_reviews = self.reviewed_by_others[user]
            balance = their_reviews.lines_reviewed - my_reviews.lines_reviewed
            total_prs = my_reviews.prs_reviewed + their_reviews.prs_reviewed

            review_balance.append({
                'user': user,
                'balance': balance,
                'they_reviewed': their_reviews.lines_reviewed,
                'they_additions': their_reviews.additions_reviewed,
                'they_deletions': their_reviews.deletions_reviewed,
                'i_reviewed': my_reviews.lines_reviewed,
                'i_additions': my_reviews.additions_reviewed,
                'i_deletions': my_reviews.deletions_reviewed,
                'total_prs': total_prs,
                'their_prs_i_reviewed': my_reviews.prs_reviewed,
                'my_prs_they_reviewed': their_reviews.prs_reviewed
            })

        # Sort by specified column
        sort_key_map = {
            'total_prs': lambda x: x['total_prs'],
            'balance': lambda x: x['balance'],
            'user': lambda x: x['user'].lower(),
            'they_reviewed': lambda x: x['they_reviewed'],
            'i_reviewed': lambda x: x['i_reviewed'],
            'their_prs': lambda x: x['their_prs_i_reviewed'],
            'my_prs': lambda x: x['my_prs_they_reviewed']
        }

        # Default to total_prs if invalid sort_by is provided
        sort_key = sort_key_map.get(self.sort_by, sort_key_map['total_prs'])

        # Sort by user alphabetically (ascending), otherwise descending
        reverse_sort = (self.sort_by != 'user')
        review_balance.sort(key=sort_key, reverse=reverse_sort)

        # ANSI color codes
        GREEN = '\033[92m'
        YELLOW = '\033[93m'
        RED = '\033[91m'
        RESET = '\033[0m'

        # Display table
        print("\nReview Balance (lines reviewed):")
        print(f"{'User':<20} {'Total PRs':<10} {'Their PRs':<12} {'My PRs':<12} {'They reviewed':<25} {'I reviewed':<25} {'Balance':<15} {'Action'}")
        print(f"{'-'*155}")

        for item in review_balance:
            user = item['user']
            balance = item['balance']
            total_prs = item['total_prs']
            they_reviewed = item['they_reviewed']
            they_additions = item['they_additions']
            they_deletions = item['they_deletions']
            i_reviewed = item['i_reviewed']
            i_additions = item['i_additions']
            i_deletions = item['i_deletions']

            # Get PR counts
            their_prs_i_reviewed = item['their_prs_i_reviewed']
            my_prs_they_reviewed = item['my_prs_they_reviewed']

            # Format: +add / -del (without total)
            they_str = f"+{they_additions:,}/-{they_deletions:,}"
            i_str = f"+{i_additions:,}/-{i_deletions:,}"

            # Determine color based on balance
            # Green: I owe them (positive balance)
            # Yellow: They owe me a little (small negative balance)
            # Red: They owe me a lot (large negative balance)
            if balance == 0:
                color = RESET
                action = "✓ Balanced"
                balance_str = "0"
            elif balance > 0:
                color = GREEN
                action = "→ I should review their PRs"
                balance_str = f"+{balance:,}"
            elif balance > -1000:  # Between -1 and -999
                color = YELLOW
                action = "← They should review my PRs"
                balance_str = f"{balance:,}"
            else:  # <= -1000
                color = RED
                action = "← They should review my PRs"
                balance_str = f"{balance:,}"

            print(f"{color}{user:<20} {total_prs:<10} {their_prs_i_reviewed:<12} {my_prs_they_reviewed:<12} {they_str:<25} {i_str:<25} {balance_str:<15} {action}{RESET}")

        # Get open PRs that need review
        open_prs_by_author = self.get_open_prs_needing_review()

        if open_prs_by_author:
            print("\n" + "="*80)
            print("OPEN PRs THAT NEED YOUR REVIEW")
            print("="*80)

            # Sort authors by review balance (prioritize those I owe reviews to)
            # Higher positive balance = I owe them more reviews = higher priority
            authors_with_prs = [(user, open_prs_by_author[user]) for user in open_prs_by_author]
            authors_with_prs.sort(key=lambda x: next(
                (item['balance'] for item in review_balance if item['user'] == x[0]),
                0
            ), reverse=True)

            total_prs_to_review = sum(len(prs) for prs in open_prs_by_author.values())
            print(f"\nYou have {total_prs_to_review} open PR(s) to review:\n")

            for author, prs in authors_with_prs:
                balance_info = next((item for item in review_balance if item['user'] == author), None)

                # Determine color and priority message
                if balance_info:
                    balance = balance_info['balance']

                    if balance == 0:
                        color = RESET
                        priority = ""
                    elif balance > 0:
                        color = GREEN
                        priority = f"(Priority: You owe them {balance:,} lines)"
                    elif balance > -1000:
                        color = YELLOW
                        priority = ""
                    else:  # <= -1000
                        color = RED
                        priority = ""
                else:
                    color = RESET
                    priority = ""

                print(f"{color}From {author} {priority}:{RESET}")
                for pr in prs:
                    total_lines = pr['additions'] + pr['deletions']
                    repo_short = pr['repo'].split('/')[-1]
                    print(f"  • [{repo_short}] #{pr['number']}: {pr['title']}")
                    print(f"    {pr['url']} (+{pr['additions']:,} / -{pr['deletions']:,} lines)")
                print()
        else:
            print("\n" + "="*80)
            print("OPEN PRs THAT NEED YOUR REVIEW")
            print("="*80)
            print("\nNo open PRs found that need your review.")

        # Rest of the detailed summary continues below
        print("\n" + "="*80)
        print("DETAILED REVIEW HISTORY")
        print("="*80)

        # Sort users by total interaction
        sorted_users = sorted(
            all_users,
            key=lambda u: (
                self.reviewed_by_me[u].prs_reviewed +
                self.reviewed_by_others[u].prs_reviewed
            ),
            reverse=True
        )

        for user in sorted_users:
            my_reviews = self.reviewed_by_me[user]
            their_reviews = self.reviewed_by_others[user]

            print(f"\n{'─'*80}")
            print(f"👤 {user}")
            print(f"{'─'*80}")

            # Summary table
            print(f"\n{'Metric':<30} {'I reviewed':<20} {'They reviewed':<20}")
            print(f"{'-'*70}")
            print(f"{'PRs reviewed':<30} {my_reviews.prs_reviewed:<20} {their_reviews.prs_reviewed:<20}")
            print(f"{'Lines reviewed (total)':<30} {my_reviews.lines_reviewed:<20} {their_reviews.lines_reviewed:<20}")
            print(f"{'  +lines (additions)':<30} {my_reviews.additions_reviewed:<20} {their_reviews.additions_reviewed:<20}")
            print(f"{'  -lines (deletions)':<30} {my_reviews.deletions_reviewed:<20} {their_reviews.deletions_reviewed:<20}")
            print(f"{'Review events':<30} {my_reviews.review_events:<20} {their_reviews.review_events:<20}")
            print(f"{'Comments written':<30} {my_reviews.comments:<20} {their_reviews.comments:<20}")

            # Calculate offsets
            line_offset = my_reviews.lines_reviewed - their_reviews.lines_reviewed
            additions_offset = my_reviews.additions_reviewed - their_reviews.additions_reviewed
            deletions_offset = my_reviews.deletions_reviewed - their_reviews.deletions_reviewed
            offset_sign = "+" if line_offset >= 0 else ""
            additions_sign = "+" if additions_offset >= 0 else ""
            deletions_sign = "+" if deletions_offset >= 0 else ""
            print(f"\n📊 Line Review Offset:")
            print(f"   Total: {offset_sign}{line_offset:,} lines (positive = you reviewed more of their code)")
            print(f"   +lines: {additions_sign}{additions_offset:,}")
            print(f"   -lines: {deletions_sign}{deletions_offset:,}")

            # List PRs I reviewed
            if my_reviews.prs:
                print(f"\n📝 PRs I reviewed ({len(my_reviews.prs)}):")
                for pr in my_reviews.prs:
                    print(f"   • #{pr['number']}: {pr['title']}")
                    print(f"     {pr['url']} (+{pr['additions']:,} / -{pr['deletions']:,} lines)")

            # List PRs they reviewed
            if their_reviews.prs:
                print(f"\n📝 PRs they reviewed ({len(their_reviews.prs)}):")
                for pr in their_reviews.prs:
                    print(f"   • #{pr['number']}: {pr['title']}")
                    print(f"     {pr['url']} (+{pr['additions']:,} / -{pr['deletions']:,} lines)")

        # Overall statistics
        print(f"\n{'='*80}")
        print("OVERALL STATISTICS")
        print(f"{'='*80}")

        total_reviewed_by_me = sum(s.prs_reviewed for s in self.reviewed_by_me.values())
        total_reviewed_by_others = sum(s.prs_reviewed for s in self.reviewed_by_others.values())
        total_lines_by_me = sum(s.lines_reviewed for s in self.reviewed_by_me.values())
        total_lines_by_others = sum(s.lines_reviewed for s in self.reviewed_by_others.values())
        total_additions_by_me = sum(s.additions_reviewed for s in self.reviewed_by_me.values())
        total_additions_by_others = sum(s.additions_reviewed for s in self.reviewed_by_others.values())
        total_deletions_by_me = sum(s.deletions_reviewed for s in self.reviewed_by_me.values())
        total_deletions_by_others = sum(s.deletions_reviewed for s in self.reviewed_by_others.values())

        print(f"\nTotal PRs I reviewed: {total_reviewed_by_me}")
        print(f"Total PRs others reviewed of mine: {total_reviewed_by_others}")
        print(f"\nTotal lines I reviewed: {total_lines_by_me:,}")
        print(f"  +lines: {total_additions_by_me:,}")
        print(f"  -lines: {total_deletions_by_me:,}")
        print(f"\nTotal lines others reviewed: {total_lines_by_others:,}")
        print(f"  +lines: {total_additions_by_others:,}")
        print(f"  -lines: {total_deletions_by_others:,}")
        print(f"\nNumber of collaborators: {len(all_users)}")


def main():
    """Main entry point for the script."""
    # Load environment variables from .env file if it exists
    load_dotenv()

    print("GitHub PR Review Analyzer")
    print("="*80)

    # Get username from environment or prompt
    username = os.environ.get('GITHUB_USERNAME')
    if not username:
        username = input("\nEnter your GitHub username: ").strip()

    if not username:
        logging.error("Username is required")
        sys.exit(1)

    logging.info(f"Starting analysis for user: {username}")

    # Get token from environment or prompt (optional but recommended)
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        token_input = input("\nEnter GitHub token (or press Enter to skip): ").strip()
        if token_input:
            token = token_input

    # Get repositories from environment or prompt
    repos = []
    repos_env = os.environ.get('GITHUB_REPOS')
    if repos_env:
        # Parse comma-separated list from environment
        repos = [r.strip() for r in repos_env.split(',') if r.strip()]
        logging.info(f"Using repositories from environment: {', '.join(repos)}")
    else:
        print("\nEnter repositories (format: owner/repo, one per line)")
        print("Press Enter on an empty line when done")
        print("Example: ls1intum/Artemis")

        while True:
            repo = input("Repository: ").strip()
            if not repo:
                break
            repos.append(repo)

    if not repos:
        logging.error("At least one repository is required")
        sys.exit(1)

    # Get time range from environment or prompt
    months_env = os.environ.get('ANALYSIS_MONTHS')
    if months_env:
        try:
            months = int(months_env)
            logging.info(f"Using time range from environment: {months} months")
        except ValueError:
            logging.warning(f"Invalid ANALYSIS_MONTHS value '{months_env}', using default: 3")
            months = 3
    else:
        months_input = input("\nAnalyze last N months [default: 3]: ").strip()
        months = int(months_input) if months_input else 3

    # Check if caching should be disabled
    use_cache = os.environ.get('USE_CACHE', 'true').lower() not in ('false', '0', 'no')

    # Get excluded users from environment or prompt
    excluded_users = set()
    excluded_env = os.environ.get('EXCLUDED_USERS')
    if excluded_env:
        # Parse comma-separated list from environment
        excluded_users = set(u.strip() for u in excluded_env.split(',') if u.strip())
        logging.info(f"Excluding users: {', '.join(excluded_users)}")
    else:
        exclude_input = input("\nEnter users to exclude (comma-separated, or press Enter to skip): ").strip()
        if exclude_input:
            excluded_users = set(u.strip() for u in exclude_input.split(',') if u.strip())
            logging.info(f"Excluding users: {', '.join(excluded_users)}")

    # Get required PR label from environment
    required_pr_label = os.environ.get('REQUIRED_PR_LABEL')
    if required_pr_label:
        required_pr_label = required_pr_label.strip()
        logging.info(f"Filtering PRs by label: '{required_pr_label}'")

    # Get sort column from environment
    sort_by = os.environ.get('SORT_BY', 'total_prs').strip().lower()
    valid_sort_options = ['total_prs', 'balance', 'user', 'they_reviewed', 'i_reviewed', 'their_prs', 'my_prs']
    if sort_by not in valid_sort_options:
        logging.warning(f"Invalid SORT_BY value '{sort_by}', using default: total_prs")
        logging.warning(f"Valid options: {', '.join(valid_sort_options)}")
        sort_by = 'total_prs'
    else:
        logging.info(f"Sorting review balance table by: {sort_by}")

    # Create analyzer
    analyzer = GitHubReviewAnalyzer(username, token, use_cache=use_cache, excluded_users=excluded_users, required_pr_label=required_pr_label, sort_by=sort_by)

    # Analyze each repository
    logging.info(f"Starting analysis of {len(repos)} repository/repositories")
    for repo in repos:
        try:
            analyzer.analyze_repository(repo, months)
        except Exception as e:
            logging.error(f"Error analyzing {repo}: {e}", exc_info=True)
            continue

    # Save cache
    analyzer._save_cache()

    # Print summary
    logging.info("Analysis complete, generating summary...")
    analyzer.print_summary()


if __name__ == "__main__":
    main()
