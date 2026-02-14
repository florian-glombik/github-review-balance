"""HTML generation and file saving functions for OutputFormatter."""

import os
from typing import Dict, Set
from datetime import datetime

from ..models import ReviewStats


def generate_html(
    self,
    reviewed_by_me: Dict[str, ReviewStats],
    reviewed_by_others: Dict[str, ReviewStats],
    open_prs_by_author: Dict[str, list],
    pr_authors: Set[str] = None,
    my_open_prs: list = None,
    all_my_open_prs: list = None
) -> str:
    """Generate HTML report of review statistics.

    Args:
        reviewed_by_me: Statistics for PRs I reviewed
        reviewed_by_others: Statistics for PRs others reviewed
        open_prs_by_author: Open PRs grouped by author
        pr_authors: Set of all users who have authored PRs in the repositories
        my_open_prs: List of my open PRs that need review (filtered)
        all_my_open_prs: List of all my open PRs (unfiltered, for PR Summary)

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
        html_parts.append(self._generate_my_open_prs_html(my_open_prs, all_my_open_prs))

    # Review balance table
    html_parts.append(self._generate_review_balance_html(all_users, reviewed_by_me, reviewed_by_others, pr_authors, open_prs_by_author, my_open_prs))

    # Open PRs
    html_parts.append(self._generate_open_prs_html(open_prs_by_author, reviewed_by_me, reviewed_by_others, my_open_prs, all_users, pr_authors))

    # Detailed history (if enabled)
    if self.show_extended_report:
        html_parts.append(self._generate_detailed_history_html(all_users, reviewed_by_me, reviewed_by_others, pr_authors))

    # Overall statistics (if enabled)
    if self.show_overall_statistics:
        html_parts.append(self._generate_overall_stats_html(reviewed_by_me, reviewed_by_others, pr_authors))

    html_parts.append(self._generate_html_footer())

    return '\n'.join(html_parts)


def save_html(
    self,
    reviewed_by_me: Dict[str, ReviewStats],
    reviewed_by_others: Dict[str, ReviewStats],
    open_prs_by_author: Dict[str, list],
    pr_authors: Set[str] = None,
    my_open_prs: list = None,
    all_my_open_prs: list = None,
    output_dir: str = None
) -> str:
    """Generate and save HTML report to file.

    Args:
        reviewed_by_me: Statistics for PRs I reviewed
        reviewed_by_others: Statistics for PRs others reviewed
        open_prs_by_author: Open PRs grouped by author
        pr_authors: Set of all users who have authored PRs in the repositories
        my_open_prs: List of my open PRs that need review (filtered)
        all_my_open_prs: List of all my open PRs (unfiltered, for PR Summary)
        output_dir: Directory to save the HTML file (defaults to current directory)

    Returns:
        Absolute path to the saved HTML file
    """
    html_content = self.generate_html(reviewed_by_me, reviewed_by_others, open_prs_by_author, pr_authors, my_open_prs, all_my_open_prs)

    # Determine output directory - default to 'reports' folder
    if output_dir is None:
        output_dir = os.path.join(os.getcwd(), 'reports')

    # Create reports directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # Create filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'github_review_analysis_{self.username}_{timestamp}.html'
    filepath = os.path.join(output_dir, filename)

    # Write HTML to file
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html_content)

    return os.path.abspath(filepath)


def _generate_empty_html(self) -> str:
    """Generate HTML for when there's no data."""
    html = self._generate_html_header({})
    html += '<div class="no-data">No review activity found.</div>'
    html += self._generate_html_footer()
    return html
