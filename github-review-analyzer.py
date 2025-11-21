#!/usr/bin/env python3
"""
GitHub PR Review Analyzer
Analyzes PR review activity between users in specified repositories.
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Set
import requests
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
    review_events: int = 0  # approvals, change requests, etc.
    comments: int = 0
    prs: List[Dict] = field(default_factory=list)


class GitHubReviewAnalyzer:
    """Analyzes GitHub PR reviews for a given user across repositories."""

    def __init__(self, username: str, token: str = None):
        self.username = username
        self.token = token or os.environ.get('GITHUB_TOKEN')
        self.session = requests.Session()

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

    def get_paginated(self, url: str, params: Dict = None) -> List[Dict]:
        """Fetch all pages of a paginated GitHub API endpoint."""
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

            # Check if there are more pages
            if len(data) < per_page:
                break

            page += 1

        logging.debug(f"Fetched {len(results)} total items from {url}")
        return results

    def analyze_repository(self, repo: str, months: int = 3):
        """Analyze PRs in a repository for the last N months."""
        logging.info(f"Analyzing repository: {repo}")

        since_date = datetime.now() - timedelta(days=months * 30)
        logging.info(f"Looking for PRs created since: {since_date.strftime('%Y-%m-%d')}")

        # Fetch all PRs (both open and closed)
        url = f"https://api.github.com/repos/{repo}/pulls"

        logging.info("Fetching pull requests...")
        all_prs = []
        for state in ['open', 'closed']:
            logging.debug(f"Fetching {state} PRs")
            prs = self.get_paginated(url, {
                'state': state,
                'sort': 'updated',
                'direction': 'desc'
            })
            all_prs.extend(prs)
            logging.debug(f"Found {len(prs)} {state} PRs")

        # Filter PRs by date
        recent_prs = [
            pr for pr in all_prs
            if datetime.strptime(pr['created_at'], '%Y-%m-%dT%H:%M:%SZ') >= since_date
        ]

        logging.info(f"Found {len(recent_prs)} PRs in the last {months} months (filtered from {len(all_prs)} total)")

        for i, pr in enumerate(recent_prs, 1):
            if i % 10 == 0:
                logging.info(f"Processing PR {i}/{len(recent_prs)}...")

            self._analyze_pr(repo, pr)

        logging.info(f"Completed analysis of repository: {repo}")

    def _analyze_pr(self, repo: str, pr: Dict):
        """Analyze a single PR for review activity."""
        pr_number = pr['number']
        pr_author = pr['user']['login']
        pr_title = pr['title']
        pr_url = pr['html_url']
        additions = pr.get('additions', 0)
        deletions = pr.get('deletions', 0)
        total_lines = additions + deletions

        logging.debug(f"Analyzing PR #{pr_number}: {pr_title} (by {pr_author}, {total_lines} lines)")

        # Fetch reviews for this PR
        reviews_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/reviews"
        reviews = self.get_paginated(reviews_url)

        # Fetch review comments for this PR
        comments_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/comments"
        review_comments = self.get_paginated(comments_url)

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

            if reviewer == self.username or reviewer == pr_author:
                continue  # Skip self-reviews

            reviewer_activity[reviewer]['reviews'].add(review_id)
            reviewer_activity[reviewer]['review_events'] += 1

        # Process review comments
        for comment in review_comments:
            commenter = comment['user']['login']

            if commenter == self.username or commenter == pr_author:
                continue

            reviewer_activity[commenter]['comments'] += 1

        # Determine if I reviewed this PR or if others reviewed my PR
        pr_info = {
            'title': pr_title,
            'url': pr_url,
            'number': pr_number,
            'lines': total_lines
        }

        if pr_author == self.username:
            # Others reviewed my PR
            for reviewer, activity in reviewer_activity.items():
                stats = self.reviewed_by_others[reviewer]
                stats.prs_reviewed += 1
                stats.lines_reviewed += total_lines
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
                stats.review_events += len(my_reviews)
                stats.comments += len(my_comments)
                stats.prs.append(pr_info)

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
            print(f"{'Lines reviewed':<30} {my_reviews.lines_reviewed:<20} {their_reviews.lines_reviewed:<20}")
            print(f"{'Review events':<30} {my_reviews.review_events:<20} {their_reviews.review_events:<20}")
            print(f"{'Comments written':<30} {my_reviews.comments:<20} {their_reviews.comments:<20}")

            # Calculate offset
            line_offset = my_reviews.lines_reviewed - their_reviews.lines_reviewed
            offset_sign = "+" if line_offset >= 0 else ""
            print(f"\n📊 Line Review Offset: {offset_sign}{line_offset:,} lines ")
            print(f"   (positive = you reviewed more of their code)")

            # List PRs I reviewed
            if my_reviews.prs:
                print(f"\n📝 PRs I reviewed ({len(my_reviews.prs)}):")
                for pr in my_reviews.prs:
                    print(f"   • #{pr['number']}: {pr['title']}")
                    print(f"     {pr['url']} ({pr['lines']:,} lines)")

            # List PRs they reviewed
            if their_reviews.prs:
                print(f"\n📝 PRs they reviewed ({len(their_reviews.prs)}):")
                for pr in their_reviews.prs:
                    print(f"   • #{pr['number']}: {pr['title']}")
                    print(f"     {pr['url']} ({pr['lines']:,} lines)")

        # Overall statistics
        print(f"\n{'='*80}")
        print("OVERALL STATISTICS")
        print(f"{'='*80}")

        total_reviewed_by_me = sum(s.prs_reviewed for s in self.reviewed_by_me.values())
        total_reviewed_by_others = sum(s.prs_reviewed for s in self.reviewed_by_others.values())
        total_lines_by_me = sum(s.lines_reviewed for s in self.reviewed_by_me.values())
        total_lines_by_others = sum(s.lines_reviewed for s in self.reviewed_by_others.values())

        print(f"\nTotal PRs I reviewed: {total_reviewed_by_me}")
        print(f"Total PRs others reviewed of mine: {total_reviewed_by_others}")
        print(f"Total lines I reviewed: {total_lines_by_me:,}")
        print(f"Total lines others reviewed: {total_lines_by_others:,}")
        print(f"Number of collaborators: {len(all_users)}")


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

    # Create analyzer
    analyzer = GitHubReviewAnalyzer(username, token)

    # Analyze each repository
    logging.info(f"Starting analysis of {len(repos)} repository/repositories")
    for repo in repos:
        try:
            analyzer.analyze_repository(repo, months)
        except Exception as e:
            logging.error(f"Error analyzing {repo}: {e}", exc_info=True)
            continue

    # Print summary
    logging.info("Analysis complete, generating summary...")
    analyzer.print_summary()


if __name__ == "__main__":
    main()
