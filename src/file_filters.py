"""File filtering utilities for excluding generated files from analysis."""

import fnmatch
import logging
from typing import List, Dict, Optional
from datetime import datetime


# Default patterns for commonly generated files
DEFAULT_EXCLUDED_FILE_PATTERNS = [
    'package-lock.json',
    'yarn.lock',
    'pnpm-lock.yaml',
    'Gemfile.lock',
    'Cargo.lock',
    'composer.lock',
    'poetry.lock',
    'Pipfile.lock',
    '*.min.js',
    '*.min.css',
    '*.bundle.js',
    '*.bundle.css',
    'dist/*',
    'build/*',
    'out/*',
    'target/*',
    '.next/*',
    'coverage/*',
    '*.generated.*',
    '*.gen.*',
    '*-lock.json',
    '*.lock',
]


class FileFilter:
    """Handles filtering of generated files from PR analysis."""

    def __init__(self, excluded_file_patterns: List[str] = None):
        """Initialize the file filter.

        Args:
            excluded_file_patterns: List of file patterns to exclude (uses default if None)
        """
        self.excluded_file_patterns = excluded_file_patterns or DEFAULT_EXCLUDED_FILE_PATTERNS

    def match_pattern(self, filename: str, pattern: str) -> bool:
        """Check if a filename matches a pattern (supports * wildcards).

        Args:
            filename: The filename to check
            pattern: The pattern to match against

        Returns:
            True if the filename matches the pattern, False otherwise
        """
        return fnmatch.fnmatch(filename, pattern)

    def is_excluded(self, filename: str) -> bool:
        """Check if a file should be excluded based on patterns.

        Args:
            filename: The filename to check

        Returns:
            True if the file should be excluded, False otherwise
        """
        return any(
            self.match_pattern(filename, pattern)
            for pattern in self.excluded_file_patterns
        )

    def calculate_filtered_line_counts(self, files: List[Dict]) -> Dict[str, int]:
        """Calculate line counts excluding generated files.

        Args:
            files: List of file objects from GitHub API

        Returns:
            Dictionary with 'additions' and 'deletions' counts after filtering
        """
        total_additions = 0
        total_deletions = 0
        filtered_additions = 0
        filtered_deletions = 0
        excluded_files_count = 0

        for file in files:
            filename = file['filename']
            additions = file.get('additions', 0)
            deletions = file.get('deletions', 0)

            total_additions += additions
            total_deletions += deletions

            # Check if file matches any excluded pattern
            if self.is_excluded(filename):
                excluded_files_count += 1
                logging.debug(f"Excluding file: {filename} (+{additions}/-{deletions})")
            else:
                filtered_additions += additions
                filtered_deletions += deletions

        if excluded_files_count > 0:
            excluded_lines = (total_additions - filtered_additions) + (total_deletions - filtered_deletions)
            logging.info(f"Excluded {excluded_files_count} generated file(s) "
                       f"({excluded_lines:,} lines: +{total_additions - filtered_additions:,}/-{total_deletions - filtered_deletions:,})")

        return {
            'additions': filtered_additions,
            'deletions': filtered_deletions
        }