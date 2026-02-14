"""Open PR review methods for GitHubReviewAnalyzer."""

import logging
from typing import Dict, List, Optional
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed


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

            # Batch fetch project states for all open PRs (if needed)
            project_states = {}
            if self.required_project_state and open_prs:
                project_states = self._batch_fetch_project_states(repo, open_prs)

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

                # Check for required label or project state (OR logic)
                if self.required_pr_label or self.required_project_state:
                    pr_labels = [label['name'] for label in pr.get('labels', [])]

                    has_required_label = self.required_pr_label and self.required_pr_label in pr_labels
                    has_required_state = False
                    if self.required_project_state and pr['number'] in project_states:
                        has_required_state = self.required_project_state in project_states[pr['number']]

                    if not (has_required_label or has_required_state):
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
