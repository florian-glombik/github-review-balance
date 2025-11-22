#!/usr/bin/env python3
"""Test script to verify PR file filtering works correctly."""

import unittest
from unittest.mock import Mock, patch, MagicMock
import importlib.util

# Import the analyzer (note: filename has hyphens, not underscores)
spec = importlib.util.spec_from_file_location("github_review_analyzer", "github-review-analyzer.py")
github_review_analyzer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(github_review_analyzer)
GitHubReviewAnalyzer = github_review_analyzer.GitHubReviewAnalyzer


class TestPRFiltering(unittest.TestCase):
    """Test cases for PR file filtering functionality."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock data for PR #11497 files
        self.mock_pr_files = [
            {
                'filename': 'package-lock.json',
                'additions': 5000,
                'deletions': 3000,
            },
            {
                'filename': 'src/main/java/Example.java',
                'additions': 50,
                'deletions': 20,
            },
            {
                'filename': 'src/test/java/ExampleTest.java',
                'additions': 30,
                'deletions': 10,
            },
        ]

        # Mock PR details
        self.mock_pr_details = {
            'additions': 5080,  # Total including package-lock.json
            'deletions': 3030,  # Total including package-lock.json
        }

    @patch('requests.Session')
    def test_pr_11497_filtering(self, mock_session_class):
        """Test that PR #11497 correctly filters out package-lock.json."""
        # Create a mock session
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        # Create analyzer with filtering enabled
        analyzer = GitHubReviewAnalyzer(
            username="test_user",
            token="test_token",
            exclude_generated_files=True,
            use_cache=False
        )

        # Mock the get_paginated method to return our mock files
        analyzer.get_paginated = Mock(return_value=self.mock_pr_files)

        repo = "ls1intum/Artemis"
        pr_number = 11497

        # Get filtered line counts
        filtered_counts = analyzer._get_filtered_line_counts(repo, pr_number, should_cache=False)

        # Verify that get_paginated was called with correct URL
        expected_files_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/files"
        analyzer.get_paginated.assert_called_once_with(expected_files_url, use_cache=False)

        # Check filtered counts (should exclude package-lock.json)
        self.assertIsNotNone(filtered_counts)
        self.assertEqual(filtered_counts['additions'], 80)  # 50 + 30
        self.assertEqual(filtered_counts['deletions'], 30)  # 20 + 10

        # Calculate what was excluded
        excluded_additions = self.mock_pr_details['additions'] - filtered_counts['additions']
        excluded_deletions = self.mock_pr_details['deletions'] - filtered_counts['deletions']

        self.assertEqual(excluded_additions, 5000)
        self.assertEqual(excluded_deletions, 3000)

    @patch('requests.Session')
    def test_filtering_disabled(self, mock_session_class):
        """Test that filtering returns None when disabled."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        # Create analyzer with filtering disabled
        analyzer = GitHubReviewAnalyzer(
            username="test_user",
            token="test_token",
            exclude_generated_files=False,
            use_cache=False
        )

        repo = "ls1intum/Artemis"
        pr_number = 11497

        # Get filtered line counts
        filtered_counts = analyzer._get_filtered_line_counts(repo, pr_number, should_cache=False)

        # Should return None when filtering is disabled
        self.assertIsNone(filtered_counts)

    @patch('requests.Session')
    def test_multiple_excluded_files(self, mock_session_class):
        """Test filtering with multiple excluded file types."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        # Mock files with multiple excluded types
        mock_files = [
            {'filename': 'package-lock.json', 'additions': 5000, 'deletions': 3000},
            {'filename': 'yarn.lock', 'additions': 2000, 'deletions': 1000},
            {'filename': 'build/output.js', 'additions': 1000, 'deletions': 500},
            {'filename': 'src/main.js', 'additions': 100, 'deletions': 50},
        ]

        analyzer = GitHubReviewAnalyzer(
            username="test_user",
            token="test_token",
            exclude_generated_files=True,
            use_cache=False
        )

        analyzer.get_paginated = Mock(return_value=mock_files)

        filtered_counts = analyzer._get_filtered_line_counts("test/repo", 123, should_cache=False)

        # Should only count src/main.js
        self.assertEqual(filtered_counts['additions'], 100)
        self.assertEqual(filtered_counts['deletions'], 50)

    @patch('requests.Session')
    def test_no_excluded_files(self, mock_session_class):
        """Test filtering when PR has no excluded files."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        # Mock files with no excluded types
        mock_files = [
            {'filename': 'src/main.js', 'additions': 100, 'deletions': 50},
            {'filename': 'src/test.js', 'additions': 50, 'deletions': 25},
        ]

        analyzer = GitHubReviewAnalyzer(
            username="test_user",
            token="test_token",
            exclude_generated_files=True,
            use_cache=False
        )

        analyzer.get_paginated = Mock(return_value=mock_files)

        filtered_counts = analyzer._get_filtered_line_counts("test/repo", 123, should_cache=False)

        # Should count all files
        self.assertEqual(filtered_counts['additions'], 150)
        self.assertEqual(filtered_counts['deletions'], 75)


def run_tests():
    """Run all tests and print results."""
    print("Running PR filtering tests...")
    print("="*80)

    # Create a test suite
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPRFiltering)

    # Run tests with verbose output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "="*80)
    if result.wasSuccessful():
        print("\n✅ All tests passed!")
    else:
        print(f"\n❌ {len(result.failures)} test(s) failed, {len(result.errors)} error(s)")

    return result


if __name__ == "__main__":
    run_tests()