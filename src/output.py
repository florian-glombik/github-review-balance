"""Output formatting and display for review analysis results."""

from typing import Dict, Set
from collections import defaultdict

from .models import ReviewStats


# ANSI color codes
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
RESET = '\033[0m'


class OutputFormatter:
    """Formats and prints review analysis results."""

    def __init__(self, username: str, sort_by: str = 'total_prs', show_extended_report: bool = False, show_overall_statistics: bool = True, max_review_count_threshold: int = None):
        """Initialize the output formatter.

        Args:
            username: The username being analyzed
            sort_by: Column to sort results by
            show_extended_report: Whether to show the extended detailed history report
            show_overall_statistics: Whether to show the overall statistics section
            max_review_count_threshold: Minimum review count to filter PRs (None = no filtering)
        """
        self.username = username
        self.sort_by = sort_by
        self.show_extended_report = show_extended_report
        self.show_overall_statistics = show_overall_statistics
        self.max_review_count_threshold = max_review_count_threshold

    def print_summary(
        self,
        reviewed_by_me: Dict[str, ReviewStats],
        reviewed_by_others: Dict[str, ReviewStats],
        open_prs_by_author: Dict[str, list]
    ):
        """Print a comprehensive summary of review statistics.

        Args:
            reviewed_by_me: Statistics for PRs I reviewed
            reviewed_by_others: Statistics for PRs others reviewed
            open_prs_by_author: Open PRs grouped by author
        """
        print("\n" + "="*80)
        print(f"REVIEW SUMMARY FOR {self.username}")
        print("="*80)

        all_users = set(reviewed_by_me.keys()) | set(reviewed_by_others.keys())

        if not all_users:
            print("\nNo review activity found.")
            return

        # Print review balance and next actions
        self._print_review_balance(all_users, reviewed_by_me, reviewed_by_others)

        # Print open PRs needing review
        self._print_open_prs(open_prs_by_author, reviewed_by_me, reviewed_by_others)

        # Print detailed history (only if extended report is enabled)
        if self.show_extended_report:
            self._print_detailed_history(all_users, reviewed_by_me, reviewed_by_others)

        # Print overall statistics (only if enabled)
        if self.show_overall_statistics:
            self._print_overall_stats(reviewed_by_me, reviewed_by_others)

    def _print_review_balance(
        self,
        all_users: Set[str],
        reviewed_by_me: Dict[str, ReviewStats],
        reviewed_by_others: Dict[str, ReviewStats]
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

                # Determine PR color based on balance (same logic as author color)
                pr_color = author_color

                # Build review info string
                review_info = f"[{review_count} review(s)]"
                if requested_my_review:
                    review_info += " [REQUESTED]"

                print(f"  {pr_color}• [{repo_short}] #{pr['number']}: {pr['title']}{RESET}")
                print(f"    {pr['url']} (+{pr['additions']:,} / -{pr['deletions']:,} lines) {review_info}")
            print()

    def _print_detailed_history(
        self,
        all_users: Set[str],
        reviewed_by_me: Dict[str, ReviewStats],
        reviewed_by_others: Dict[str, ReviewStats]
    ):
        """Print detailed review history for each user."""
        print("\n" + "="*80)
        print("DETAILED REVIEW HISTORY")
        print("="*80)

        # Sort users by total interaction
        sorted_users = sorted(
            all_users,
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
        reviewed_by_others: Dict[str, ReviewStats]
    ):
        """Print overall statistics."""
        print(f"\n{'='*80}")
        print("OVERALL STATISTICS")
        print(f"{'='*80}")

        total_reviewed_by_me = sum(s.prs_reviewed for s in reviewed_by_me.values())
        total_reviewed_by_others = sum(s.prs_reviewed for s in reviewed_by_others.values())
        total_lines_by_me = sum(s.lines_reviewed for s in reviewed_by_me.values())
        total_lines_by_others = sum(s.lines_reviewed for s in reviewed_by_others.values())
        total_additions_by_me = sum(s.additions_reviewed for s in reviewed_by_me.values())
        total_additions_by_others = sum(s.additions_reviewed for s in reviewed_by_others.values())
        total_deletions_by_me = sum(s.deletions_reviewed for s in reviewed_by_me.values())
        total_deletions_by_others = sum(s.deletions_reviewed for s in reviewed_by_others.values())

        all_users = set(reviewed_by_me.keys()) | set(reviewed_by_others.keys())

        print(f"\nTotal PRs I reviewed: {total_reviewed_by_me}")
        print(f"Total PRs others reviewed of mine: {total_reviewed_by_others}")
        print(f"\nTotal lines I reviewed: {total_lines_by_me:,}")
        print(f"  +lines: {total_additions_by_me:,}")
        print(f"  -lines: {total_deletions_by_me:,}")
        print(f"\nTotal lines others reviewed: {total_lines_by_others:,}")
        print(f"  +lines: {total_additions_by_others:,}")
        print(f"  -lines: {total_deletions_by_others:,}")
        print(f"\nNumber of collaborators: {len(all_users)}")