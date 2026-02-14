"""Output formatting and display for review analysis results."""

import os
from typing import Dict, Set
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
            filter_non_pr_authors: Whether to filter out users who have not opened any PRs
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
