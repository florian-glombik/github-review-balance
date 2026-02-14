"""PR processing methods for GitHubReviewAnalyzer."""

import logging
from typing import Dict, List
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..models import ReviewStats


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
