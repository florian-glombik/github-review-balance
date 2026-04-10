"""Output formatting and display for review analysis results."""

import os
from typing import Dict, Mapping, Optional, Set
from collections import defaultdict
from datetime import datetime

from ..models import ReviewStats


# ANSI color codes
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
CYAN = '\033[96m'
BOLD = '\033[1m'
RESET = '\033[0m'


class OutputFormatter:
    """Formats and prints review analysis results."""

    def __init__(self, username: str, sort_by: str = 'total_prs', show_extended_report: bool = False, show_overall_statistics: bool = True, max_review_count_threshold: int = None, filter_non_pr_authors: bool = False, config: dict = None, user_config=None):
        """Initialize the output formatter.

        Args:
            username: The username being analyzed
            sort_by: Column to sort results by
            show_extended_report: Whether to show the extended detailed history report
            show_overall_statistics: Whether to show the overall statistics section
            max_review_count_threshold: Minimum review count to filter PRs (None = no filtering)
            filter_non_pr_authors: Only show users who authored at least one PR in the analyzed window
            config: Configuration dictionary with analysis parameters (repositories, months, excluded_users, etc.)
            user_config: UserConfig instance for nicknames and language preferences
        """
        self.username = username
        self.sort_by = sort_by
        self.show_extended_report = show_extended_report
        self.show_overall_statistics = show_overall_statistics
        self.max_review_count_threshold = max_review_count_threshold
        self.filter_non_pr_authors = filter_non_pr_authors
        self.config = config or {}
        self.user_config = user_config

        # Section collapse settings (defaults match current behavior)
        self.section_settings_expanded = self.config.get('section_settings_expanded', True)
        self.section_my_open_prs_expanded = self.config.get('section_my_open_prs_expanded', True)
        self.section_review_history_expanded = self.config.get('section_review_history_expanded', False)
        self.section_my_prs_for_author_expanded = self.config.get('section_my_prs_for_author_expanded', False)
        self.section_detailed_history_expanded = self.config.get('section_detailed_history_expanded', False)

        # Language settings for messages
        self.pr_summary_language = self.config.get('pr_summary_language', 'english')
        self.my_open_prs_language = self.config.get('my_open_prs_language', 'english')
        self.my_prs_language = self.config.get('my_prs_language', 'english')

    def _get_display_name(self, github_username: str) -> str:
        """Get the display name for a user (nickname if set, otherwise GitHub username)."""
        if self.user_config:
            return self.user_config.get_nickname(github_username)
        return github_username

    def _get_html_display_name(self, github_username: str) -> str:
        """Get the HTML display name: 'Nickname (github_username)' if nickname is set, otherwise just the username."""
        display_name = self._get_display_name(github_username)
        if display_name != github_username:
            return f'{display_name} ({github_username})'
        return github_username

    def _get_user_language(self, github_username: str) -> str:
        """Get the language preference for a user."""
        if self.user_config:
            return self.user_config.get_language(github_username)
        return 'english'

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

    def _get_effective_pr_authors(
        self,
        pr_authors: Optional[Set[str]] = None,
        open_prs_by_author: Optional[Mapping[str, list]] = None
    ) -> Optional[Set[str]]:
        """Merge known PR authors with authors from current open PRs."""
        if pr_authors is None and not open_prs_by_author:
            return None

        effective_pr_authors = set(pr_authors or set())
        if open_prs_by_author:
            effective_pr_authors.update(open_prs_by_author.keys())
        return effective_pr_authors

    def _filter_users_by_pr_authors(
        self,
        users: Set[str],
        pr_authors: Optional[Set[str]] = None,
        reviewed_by_me: Optional[Dict[str, ReviewStats]] = None,
        reviewed_by_others: Optional[Dict[str, ReviewStats]] = None
    ) -> Set[str]:
        """Apply filter_non_pr_authors using authored PR evidence."""
        if not (self.filter_non_pr_authors and pr_authors is not None):
            return set(users)

        filtered_users = {user for user in users if user in pr_authors}

        # Keep users whose PRs I reviewed, even if pr_authors is stale/incomplete.
        if reviewed_by_me is not None:
            for user in users:
                my_reviews = reviewed_by_me.get(user)
                if my_reviews and my_reviews.prs_reviewed > 0:
                    filtered_users.add(user)

        return filtered_users

    def _build_review_balance_entries(
        self,
        users: Set[str],
        reviewed_by_me: Dict[str, ReviewStats],
        reviewed_by_others: Dict[str, ReviewStats],
        pr_authors: Optional[Set[str]] = None
    ) -> list:
        """Build sorted review-balance rows, excluding users with zero interactions."""
        review_balance = []
        filtered_users = self._filter_users_by_pr_authors(
            users,
            pr_authors,
            reviewed_by_me,
            reviewed_by_others
        )

        for user in filtered_users:
            my_reviews = reviewed_by_me[user]
            their_reviews = reviewed_by_others[user]
            total_prs = my_reviews.prs_reviewed + their_reviews.prs_reviewed

            if total_prs == 0:
                continue

            review_balance.append({
                'user': user,
                'balance': their_reviews.lines_reviewed - my_reviews.lines_reviewed,
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

        return self._sort_review_balance(review_balance)


# Import and attach methods from submodules
from .message_templates import _get_message_templates, _generate_pr_summary_message
from .console import print_summary, _print_review_balance, _print_balance_row, _print_open_prs, _print_detailed_history, _print_overall_stats
from .html_generator import generate_html, save_html, _generate_empty_html
from .html_header import _generate_html_header
from .html_sections import (_generate_settings_html, _generate_my_open_prs_html,
                            _generate_review_balance_html, _generate_balance_row_html,
                            _generate_open_prs_html, _generate_detailed_history_html,
                            _generate_overall_stats_html, _generate_html_footer)

OutputFormatter._get_message_templates = _get_message_templates
OutputFormatter._generate_pr_summary_message = _generate_pr_summary_message
OutputFormatter.print_summary = print_summary
OutputFormatter._print_review_balance = _print_review_balance
OutputFormatter._print_balance_row = _print_balance_row
OutputFormatter._print_open_prs = _print_open_prs
OutputFormatter._print_detailed_history = _print_detailed_history
OutputFormatter._print_overall_stats = _print_overall_stats
OutputFormatter.generate_html = generate_html
OutputFormatter.save_html = save_html
OutputFormatter._generate_empty_html = _generate_empty_html
OutputFormatter._generate_html_header = _generate_html_header
OutputFormatter._generate_settings_html = _generate_settings_html
OutputFormatter._generate_my_open_prs_html = _generate_my_open_prs_html
OutputFormatter._generate_review_balance_html = _generate_review_balance_html
OutputFormatter._generate_balance_row_html = _generate_balance_row_html
OutputFormatter._generate_open_prs_html = _generate_open_prs_html
OutputFormatter._generate_detailed_history_html = _generate_detailed_history_html
OutputFormatter._generate_overall_stats_html = _generate_overall_stats_html
OutputFormatter._generate_html_footer = _generate_html_footer
