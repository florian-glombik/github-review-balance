#!/usr/bin/env python3
"""
GitHub PR Review Analyzer
Analyzes PR review activity between users in specified repositories.
"""

import os
import sys
import logging
from dotenv import load_dotenv

from src.github_review_analyzer import GitHubReviewAnalyzer
from src.output import OutputFormatter

# Configure logging (can be overridden by LOG_LEVEL environment variable)
log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%m/%d/%Y %I:%M:%S %p'
)


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

    # Check if generated files should be excluded
    exclude_generated_files = os.environ.get('EXCLUDE_GENERATED_FILES', 'false').lower() in ('true', '1', 'yes')
    if exclude_generated_files:
        logging.info("Excluding generated files from line count calculations")

    # Get custom file patterns to exclude (if specified)
    excluded_file_patterns = None
    excluded_patterns_env = os.environ.get('EXCLUDED_FILE_PATTERNS')
    if excluded_patterns_env:
        # Parse comma-separated list from environment
        excluded_file_patterns = [p.strip() for p in excluded_patterns_env.split(',') if p.strip()]
        logging.info(f"Using custom excluded file patterns: {', '.join(excluded_file_patterns)}")

    # Check if extended report should be shown
    show_extended_report = os.environ.get('SHOW_EXTENDED_REPORT', 'false').lower() in ('true', '1', 'yes')
    if show_extended_report:
        logging.info("Extended report (detailed history) will be shown")

    # Check if overall statistics should be shown
    show_overall_statistics = os.environ.get('SHOW_OVERALL_STATISTICS', 'true').lower() not in ('false', '0', 'no')
    if not show_overall_statistics:
        logging.info("Overall statistics section will be hidden")

    # Get minimum review count threshold from environment
    max_review_count_threshold = None
    threshold_env = os.environ.get('MAX_REVIEW_COUNT_THRESHOLD')
    if threshold_env:
        try:
            max_review_count_threshold = int(threshold_env)
            logging.info(f"Will filter out PRs with {max_review_count_threshold}+ reviews (except review requests)")
        except ValueError:
            logging.warning(f"Invalid MAX_REVIEW_COUNT_THRESHOLD value '{threshold_env}', ignoring")

    # Check if non-PR authors should be filtered out
    filter_non_pr_authors = os.environ.get('FILTER_NON_PR_AUTHORS', 'false').lower() in ('true', '1', 'yes')
    if filter_non_pr_authors:
        logging.info("Filtering out users who have not opened any PRs")

    # Create analyzer
    analyzer = GitHubReviewAnalyzer(
        username,
        token,
        use_cache=use_cache,
        excluded_users=excluded_users,
        required_pr_label=required_pr_label,
        sort_by=sort_by,
        exclude_generated_files=exclude_generated_files,
        excluded_file_patterns=excluded_file_patterns,
        max_review_count_threshold=max_review_count_threshold
    )

    # Analyze each repository
    logging.info(f"Starting analysis of {len(repos)} repository/repositories")
    for repo in repos:
        try:
            analyzer.analyze_repository(repo, months)
        except Exception as e:
            logging.error(f"Error analyzing {repo}: {e}", exc_info=True)
            continue

    # Save cache
    analyzer.save_cache()

    # Get open PRs and print summary
    logging.info("Analysis complete, generating summary...")
    open_prs_by_author = analyzer.get_open_prs_needing_review()

    output_formatter = OutputFormatter(username, sort_by, show_extended_report, show_overall_statistics, max_review_count_threshold, filter_non_pr_authors)
    output_formatter.print_summary(
        analyzer.reviewed_by_me,
        analyzer.reviewed_by_others,
        open_prs_by_author,
        analyzer.pr_authors
    )


if __name__ == "__main__":
    main()