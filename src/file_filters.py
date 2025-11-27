"""File filtering utilities for excluding generated files from analysis."""

import fnmatch
import logging
from typing import List, Dict, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed


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

    def _process_file_chunk(self, files_chunk: List[Dict]) -> Dict[str, int]:
        """Process a chunk of files and calculate line counts.

        Args:
            files_chunk: Subset of file objects to process

        Returns:
            Dictionary with aggregated additions, deletions, total_additions, total_deletions, and excluded_count
        """
        chunk_total_additions = 0
        chunk_total_deletions = 0
        chunk_filtered_additions = 0
        chunk_filtered_deletions = 0
        chunk_excluded_count = 0

        for file in files_chunk:
            filename = file['filename']
            additions = file.get('additions', 0)
            deletions = file.get('deletions', 0)

            chunk_total_additions += additions
            chunk_total_deletions += deletions

            if self.is_excluded(filename):
                chunk_excluded_count += 1
                logging.debug(f"Excluding file: {filename} (+{additions}/-{deletions})")
            else:
                chunk_filtered_additions += additions
                chunk_filtered_deletions += deletions

        return {
            'total_additions': chunk_total_additions,
            'total_deletions': chunk_total_deletions,
            'filtered_additions': chunk_filtered_additions,
            'filtered_deletions': chunk_filtered_deletions,
            'excluded_count': chunk_excluded_count
        }

    def calculate_filtered_line_counts(self, files: List[Dict]) -> Dict[str, int]:
        """Calculate line counts excluding generated files.

        Uses parallel processing for large file sets (50+ files).

        Args:
            files: List of file objects from GitHub API

        Returns:
            Dictionary with 'additions' and 'deletions' counts after filtering
        """
        # Use parallel processing for large PRs
        if len(files) >= 50:
            return self._calculate_filtered_line_counts_parallel(files)

        # Sequential processing for smaller PRs
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

    def _calculate_filtered_line_counts_parallel(self, files: List[Dict]) -> Dict[str, int]:
        """Calculate line counts using parallel processing for large file sets.

        Args:
            files: List of file objects from GitHub API

        Returns:
            Dictionary with 'additions' and 'deletions' counts after filtering
        """
        logging.debug(f"Processing {len(files)} files in parallel")

        # Split files into chunks
        chunk_size = max(10, len(files) // 8)  # At least 10 files per chunk
        file_chunks = [files[i:i + chunk_size] for i in range(0, len(files), chunk_size)]

        total_additions = 0
        total_deletions = 0
        filtered_additions = 0
        filtered_deletions = 0
        excluded_files_count = 0

        # Process chunks in parallel
        max_workers = min(8, len(file_chunks))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_chunk = {
                executor.submit(self._process_file_chunk, chunk): chunk
                for chunk in file_chunks
            }

            for future in as_completed(future_to_chunk):
                try:
                    result = future.result()
                    total_additions += result['total_additions']
                    total_deletions += result['total_deletions']
                    filtered_additions += result['filtered_additions']
                    filtered_deletions += result['filtered_deletions']
                    excluded_files_count += result['excluded_count']
                except Exception as e:
                    logging.warning(f"Error processing file chunk: {e}")

        if excluded_files_count > 0:
            excluded_lines = (total_additions - filtered_additions) + (total_deletions - filtered_deletions)
            logging.info(f"Excluded {excluded_files_count} generated file(s) "
                       f"({excluded_lines:,} lines: +{total_additions - filtered_additions:,}/-{total_deletions - filtered_deletions:,})")

        return {
            'additions': filtered_additions,
            'deletions': filtered_deletions
        }