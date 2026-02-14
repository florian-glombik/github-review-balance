"""My open PRs methods for GitHubReviewAnalyzer."""

import logging
from typing import Dict, List
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed


def get_my_open_prs(self, apply_label_filter: bool = True) -> List[Dict]:
    """Fetch my open PRs from analyzed repositories.

    Args:
        apply_label_filter: If True, filter PRs by required_pr_label or required_project_state.
                           If False, return all open PRs (for PR Summary).

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

            # Batch fetch project states (always fetch for PR summary categorization)
            project_states = {}
            if open_prs:
                project_states = self._batch_fetch_project_states(repo, open_prs)

            for pr in open_prs:
                pr_author = pr['user']['login']

                # Only include my PRs
                if pr_author != self.username:
                    continue

                # Skip draft PRs (only when filtering is enabled; include drafts in PR Summary)
                if apply_label_filter and pr.get('draft', False):
                    continue

                # Check for required label or project state (if specified and filtering is enabled)
                if apply_label_filter and (self.required_pr_label or self.required_project_state):
                    pr_labels = [label['name'] for label in pr.get('labels', [])]

                    has_required_label = self.required_pr_label and self.required_pr_label in pr_labels
                    has_required_state = False
                    if self.required_project_state and pr['number'] in project_states:
                        has_required_state = self.required_project_state in project_states[pr['number']]

                    if not (has_required_label or has_required_state):
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
                        'has_change_requests': has_change_requests,
                        'project_states': project_states.get(pr_number, [])
                    })
                except Exception as e:
                    logging.warning(f"Error fetching PR details for #{pr_number}: {e}")

        except Exception as e:
            logging.error(f"Error fetching my open PRs from {repo}: {e}")

    return my_prs
