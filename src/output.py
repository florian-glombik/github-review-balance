"""Output formatting and display for review analysis results."""

import os
from typing import Dict, Set
from collections import defaultdict
from datetime import datetime

from .models import ReviewStats


# ANSI color codes
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
CYAN = '\033[96m'
BOLD = '\033[1m'
RESET = '\033[0m'


class OutputFormatter:
    """Formats and prints review analysis results."""

    def __init__(self, username: str, sort_by: str = 'total_prs', show_extended_report: bool = False, show_overall_statistics: bool = True, max_review_count_threshold: int = None, filter_non_pr_authors: bool = False, config: dict = None):
        """Initialize the output formatter.

        Args:
            username: The username being analyzed
            sort_by: Column to sort results by
            show_extended_report: Whether to show the extended detailed history report
            show_overall_statistics: Whether to show the overall statistics section
            max_review_count_threshold: Minimum review count to filter PRs (None = no filtering)
            filter_non_pr_authors: Whether to filter out users who have not opened any PRs
            config: Configuration dictionary with analysis parameters (repositories, months, excluded_users, etc.)
        """
        self.username = username
        self.sort_by = sort_by
        self.show_extended_report = show_extended_report
        self.show_overall_statistics = show_overall_statistics
        self.max_review_count_threshold = max_review_count_threshold
        self.filter_non_pr_authors = filter_non_pr_authors
        self.config = config or {}

    def print_summary(
        self,
        reviewed_by_me: Dict[str, ReviewStats],
        reviewed_by_others: Dict[str, ReviewStats],
        open_prs_by_author: Dict[str, list],
        pr_authors: Set[str] = None
    ):
        """Print a comprehensive summary of review statistics.

        Args:
            reviewed_by_me: Statistics for PRs I reviewed
            reviewed_by_others: Statistics for PRs others reviewed
            open_prs_by_author: Open PRs grouped by author
            pr_authors: Set of all users who have authored PRs in the repositories
        """
        print("\n" + "="*80)
        print(f"REVIEW SUMMARY FOR {self.username}")
        print("="*80)

        all_users = set(reviewed_by_me.keys()) | set(reviewed_by_others.keys())

        if not all_users:
            print("\nNo review activity found.")
            return

        # Print review balance and next actions
        self._print_review_balance(all_users, reviewed_by_me, reviewed_by_others, pr_authors)

        # Print open PRs needing review
        self._print_open_prs(open_prs_by_author, reviewed_by_me, reviewed_by_others)

        # Print detailed history (only if extended report is enabled)
        if self.show_extended_report:
            self._print_detailed_history(all_users, reviewed_by_me, reviewed_by_others, pr_authors)

        # Print overall statistics (only if enabled)
        if self.show_overall_statistics:
            self._print_overall_stats(reviewed_by_me, reviewed_by_others, pr_authors)

    def _print_review_balance(
        self,
        all_users: Set[str],
        reviewed_by_me: Dict[str, ReviewStats],
        reviewed_by_others: Dict[str, ReviewStats],
        pr_authors: Set[str] = None
    ):
        """Print the review balance table."""
        print("\n" + "="*80)
        print("REVIEW BALANCE & NEXT ACTIONS")
        print("="*80)

        # Calculate review balance for each user
        review_balance = []
        for user in all_users:
            my_reviews = reviewed_by_me[user]
            their_reviews = reviewed_by_others[user]
            balance = their_reviews.lines_reviewed - my_reviews.lines_reviewed
            total_prs = my_reviews.prs_reviewed + their_reviews.prs_reviewed

            # Filter out users who have not opened any PRs (only if flag is set)
            # Check if user is in pr_authors set (which includes all PR authors from analyzed PRs)
            if self.filter_non_pr_authors and pr_authors is not None and user not in pr_authors:
                continue

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
        review_balance = self._sort_review_balance(review_balance)

        # Display table
        print("\nReview Balance (lines reviewed):")
        print(f"{'User':<20} {'Total PRs':<10} {'Their PRs':<12} {'My PRs':<12} {'They reviewed':<25} {'I reviewed':<25} {'Balance':<15} {'Action'}")
        print(f"{'-'*155}")

        for item in review_balance:
            self._print_balance_row(item)

        return review_balance

    def _sort_review_balance(self, review_balance: list) -> list:
        """Sort the review balance list by the specified column."""
        sort_key_map = {
            'total_prs': lambda x: x['total_prs'],
            'balance': lambda x: x['balance'],
            'user': lambda x: x['user'].lower(),
            'they_reviewed': lambda x: x['they_reviewed'],
            'i_reviewed': lambda x: x['i_reviewed'],
            'their_prs': lambda x: x['their_prs_i_reviewed'],
            'my_prs': lambda x: x['my_prs_they_reviewed']
        }

        sort_key = sort_key_map.get(self.sort_by, sort_key_map['total_prs'])
        reverse_sort = (self.sort_by != 'user')

        return sorted(review_balance, key=sort_key, reverse=reverse_sort)

    def _print_balance_row(self, item: dict):
        """Print a single row of the balance table."""
        user = item['user']
        balance = item['balance']
        total_prs = item['total_prs']
        they_reviewed = item['they_reviewed']
        they_additions = item['they_additions']
        they_deletions = item['they_deletions']
        i_reviewed = item['i_reviewed']
        i_additions = item['i_additions']
        i_deletions = item['i_deletions']
        their_prs_i_reviewed = item['their_prs_i_reviewed']
        my_prs_they_reviewed = item['my_prs_they_reviewed']

        # Format: +add / -del
        they_str = f"+{they_additions:,}/-{they_deletions:,}"
        i_str = f"+{i_additions:,}/-{i_deletions:,}"

        # Determine color and action based on balance
        if balance == 0:
            color = RESET
            action = "✓ Balanced"
            balance_str = "0"
        elif balance > 0:
            color = GREEN
            action = "→ I should review their PRs"
            balance_str = f"+{balance:,}"
        elif balance > -1000:
            color = YELLOW
            action = "← They should review my PRs"
            balance_str = f"{balance:,}"
        else:
            color = RED
            action = "← They should review my PRs"
            balance_str = f"{balance:,}"

        print(f"{color}{user:<20} {total_prs:<10} {their_prs_i_reviewed:<12} {my_prs_they_reviewed:<12} {they_str:<25} {i_str:<25} {balance_str:<15} {action}{RESET}")

    def _print_open_prs(
        self,
        open_prs_by_author: Dict[str, list],
        reviewed_by_me: Dict[str, ReviewStats],
        reviewed_by_others: Dict[str, ReviewStats]
    ):
        """Print open PRs that need review."""
        print("\n" + "="*80)
        print("OPEN PRs THAT NEED YOUR REVIEW")
        print("="*80)

        if not open_prs_by_author:
            print("\nNo open PRs found that need your review.")
            return

        # Calculate review balance for sorting and coloring
        all_users = set(reviewed_by_me.keys()) | set(reviewed_by_others.keys())
        review_balance = []
        for user in all_users:
            my_reviews = reviewed_by_me[user]
            their_reviews = reviewed_by_others[user]
            balance = their_reviews.lines_reviewed - my_reviews.lines_reviewed
            review_balance.append({
                'user': user,
                'balance': balance
            })

        # Filter PRs based on review count threshold
        filtered_prs_by_author = {}
        filtered_count = 0

        for author, prs in open_prs_by_author.items():
            filtered_prs = []
            for pr in prs:
                review_count = pr.get('review_count', 0)
                requested_my_review = pr.get('requested_my_review', False)

                # Always include PRs where my review was explicitly requested
                # Otherwise, apply threshold filtering
                if requested_my_review:
                    filtered_prs.append(pr)
                elif self.max_review_count_threshold is None or review_count < self.max_review_count_threshold:
                    filtered_prs.append(pr)
                else:
                    filtered_count += 1

            if filtered_prs:
                filtered_prs_by_author[author] = filtered_prs

        # Sort authors by review balance
        authors_with_prs = [(user, filtered_prs_by_author[user]) for user in filtered_prs_by_author]
        authors_with_prs.sort(key=lambda x: next(
            (item['balance'] for item in review_balance if item['user'] == x[0]),
            0
        ), reverse=True)

        total_prs_to_review = sum(len(prs) for prs in filtered_prs_by_author.values())

        if total_prs_to_review == 0:
            print("\nNo open PRs found that need your review.")
            if filtered_count > 0:
                print(f"({filtered_count} PR(s) filtered out due to review count threshold)")
            return

        print(f"\nYou have {total_prs_to_review} open PR(s) to review", end='')
        if filtered_count > 0:
            print(f" ({filtered_count} filtered out by threshold):\n")
        else:
            print(":\n")

        for author, prs in authors_with_prs:
            balance_info = next((item for item in review_balance if item['user'] == author), None)

            # Determine color and priority based on balance
            if balance_info:
                balance = balance_info['balance']
                if balance == 0:
                    author_color = RESET
                    priority = ""
                elif balance > 0:
                    author_color = GREEN
                    priority = f"(Priority: You owe them {balance:,} lines)"
                elif balance > -1000:
                    author_color = YELLOW
                    priority = ""
                else:
                    author_color = RED
                    priority = ""
            else:
                author_color = RESET
                priority = ""

            print(f"{author_color}From {author} {priority}:{RESET}")
            for pr in prs:
                repo_short = pr['repo'].split('/')[-1]
                review_count = pr.get('review_count', 0)
                requested_my_review = pr.get('requested_my_review', False)
                changes_requested = pr.get('changes_requested', False)

                # Build status indicators
                indicators = []
                if changes_requested:
                    indicators.append(f"{RED}⚠️  [CHANGES REQUESTED]{RESET}")
                if requested_my_review:
                    indicators.append(f"{CYAN}{BOLD}👉 [REVIEW REQUESTED]{RESET}")

                # Use cyan/bold color for requested reviews to make them stand out
                if requested_my_review or changes_requested:
                    pr_color = CYAN + BOLD if requested_my_review else RED
                else:
                    pr_color = author_color

                # Build review info string
                review_info = f"[{review_count} review(s)]"

                indicator_str = " ".join(indicators) if indicators else ""
                print(f"  {pr_color}• [{repo_short}] #{pr['number']}: {pr['title']}{RESET} {indicator_str}")
                print(f"    {pr['url']} (+{pr['additions']:,} / -{pr['deletions']:,} lines) {review_info}")
            print()

    def _print_detailed_history(
        self,
        all_users: Set[str],
        reviewed_by_me: Dict[str, ReviewStats],
        reviewed_by_others: Dict[str, ReviewStats],
        pr_authors: Set[str] = None
    ):
        """Print detailed review history for each user."""
        print("\n" + "="*80)
        print("DETAILED REVIEW HISTORY")
        print("="*80)

        # Filter users based on filter_non_pr_authors flag
        filtered_users = all_users
        if self.filter_non_pr_authors and pr_authors is not None:
            # Filter out users who never opened PRs (i.e., not in pr_authors set)
            filtered_users = {user for user in all_users if user in pr_authors}

        # Sort users by total interaction
        sorted_users = sorted(
            filtered_users,
            key=lambda u: (
                reviewed_by_me[u].prs_reviewed +
                reviewed_by_others[u].prs_reviewed
            ),
            reverse=True
        )

        for user in sorted_users:
            my_reviews = reviewed_by_me[user]
            their_reviews = reviewed_by_others[user]

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

    def _print_overall_stats(
        self,
        reviewed_by_me: Dict[str, ReviewStats],
        reviewed_by_others: Dict[str, ReviewStats],
        pr_authors: Set[str] = None
    ):
        """Print overall statistics."""
        print(f"\n{'='*80}")
        print("OVERALL STATISTICS")
        print(f"{'='*80}")

        # Filter users based on filter_non_pr_authors flag
        all_users = set(reviewed_by_me.keys()) | set(reviewed_by_others.keys())
        if self.filter_non_pr_authors and pr_authors is not None:
            # Filter out users who never opened PRs (i.e., not in pr_authors set)
            filtered_users = {user for user in all_users if user in pr_authors}
        else:
            filtered_users = all_users

        # Calculate stats only for filtered users
        total_reviewed_by_me = sum(reviewed_by_me[u].prs_reviewed for u in filtered_users)
        total_reviewed_by_others = sum(reviewed_by_others[u].prs_reviewed for u in filtered_users)
        total_lines_by_me = sum(reviewed_by_me[u].lines_reviewed for u in filtered_users)
        total_lines_by_others = sum(reviewed_by_others[u].lines_reviewed for u in filtered_users)
        total_additions_by_me = sum(reviewed_by_me[u].additions_reviewed for u in filtered_users)
        total_additions_by_others = sum(reviewed_by_others[u].additions_reviewed for u in filtered_users)
        total_deletions_by_me = sum(reviewed_by_me[u].deletions_reviewed for u in filtered_users)
        total_deletions_by_others = sum(reviewed_by_others[u].deletions_reviewed for u in filtered_users)

        print(f"\nTotal PRs I reviewed: {total_reviewed_by_me}")
        print(f"Total PRs others reviewed of mine: {total_reviewed_by_others}")
        print(f"\nTotal lines I reviewed: {total_lines_by_me:,}")
        print(f"  +lines: {total_additions_by_me:,}")
        print(f"  -lines: {total_deletions_by_me:,}")
        print(f"\nTotal lines others reviewed: {total_lines_by_others:,}")
        print(f"  +lines: {total_additions_by_others:,}")
        print(f"  -lines: {total_deletions_by_others:,}")
        print(f"\nNumber of collaborators: {len(filtered_users)}")

    def generate_html(
        self,
        reviewed_by_me: Dict[str, ReviewStats],
        reviewed_by_others: Dict[str, ReviewStats],
        open_prs_by_author: Dict[str, list],
        pr_authors: Set[str] = None,
        my_open_prs: list = None
    ) -> str:
        """Generate HTML report of review statistics.

        Args:
            reviewed_by_me: Statistics for PRs I reviewed
            reviewed_by_others: Statistics for PRs others reviewed
            open_prs_by_author: Open PRs grouped by author
            pr_authors: Set of all users who have authored PRs in the repositories
            my_open_prs: List of my open PRs that need review

        Returns:
            HTML string containing the full report
        """
        all_users = set(reviewed_by_me.keys()) | set(reviewed_by_others.keys())

        if not all_users:
            return self._generate_empty_html()

        html_parts = []
        html_parts.append(self._generate_html_header(open_prs_by_author))

        # Settings section
        html_parts.append(self._generate_settings_html())

        # My open PRs section
        if my_open_prs:
            html_parts.append(self._generate_my_open_prs_html(my_open_prs))

        # Review balance table
        html_parts.append(self._generate_review_balance_html(all_users, reviewed_by_me, reviewed_by_others, pr_authors, open_prs_by_author, my_open_prs))

        # Open PRs
        html_parts.append(self._generate_open_prs_html(open_prs_by_author, reviewed_by_me, reviewed_by_others, my_open_prs))

        # Detailed history (if enabled)
        if self.show_extended_report:
            html_parts.append(self._generate_detailed_history_html(all_users, reviewed_by_me, reviewed_by_others, pr_authors))

        # Overall statistics (if enabled)
        if self.show_overall_statistics:
            html_parts.append(self._generate_overall_stats_html(reviewed_by_me, reviewed_by_others, pr_authors))

        html_parts.append(self._generate_html_footer())

        return '\n'.join(html_parts)

    def _generate_html_header(self, open_prs_by_author: Dict[str, list] = None) -> str:
        """Generate HTML header with CSS styles."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        users_with_open_prs = set(open_prs_by_author.keys()) if open_prs_by_author else set()
        users_with_open_prs_json = str(list(users_with_open_prs)).replace("'", '"')

        return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GitHub Review Analysis - {self.username}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            line-height: 1.6;
            color: #333;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            min-height: 100vh;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            padding: 40px;
        }}

        h1 {{
            color: #667eea;
            margin-bottom: 10px;
            font-size: 2.5em;
            text-align: center;
        }}

        h2 {{
            color: #667eea;
            margin-top: 40px;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 3px solid #667eea;
            font-size: 1.8em;
        }}

        h3 {{
            color: #764ba2;
            margin-top: 30px;
            margin-bottom: 15px;
            font-size: 1.3em;
        }}

        .timestamp {{
            text-align: center;
            color: #666;
            font-size: 0.9em;
            margin-bottom: 30px;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        }}

        thead {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }}

        th {{
            padding: 15px;
            text-align: left;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.85em;
            letter-spacing: 0.5px;
            cursor: pointer;
            user-select: none;
            position: relative;
            transition: background-color 0.2s ease;
        }}

        th:hover {{
            background-color: rgba(0, 0, 0, 0.1);
        }}

        th::after {{
            content: ' ⇅';
            opacity: 0.3;
            font-size: 0.8em;
        }}

        th.sort-asc::after {{
            content: ' ↑';
            opacity: 1;
        }}

        th.sort-desc::after {{
            content: ' ↓';
            opacity: 1;
        }}

        td {{
            padding: 12px 15px;
            border-bottom: 1px solid #f0f0f0;
        }}

        tbody tr {{
            cursor: pointer;
            transition: background-color 0.2s ease;
        }}

        tbody tr:hover {{
            background-color: #f8f9fa;
        }}

        tbody tr.highlight {{
            animation: highlight-fade 2s ease-out;
        }}

        @keyframes highlight-fade {{
            0% {{
                background-color: #ffd700;
            }}
            100% {{
                background-color: transparent;
            }}
        }}

        .balance-positive {{
            color: #28a745;
            font-weight: 600;
        }}

        .balance-negative {{
            color: #dc3545;
            font-weight: 600;
        }}

        .balance-warning {{
            color: #ffc107;
            font-weight: 600;
        }}

        .balance-neutral {{
            color: #6c757d;
        }}

        .pr-list {{
            list-style: none;
            margin: 10px 0;
        }}

        .pr-item {{
            margin: 15px 0;
            padding: 0;
            background: #f8f9fa;
            border-left: 4px solid #667eea;
            border-radius: 4px;
        }}

        .pr-item-link {{
            display: block;
            padding: 15px;
            text-decoration: none;
            color: inherit;
        }}

        .pr-item-link:hover {{
            background: rgba(102, 126, 234, 0.05);
        }}

        .pr-item.priority-high {{
            border-left-color: #28a745;
            background: #e8f5e9;
        }}

        .pr-item.priority-medium {{
            border-left-color: #ffc107;
            background: #fff8e1;
        }}

        .pr-item.priority-low {{
            border-left-color: #dc3545;
            background: #ffebee;
        }}

        .pr-item.requested {{
            border-left-color: #17a2b8;
            background: #e0f7fa;
            border-width: 6px;
        }}

        .pr-title {{
            font-weight: 600;
            color: #333;
            margin-bottom: 5px;
        }}

        .pr-meta {{
            font-size: 0.9em;
            color: #666;
        }}

        .pr-link {{
            color: #667eea;
            text-decoration: none;
            word-break: break-all;
        }}

        .pr-link:hover {{
            text-decoration: underline;
        }}

        .author-section {{
            margin: 20px 0;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 8px;
            scroll-margin-top: 20px;
        }}

        .author-name {{
            font-size: 1.2em;
            font-weight: 600;
            margin-bottom: 10px;
        }}

        .author-link {{
            color: #667eea;
            text-decoration: none;
        }}

        .author-link:hover {{
            text-decoration: underline;
        }}

        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}

        .stat-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }}

        .stat-label {{
            font-size: 0.9em;
            opacity: 0.9;
            margin-bottom: 5px;
        }}

        .stat-value {{
            font-size: 2em;
            font-weight: 700;
        }}

        .badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: 600;
            margin-left: 8px;
        }}

        .badge-requested {{
            background: #17a2b8;
            color: white;
        }}

        .badge-reviews {{
            background: #6c757d;
            color: white;
        }}

        .badge-changes-requested {{
            background: #dc3545;
            color: white;
        }}

        .no-data {{
            text-align: center;
            padding: 40px;
            color: #999;
            font-style: italic;
        }}

        .detailed-section {{
            margin: 30px 0;
            padding: 20px;
            background: #fafafa;
            border-radius: 8px;
            border: 1px solid #e0e0e0;
        }}

        .metric-table {{
            width: 100%;
            margin: 15px 0;
        }}

        .metric-table td {{
            padding: 8px;
        }}

        .metric-table td:first-child {{
            font-weight: 600;
            width: 40%;
        }}

        .back-to-table {{
            display: inline-block;
            color: #667eea;
            text-decoration: none;
            font-size: 0.85em;
            opacity: 0.7;
            transition: opacity 0.2s ease;
            margin-right: 10px;
        }}

        .back-to-table:hover {{
            opacity: 1;
            text-decoration: underline;
        }}

        .settings-section {{
            background: #f8f9fa;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
            border: 1px solid #e0e0e0;
        }}

        .settings-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 15px;
            margin-top: 15px;
        }}

        .setting-item {{
            display: flex;
            flex-direction: column;
        }}

        .setting-label {{
            font-weight: 600;
            color: #555;
            margin-bottom: 5px;
            font-size: 0.9em;
        }}

        .setting-value {{
            color: #333;
            padding: 8px 12px;
            background: white;
            border-radius: 4px;
            border: 1px solid #ddd;
        }}

        .my-prs-section {{
            background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%);
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
            border: 3px solid #4caf50;
        }}

        .copy-button {{
            background: #667eea;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.9em;
            margin-top: 10px;
            transition: background-color 0.2s ease;
        }}

        .copy-button:hover {{
            background: #5568d3;
        }}

        .copy-button:active {{
            background: #4556bb;
        }}

        .copy-button.copied {{
            background: #4caf50;
        }}

        .message-box {{
            background: white;
            border: 1px solid #ddd;
            border-radius: 4px;
            padding: 15px;
            margin: 10px 0;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
            white-space: pre-wrap;
            line-height: 1.6;
        }}

        tbody tr.disabled {{
            opacity: 0.5;
            cursor: not-allowed !important;
        }}

        tbody tr.disabled:hover {{
            background-color: transparent !important;
        }}

        details {{
            background: #fafafa;
            border-radius: 8px;
            padding: 15px;
            margin: 20px 0;
            border: 1px solid #e0e0e0;
        }}

        summary {{
            cursor: pointer;
            font-weight: 600;
            font-size: 1.2em;
            color: #667eea;
            padding: 10px;
            margin: -15px -15px 15px -15px;
            background: linear-gradient(135deg, #e8eaf6 0%, #d1d5f0 100%);
            border-radius: 8px 8px 0 0;
            user-select: none;
        }}

        summary:hover {{
            background: linear-gradient(135deg, #d1d5f0 0%, #c5cae9 100%);
        }}

        details[open] summary {{
            border-radius: 8px 8px 0 0;
            margin-bottom: 20px;
        }}

        .user-pr-item {{
            padding: 10px;
            margin: 5px 0;
            background: #f0f0f0;
            border-radius: 4px;
            border-left: 4px solid #667eea;
        }}

        .user-pr-item:hover {{
            background: #e8e8e8;
        }}

        @media (max-width: 768px) {{
            .container {{
                padding: 20px;
            }}

            h1 {{
                font-size: 1.8em;
            }}

            h2 {{
                font-size: 1.4em;
            }}

            table {{
                font-size: 0.9em;
            }}

            th, td {{
                padding: 8px;
            }}

            .stats-grid {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
    <script>
        const usersWithOpenPRs = {users_with_open_prs_json};
        const defaultSortBy = '{self.sort_by}';

        document.addEventListener('DOMContentLoaded', function() {{
            // Table sorting functionality
            const table = document.querySelector('table');
            if (table) {{
                const headers = table.querySelectorAll('th');
                const tbody = table.querySelector('tbody');

                // Set initial sort indicator
                const sortColumnMap = {{
                    'total_prs': 1,
                    'their_prs': 2,
                    'my_prs': 3,
                    'they_reviewed': 4,
                    'i_reviewed': 5,
                    'balance': 6,
                    'user': 0
                }};

                const defaultColumnIndex = sortColumnMap[defaultSortBy] || 1;
                const defaultHeader = headers[defaultColumnIndex];
                if (defaultHeader) {{
                    defaultHeader.classList.add('sort-desc');
                }}

                headers.forEach((header, index) => {{
                    header.addEventListener('click', () => {{
                        sortTable(index, header);
                    }});
                }});

                function sortTable(columnIndex, header) {{
                    const rows = Array.from(tbody.querySelectorAll('tr'));
                    const currentSort = header.classList.contains('sort-asc') ? 'asc' :
                                       header.classList.contains('sort-desc') ? 'desc' : 'none';

                    // Remove sort classes from all headers
                    headers.forEach(h => h.classList.remove('sort-asc', 'sort-desc'));

                    // Determine new sort direction
                    const newSort = currentSort === 'none' ? 'desc' :
                                   currentSort === 'desc' ? 'asc' : 'desc';

                    header.classList.add(newSort === 'asc' ? 'sort-asc' : 'sort-desc');

                    // Sort rows
                    rows.sort((a, b) => {{
                        const aValue = a.cells[columnIndex].textContent.trim();
                        const bValue = b.cells[columnIndex].textContent.trim();

                        // Try to parse as number (handle formats like "+1,234" or "-1,234")
                        const aNum = parseFloat(aValue.replace(/[+,]/g, ''));
                        const bNum = parseFloat(bValue.replace(/[+,]/g, ''));

                        if (!isNaN(aNum) && !isNaN(bNum)) {{
                            return newSort === 'asc' ? aNum - bNum : bNum - aNum;
                        }}

                        // String comparison
                        return newSort === 'asc' ?
                            aValue.localeCompare(bValue) :
                            bValue.localeCompare(aValue);
                    }});

                    // Re-append sorted rows
                    rows.forEach(row => tbody.appendChild(row));
                }}

                // Row click navigation with disabled state check
                tbody.querySelectorAll('tr').forEach(row => {{
                    const username = row.cells[0].textContent.trim();

                    // Mark rows without open PRs as disabled
                    if (!usersWithOpenPRs.includes(username)) {{
                        row.classList.add('disabled');
                    }}

                    row.addEventListener('click', () => {{
                        if (row.classList.contains('disabled')) {{
                            alert(`No open PRs to review from ${{username}}`);
                            return;
                        }}

                        const targetSection = document.getElementById('user-' + username);
                        if (targetSection) {{
                            targetSection.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
                        }}
                    }});
                }});
            }}

            // Handle back-to-table links with highlighting
            document.querySelectorAll('.back-to-table').forEach(link => {{
                link.addEventListener('click', (e) => {{
                    e.preventDefault();
                    const username = link.dataset.username;
                    const table = document.querySelector('table');

                    if (table) {{
                        table.scrollIntoView({{ behavior: 'smooth', block: 'start' }});

                        // Highlight the user's row
                        setTimeout(() => {{
                            const rows = table.querySelectorAll('tbody tr');
                            rows.forEach(row => {{
                                if (row.cells[0].textContent.trim() === username) {{
                                    row.classList.remove('highlight');
                                    // Force reflow to restart animation
                                    void row.offsetWidth;
                                    row.classList.add('highlight');

                                    // Remove highlight class after animation
                                    setTimeout(() => {{
                                        row.classList.remove('highlight');
                                    }}, 2000);
                                }}
                            }});
                        }}, 500);
                    }}
                }});
            }});

            // Copy to clipboard functionality
            document.querySelectorAll('.copy-button').forEach(button => {{
                button.addEventListener('click', function() {{
                    const messageBox = this.previousElementSibling;
                    if (messageBox && messageBox.classList.contains('message-box')) {{
                        const text = messageBox.textContent;
                        navigator.clipboard.writeText(text).then(() => {{
                            const originalText = this.textContent;
                            this.textContent = 'Copied!';
                            this.classList.add('copied');
                            setTimeout(() => {{
                                this.textContent = originalText;
                                this.classList.remove('copied');
                            }}, 2000);
                        }}).catch(err => {{
                            console.error('Failed to copy:', err);
                            alert('Failed to copy to clipboard');
                        }});
                    }}
                }});
            }});

            // PR copy button functionality
            document.querySelectorAll('.pr-copy-button').forEach(button => {{
                button.addEventListener('click', function(e) {{
                    e.stopPropagation();
                    const message = this.dataset.message;
                    if (message) {{
                        navigator.clipboard.writeText(message).then(() => {{
                            const originalText = this.textContent;
                            const originalBg = this.style.backgroundColor;
                            this.textContent = 'Copied!';
                            this.style.backgroundColor = '#4caf50';
                            setTimeout(() => {{
                                this.textContent = originalText;
                                this.style.backgroundColor = originalBg;
                            }}, 2000);
                        }}).catch(err => {{
                            console.error('Failed to copy:', err);
                            alert('Failed to copy to clipboard');
                        }});
                    }}
                }});
            }});
        }});
    </script>
</head>
<body>
    <div class="container">
        <h1>GitHub PR Review Analysis</h1>
        <div class="timestamp">Generated on {timestamp} for user: <strong>{self.username}</strong></div>
'''

    def _generate_html_footer(self) -> str:
        """Generate HTML footer."""
        return '''    </div>
</body>
</html>'''

    def _generate_settings_html(self) -> str:
        """Generate HTML for settings section."""
        html = '<details open>\n'
        html += '<summary>Analysis Settings</summary>\n'
        html += '<div class="settings-section">\n'
        html += '<div class="settings-grid">\n'

        # Repositories
        if 'repositories' in self.config:
            repos = self.config['repositories']
            html += '<div class="setting-item">\n'
            html += '<div class="setting-label">Repositories</div>\n'
            html += f'<div class="setting-value">{", ".join(repos)}</div>\n'
            html += '</div>\n'

        # Time range
        if 'months' in self.config:
            html += '<div class="setting-item">\n'
            html += '<div class="setting-label">Time Range</div>\n'
            html += f'<div class="setting-value">Last {self.config["months"]} months</div>\n'
            html += '</div>\n'

        # Excluded users
        if 'excluded_users' in self.config and self.config['excluded_users']:
            html += '<div class="setting-item">\n'
            html += '<div class="setting-label">Excluded Users</div>\n'
            html += f'<div class="setting-value">{", ".join(sorted(self.config["excluded_users"]))}</div>\n'
            html += '</div>\n'

        # Required PR label
        if 'required_pr_label' in self.config and self.config['required_pr_label']:
            html += '<div class="setting-item">\n'
            html += '<div class="setting-label">Required PR Label</div>\n'
            html += f'<div class="setting-value">{self.config["required_pr_label"]}</div>\n'
            html += '</div>\n'

        # Sort by
        html += '<div class="setting-item">\n'
        html += '<div class="setting-label">Default Sort</div>\n'
        html += f'<div class="setting-value">{self.sort_by}</div>\n'
        html += '</div>\n'

        # Exclude generated files
        if 'exclude_generated_files' in self.config:
            html += '<div class="setting-item">\n'
            html += '<div class="setting-label">Exclude Generated Files</div>\n'
            html += f'<div class="setting-value">{"Yes" if self.config["exclude_generated_files"] else "No"}</div>\n'
            html += '</div>\n'

        # Max review count threshold
        if self.max_review_count_threshold is not None:
            html += '<div class="setting-item">\n'
            html += '<div class="setting-label">Max Review Count Threshold</div>\n'
            html += f'<div class="setting-value">{self.max_review_count_threshold}</div>\n'
            html += '</div>\n'

        # Filter non-PR authors
        if self.filter_non_pr_authors:
            html += '<div class="setting-item">\n'
            html += '<div class="setting-label">Filter Non-PR Authors</div>\n'
            html += '<div class="setting-value">Yes</div>\n'
            html += '</div>\n'

        html += '</div>\n</div>\n</details>\n'
        return html

    def _generate_my_open_prs_html(self, my_open_prs: list) -> str:
        """Generate HTML for my open PRs section with copyable messages per PR."""
        html = '<div class="my-prs-section">\n'
        html += '<h2>My Open PRs Needing Review</h2>\n'
        html += f'<p>You have <strong>{len(my_open_prs)}</strong> open PR(s). Click either button to copy a Slack-ready message requesting code review or testing.</p>\n'

        for pr in my_open_prs:
            repo_name = pr['repo']
            repo_short = repo_name.split('/')[-1]
            pr_number = pr['number']
            pr_title = pr['title']
            pr_url = pr['url']
            additions = pr['additions']
            deletions = pr['deletions']
            total_lines = additions + deletions

            # Generate messages for this PR in Slack format
            # Slack uses *text* for bold and <url|text> for links
            # Remove backticks from title as they break Slack link formatting
            slack_title = pr_title.replace('`', '')

            code_review_message = f"Hey everyone, I need your help for *a code review* on this PR <{pr_url}|{slack_title}> (+{additions:,}/-{deletions:,} lines, ~{total_lines:,} total)\n\n"
            code_review_message += "As always, I am happy to trade reviews :smile:"

            testing_message = f"Hey everyone, I need your help for *testing* on this PR <{pr_url}|{slack_title}> (+{additions:,}/-{deletions:,} lines, ~{total_lines:,} total)\n\n"
            testing_message += "As always, I am happy to trade reviews :smile:"

            # Escape only quotes and backslashes for HTML data attribute (preserve Slack formatting)
            escaped_code_message = code_review_message.replace('\\', '\\\\').replace('"', '&quot;')
            escaped_test_message = testing_message.replace('\\', '\\\\').replace('"', '&quot;')

            html += '<div style="margin: 20px 0; padding: 15px; background: white; border-radius: 8px; border: 2px solid #4caf50;">\n'
            html += f'<div style="font-weight: 600; font-size: 1.1em; margin-bottom: 10px;">[{repo_short}] #{pr_number}: {pr_title}</div>\n'
            html += f'<div style="font-size: 0.9em; color: #666; margin-bottom: 5px;"><a href="{pr_url}" target="_blank">{pr_url}</a></div>\n'
            html += f'<div style="font-size: 0.9em; color: #666; margin-bottom: 10px;">(+{additions:,} / -{deletions:,} lines)</div>\n'
            html += '<div style="display: flex; gap: 10px;">\n'
            html += f'<button class="pr-copy-button" data-message="{escaped_code_message}" style="flex: 1; background: #667eea; color: white; border: none; padding: 10px 16px; border-radius: 4px; cursor: pointer; font-size: 0.9em; transition: background-color 0.2s ease;">Copy Code Review Message</button>\n'
            html += f'<button class="pr-copy-button" data-message="{escaped_test_message}" style="flex: 1; background: #764ba2; color: white; border: none; padding: 10px 16px; border-radius: 4px; cursor: pointer; font-size: 0.9em; transition: background-color 0.2s ease;">Copy Testing Message</button>\n'
            html += '</div>\n'
            html += '</div>\n'

        html += '</div>\n'

        return html

    def _generate_empty_html(self) -> str:
        """Generate HTML for when there's no data."""
        html = self._generate_html_header({})
        html += '<div class="no-data">No review activity found.</div>'
        html += self._generate_html_footer()
        return html

    def _generate_review_balance_html(
        self,
        all_users: Set[str],
        reviewed_by_me: Dict[str, ReviewStats],
        reviewed_by_others: Dict[str, ReviewStats],
        pr_authors: Set[str] = None,
        open_prs_by_author: Dict[str, list] = None,
        my_open_prs: list = None
    ) -> str:
        """Generate HTML for review balance table."""
        # Calculate review balance for each user
        review_balance = []
        for user in all_users:
            my_reviews = reviewed_by_me[user]
            their_reviews = reviewed_by_others[user]
            balance = their_reviews.lines_reviewed - my_reviews.lines_reviewed
            total_prs = my_reviews.prs_reviewed + their_reviews.prs_reviewed

            # Filter out users who have not opened any PRs (only if flag is set)
            if self.filter_non_pr_authors and pr_authors is not None and user not in pr_authors:
                continue

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
        review_balance = self._sort_review_balance(review_balance)

        html = '<h2 id="review-table">Review Balance & Next Actions</h2>\n'
        html += '<table>\n'
        html += '<thead><tr>\n'
        html += '<th>User</th><th>Total PRs</th><th>Their PRs</th><th>My PRs</th>'
        html += '<th>They Reviewed</th><th>I Reviewed</th><th>Balance</th><th>Action</th>\n'
        html += '</tr></thead>\n<tbody>\n'

        for item in review_balance:
            html += self._generate_balance_row_html(item)

        html += '</tbody>\n</table>\n'
        return html

    def _generate_balance_row_html(self, item: dict) -> str:
        """Generate HTML for a single balance table row."""
        user = item['user']
        balance = item['balance']
        total_prs = item['total_prs']
        they_reviewed = item['they_reviewed']
        they_additions = item['they_additions']
        they_deletions = item['they_deletions']
        i_reviewed = item['i_reviewed']
        i_additions = item['i_additions']
        i_deletions = item['i_deletions']
        their_prs_i_reviewed = item['their_prs_i_reviewed']
        my_prs_they_reviewed = item['my_prs_they_reviewed']

        # Format: +add / -del
        they_str = f"+{they_additions:,}/-{they_deletions:,}"
        i_str = f"+{i_additions:,}/-{i_deletions:,}"

        # Determine color and action based on balance
        if balance == 0:
            balance_class = "balance-neutral"
            action = "✓ Balanced"
            balance_str = "0"
        elif balance > 0:
            balance_class = "balance-positive"
            action = "→ I should review their PRs"
            balance_str = f"+{balance:,}"
        elif balance > -1000:
            balance_class = "balance-warning"
            action = "← They should review my PRs"
            balance_str = f"{balance:,}"
        else:
            balance_class = "balance-negative"
            action = "← They should review my PRs"
            balance_str = f"{balance:,}"

        return f'''<tr class="{balance_class}">
    <td>{user}</td>
    <td>{total_prs}</td>
    <td>{their_prs_i_reviewed}</td>
    <td>{my_prs_they_reviewed}</td>
    <td>{they_str}</td>
    <td>{i_str}</td>
    <td class="{balance_class}">{balance_str}</td>
    <td>{action}</td>
</tr>
'''

    def _generate_open_prs_html(
        self,
        open_prs_by_author: Dict[str, list],
        reviewed_by_me: Dict[str, ReviewStats],
        reviewed_by_others: Dict[str, ReviewStats],
        my_open_prs: list = None
    ) -> str:
        """Generate HTML for open PRs section."""
        html = '<h2>Open PRs That Need Your Review</h2>\n'

        if not open_prs_by_author:
            html += '<div class="no-data">No open PRs found that need your review.</div>\n'
            return html

        # Calculate review balance for sorting and coloring
        all_users = set(reviewed_by_me.keys()) | set(reviewed_by_others.keys())
        review_balance = []
        for user in all_users:
            my_reviews = reviewed_by_me[user]
            their_reviews = reviewed_by_others[user]
            balance = their_reviews.lines_reviewed - my_reviews.lines_reviewed
            review_balance.append({
                'user': user,
                'balance': balance
            })

        # Filter PRs based on review count threshold
        filtered_prs_by_author = {}
        filtered_count = 0

        for author, prs in open_prs_by_author.items():
            filtered_prs = []
            for pr in prs:
                review_count = pr.get('review_count', 0)
                requested_my_review = pr.get('requested_my_review', False)

                if requested_my_review:
                    filtered_prs.append(pr)
                elif self.max_review_count_threshold is None or review_count < self.max_review_count_threshold:
                    filtered_prs.append(pr)
                else:
                    filtered_count += 1

            if filtered_prs:
                filtered_prs_by_author[author] = filtered_prs

        # Sort authors by review balance
        authors_with_prs = [(user, filtered_prs_by_author[user]) for user in filtered_prs_by_author]
        authors_with_prs.sort(key=lambda x: next(
            (item['balance'] for item in review_balance if item['user'] == x[0]),
            0
        ), reverse=True)

        total_prs_to_review = sum(len(prs) for prs in filtered_prs_by_author.values())

        if total_prs_to_review == 0:
            html += '<div class="no-data">No open PRs found that need your review.'
            if filtered_count > 0:
                html += f' ({filtered_count} PR(s) filtered out due to review count threshold)'
            html += '</div>\n'
            return html

        html += f'<p>You have <strong>{total_prs_to_review}</strong> open PR(s) to review'
        if filtered_count > 0:
            html += f' ({filtered_count} filtered out by threshold)'
        html += '</p>\n'

        for author, prs in authors_with_prs:
            balance_info = next((item for item in review_balance if item['user'] == author), None)

            # Determine priority class based on balance
            if balance_info:
                balance = balance_info['balance']
                if balance > 0:
                    priority_class = "priority-high"
                    priority_text = f"Priority: You owe them {balance:,} lines"
                elif balance > -1000:
                    priority_class = "priority-medium"
                    priority_text = ""
                else:
                    priority_class = "priority-low"
                    priority_text = ""
            else:
                priority_class = ""
                priority_text = ""

            html += f'<div class="author-section" id="user-{author}">\n'
            html += f'<div class="author-name">'
            html += f'From <a href="https://github.com/{author}" class="author-link" target="_blank">{author}</a>'
            if priority_text:
                html += f' <span style="color: #28a745;">({priority_text})</span>'
            html += f' <a href="#" class="back-to-table" data-username="{author}">↑ overview</a>'
            html += '</div>\n'
            html += '<ul class="pr-list">\n'

            for pr in prs:
                repo_short = pr['repo'].split('/')[-1]
                review_count = pr.get('review_count', 0)
                requested_my_review = pr.get('requested_my_review', False)
                changes_requested = pr.get('changes_requested', False)

                pr_class = priority_class
                if requested_my_review:
                    pr_class += " requested"

                html += f'<li class="pr-item {pr_class}">\n'
                html += f'<a href="{pr["url"]}" class="pr-item-link" target="_blank">\n'
                html += f'<div class="pr-title">[{repo_short}] #{pr["number"]}: {pr["title"]}'
                if changes_requested:
                    html += '<span class="badge badge-changes-requested">CHANGES REQUESTED</span>'
                if requested_my_review:
                    html += '<span class="badge badge-requested">REVIEW REQUESTED</span>'
                html += f'<span class="badge badge-reviews">{review_count} review(s)</span>'
                html += '</div>\n'
                html += f'<div class="pr-meta">'
                html += f'{pr["url"]} '
                html += f'(+{pr["additions"]:,} / -{pr["deletions"]:,} lines)'
                html += '</div>\n'
                html += '</a>\n'
                html += '</li>\n'

            html += '</ul>\n'

            # Add collapsible details section showing review history with this user
            my_reviews = reviewed_by_me.get(author)
            their_reviews = reviewed_by_others.get(author)

            if my_reviews or their_reviews:
                html += '<details style="margin-top: 20px;">\n'
                html += f'<summary style="cursor: pointer; font-weight: 600; color: #667eea;">Review History with {author}</summary>\n'
                html += '<div style="padding: 15px; background: #fafafa; border-radius: 4px; margin-top: 10px;">\n'

                # Summary table
                html += '<table class="metric-table" style="width: 100%; margin: 10px 0;">\n'
                html += '<thead><tr><th>Metric</th><th>I Reviewed</th><th>They Reviewed</th></tr></thead>\n'
                html += '<tbody>\n'

                my_prs_reviewed = my_reviews.prs_reviewed if my_reviews else 0
                their_prs_reviewed = their_reviews.prs_reviewed if their_reviews else 0
                my_lines = my_reviews.lines_reviewed if my_reviews else 0
                their_lines = their_reviews.lines_reviewed if their_reviews else 0
                my_additions = my_reviews.additions_reviewed if my_reviews else 0
                their_additions = their_reviews.additions_reviewed if their_reviews else 0
                my_deletions = my_reviews.deletions_reviewed if my_reviews else 0
                their_deletions = their_reviews.deletions_reviewed if their_reviews else 0
                my_events = my_reviews.review_events if my_reviews else 0
                their_events = their_reviews.review_events if their_reviews else 0
                my_comments = my_reviews.comments if my_reviews else 0
                their_comments = their_reviews.comments if their_reviews else 0

                html += f'<tr><td>PRs reviewed</td><td>{my_prs_reviewed}</td><td>{their_prs_reviewed}</td></tr>\n'
                html += f'<tr><td>Lines reviewed (total)</td><td>{my_lines:,}</td><td>{their_lines:,}</td></tr>\n'
                html += f'<tr><td>&nbsp;&nbsp;+lines (additions)</td><td>{my_additions:,}</td><td>{their_additions:,}</td></tr>\n'
                html += f'<tr><td>&nbsp;&nbsp;-lines (deletions)</td><td>{my_deletions:,}</td><td>{their_deletions:,}</td></tr>\n'
                html += f'<tr><td>Review events</td><td>{my_events}</td><td>{their_events}</td></tr>\n'
                html += f'<tr><td>Comments written</td><td>{my_comments}</td><td>{their_comments}</td></tr>\n'
                html += '</tbody>\n</table>\n'

                # List PRs I reviewed
                if my_reviews and my_reviews.prs:
                    html += f'<p style="margin-top: 15px;"><strong>📝 PRs I reviewed from {author} ({len(my_reviews.prs)}):</strong></p>\n'
                    html += '<ul style="margin-left: 20px;">\n'
                    for pr in my_reviews.prs:
                        html += f'<li>#{pr["number"]}: {pr["title"]}<br>\n'
                        html += f'<a href="{pr["url"]}" class="pr-link" target="_blank">{pr["url"]}</a> '
                        html += f'(+{pr["additions"]:,} / -{pr["deletions"]:,} lines)</li>\n'
                    html += '</ul>\n'

                # List PRs they reviewed
                if their_reviews and their_reviews.prs:
                    html += f'<p style="margin-top: 15px;"><strong>📝 PRs {author} reviewed for me ({len(their_reviews.prs)}):</strong></p>\n'
                    html += '<ul style="margin-left: 20px;">\n'
                    for pr in their_reviews.prs:
                        html += f'<li>#{pr["number"]}: {pr["title"]}<br>\n'
                        html += f'<a href="{pr["url"]}" class="pr-link" target="_blank">{pr["url"]}</a> '
                        html += f'(+{pr["additions"]:,} / -{pr["deletions"]:,} lines)</li>\n'
                    html += '</ul>\n'

                html += '</div>\n</details>\n'

            # Add section for my PRs that this user can review
            if my_open_prs:
                html += '<div style="margin-top: 20px; padding-top: 15px; border-top: 2px solid #ddd;">\n'
                html += f'<h3 style="color: #667eea; margin-bottom: 10px;">My PRs for {author} to Review</h3>\n'
                html += '<p style="font-size: 0.9em; color: #666; margin-bottom: 10px;">Click either button to copy a personalized Slack-ready message requesting code review or testing</p>\n'

                for pr in my_open_prs:
                    repo_name = pr['repo']
                    repo_short = repo_name.split('/')[-1]
                    pr_title = pr['title']
                    pr_url = pr['url']
                    additions = pr['additions']
                    deletions = pr['deletions']
                    total_lines = additions + deletions

                    # Generate personalized messages for this user in Slack format
                    # Slack uses *text* for bold and <url|text> for links
                    # Remove backticks from title as they break Slack link formatting
                    slack_title = pr_title.replace('`', '')

                    code_review_message = f"Hey {author}, I need your help for *a code review* on this PR <{pr_url}|{slack_title}> (+{additions:,}/-{deletions:,} lines, ~{total_lines:,} total)\n\n"
                    code_review_message += "As always, I am happy to trade reviews :smile:"

                    testing_message = f"Hey {author}, I need your help for *testing* on this PR <{pr_url}|{slack_title}> (+{additions:,}/-{deletions:,} lines, ~{total_lines:,} total)\n\n"
                    testing_message += "As always, I am happy to trade reviews :smile:"

                    # Escape only quotes and backslashes for HTML data attribute (preserve Slack formatting)
                    escaped_code_message = code_review_message.replace('\\', '\\\\').replace('"', '&quot;')
                    escaped_test_message = testing_message.replace('\\', '\\\\').replace('"', '&quot;')

                    html += f'<div style="margin: 10px 0; padding: 15px; background: #f0f0f0; border-radius: 4px; border-left: 4px solid #667eea;">\n'
                    html += f'<div style="font-weight: 600; margin-bottom: 10px;">[{repo_short}] #{pr["number"]}: {pr_title}</div>\n'
                    html += f'<div style="font-size: 0.9em; color: #666; margin-bottom: 5px;">{pr_url}</div>\n'
                    html += f'<div style="font-size: 0.9em; color: #666; margin-bottom: 10px;">(+{additions:,} / -{deletions:,} lines)</div>\n'
                    html += '<div style="display: flex; gap: 10px;">\n'
                    html += f'<button class="pr-copy-button" data-message="{escaped_code_message}" style="flex: 1; background: #667eea; color: white; border: none; padding: 8px 12px; border-radius: 4px; cursor: pointer; font-size: 0.85em; transition: background-color 0.2s ease;">Copy Code Review Message</button>\n'
                    html += f'<button class="pr-copy-button" data-message="{escaped_test_message}" style="flex: 1; background: #764ba2; color: white; border: none; padding: 8px 12px; border-radius: 4px; cursor: pointer; font-size: 0.85em; transition: background-color 0.2s ease;">Copy Testing Message</button>\n'
                    html += '</div>\n'
                    html += '</div>\n'

                html += '</div>\n'

            html += '</div>\n'

        return html

    def _generate_detailed_history_html(
        self,
        all_users: Set[str],
        reviewed_by_me: Dict[str, ReviewStats],
        reviewed_by_others: Dict[str, ReviewStats],
        pr_authors: Set[str] = None
    ) -> str:
        """Generate HTML for detailed review history."""
        html = '<details>\n'
        html += '<summary>Detailed Review History</summary>\n'

        # Filter users based on filter_non_pr_authors flag
        filtered_users = all_users
        if self.filter_non_pr_authors and pr_authors is not None:
            filtered_users = {user for user in all_users if user in pr_authors}

        # Sort users by total interaction
        sorted_users = sorted(
            filtered_users,
            key=lambda u: (
                reviewed_by_me[u].prs_reviewed +
                reviewed_by_others[u].prs_reviewed
            ),
            reverse=True
        )

        for user in sorted_users:
            my_reviews = reviewed_by_me[user]
            their_reviews = reviewed_by_others[user]

            html += f'<div class="detailed-section">\n'
            html += f'<h3>👤 {user}</h3>\n'

            # Summary table
            html += '<table class="metric-table">\n'
            html += '<thead><tr><th>Metric</th><th>I Reviewed</th><th>They Reviewed</th></tr></thead>\n'
            html += '<tbody>\n'
            html += f'<tr><td>PRs reviewed</td><td>{my_reviews.prs_reviewed}</td><td>{their_reviews.prs_reviewed}</td></tr>\n'
            html += f'<tr><td>Lines reviewed (total)</td><td>{my_reviews.lines_reviewed:,}</td><td>{their_reviews.lines_reviewed:,}</td></tr>\n'
            html += f'<tr><td>&nbsp;&nbsp;+lines (additions)</td><td>{my_reviews.additions_reviewed:,}</td><td>{their_reviews.additions_reviewed:,}</td></tr>\n'
            html += f'<tr><td>&nbsp;&nbsp;-lines (deletions)</td><td>{my_reviews.deletions_reviewed:,}</td><td>{their_reviews.deletions_reviewed:,}</td></tr>\n'
            html += f'<tr><td>Review events</td><td>{my_reviews.review_events}</td><td>{their_reviews.review_events}</td></tr>\n'
            html += f'<tr><td>Comments written</td><td>{my_reviews.comments}</td><td>{their_reviews.comments}</td></tr>\n'
            html += '</tbody>\n</table>\n'

            # Calculate offsets
            line_offset = my_reviews.lines_reviewed - their_reviews.lines_reviewed
            additions_offset = my_reviews.additions_reviewed - their_reviews.additions_reviewed
            deletions_offset = my_reviews.deletions_reviewed - their_reviews.deletions_reviewed
            offset_sign = "+" if line_offset >= 0 else ""
            additions_sign = "+" if additions_offset >= 0 else ""
            deletions_sign = "+" if deletions_offset >= 0 else ""

            html += '<p><strong>📊 Line Review Offset:</strong></p>\n'
            html += '<ul>\n'
            html += f'<li>Total: {offset_sign}{line_offset:,} lines (positive = you reviewed more of their code)</li>\n'
            html += f'<li>+lines: {additions_sign}{additions_offset:,}</li>\n'
            html += f'<li>-lines: {deletions_sign}{deletions_offset:,}</li>\n'
            html += '</ul>\n'

            # List PRs I reviewed
            if my_reviews.prs:
                html += f'<p><strong>📝 PRs I reviewed ({len(my_reviews.prs)}):</strong></p>\n'
                html += '<ul>\n'
                for pr in my_reviews.prs:
                    html += f'<li>#{pr["number"]}: {pr["title"]}<br>\n'
                    html += f'<a href="{pr["url"]}" class="pr-link" target="_blank">{pr["url"]}</a> '
                    html += f'(+{pr["additions"]:,} / -{pr["deletions"]:,} lines)</li>\n'
                html += '</ul>\n'

            # List PRs they reviewed
            if their_reviews.prs:
                html += f'<p><strong>📝 PRs they reviewed ({len(their_reviews.prs)}):</strong></p>\n'
                html += '<ul>\n'
                for pr in their_reviews.prs:
                    html += f'<li>#{pr["number"]}: {pr["title"]}<br>\n'
                    html += f'<a href="{pr["url"]}" class="pr-link" target="_blank">{pr["url"]}</a> '
                    html += f'(+{pr["additions"]:,} / -{pr["deletions"]:,} lines)</li>\n'
                html += '</ul>\n'

            html += '</div>\n'

        html += '</details>\n'
        return html

    def _generate_overall_stats_html(
        self,
        reviewed_by_me: Dict[str, ReviewStats],
        reviewed_by_others: Dict[str, ReviewStats],
        pr_authors: Set[str] = None
    ) -> str:
        """Generate HTML for overall statistics."""
        html = '<h2>Overall Statistics</h2>\n'

        # Filter users based on filter_non_pr_authors flag
        all_users = set(reviewed_by_me.keys()) | set(reviewed_by_others.keys())
        if self.filter_non_pr_authors and pr_authors is not None:
            filtered_users = {user for user in all_users if user in pr_authors}
        else:
            filtered_users = all_users

        # Calculate stats only for filtered users
        total_reviewed_by_me = sum(reviewed_by_me[u].prs_reviewed for u in filtered_users)
        total_reviewed_by_others = sum(reviewed_by_others[u].prs_reviewed for u in filtered_users)
        total_lines_by_me = sum(reviewed_by_me[u].lines_reviewed for u in filtered_users)
        total_lines_by_others = sum(reviewed_by_others[u].lines_reviewed for u in filtered_users)
        total_additions_by_me = sum(reviewed_by_me[u].additions_reviewed for u in filtered_users)
        total_additions_by_others = sum(reviewed_by_others[u].additions_reviewed for u in filtered_users)
        total_deletions_by_me = sum(reviewed_by_me[u].deletions_reviewed for u in filtered_users)
        total_deletions_by_others = sum(reviewed_by_others[u].deletions_reviewed for u in filtered_users)

        html += '<div class="stats-grid">\n'
        html += f'<div class="stat-card"><div class="stat-label">Total PRs I Reviewed</div><div class="stat-value">{total_reviewed_by_me}</div></div>\n'
        html += f'<div class="stat-card"><div class="stat-label">Total PRs Others Reviewed</div><div class="stat-value">{total_reviewed_by_others}</div></div>\n'
        html += f'<div class="stat-card"><div class="stat-label">Total Lines I Reviewed</div><div class="stat-value">{total_lines_by_me:,}</div></div>\n'
        html += f'<div class="stat-card"><div class="stat-label">Total Lines Others Reviewed</div><div class="stat-value">{total_lines_by_others:,}</div></div>\n'
        html += '</div>\n'

        html += '<table class="metric-table">\n'
        html += '<tbody>\n'
        html += f'<tr><td>Lines I reviewed (+/-)</td><td>+{total_additions_by_me:,} / -{total_deletions_by_me:,}</td></tr>\n'
        html += f'<tr><td>Lines others reviewed (+/-)</td><td>+{total_additions_by_others:,} / -{total_deletions_by_others:,}</td></tr>\n'
        html += f'<tr><td>Number of collaborators</td><td>{len(filtered_users)}</td></tr>\n'
        html += '</tbody>\n</table>\n'

        return html

    def save_html(
        self,
        reviewed_by_me: Dict[str, ReviewStats],
        reviewed_by_others: Dict[str, ReviewStats],
        open_prs_by_author: Dict[str, list],
        pr_authors: Set[str] = None,
        my_open_prs: list = None,
        output_dir: str = None
    ) -> str:
        """Generate and save HTML report to file.

        Args:
            reviewed_by_me: Statistics for PRs I reviewed
            reviewed_by_others: Statistics for PRs others reviewed
            open_prs_by_author: Open PRs grouped by author
            pr_authors: Set of all users who have authored PRs in the repositories
            my_open_prs: List of my open PRs that need review
            output_dir: Directory to save the HTML file (defaults to current directory)

        Returns:
            Absolute path to the saved HTML file
        """
        html_content = self.generate_html(reviewed_by_me, reviewed_by_others, open_prs_by_author, pr_authors, my_open_prs)

        # Determine output directory
        if output_dir is None:
            output_dir = os.getcwd()

        # Create filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'github_review_analysis_{self.username}_{timestamp}.html'
        filepath = os.path.join(output_dir, filename)

        # Write HTML to file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)

        return os.path.abspath(filepath)